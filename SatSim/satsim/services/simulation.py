"""Simulation orchestration.

``simulate`` is a pure function from scenario definition to numerical
results (no database writes, easy to test); ``run_scenario`` wraps it
with persistence and plot generation for the web/API layers.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

from ..core import access as access_mod
from ..core import analysis
from ..core.frames import ecef_to_geodetic, eci_to_ecef_km, time_grid
from ..core.propagator import propagate_elements
from ..models import PassRecord, Scenario, SimulationRun
from .scenarios import ValidationError, get_scenario

logger = logging.getLogger(__name__)


@dataclass
class StationResult:
    """Everything computed for one ground station."""

    station: object  # StationGeometry
    windows: list  # AccessWindow, all satellites
    report: object  # CoverageReport
    elevations_by_sat: dict  # name -> 1-D elevation array
    visible_counts: np.ndarray


@dataclass
class SimulationOutput:
    scenario_name: str
    epoch: object  # datetime
    duration_s: float
    times_s: np.ndarray
    ground_tracks: dict = field(default_factory=dict)  # name -> (lat, lon)
    station_results: list = field(default_factory=list)
    network_report: object = None  # CoverageReport over all stations
    elapsed_s: float = 0.0

    @property
    def all_windows(self) -> list:
        windows = []
        for sr in self.station_results:
            windows.extend(sr.windows)
        windows.sort(key=lambda w: w.start_s)
        return windows

    def metrics_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "epoch": self.epoch.isoformat(),
            "duration_s": self.duration_s,
            "num_satellites": len(self.ground_tracks),
            "num_stations": len(self.station_results),
            "elapsed_s": round(self.elapsed_s, 3),
            "network": (
                self.network_report.to_dict() if self.network_report else None
            ),
            "stations": {
                sr.station.name: sr.report.to_dict()
                for sr in self.station_results
            },
        }

    def passes_dataframe(self) -> pd.DataFrame:
        """Chronological pass schedule as a pandas DataFrame."""
        rows = []
        for w in self.all_windows:
            rows.append({
                "satellite": w.satellite,
                "station": w.station,
                "aos_utc": self.epoch + timedelta(seconds=w.start_s),
                "los_utc": self.epoch + timedelta(seconds=w.end_s),
                "duration_s": round(w.duration_s, 1),
                "max_elevation_deg": round(w.max_elevation_deg, 2),
            })
        return pd.DataFrame(
            rows,
            columns=["satellite", "station", "aos_utc", "los_utc",
                     "duration_s", "max_elevation_deg"],
        )


def simulate(scenario: Scenario) -> SimulationOutput:
    """Propagate every satellite and analyse coverage for every station.

    Raises :class:`ValidationError` if the scenario has no satellites or
    no ground stations -- there is nothing to analyse without both.
    """
    satellites = list(scenario.satellites)
    stations = [gs.to_geometry() for gs in scenario.ground_stations]
    if not satellites:
        raise ValidationError("Scenario has no satellites to simulate")
    if not stations:
        raise ValidationError("Scenario has no ground stations to analyse")

    started = time.time()
    epoch = scenario.start_time
    times_s = np.arange(
        0.0, scenario.duration_s + scenario.time_step_s / 2.0,
        scenario.time_step_s,
    )
    astropy_times = time_grid(epoch, times_s)

    # Propagate and rotate to ECEF, satellite by satellite.
    ecef_by_sat = {}
    ground_tracks = {}
    for sat in satellites:
        eph = propagate_elements(
            sat.to_elements(), epoch, times_s, include_j2=True, name=sat.name
        )
        ecef = eci_to_ecef_km(eph.positions_km, astropy_times)
        ecef_by_sat[sat.name] = ecef
        lat, lon, _height = ecef_to_geodetic(ecef)
        ground_tracks[sat.name] = (lat, lon)

    # Per-station access analysis.
    station_results = []
    for station in stations:
        elevations = {}
        windows = []
        for sat_name, ecef in ecef_by_sat.items():
            _az, elevation, _rng = station.look_angles(ecef)
            elevations[sat_name] = elevation
            windows.extend(access_mod.find_access_windows(
                times_s, elevation, station.min_elevation_deg,
                satellite=sat_name, station=station.name,
            ))
        counts = analysis.visible_counts(
            elevations.values(), station.min_elevation_deg
        )
        report = analysis.build_report(
            scenario.duration_s, windows, visible_counts=counts
        )
        station_results.append(StationResult(
            station=station,
            windows=sorted(windows, key=lambda w: w.start_s),
            report=report,
            elevations_by_sat=elevations,
            visible_counts=counts,
        ))

    # Network-level report: union of every station's contacts.
    all_windows = [w for sr in station_results for w in sr.windows]
    network_report = analysis.build_report(scenario.duration_s, all_windows)

    return SimulationOutput(
        scenario_name=scenario.name,
        epoch=epoch,
        duration_s=scenario.duration_s,
        times_s=times_s,
        ground_tracks=ground_tracks,
        station_results=station_results,
        network_report=network_report,
        elapsed_s=time.time() - started,
    )


def run_scenario(session, scenario_id: int, plots_dir: str = None) -> SimulationRun:
    """Simulate a scenario, persist the run + passes, and render plots.

    Plot rendering is best-effort: figures are a presentation artifact,
    while the metrics and pass schedule are the analysis product.  If
    matplotlib is missing or broken in the local environment the run is
    still stored and reported, with the failure recorded under the
    ``plots_error`` metric.
    """
    scenario = get_scenario(session, scenario_id)
    output = simulate(scenario)
    metrics = output.metrics_dict()

    run = SimulationRun(
        scenario_id=scenario.id,
        status="completed",
        elapsed_s=output.elapsed_s,
        metrics_json=json.dumps(metrics),
    )
    session.add(run)
    session.flush()  # allocate run.id for pass records and plot names

    for w in output.all_windows:
        session.add(PassRecord(
            run_id=run.id,
            satellite_name=w.satellite,
            station_name=w.station,
            start_time=output.epoch + timedelta(seconds=w.start_s),
            end_time=output.epoch + timedelta(seconds=w.end_s),
            duration_s=w.duration_s,
            max_elevation_deg=w.max_elevation_deg,
        ))

    if plots_dir is not None:
        plots, plots_error = _render_plots(output, plots_dir, run.id)
        run.plots_json = json.dumps(plots)
        if plots_error:
            metrics["plots_error"] = plots_error
            run.metrics_json = json.dumps(metrics)

    session.commit()
    return run


def _render_plots(output: SimulationOutput, plots_dir: str, run_id: int):
    """Render run figures, returning ``(file_names, error_message)``.

    Any failure -- a missing or misbuilt matplotlib, an unwritable plots
    directory, a rendering bug -- is caught and reported rather than
    discarding a completed simulation.
    """
    try:
        # Imported lazily so headless/scripted use never pays the
        # matplotlib import cost, and so an import-time failure (e.g. a
        # broken native extension) is contained here.
        from ..plotting import save_run_plots

        return save_run_plots(output, plots_dir, run_id), None
    except Exception as exc:
        message = "%s: %s" % (type(exc).__name__, exc)
        logger.warning(
            "Plot rendering failed for run %s; metrics and passes were "
            "saved. %s", run_id, message,
        )
        return [], message
