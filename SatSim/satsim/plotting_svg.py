"""Fallback figure generation with no third-party plotting dependency.

:mod:`satsim.plotting` is the preferred backend, but matplotlib is a
large stack with compiled extensions (``ft2font``, ``kiwisolver``,
FreeType ...) that is easy to break -- a mixed 32/64-bit Anaconda
install on Windows, for example, raises ``ImportError: DLL load failed
while importing ft2font`` on the first import.  Figures are the whole
point of a viability study, so SatSim keeps a second renderer that
writes SVG directly and needs nothing but numpy.

The output mirrors :mod:`satsim.plotting` figure for figure and reads
its palette from :mod:`satsim.plot_style`, so a run rendered by either
backend looks the same on the results page.
"""

from __future__ import annotations

import os

import numpy as np

from .plot_style import (
    BASELINE,
    FONT_STACK,
    GRIDLINE,
    INK_MUTED,
    INK_PRIMARY,
    INK_SECONDARY,
    MAX_INDIVIDUAL_SERIES,
    SERIES_COLORS,
    SURFACE,
)

# Series are decimated before they reach the document: a 24 h window at
# a 60 s step is 1441 samples per satellite, which is far more detail
# than a 1000 px wide figure can show and bloats the file.
MAX_TRACK_POINTS = 600
MAX_PROFILE_POINTS = 1500


def save_run_plots(output, plots_dir: str, run_id: int) -> list:
    """Render all figures for a simulation run as SVG.

    Mirrors :func:`satsim.plotting.save_run_plots`; returns the list of
    file names written (relative to ``plots_dir``).
    """
    os.makedirs(plots_dir, exist_ok=True)
    files = []

    name = "run%d_ground_track.svg" % run_id
    _write(os.path.join(plots_dir, name), ground_tracks_svg(output))
    files.append(name)

    for index, sr in enumerate(output.station_results):
        name = "run%d_station%d.svg" % (run_id, index)
        _write(os.path.join(plots_dir, name), station_coverage_svg(output, sr))
        files.append(name)
    return files


# ----------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------
def ground_tracks_svg(output) -> str:
    """World-map ground tracks for every satellite plus station sites."""
    width, height = 1050, 540
    tracks = sorted(output.ground_tracks.items())
    many = len(tracks) > MAX_INDIVIDUAL_SERIES
    legend = (not many) and len(tracks) > 1

    right = 168 if legend else 24
    axes = _Axes(x=64, y=52, width=width - 64 - right, height=height - 52 - 52,
                 xlim=(-180.0, 180.0), ylim=(-90.0, 90.0))

    title = "Ground tracks - %s" % output.scenario_name
    if many:
        title += "  (%d satellites)" % len(tracks)

    body = [_title(title, axes)]
    body += _frame(axes,
                   xticks=np.arange(-180, 181, 30),
                   yticks=np.arange(-90, 91, 30),
                   xlabel="Longitude (deg)",
                   ylabel="Latitude (deg)")

    clip_id = "clip-tracks"
    series = []
    for index, (_name, (lat, lon)) in enumerate(tracks):
        lat_d, lon_d = _decimate(MAX_TRACK_POINTS, lat, lon)
        color = SERIES_COLORS[0] if many else SERIES_COLORS[index]
        opacity = 0.35 if many else 0.9
        series.append(_path(_polyline_d(axes, _split_dateline(lon_d), lat_d),
                            stroke=color, width=1.6, opacity=opacity))
    body.append(_clipped(clip_id, axes, series))

    for sr in output.station_results:
        st = sr.station
        x = axes.px(st.longitude_deg)
        y = axes.py(st.latitude_deg)
        body.append(_marker_triangle(x, y, size=9.0))
        body.append(_text(x, y - 10.0, st.name, INK_SECONDARY, 9,
                          anchor="middle"))

    if legend:
        body.append(_legend([(name, SERIES_COLORS[i])
                             for i, (name, _) in enumerate(tracks)],
                            x=axes.right + 18, y=axes.y))

    return _document(width, height, body)


