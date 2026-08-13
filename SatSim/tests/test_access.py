import numpy as np
import pytest

from satsim.core.access import find_access_windows, merge_intervals
from satsim.core.stations import StationGeometry


def test_single_window_with_interpolated_edges():
    t = np.array([0.0, 60.0, 120.0, 180.0, 240.0])
    el = np.array([-10.0, 0.0, 20.0, 0.0, -10.0])
    windows = find_access_windows(t, el, 10.0, "SAT", "GS")
    assert len(windows) == 1
    w = windows[0]
    # Elevation crosses 10 deg halfway between samples on both sides.
    assert w.start_s == pytest.approx(90.0)
    assert w.end_s == pytest.approx(150.0)
    assert w.max_elevation_deg == pytest.approx(20.0)
    assert w.satellite == "SAT" and w.station == "GS"


def test_window_open_at_boundaries():
    t = np.array([0.0, 60.0, 120.0])
    windows = find_access_windows(t, np.array([20.0, 25.0, 30.0]), 10.0)
    assert len(windows) == 1
    assert windows[0].start_s == 0.0
    assert windows[0].end_s == 120.0


def test_multiple_windows():
    t = np.arange(0.0, 601.0, 60.0)
    el = np.array([-5, 15, -5, -5, 15, 15, -5, -5, -5, 15, 15], dtype=float)
    windows = find_access_windows(t, el, 10.0)
    assert len(windows) == 3


def test_no_visibility():
    t = np.arange(0.0, 300.0, 60.0)
    assert find_access_windows(t, np.full(t.shape, -20.0), 5.0) == []


def test_merge_intervals():
    merged = merge_intervals([(0, 10), (5, 20), (30, 40), (40, 45), (50, 50)])
    assert merged == [(0.0, 20.0), (30.0, 45.0)]


def test_overhead_satellite_elevation():
    station = StationGeometry("EQ", 0.0, 0.0, 0.0)
    # Directly overhead on the equator at the prime meridian (ECEF x-axis)
    az, el, rng = station.look_angles(np.array([[7000.0, 0.0, 0.0]]))
    assert el[0] == pytest.approx(90.0, abs=1e-6)
    assert rng[0] == pytest.approx(7000.0 - 6378.137, abs=1e-3)


def test_horizon_geometry():
    station = StationGeometry("EQ", 0.0, 0.0, 0.0)
    # A point due east on the equator at the same radius sits well below
    # the horizon.
    az, el, _ = station.look_angles(np.array([[0.0, 6378.137, 0.0]]))
    assert el[0] < 0.0
    assert az[0] == pytest.approx(90.0, abs=1.0)
