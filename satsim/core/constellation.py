"""Constellation pattern generators.

Currently implements the Walker delta pattern (notation ``i: t/p/f``),
which covers most LEO communication / Earth-observation constellation
designs.  Additional patterns (streets-of-coverage, flower, hybrid
shells) can be added here without touching the rest of the application.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import R_EARTH_EQ_KM
from .elements import ClassicalElements, mean_to_true_anomaly_deg


class ConstellationError(ValueError):
    """Raised when constellation parameters are invalid."""


@dataclass
class ConstellationMember:
    name: str
    plane: int
    slot: int
    elements: ClassicalElements


def walker_delta(
    total_satellites: int,
    planes: int,
    relative_phasing: int,
    altitude_km: float,
    inclination_deg: float,
    eccentricity: float = 0.0,
    arg_perigee_deg: float = 0.0,
    raan_offset_deg: float = 0.0,
    name_prefix: str = "SAT",
    raan_spread_deg: float = 360.0,
) -> list:
    """Generate a Walker delta constellation ``i: t/p/f``.

    Parameters
    ----------
    total_satellites : int
        Total number of satellites ``t`` (must divide evenly by ``p``).
    planes : int
        Number of equally spaced orbital planes ``p``.
    relative_phasing : int
        Walker phasing factor ``f`` in ``[0, p-1]``: satellites in
        adjacent planes are offset by ``f * 360 / t`` degrees of mean
        anomaly.
    altitude_km : float
        Circular-orbit reference altitude; the semi-major axis is
        ``R_earth + altitude_km``.
    inclination_deg : float
        Inclination shared by every plane.
    raan_offset_deg : float
        RAAN of the first plane (rotates the whole pattern).
    raan_spread_deg : float
        Node spread of the pattern: 360 for a delta pattern (default),
        180 for a Walker star (polar) pattern.

    Returns
    -------
    list of :class:`ConstellationMember`
    """
    if total_satellites < 1:
        raise ConstellationError("total_satellites must be >= 1")
    if planes < 1:
        raise ConstellationError("planes must be >= 1")
    if total_satellites % planes != 0:
        raise ConstellationError(
            "total_satellites (%d) must be divisible by planes (%d)"
            % (total_satellites, planes)
        )
    if not (0 <= relative_phasing < planes):
        raise ConstellationError(
            "relative_phasing must be in [0, planes-1], got %d" % relative_phasing
        )

    sats_per_plane = total_satellites // planes
    plane_spacing_deg = raan_spread_deg / planes
    slot_spacing_deg = 360.0 / sats_per_plane
    phase_step_deg = relative_phasing * 360.0 / total_satellites

    members = []
    for plane in range(planes):
        raan = (raan_offset_deg + plane * plane_spacing_deg) % 360.0
        for slot in range(sats_per_plane):
            mean_anomaly = (slot * slot_spacing_deg + plane * phase_step_deg) % 360.0
            elements = ClassicalElements(
                semi_major_axis_km=R_EARTH_EQ_KM + altitude_km,
                eccentricity=eccentricity,
                inclination_deg=inclination_deg,
                raan_deg=raan,
                arg_perigee_deg=arg_perigee_deg,
                true_anomaly_deg=mean_to_true_anomaly_deg(mean_anomaly, eccentricity),
            ).validate()
            members.append(ConstellationMember(
                name="%s-%d%02d" % (name_prefix, plane + 1, slot + 1),
                plane=plane + 1,
                slot=slot + 1,
                elements=elements,
            ))
    return members