def station_coverage_svg(output, station_result) -> str:
    """Elevation profiles and simultaneous-visibility count for one site."""
    width, height = 1050, 620
    station = station_result.station
    profiles = sorted(station_result.elevations_by_sat.items())
    many = len(profiles) > MAX_INDIVIDUAL_SERIES
    legend = (not many) and len(profiles) > 1

    hours = np.asarray(output.times_s, dtype=float) / 3600.0
    xlim = (float(hours[0]), float(hours[-1])) if hours.size else (0.0, 1.0)
    if xlim[0] == xlim[1]:
        xlim = (xlim[0], xlim[0] + 1.0)

    right = 168 if legend else 24
    plot_width = width - 64 - right
    # 2.2 : 1.0 height ratio, matching the matplotlib figure.
    top_h, bottom_h, gap = 322, 146, 40
    el_axes = _Axes(x=64, y=52, width=plot_width, height=top_h,
                    xlim=xlim, ylim=(0.0, 90.0))

    counts = np.asarray(station_result.visible_counts, dtype=float)
    top = max(1, int(np.max(counts)) if counts.size else 1)
    count_axes = _Axes(x=64, y=52 + top_h + gap, width=plot_width,
                       height=bottom_h, xlim=xlim, ylim=(0.0, float(top + 1)))

    title = "Access from %s - %s" % (station.name, output.scenario_name)
    if many:
        title += "  (%d satellites)" % len(profiles)

    body = [_title(title, el_axes)]
    body += _frame(el_axes,
                   xticks=_nice_ticks(xlim[0], xlim[1]),
                   yticks=np.arange(0, 91, 15),
                   xlabel=None, ylabel="Elevation (deg)",
                   xtick_labels=False)

    series = []
    for index, (_name, elevation) in enumerate(profiles):
        elevation = np.asarray(elevation, dtype=float)
        # Only the visible arcs are drawn; below the horizon is a gap.
        visible = np.where(elevation >= 0.0, elevation, np.nan)
        h_d, v_d = _decimate(MAX_PROFILE_POINTS, hours, visible)
        color = SERIES_COLORS[0] if many else SERIES_COLORS[index]
        opacity = 0.35 if many else 0.9
        series.append(_path(_polyline_d(el_axes, h_d, v_d),
                            stroke=color, width=1.6, opacity=opacity))
    body.append(_clipped("clip-elev", el_axes, series))

    mask_y = el_axes.py(station.min_elevation_deg)
    body.append(_line(el_axes.x, mask_y, el_axes.right, mask_y,
                      stroke=INK_SECONDARY, width=1.0, dash="4 3"))
    body.append(_text(el_axes.right - 2, mask_y - 4,
                      "%.0f deg mask" % station.min_elevation_deg,
                      INK_SECONDARY, 8, anchor="end"))

    if legend:
        body.append(_legend([(name, SERIES_COLORS[i])
                             for i, (name, _) in enumerate(profiles)],
                            x=el_axes.right + 18, y=el_axes.y))

    step = max(1, (top + 1) // 5)
    body += _frame(count_axes,
                   xticks=_nice_ticks(xlim[0], xlim[1]),
                   yticks=np.arange(0, top + 2, step),
                   xlabel="Time since epoch (hours)",
                   ylabel="Visible sats")
    if counts.size:
        fill_d, line_d = _step_paths(count_axes, hours, counts)
        body.append(_clipped("clip-count", count_axes, [
            _path(fill_d, stroke=None, width=0, opacity=0.25,
                  fill=SERIES_COLORS[0]),
            _path(line_d, stroke=SERIES_COLORS[0], width=1.6, opacity=1.0),
        ]))

    return _document(width, height, body)


# ----------------------------------------------------------------------
# Axes and drawing primitives
# ----------------------------------------------------------------------
class _Axes:
    """A rectangular plot area plus its data-to-pixel mapping."""

    def __init__(self, x, y, width, height, xlim, ylim):
        self.x = float(x)
        self.y = float(y)
        self.width = float(width)
        self.height = float(height)
        self.xlim = (float(xlim[0]), float(xlim[1]))
        self.ylim = (float(ylim[0]), float(ylim[1]))

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    def px(self, value):
        lo, hi = self.xlim
        span = (hi - lo) or 1.0
        return self.x + (float(value) - lo) / span * self.width

    def py(self, value):
        lo, hi = self.ylim
        span = (hi - lo) or 1.0
        # SVG y grows downwards.
        return self.bottom - (float(value) - lo) / span * self.height


def _document(width, height, body) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="%s">'
        % (width, height, width, height, FONT_STACK),
        '<rect width="%d" height="%d" fill="%s"/>' % (width, height, SURFACE),
    ]
    parts.extend(body)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _frame(axes, xticks, yticks, xlabel, ylabel, xtick_labels=True):
    """Grid, ticks, axis lines and axis labels for one plot area."""
    out = []
    for value in xticks:
        x = axes.px(value)
        out.append(_line(x, axes.y, x, axes.bottom, GRIDLINE, 0.8))
        if xtick_labels:
            out.append(_text(x, axes.bottom + 16, _tick_label(value),
                             INK_MUTED, 10, anchor="middle"))
    for value in yticks:
        y = axes.py(value)
        out.append(_line(axes.x, y, axes.right, y, GRIDLINE, 0.8))
        out.append(_text(axes.x - 8, y + 3.5, _tick_label(value),
                         INK_MUTED, 10, anchor="end"))

    # Only the left and bottom spines, matching the matplotlib style.
    out.append(_line(axes.x, axes.y, axes.x, axes.bottom, BASELINE, 1.0))
    out.append(_line(axes.x, axes.bottom, axes.right, axes.bottom,
                     BASELINE, 1.0))

    if xlabel:
        out.append(_text(axes.x + axes.width / 2.0, axes.bottom + 38,
                         xlabel, INK_SECONDARY, 10, anchor="middle"))
    if ylabel:
        y_mid = axes.y + axes.height / 2.0
        out.append(
            '<text x="%.1f" y="%.1f" fill="%s" font-size="10" '
            'text-anchor="middle" transform="rotate(-90 %.1f %.1f)">%s</text>'
            % (axes.x - 42, y_mid, INK_SECONDARY, axes.x - 42, y_mid,
               _esc(ylabel))
        )
    return out


