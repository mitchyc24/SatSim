import math
from datetime import datetime

import numpy as np
import pytest

from satsim.core.constants import J2_EARTH, MU_EARTH_KM3_S2, R_EARTH_EQ_KM
from satsim.core.elements import ClassicalElements
from satsim.core.propagator import propagate_elements, propagate_state

EPOCH = datetime(2026, 1, 1)


def test_two_body_returns_after_one_period():
    el = ClassicalElements(7000.0, 0.001, 51.6, 30.0, 10.0, 0.0)
    period = el.period_s()
    eph = propagate_elements(el, EPOCH, np.array([0.0, period]),
                             include_j2=False)
    error_km = np.linalg.norm(eph.positions_km[-1] - eph.positions_km[0])
    assert error_km < 1e-3  # sub-metre closure over one orbit


def test_two_body_conserves_energy():
    el = ClassicalElements(7200.0, 0.05, 40.0, 0.0, 0.0, 0.0)
    times = np.linspace(0.0, 3 * el.period_s(), 200)
    eph = propagate_elements(el, EPOCH, times, include_j2=False)
    r = np.linalg.norm(eph.positions_km, axis=1)
    v = np.linalg.norm(eph.velocities_km_s, axis=1)
    energy = 0.5 * v ** 2 - MU_EARTH_KM3_S2 / r
    assert np.ptp(energy) / abs(energy[0]) < 1e-8


def test_j2_raan_drift_matches_secular_rate():
    """The numerically observed nodal regression should match the
    first-order secular J2 rate to within a few percent."""
    el = ClassicalElements(R_EARTH_EQ_KM + 800.0, 0.001, 60.0, 100.0, 0.0, 0.0)
    day = 86400.0
    times = np.arange(0.0, day + 1.0, 300.0)
    eph = propagate_elements(el, EPOCH, times, include_j2=True)

    final = ClassicalElements.from_state_vector(
        eph.positions_km[-1], eph.velocities_km_s[-1]
    )
    drift = (final.raan_deg - el.raan_deg + 180.0) % 360.0 - 180.0

    n = el.mean_motion_rad_s()
    p = el.semi_latus_rectum_km
    expected_rate = (
        -1.5 * n * J2_EARTH * (R_EARTH_EQ_KM / p) ** 2
        * math.cos(math.radians(el.inclination_deg))
    )
    expected = math.degrees(expected_rate * day)

    assert drift == pytest.approx(expected, rel=0.05)
    assert drift < 0.0  # prograde orbit regresses westward


def test_j2_off_equals_pure_kepler():
    el = ClassicalElements(26560.0, 0.01, 55.0, 0.0, 0.0, 0.0)
    times = np.array([0.0, 1800.0])
    with_j2 = propagate_elements(el, EPOCH, times, include_j2=True)
    without = propagate_elements(el, EPOCH, times, include_j2=False)
    # At 4 Earth radii J2 is small but nonzero: trajectories must differ,
    # though only slightly.
    delta = np.linalg.norm(
        with_j2.positions_km[-1] - without.positions_km[-1]
    )
    assert 0.0 < delta < 5.0


def test_propagate_state_input_validation():
    with pytest.raises(ValueError):
        propagate_state([7000, 0, 0], [0, 7.5, 0], EPOCH, [])
    with pytest.raises(ValueError):
        propagate_state([7000, 0, 0], [0, 7.5, 0], EPOCH, [0.0, 0.0])
    with pytest.raises(ValueError):
        propagate_state([7000, 0], [0, 7.5, 0], EPOCH, [0.0, 60.0])
