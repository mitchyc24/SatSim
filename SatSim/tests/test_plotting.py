"""Tests for the two figure backends.

The SVG backend is the one that has to work when matplotlib does not, so
it is checked directly rather than only through the run endpoint: it must
produce a well-formed document that actually contains the data.
"""

import os
import xml.etree.ElementTree as ElementTree
from datetime import datetime

import numpy as np
import pytest

from satsim import plot_style, plotting_svg
from satsim.core.stations import StationGeometry
from satsim.services.simulation import SimulationOutput, StationResult


class _Report:
    def to_dict(self):
        return {}


def _output(num_satellites=2, num_samples=120):
    """A minimal SimulationOutput with plausible geometry."""
    times = np.arange(0.0, num_samples * 60.0, 60.0)
    hours = times / 3600.0

    ground_tracks = {}
    elevations = {}
    for index in range(num_satellites):
        phase = index * 1.3
        lon = ((hours * 200.0 + phase * 60.0 + 180.0) % 360.0) - 180.0
        lat = 53.0 * np.sin(hours * 4.0 + phase)
        ground_tracks["SAT-%d" % index] = (lat, lon)
        elevations["SAT-%d" % index] = 90.0 * np.sin(hours * 5.0 + phase)

    station = StationGeometry(
        name="Ottawa", latitude_deg=45.42, longitude_deg=-75.70,
        min_elevation_deg=5.0,
    )
    counts = np.sum(
        [np.asarray(e) >= 5.0 for e in elevations.values()], axis=0
    ).astype(float)

    return SimulationOutput(
        scenario_name="Test scenario",
        epoch=datetime(2026, 1, 1),
        duration_s=float(times[-1]),
        times_s=times,
        ground_tracks=ground_tracks,
        station_results=[StationResult(
            station=station, windows=[], report=_Report(),
            elevations_by_sat=elevations, visible_counts=counts,
        )],
        network_report=_Report(),
    )


def _parse(svg_text):
    assert svg_text.startswith("<?xml")
    return ElementTree.fromstring(svg_text)


def test_ground_track_svg_is_well_formed():
    root = _parse(plotting_svg.ground_tracks_svg(_output()))
    assert root.tag.endswith("svg")
    texts = [node.text for node in root.iter() if node.tag.endswith("text")]
    assert "Ground tracks - Test scenario" in texts
    assert "Ottawa" in texts          # station is labelled
    assert "Longitude (deg)" in texts
    # One path per satellite track, each carrying real coordinates.
    paths = [n for n in root.iter() if n.tag.endswith("path")]
    assert len(paths) >= 2
    assert all(node.get("d") for node in paths)


def test_station_coverage_svg_is_well_formed():
    output = _output()
    root = _parse(plotting_svg.station_coverage_svg(
        output, output.station_results[0]
    ))
    texts = [node.text for node in root.iter() if node.tag.endswith("text")]
    assert "Access from Ottawa - Test scenario" in texts
    assert "Elevation (deg)" in texts
    assert "Visible sats" in texts
    assert "5 deg mask" in texts


def test_svg_escapes_scenario_names():
    """Names reach the document as text, so they must be escaped."""
    output = _output()
    output.scenario_name = 'Ops & <Test> "one"'
    root = _parse(plotting_svg.ground_tracks_svg(output))
    titles = [node.text for node in root.iter() if node.tag.endswith("text")]
    assert 'Ground tracks - Ops & <Test> "one"' in titles


def test_many_satellites_drop_to_a_composite_encoding():
    """Past the palette's length, series stop claiming individual identity."""
    limit = plot_style.MAX_INDIVIDUAL_SERIES
    few = plotting_svg.ground_tracks_svg(_output(num_satellites=limit))
    many = plotting_svg.ground_tracks_svg(_output(num_satellites=limit + 1))
    assert "SAT-0" in few                       # legend present
    assert "SAT-0" not in many                  # legend dropped
    assert "(%d satellites)" % (limit + 1) in many
    assert plot_style.SERIES_COLORS[1] not in many


def test_save_run_plots_writes_one_file_per_figure(tmp_path):
    output = _output()
    names = plotting_svg.save_run_plots(output, str(tmp_path), run_id=7)
    assert names == ["run7_ground_track.svg", "run7_station0.svg"]
    for name in names:
        path = os.path.join(str(tmp_path), name)
        assert os.path.getsize(path) > 0
        with open(path, encoding="utf-8") as handle:
            _parse(handle.read())


def test_long_series_are_decimated():
    """A fine time step must not blow the document up point-for-point."""
    output = _output(num_satellites=1, num_samples=5000)
    root = _parse(plotting_svg.ground_tracks_svg(output))
    path = [n for n in root.iter() if n.tag.endswith("path")][0]
    vertices = path.get("d").count("L") + path.get("d").count("M")
    assert vertices <= plotting_svg.MAX_TRACK_POINTS + 2


def test_matplotlib_backend_still_renders(tmp_path):
    """The preferred backend keeps working where matplotlib is healthy."""
    plotting = pytest.importorskip("satsim.plotting")
    output = _output()
    names = plotting.save_run_plots(output, str(tmp_path), run_id=3)
    assert names == ["run3_ground_track.png", "run3_station0.png"]
    for name in names:
        assert os.path.getsize(os.path.join(str(tmp_path), name)) > 0
