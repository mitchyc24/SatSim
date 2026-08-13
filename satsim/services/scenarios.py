"""Scenario, satellite, and ground-station management."""

from __future__ import annotations

from datetime import datetime

from ..core.constellation import ConstellationError, walker_delta
from ..core.elements import ClassicalElements, ElementError
from ..core.stations import StationError, StationGeometry
from ..models import GroundStation, Satellite, Scenario, SimulationRun

# Guard rails for the sampled simulation grid: enough for multi-day
# LEO scenarios at fine resolution while keeping runs interactive.
MAX_TIME_SAMPLES = 50000
MAX_SATELLITES = 200
MAX_DURATION_S = 86400.0 * 14


class ValidationError(ValueError):
    """User-facing input problem (maps to HTTP 400 / a form error)."""


class NotFoundError(LookupError):
    """Requested entity does not exist (maps to HTTP 404)."""


# ----------------------------------------------------------------------
# Scenarios
# ----------------------------------------------------------------------
def list_scenarios(session):
    return session.query(Scenario).order_by(Scenario.created_at.desc()).all()


def get_scenario(session, scenario_id: int) -> Scenario:
    scenario = session.get(Scenario, int(scenario_id))
    if scenario is None:
        raise NotFoundError("Scenario %s not found" % scenario_id)
    return scenario


def create_scenario(
    session,
    name: str,
    start_time: datetime,
    duration_s: float = 86400.0,
    time_step_s: float = 60.0,
    description: str = "",
) -> Scenario:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Scenario name is required")
    if not isinstance(start_time, datetime):
        raise ValidationError("start_time must be a datetime")
    duration_s = _positive_float(duration_s, "duration_s")
    time_step_s = _positive_float(time_step_s, "time_step_s")
    if duration_s > MAX_DURATION_S:
        raise ValidationError(
            "duration_s exceeds the %d-day limit" % int(MAX_DURATION_S / 86400)
        )
    samples = duration_s / time_step_s
    if samples > MAX_TIME_SAMPLES:
        raise ValidationError(
            "duration/time_step yields %d samples (limit %d); "
            "increase the time step" % (samples, MAX_TIME_SAMPLES)
        )

    scenario = Scenario(
        name=name,
        description=description or "",
        start_time=start_time,
        duration_s=duration_s,
        time_step_s=time_step_s,
    )
    session.add(scenario)
    session.commit()
    return scenario


def delete_scenario(session, scenario_id: int):
    session.delete(get_scenario(session, scenario_id))
    session.commit()


# ----------------------------------------------------------------------
# Satellites
# ----------------------------------------------------------------------
def add_satellite(
    session,
    scenario: Scenario,
    name: str,
    semi_major_axis_km: float,
    eccentricity: float = 0.0,
    inclination_deg: float = 0.0,
    raan_deg: float = 0.0,
    arg_perigee_deg: float = 0.0,
    true_anomaly_deg: float = 0.0,
    constellation: str = "",
) -> Satellite:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Satellite name is required")
    _check_satellite_budget(scenario, adding=1)
    try:
        ClassicalElements(
            semi_major_axis_km=float(semi_major_axis_km),
            eccentricity=float(eccentricity),
            inclination_deg=float(inclination_deg),
            raan_deg=float(raan_deg),
            arg_perigee_deg=float(arg_perigee_deg),
            true_anomaly_deg=float(true_anomaly_deg),
        ).validate()
    except (ElementError, TypeError, ValueError) as exc:
        raise ValidationError(str(exc))

    satellite = Satellite(
        scenario_id=scenario.id,
        name=name,
        constellation=constellation or "",
        semi_major_axis_km=float(semi_major_axis_km),
        eccentricity=float(eccentricity),
        inclination_deg=float(inclination_deg),
        raan_deg=float(raan_deg),
        arg_perigee_deg=float(arg_perigee_deg),
        true_anomaly_deg=float(true_anomaly_deg),
    )
    session.add(satellite)
    session.commit()
    return satellite


