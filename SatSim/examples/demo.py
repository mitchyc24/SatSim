"""Headless SatSim demo: build a Walker constellation, simulate a day,
and print the viability report -- no web server or database involved.

Run from the repository root:

    python examples/demo.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from satsim.core import (  # noqa: E402
    StationGeometry,
    build_report,
    find_access_windows,
    visible_counts,
    walker_delta,
    propagate_elements,
)
from satsim.core.frames import eci_to_ecef_km, time_grid  # noqa: E402


def main():
    epoch = datetime(2026, 1, 1, 0, 0, 0)
    duration_s = 86400.0
    step_s = 60.0
    times_s = np.arange(0.0, duration_s + step_s / 2, step_s)
    astropy_times = time_grid(epoch, times_s)

    # A small LEO comms shell: Walker delta 53 deg, 24/3/1 at 550 km.
    members = walker_delta(
        total_satellites=24, planes=3, relative_phasing=1,
        altitude_km=550.0, inclination_deg=53.0, name_prefix="DEMO",
    )
    stations = [
        StationGeometry("Ottawa", 45.4215, -75.6972, 70.0, 10.0),
        StationGeometry("Inuvik", 68.3607, -133.7230, 15.0, 10.0),
    ]

    print("Propagating %d satellites over %.0f h ..."
          % (len(members), duration_s / 3600))
    ecef_by_sat = {}
    for member in members:
        eph = propagate_elements(member.elements, epoch, times_s,
                                 name=member.name)
        ecef_by_sat[member.name] = eci_to_ecef_km(
            eph.positions_km, astropy_times
        )

    for station in stations:
        windows = []
        elevations = []
        for name, ecef in ecef_by_sat.items():
            _az, el, _rng = station.look_angles(ecef)
            elevations.append(el)
            windows.extend(find_access_windows(
                times_s, el, station.min_elevation_deg,
                satellite=name, station=station.name,
            ))
        counts = visible_counts(elevations, station.min_elevation_deg)
        report = build_report(duration_s, windows, visible_counts=counts)

        print("\n=== %s (mask %.0f deg) ===" % (station.name,
                                                station.min_elevation_deg))
        print("  Coverage:        %6.2f %%" % (100 * report.coverage_fraction))
        print("  Contact time:    %6.1f min" % (report.total_contact_s / 60))
        print("  Passes:          %6d" % report.num_passes)
        print("  Mean pass:       %6.1f min" % (report.mean_pass_duration_s / 60))
        print("  Max gap:         %6.1f min" % (report.max_gap_s / 60))
        print("  Mean visible:    %6.2f satellites" % report.mean_visible_count)


if __name__ == "__main__":
    main()
