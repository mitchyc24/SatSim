"""Numerical orbit propagation.

Integrates the two-body equations of motion, optionally perturbed by the
Earth's J2 zonal harmonic (oblateness), with SciPy's adaptive
Runge-Kutta 4(5) integrator (:func:`scipy.integrate.solve_ivp`).

Positions/velocities are in an Earth-centred inertial frame (treated as
GCRS for downstream frame transformations), in km and km/s.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from scipy.integrate import solve_ivp

from .constants import J2_EARTH, MU_EARTH_KM3_S2, R_EARTH_EQ_KM
from .elements import ClassicalElements


class PropagationError(RuntimeError):
    """Raised when the numerical integrator fails."""


@dataclass
class Ephemeris:
    """Propagated trajectory sampled on a fixed time grid.

    ``times_s`` are offsets in seconds from ``epoch``; ``states_eci_km``
    has shape ``(N, 6)`` holding ``[x, y, z, vx, vy, vz]`` per row.
    """

    epoch: datetime
    times_s: np.ndarray
    states_eci_km: np.ndarray
    name: str = field(default="")

    @property
    def positions_km(self) -> np.ndarray:
        return self.states_eci_km[:, :3]

    @property
    def velocities_km_s(self) -> np.ndarray:
        return self.states_eci_km[:, 3:]


def acceleration_km_s2(
    r_km: np.ndarray,
    mu_km3_s2: float = MU_EARTH_KM3_S2,
    include_j2: bool = True,
    j2: float = J2_EARTH,
    r_eq_km: float = R_EARTH_EQ_KM,
) -> np.ndarray:
    """Point-mass gravity plus (optionally) the J2 perturbation."""
    x, y, z = r_km
    r2 = x * x + y * y + z * z
    r = np.sqrt(r2)
    a = -mu_km3_s2 / (r2 * r) * r_km

    if include_j2:
        factor = 1.5 * j2 * mu_km3_s2 * r_eq_km ** 2 / (r2 * r2 * r)
        zsq = 5.0 * z * z / r2
        a = a + factor * np.array([
            x * (zsq - 1.0),
            y * (zsq - 1.0),
            z * (zsq - 3.0),
        ])
    return a


def propagate_state(
    r0_km,
    v0_km_s,
    epoch: datetime,
    times_s,
    include_j2: bool = True,
    mu_km3_s2: float = MU_EARTH_KM3_S2,
    name: str = "",
    rtol: float = 1e-9,
    atol: float = 1e-9,
) -> Ephemeris:
    """Propagate an initial ECI state vector over the given time grid.

    ``times_s`` must be a monotonically increasing 1-D sequence of
    offsets (seconds) from ``epoch``; the first entry may be 0.
    """
    times = np.asarray(times_s, dtype=float)
    if times.ndim != 1 or times.size == 0:
        raise ValueError("times_s must be a non-empty 1-D sequence")
    if times.size > 1 and np.any(np.diff(times) <= 0.0):
        raise ValueError("times_s must be strictly increasing")

    y0 = np.concatenate([np.asarray(r0_km, dtype=float),
                         np.asarray(v0_km_s, dtype=float)])
    if y0.shape != (6,):
        raise ValueError("r0_km and v0_km_s must each have three components")

    if times.size == 1 and times[0] == 0.0:
        return Ephemeris(epoch=epoch, times_s=times,
                         states_eci_km=y0.reshape(1, 6), name=name)

    def rhs(_t, y):
        return np.concatenate([
            y[3:],
            acceleration_km_s2(y[:3], mu_km3_s2=mu_km3_s2, include_j2=include_j2),
        ])

    solution = solve_ivp(
        rhs,
        t_span=(times[0], times[-1]),
        y0=y0,
        method="RK45",
        t_eval=times,
        rtol=rtol,
        atol=atol,
    )
    if not solution.success:
        raise PropagationError("Orbit integration failed: %s" % solution.message)

    return Ephemeris(epoch=epoch, times_s=times,
                     states_eci_km=solution.y.T.copy(), name=name)


def propagate_elements(
    elements: ClassicalElements,
    epoch: datetime,
    times_s,
    include_j2: bool = True,
    mu_km3_s2: float = MU_EARTH_KM3_S2,
    name: str = "",
) -> Ephemeris:
    """Propagate a classical element set (defined at ``epoch``)."""
    elements.validate()
    r0, v0 = elements.to_state_vector(mu_km3_s2)
    return propagate_state(
        r0, v0, epoch, times_s,
        include_j2=include_j2, mu_km3_s2=mu_km3_s2, name=name,
    )
