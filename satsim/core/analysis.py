"""Coverage / viability metrics derived from access windows.

The metrics answer the questions a constellation viability study asks:

* What fraction of the time does a site have at least one satellite in
  view (``coverage_fraction``)?
* How long are the outages between contacts (``max_gap_s``,
  ``mean_gap_s`` -- i.e. revisit performance)?
* What do individual passes look like (count, mean/max duration)?

Gap accounting includes any uncovered time at the start and end of the
analysis interval, so a scenario with no contacts reports a single gap
equal to the full duration.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .access import merge_intervals


@dataclass
class CoverageReport:
    duration_s: float
    coverage_fraction: float
    total_contact_s: float
    num_passes: int
    mean_pass_duration_s: float
    max_pass_duration_s: float
    num_gaps: int
    mean_gap_s: float
    max_gap_s: float
    # None when per-sample visibility counts were not supplied
    mean_visible_count: float = None

    def to_dict(self) -> dict:
        return asdict(self)


def coverage_gaps(duration_s: float, merged_intervals) -> list:
    """Complement of the merged coverage intervals within [0, duration]."""
    gaps = []
    cursor = 0.0
    for start, end in merged_intervals:
        start = max(0.0, start)
        end = min(duration_s, end)
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration_s:
        gaps.append((cursor, duration_s))
    return gaps


def build_report(duration_s: float, windows,
                 visible_counts=None) -> CoverageReport:
    """Summarise a set of access windows into a :class:`CoverageReport`.

    Parameters
    ----------
    duration_s : float
        Length of the analysis interval.
    windows : iterable of :class:`~satsim.core.access.AccessWindow`
        All windows contributing to this report (typically every
        satellite seen from one station, or the whole network).
    visible_counts : optional 1-D array
        Number of simultaneously visible satellites per time sample;
        used for the ``mean_visible_count`` statistic.
    """
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive")

    windows = list(windows)
    merged = merge_intervals((w.start_s, w.end_s) for w in windows)
    total_contact = sum(e - s for s, e in merged)
    gaps = coverage_gaps(duration_s, merged)
    gap_lengths = [e - s for s, e in gaps]
    durations = [w.duration_s for w in windows]

    return CoverageReport(
        duration_s=float(duration_s),
        coverage_fraction=float(total_contact / duration_s),
        total_contact_s=float(total_contact),
        num_passes=len(windows),
        mean_pass_duration_s=float(np.mean(durations)) if durations else 0.0,
        max_pass_duration_s=float(np.max(durations)) if durations else 0.0,
        num_gaps=len(gap_lengths),
        mean_gap_s=float(np.mean(gap_lengths)) if gap_lengths else 0.0,
        max_gap_s=float(np.max(gap_lengths)) if gap_lengths else 0.0,
        mean_visible_count=(
            float(np.mean(visible_counts)) if visible_counts is not None else None
        ),
    )


def visible_counts(elevations_by_satellite, min_elevation_deg: float) -> np.ndarray:
    """Number of satellites above the elevation mask per time sample.

    ``elevations_by_satellite`` is an iterable of 1-D elevation arrays
    (one per satellite) sharing the same time grid.
    """
    profiles = [np.asarray(e, dtype=float) for e in elevations_by_satellite]
    if not profiles:
        return np.zeros(0)
    stacked = np.vstack(profiles)
    return np.sum(stacked >= min_elevation_deg, axis=0)
