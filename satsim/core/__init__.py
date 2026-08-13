"""SatSim astrodynamics core.

Pure computational engine with **no** web or database dependencies:
everything in this package operates on plain Python/numpy data and can
be used standalone (scripts, notebooks, tests) or through the Flask
application layered on top.
"""

from .access import AccessWindow, find_access_windows, merge_intervals
from .analysis import CoverageReport, build_report, visible_counts
from .constellation import ConstellationMember, walker_delta
from .elements import (
    ClassicalElements,
    ElementError,
    mean_to_true_anomaly_deg,
    true_to_mean_anomaly_deg,
)
from .propagator import Ephemeris, propagate_elements, propagate_state
from .stations import StationGeometry, StationError

__all__ = [
    "AccessWindow",
    "ClassicalElements",
    "ConstellationMember",
    "CoverageReport",
    "ElementError",
    "Ephemeris",
    "StationError",
    "StationGeometry",
    "build_report",
    "find_access_windows",
    "mean_to_true_anomaly_deg",
    "merge_intervals",
    "propagate_elements",
    "propagate_state",
    "true_to_mean_anomaly_deg",
    "visible_counts",
    "walker_delta",
]