def add_walker_constellation(
    session,
    scenario: Scenario,
    total_satellites: int,
    planes: int,
    relative_phasing: int,
    altitude_km: float,
    inclination_deg: float,
    name_prefix: str = "SAT",
    raan_offset_deg: float = 0.0,
    pattern: str = "delta",
):
    """Generate a Walker constellation and attach it to the scenario."""
    name_prefix = (name_prefix or "SAT").strip() or "SAT"
    if pattern not in ("delta", "star"):
        raise ValidationError("pattern must be 'delta' or 'star'")
    try:
        members = walker_delta(
            total_satellites=int(total_satellites),
            planes=int(planes),
            relative_phasing=int(relative_phasing),
            altitude_km=float(altitude_km),
            inclination_deg=float(inclination_deg),
            raan_offset_deg=float(raan_offset_deg),
            name_prefix=name_prefix,
            raan_spread_deg=360.0 if pattern == "delta" else 180.0,
        )
    except (ConstellationError, ElementError, TypeError, ValueError) as exc:
        raise ValidationError(str(exc))
    _check_satellite_budget(scenario, adding=len(members))

    label = "%s Walker %s %d/%d/%d" % (
        name_prefix, pattern, int(total_satellites), int(planes),
        int(relative_phasing),
    )
    rows = []
    for member in members:
        el = member.elements
        rows.append(Satellite(
            scenario_id=scenario.id,
            name=member.name,
            constellation=label,
            semi_major_axis_km=el.semi_major_axis_km,
            eccentricity=el.eccentricity,
            inclination_deg=el.inclination_deg,
            raan_deg=el.raan_deg,
            arg_perigee_deg=el.arg_perigee_deg,
            true_anomaly_deg=el.true_anomaly_deg,
        ))
    session.add_all(rows)
    session.commit()
    return rows


def delete_satellite(session, scenario: Scenario, satellite_id: int):
    satellite = (
        session.query(Satellite)
        .filter_by(id=int(satellite_id), scenario_id=scenario.id)
        .first()
    )
    if satellite is None:
        raise NotFoundError("Satellite %s not found in scenario" % satellite_id)
    session.delete(satellite)
    session.commit()


# ----------------------------------------------------------------------
# Ground stations
# ----------------------------------------------------------------------
def add_ground_station(
    session,
    scenario: Scenario,
    name: str,
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float = 0.0,
    min_elevation_deg: float = 5.0,
) -> GroundStation:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Ground station name is required")
    try:
        StationGeometry(
            name=name,
            latitude_deg=float(latitude_deg),
            longitude_deg=float(longitude_deg),
            altitude_m=float(altitude_m),
            min_elevation_deg=float(min_elevation_deg),
        ).validate()
    except (StationError, TypeError, ValueError) as exc:
        raise ValidationError(str(exc))

    station = GroundStation(
        scenario_id=scenario.id,
        name=name,
        latitude_deg=float(latitude_deg),
        longitude_deg=float(longitude_deg),
        altitude_m=float(altitude_m),
        min_elevation_deg=float(min_elevation_deg),
    )
    session.add(station)
    session.commit()
    return station


def delete_ground_station(session, scenario: Scenario, station_id: int):
    station = (
        session.query(GroundStation)
        .filter_by(id=int(station_id), scenario_id=scenario.id)
        .first()
    )
    if station is None:
        raise NotFoundError("Ground station %s not found in scenario" % station_id)
    session.delete(station)
    session.commit()


# ----------------------------------------------------------------------
# Runs
# ----------------------------------------------------------------------
def get_run(session, run_id: int) -> SimulationRun:
    run = session.get(SimulationRun, int(run_id))
    if run is None:
        raise NotFoundError("Simulation run %s not found" % run_id)
    return run


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _positive_float(value, label: str) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValidationError("%s must be a number" % label)
    if value <= 0.0:
        raise ValidationError("%s must be positive" % label)
    return value


def _check_satellite_budget(scenario: Scenario, adding: int):
    if len(scenario.satellites) + adding > MAX_SATELLITES:
        raise ValidationError(
            "Scenario would exceed the %d-satellite limit" % MAX_SATELLITES
        )
