import numpy as np
import pytest

from satsim.core.access import AccessWindow
from satsim.core.analysis import build_report, coverage_gaps, visible_counts


def _window(start, end, sat="S", gs="G", max_el=45.0):
    return AccessWindow(sat, gs, start, end, max_el)


def test_report_basic():
    windows = [_window(100.0, 400.0), _window(300.0, 600.0),
               _window(800.0, 900.0)]
    report = build_report(1000.0, windows)
    # Merged coverage: [100, 600] + [800, 900] = 600 s
    assert report.total_contact_s == pytest.approx(600.0)
    assert report.coverage_fraction == pytest.approx(0.6)
    assert report.num_passes == 3
    # Gaps: [0,100], [600,800], [900,1000]
    assert report.num_gaps == 3
    assert report.max_gap_s == pytest.approx(200.0)
    assert report.mean_gap_s == pytest.approx(400.0 / 3.0)
    assert report.max_pass_duration_s == pytest.approx(300.0)


def test_report_no_windows():
    report = build_report(1000.0, [])
    assert report.coverage_fraction == 0.0
    assert report.num_passes == 0
    assert report.num_gaps == 1
    assert report.max_gap_s == pytest.approx(1000.0)


def test_report_full_coverage():
    report = build_report(500.0, [_window(0.0, 500.0)])
    assert report.coverage_fraction == pytest.approx(1.0)
    assert report.num_gaps == 0
    assert report.max_gap_s == 0.0


def test_coverage_gaps_clip_to_duration():
    gaps = coverage_gaps(100.0, [(-50.0, 20.0), (80.0, 200.0)])
    assert gaps == [(20.0, 80.0)]


def test_visible_counts():
    e1 = np.array([10.0, -5.0, 20.0])
    e2 = np.array([-5.0, -5.0, 30.0])
    counts = visible_counts([e1, e2], 5.0)
    np.testing.assert_array_equal(counts, [1, 0, 2])
    assert visible_counts([], 5.0).size == 0


def test_report_rejects_bad_duration():
    with pytest.raises(ValueError):
        build_report(0.0, [])