def _clipped(clip_id, axes, elements):
    """Group ``elements`` behind a clip rectangle covering ``axes``."""
    return (
        '<clipPath id="%s"><rect x="%.1f" y="%.1f" width="%.1f" '
        'height="%.1f"/></clipPath>\n<g clip-path="url(#%s)">%s</g>'
        % (clip_id, axes.x, axes.y, axes.width, axes.height, clip_id,
           "".join(elements))
    )


def _title(text, axes):
    return _text(axes.x, axes.y - 22, text, INK_PRIMARY, 12, weight="600")


def _line(x1, y1, x2, y2, stroke, width, dash=None):
    dash_attr = ' stroke-dasharray="%s"' % dash if dash else ""
    return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
            'stroke-width="%.2f"%s/>'
            % (x1, y1, x2, y2, stroke, width, dash_attr))


def _text(x, y, text, fill, size, anchor="start", weight=None):
    weight_attr = ' font-weight="%s"' % weight if weight else ""
    return ('<text x="%.1f" y="%.1f" fill="%s" font-size="%d" '
            'text-anchor="%s"%s>%s</text>'
            % (x, y, fill, size, anchor, weight_attr, _esc(text)))


def _path(d, stroke, width, opacity=1.0, fill="none"):
    if not d:
        return ""
    stroke_attr = ""
    if stroke:
        stroke_attr = (' stroke="%s" stroke-width="%.2f" stroke-linejoin="round"'
                       ' stroke-linecap="round"' % (stroke, width))
    return ('<path d="%s" fill="%s"%s opacity="%.2f"/>'
            % (d, fill, stroke_attr, opacity))


