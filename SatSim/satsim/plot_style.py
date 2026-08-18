"""Shared chart styling for every figure SatSim renders.

Both figure backends -- :mod:`satsim.plotting` (matplotlib) and
:mod:`satsim.plotting_svg` (the dependency-free fallback) -- read their
palette and typography from here so the two produce visually
interchangeable output.  This module deliberately imports nothing: it
has to stay importable in an environment where matplotlib is broken.
"""

from __future__ import annotations

# Validated categorical palette (light surface), fixed slot order.
SERIES_COLORS = [
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
]

#: Above this many series the plots drop per-satellite identity and
#: switch to a single-hue composite encoding.
MAX_INDIVIDUAL_SERIES = len(SERIES_COLORS)

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

FONT_STACK = (
    "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', "
    "Arial, sans-serif"
)
