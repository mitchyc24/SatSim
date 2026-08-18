from datetime import datetime, timedelta

import numpy as np
import pytest

from satsim.core.frames import (
    ecef_to_geodetic,
    eci_to_ecef_km,
    geodetic_to_ecef_km,
    eci_to_ecef_angle_deg,
    time_grid,
)

EPOCH = datetime(2026, 1, 1, 12, 0, 0)


def test_eci_to_ecef_preserves_radius():
    r_eci = np.array([[7000.0, 0.0, 0.0], [0.0, 7000.0, 100.0]])
    times = time_grid(EPOCH, np.array([0.0, 60.0]))
    r_ecef = eci_to_ecef_km(r_eci, times)
    assert r_ecef.shape == (2, 3)
    np.testing.assert_allclose(
        np.linalg.norm(r_ecef, axis=1),
        np.linalg.norm(r_eci, axis=1),
        rtol=1e-6,
    )


def test_ecef_rotates_with_earth():
    """The same inertial point maps to different ECEF longitudes as the
    Earth turns underneath (~15 deg/hour)."""
    r_eci = np.array([[7000.0, 0.0, 0.0], [7000.0, 0.0, 0.0]])
    times = time_grid(EPOCH, np.array([0.0, 3600.0]))
    r_ecef = eci_to_ecef_km(r_eci, times)
    _lat, lon, _h = ecef_to_geodetic(r_ecef)
    dlon = (lon[0] - lon[1]) % 360.0
    assert dlon == pytest.approx(15.04, abs=0.1)


def test_geodetic_round_trip():
    lat, lon, alt_m = 45.4215, -75.6972, 70.0
    ecef = geodetic_to_ecef_km(lat, lon, alt_m)
    lat2, lon2, h2 = ecef_to_geodetic(ecef)
    assert lat2[0] == pytest.approx(lat, abs=1e-9)
    assert lon2[0] == pytest.approx(lon, abs=1e-9)
    assert h2[0] * 1000.0 == pytest.approx(alt_m, abs=1e-3)


def test_equator_prime_meridian():
    ecef = geodetic_to_ecef_km(0.0, 0.0, 0.0)
    # WGS-84 equatorial radius along the x-axis
    np.testing.assert_allclose(ecef, [6378.137, 0.0, 0.0], atol=1e-6)


def test_frame_angle_matches_the_full_rotation():
    """The single-angle spin used by the 3D view must match the transform.

    The 3D view places Earth-fixed assets with this one number, so it has
    to agree with the astropy GCRS->ITRS rotation the analysis uses -- a
    sidereal-time formula would be a third of a degree out by now.
    """
    angle = eci_to_ecef_angle_deg(EPOCH)
    assert 0.0 <= angle < 360.0

    # An inertial point on the x-axis lands at ECEF longitude -angle.
    r_ecef = eci_to_ecef_km(np.array([[7000.0, 0.0, 0.0]]),
                            time_grid(EPOCH, np.array([0.0])))
    _lat, lon, _h = ecef_to_geodetic(r_ecef)
    assert ((-lon[0]) % 360.0) == pytest.approx(angle, abs=0.01)


def test_frame_angle_advances_one_turn_per_sidereal_day():
    start = eci_to_ecef_angle_deg(EPOCH)
    later = eci_to_ecef_angle_deg(EPOCH + timedelta(seconds=86164.0905))
    drift = ((later - start + 180.0) % 360.0) - 180.0
    assert drift == pytest.approx(0.0, abs=0.01)