def _marker_triangle(x, y, size):
    half = size / 2.0
    points = "%.1f,%.1f %.1f,%.1f %.1f,%.1f" % (
        x, y - half, x - half, y + half, x + half, y + half)
    return ('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.2"/>'
            % (points, INK_PRIMARY, SURFACE))


def _legend(entries, x, y):
    out = []
    for index, (label, color) in enumerate(entries):
        row_y = y + index * 16.0
        out.append('<rect x="%.1f" y="%.1f" width="10" height="3" fill="%s" '
                   'rx="1.5"/>' % (x, row_y, color))
        out.append(_text(x + 16, row_y + 4, label, INK_SECONDARY, 9))
    return "".join(out)


# ----------------------------------------------------------------------
# Data helpers
# ----------------------------------------------------------------------
def _polyline_d(axes, xs, ys) -> str:
    """Build a path, starting a new subpath wherever the data has a NaN."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    parts = []
    pen_down = False
    for x, y in zip(xs, ys):
        if not (np.isfinite(x) and np.isfinite(y)):
            pen_down = False
            continue
        command = "L" if pen_down else "M"
        parts.append("%s%.1f %.1f" % (command, axes.px(x), axes.py(y)))
        pen_down = True
    return " ".join(parts)


def _step_paths(axes, xs, ys):
    """Post-step outline and its filled area, as two path strings."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    points = []
    for index in range(len(xs)):
        points.append((axes.px(xs[index]), axes.py(ys[index])))
        if index + 1 < len(xs):
            points.append((axes.px(xs[index + 1]), axes.py(ys[index])))

    line = " ".join(
        "%s%.1f %.1f" % ("M" if i == 0 else "L", px, py)
        for i, (px, py) in enumerate(points)
    )
    baseline = axes.py(axes.ylim[0])
    fill = "%s L%.1f %.1f L%.1f %.1f Z" % (
        line, points[-1][0], baseline, points[0][0], baseline)
    return fill, line


def _decimate(max_points, *arrays):
    """Thin arrays to at most ``max_points`` samples, keeping the last one."""
    arrays = [np.asarray(a, dtype=float) for a in arrays]
    length = len(arrays[0]) if arrays else 0
    if length <= max_points:
        return arrays
    step = int(np.ceil(length / float(max_points)))
    index = np.arange(0, length, step)
    if index[-1] != length - 1:
        index = np.append(index, length - 1)
    return [a[index] for a in arrays]


def _split_dateline(lon):
    """Insert NaNs where a track wraps across the +-180 deg meridian so
    the path does not sweep back across the whole map."""
    lon = np.asarray(lon, dtype=float).copy()
    if lon.size < 2:
        return lon
    jumps = np.abs(np.diff(lon)) > 180.0
    lon[1:][jumps] = np.nan
    return lon


def _nice_ticks(lo, hi, target=8):
    """Round tick locations covering ``[lo, hi]``."""
    span = float(hi) - float(lo)
    if span <= 0:
        return np.array([lo])
    raw = span / float(target)
    magnitude = 10.0 ** np.floor(np.log10(raw))
    for multiple in (1.0, 2.0, 2.5, 5.0, 10.0):
        step = multiple * magnitude
        if step >= raw:
            break
    start = np.ceil(lo / step) * step
    ticks = np.arange(start, hi + step / 2.0, step)
    # arange can overshoot; a tick outside the axis would draw its
    # gridline past the plot frame.
    return ticks[(ticks >= lo - 1e-9) & (ticks <= hi + 1e-9)]


def _tick_label(value):
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        return "%d" % int(round(value))
    return ("%.2f" % value).rstrip("0").rstrip(".")


def _esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _write(path: str, content: str):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
