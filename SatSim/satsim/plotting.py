"""Matplotlib figure generation for simulation results.

Static PNGs are rendered headlessly (Agg backend) into the Flask
instance directory and served by the web layer.  Styling follows the
project's chart conventions: a fixed categorical series order (never
cycled -- above eight satellites the plots switch to a single-hue
composite encoding), recessive grid/axes, and identity carried by a
legend plus direct labels rather than color alone.  The numbers behind
every figure are also shown as tables on the results page.
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

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
MAX_INDIVIDUAL_SERIES = len(SERIES_COLORS)

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

_RC = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "text.color": INK_PRIMARY,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "axes.grid": True,
    "grid.color": GRIDLINE,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
    "legend.frameon": False,
}


def save_run_plots(output, plots_dir: str, run_id: int) -> list:
    """Render all figures for a simulation run.

    Returns the list of file names written (relative to ``plots_dir``).
    """
    os.makedirs(plots_dir, exist_ok=True)
    files = []

    name = "run%d_ground_track.png" % run_id
    _save(plot_ground_tracks(output), os.path.join(plots_dir, name))
    files.append(name)

    for index, sr in enumerate(output.station_results):
        name = "run%d_station%d.png" % (run_id, index)
        _save(plot_station_coverage(output, sr), os.path.join(plots_dir, name))
        files.append(name)
    return files


def plot_ground_tracks(output):
    """World-map ground tracks for every satellite plus station sites."""
    with plt.rc_context(_RC):
        fig, ax = plt.subplots(figsize=(10.5, 5.4))
        many = len(output.ground_tracks) > MAX_INDIVIDUAL_SERIES

        for index, (sat_name, (lat, lon)) in enumerate(
            sorted(output.ground_tracks.items())
        ):
            if many:
                color, alpha, label = SERIES_COLORS[0], 0.35, None
            else:
                color, alpha = SERIES_COLORS[index], 0.9
                label = sat_name
            ax.plot(_split_dateline(lon), lat,
                    color=color, linewidth=1.6, alpha=alpha, label=label)

        for sr in output.station_results:
            st = sr.station
            ax.plot(st.longitude_deg, st.latitude_deg, marker="^",
                    markersize=9, color=INK_PRIMARY, markeredgecolor=SURFACE,
                    markeredgewidth=1.2, linestyle="none", zorder=5)
            ax.annotate(st.name, (st.longitude_deg, st.latitude_deg),
                        xytext=(0, 8), textcoords="offset points",
                        ha="center", fontsize=9, color=INK_SECONDARY)

        ax.set_xlim(-180, 180)
        ax.set_ylim(-90, 90)
        ax.set_xticks(np.arange(-180, 181, 30))
        ax.set_yticks(np.arange(-90, 91, 30))
        ax.set_xlabel("Longitude (deg)")
        ax.set_ylabel("Latitude (deg)")
        title = "Ground tracks - %s" % output.scenario_name
        if many:
            title += "  (%d satellites)" % len(output.ground_tracks)
        ax.set_title(title, color=INK_PRIMARY, loc="left")
        if not many and len(output.ground_tracks) > 1:
            ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0),
                      fontsize=8, labelcolor=INK_SECONDARY)
        fig.tight_layout()
        return fig


def plot_station_coverage(output, station_result):
    """Elevation profiles and simultaneous-visibility count for one site."""
    with plt.rc_context(_RC):
        fig, (ax_el, ax_count) = plt.subplots(
            2, 1, figsize=(10.5, 6.2), sharex=True,
            gridspec_kw={"height_ratios": [2.2, 1.0]},
        )
        hours = output.times_s / 3600.0
        station = station_result.station
        profiles = sorted(station_result.elevations_by_sat.items())
        many = len(profiles) > MAX_INDIVIDUAL_SERIES

        for index, (sat_name, elevation) in enumerate(profiles):
            visible = np.where(elevation >= 0.0, elevation, np.nan)
            if many:
                color, alpha, label = SERIES_COLORS[0], 0.35, None
            else:
                color, alpha = SERIES_COLORS[index], 0.9
                label = sat_name
            ax_el.plot(hours, visible, color=color, linewidth=1.6,
                       alpha=alpha, label=label)

        ax_el.axhline(station.min_elevation_deg, color=INK_SECONDARY,
                      linewidth=1.0, linestyle=(0, (4, 3)))
        ax_el.annotate("%.0f deg mask" % station.min_elevation_deg,
                       (hours[-1], station.min_elevation_deg),
                       xytext=(-2, 4), textcoords="offset points",
                       ha="right", fontsize=8, color=INK_SECONDARY)
        ax_el.set_ylim(0, 90)
        ax_el.set_ylabel("Elevation (deg)")
        title = "Access from %s - %s" % (station.name, output.scenario_name)
        if many:
            title += "  (%d satellites)" % len(profiles)
        ax_el.set_title(title, color=INK_PRIMARY, loc="left")
        if not many and len(profiles) > 1:
            ax_el.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0),
                         fontsize=8, labelcolor=INK_SECONDARY)

        counts = station_result.visible_counts
        ax_count.fill_between(hours, counts, step="post",
                              color=SERIES_COLORS[0], alpha=0.25, linewidth=0)
        ax_count.step(hours, counts, where="post",
                      color=SERIES_COLORS[0], linewidth=1.6)
        top = max(1, int(np.max(counts)) if counts.size else 1)
        ax_count.set_ylim(0, top + 1)
        ax_count.set_yticks(np.arange(0, top + 2, max(1, (top + 1) // 5)))
        ax_count.set_ylabel("Visible sats")
        ax_count.set_xlabel("Time since epoch (hours)")
        ax_count.set_xlim(hours[0], hours[-1])
        fig.tight_layout()
        return fig


def _save(fig, path: str):
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _split_dateline(lon: np.ndarray) -> np.ndarray:
    """Insert NaNs where a track wraps across the +-180 deg meridian so
    matplotlib does not draw a horizontal line across the map."""
    lon = np.asarray(lon, dtype=float).copy()
    jumps = np.abs(np.diff(lon)) > 180.0
    lon[1:][jumps] = np.nan
    return lon
