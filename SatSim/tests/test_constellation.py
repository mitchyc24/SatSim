import pytest

from satsim.core.constants import R_EARTH_EQ_KM
from satsim.core.constellation import ConstellationError, walker_delta


def test_walker_delta_structure():
    members = walker_delta(24, 3, 1, 550.0, 53.0)
    assert len(members) == 24

    raans = sorted({m.elements.raan_deg for m in members})
    assert raans == pytest.approx([0.0, 120.0, 240.0])

    # Eight satellites per plane, spaced 45 deg in anomaly
    plane1 = [m for m in members if m.plane == 1]
    assert len(plane1) == 8
    anomalies = sorted(m.elements.true_anomaly_deg for m in plane1)
    assert anomalies == pytest.approx([0, 45, 90, 135, 180, 225, 270, 315])

    for m in members:
        assert m.elements.semi_major_axis_km == pytest.approx(
            R_EARTH_EQ_KM + 550.0
        )
        assert m.elements.inclination_deg == 53.0


def test_walker_phasing_offset():
    members = walker_delta(9, 3, 1, 700.0, 60.0)
    # Phase step is f * 360/t = 40 deg between adjacent planes.
    plane_leads = {m.plane: m.elements.true_anomaly_deg
                   for m in members if m.slot == 1}
    assert plane_leads[2] - plane_leads[1] == pytest.approx(40.0)
    assert plane_leads[3] - plane_leads[2] == pytest.approx(40.0)


def test_walker_star_spread():
    members = walker_delta(6, 3, 0, 800.0, 86.4, raan_spread_deg=180.0)
    raans = sorted({m.elements.raan_deg for m in members})
    assert raans == pytest.approx([0.0, 60.0, 120.0])


def test_walker_unique_names():
    members = walker_delta(12, 4, 2, 600.0, 45.0, name_prefix="X")
    names = [m.name for m in members]
    assert len(set(names)) == 12
    assert names[0] == "X-101"


def test_walker_validation():
    with pytest.raises(ConstellationError):
        walker_delta(10, 3, 0, 550.0, 53.0)  # 10 not divisible by 3
    with pytest.raises(ConstellationError):
        walker_delta(9, 3, 3, 550.0, 53.0)  # f out of range
    with pytest.raises(ConstellationError):
        walker_delta(0, 1, 0, 550.0, 53.0)
