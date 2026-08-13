import math

import numpy as np
import pytest

from satsim.core.constants import MU_EARTH_KM3_S2, R_EARTH_EQ_KM
from satsim.core.elements import (
    ClassicalElements,
    ElementError,
    mean_to_true_anomaly_deg,
    solve_kepler,
    true_to_mean_anomaly_deg,
)


def test_state_vector_round_trip():
    el = ClassicalElements(7000.0, 0.01, 51.6, 120.0, 45.0, 30.0)
    r, v = el.to_state_vector()
    back = ClassicalElements.from_state_vector(r, v)
    assert back.semi_major_axis_km == pytest.approx(el.semi_major_axis_km, rel=1e-9)
    assert back.eccentricity == pytest.approx(el.eccentricity, abs=1e-9)
    assert back.inclination_deg == pytest.approx(el.inclination_deg, abs=1e-9)
    assert back.raan_deg == pytest.approx(el.raan_deg, abs=1e-9)
    assert back.arg_perigee_deg == pytest.approx(el.arg_perigee_deg, abs=1e-8)
    assert back.true_anomaly_deg == pytest.approx(el.true_anomaly_deg, abs=1e-8)


def test_circular_orbit_speed():
    a = 7000.0
    el = ClassicalElements(a, 0.0, 30.0, 0.0, 0.0, 0.0)
    r, v = el.to_state_vector()
    assert np.linalg.norm(r) == pytest.approx(a, rel=1e-12)
    assert np.linalg.norm(v) == pytest.approx(
        math.sqrt(MU_EARTH_KM3_S2 / a), rel=1e-12
    )
    # r and v orthogonal on a circular orbit
    assert abs(np.dot(r, v)) < 1e-9


def test_circular_round_trip_uses_argument_of_latitude():
    el = ClassicalElements(7000.0, 0.0, 51.6, 40.0, 0.0, 123.0)
    r, v = el.to_state_vector()
    back = ClassicalElements.from_state_vector(r, v)
    assert back.eccentricity == pytest.approx(0.0, abs=1e-10)
    assert back.arg_perigee_deg == pytest.approx(0.0, abs=1e-8)
    assert back.true_anomaly_deg == pytest.approx(123.0, abs=1e-6)


def test_period():
    el = ClassicalElements(R_EARTH_EQ_KM + 550.0, 0.0, 53.0, 0.0, 0.0, 0.0)
    # ~95.6 minutes for a 550 km orbit
    assert el.period_s() == pytest.approx(95.6 * 60.0, rel=0.01)


def test_validation_rejects_bad_elements():
    with pytest.raises(ElementError):
        ClassicalElements(7000.0, 1.2, 0.0, 0.0, 0.0, 0.0).validate()
    with pytest.raises(ElementError):
        ClassicalElements(-1.0, 0.0, 0.0, 0.0, 0.0, 0.0).validate()
    with pytest.raises(ElementError):  # perigee below the atmosphere floor
        ClassicalElements(R_EARTH_EQ_KM + 50.0, 0.0, 0.0, 0.0, 0.0, 0.0).validate()
    with pytest.raises(ElementError):
        ClassicalElements(7000.0, 0.0, 200.0, 0.0, 0.0, 0.0).validate()


def test_kepler_solver():
    for e in (0.0, 0.1, 0.7, 0.9):
        for m_deg in (0.0, 45.0, 180.0, 275.0):
            m = math.radians(m_deg)
            big_e = solve_kepler(m, e)
            assert big_e - e * math.sin(big_e) == pytest.approx(m, abs=1e-10)


def test_anomaly_round_trip():
    for e in (0.0, 0.05, 0.4):
        for m in (0.0, 10.0, 90.0, 200.0, 359.0):
            nu = mean_to_true_anomaly_deg(m, e)
            assert true_to_mean_anomaly_deg(nu, e) == pytest.approx(m, abs=1e-8)
