"""Line-of-sight access (contact window) computation.

Access windows are found by scanning a sampled elevation profile for
threshold crossings and refining each rise/set time with linear
interpolation between the bracketing samples.  Accuracy is therefore a
small fraction of the simulation time step -- ample for constellation
viability work.  Windows that begin before or extend past the analysis
interval are clipped to it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class AccessWindow:
    """A single contact window between one satellite and one station.

    Times are offsets in seconds from the scenario epoch.
    """

    satellite: str
    station: str
    start_s: float
    end_s: float
    max_elevation_deg: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    def to_dict(self) -> dict:
        return {
            "satellite": self.satellite,
            "station": self.station,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "duration_s": self.duration_s,
            "max_elevation_deg": self.max_elevation_deg,
        }


def _crossing_time(t0: float, t1: float, e0: float, e1: float,
                   threshold: float) -> float:
    """Linear interpolation of the elevation threshold crossing."""
    if e1 == e0:
        return t0
    return t0 + (threshold - e0) / (e1 - e0) * (t1 - t0)


def find_access_windows(
    times_s: np.ndarray,
    elevation_deg: np.ndarray,
    min_elevation_deg: float,
    satellite: str = "",
    station: str = "",
) -> list:
    """Extract access windows from a sampled elevation profile.

    Parameters
    ----------
    times_s, elevation_deg : 1-D arrays of equal length
    min_elevation_deg : visibility threshold

    Returns
    -------
    list of :class:`AccessWindow`, in chronological order.
    """
    t = np.asarray(times_s, dtype=float)
    el = np.asarray(elevation_deg, dtype=float)
    if t.shape != el.shape or t.ndim != 1:
        raise ValueError("times_s and elevation_deg must be equal-length 1-D arrays")
    if t.size == 0:
        return []

    visible = el >= min_elevation_deg
    windows = []
    start = None
    peak = None

    for i in range(t.size):
        if visible[i] and start is None:
            if i == 0:
                start = t[0]
            else:
                start = _crossing_time(t[i - 1], t[i], el[i - 1], el[i],
                                       min_elevation_deg)
            peak = el[i]
        elif visible[i]:
            peak = max(peak, el[i])
        elif start is not None:
            end = _crossing_time(t[i - 1], t[i], el[i - 1], el[i],
                                 min_elevation_deg)
            windows.append(AccessWindow(satellite, station, float(start),
                                        float(end), float(peak)))
            start = None
            peak = None

    if start is not None:  # window still open at the end of the interval
        windows.append(AccessWindow(satellite, station, float(start),
                                    float(t[-1]), float(peak)))
    return windows


def merge_intervals(intervals) -> list:
    """Merge overlapping/adjacent ``(start, end)`` intervals.

    Used to union access windows from several satellites (or stations)
    into combined coverage intervals.
    """
    ordered = sorted((float(s), float(e)) for s, e in intervals if e > s)
    merged = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]
