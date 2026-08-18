"""Classical (Keplerian) orbital elements and conversions to/from
Cartesian state vectors.

The element set follows the classical convention:

* ``semi_major_axis_km`` -- a
* ``eccentricity``       -- e   (0 <= e < 1, closed orbits only)
* ``inclination_deg``    -- i
* ``raan_deg``           -- Omega, right ascension of the ascending node
* ``arg_perigee_deg``    -- omega, argument of perigee
* ``true_anomaly_deg``   -- nu, true anomaly at epoch

State vectors are expressed in an Earth-centred inertial (ECI) frame in
kilometres and kilometres per second.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np

from .constants import MU_EARTH_KM3_S2, R_EARTH_EQ_KM

# Below this eccentricity / inclination the orbit is treated as
# circular / equatorial when recovering elements from a state vector.
_SMALL = 1e-10

# Reject orbits whose perigee dips below this altitude (km) -- a
# constellation-viability tool has no use for orbits that re-enter.
MIN_PERIGEE_ALTITUDE_KM = 100.0

MAX_ECCENTRICITY = 0.95


class ElementError(ValueError):
    """Raised when an orbital element set is physically invalid."""


@dataclass
class ClassicalElements:
    semi_major_axis_km: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float
    arg_perigee_deg: float
    true_anomaly_deg: float

    # ------------------------------------------------------------------
    # Validation and derived quantities
    # ------------------------------------------------------------------
    def validate(self) -> "ClassicalElements":
        """Raise :class:`ElementError` if the element set is unusable."""
        if not (0.0 <= self.eccentricity <= MAX_ECCENTRICITY):
            raise ElementError(
                "Eccentricity must be in [0, %.2f], got %r"
                % (MAX_ECCENTRICITY, self.eccentricity)
            )
        if self.semi_major_axis_km <= 0.0:
            raise ElementError(
                "Semi-major axis must be positive, got %r" % self.semi_major_axis_km
            )
        if not (0.0 <= self.inclination_deg <= 180.0):
            raise ElementError(
                "Inclination must be in [0, 180] deg, got %r" % self.inclination_deg
            )
        if self.perigee_altitude_km < MIN_PERIGEE_ALTITUDE_KM:
            raise ElementError(
                "Perigee altitude %.1f km is below the %.0f km minimum"
                % (self.perigee_altitude_km, MIN_PERIGEE_ALTITUDE_KM)
            )
        return self

    @property
    def semi_latus_rectum_km(self) -> float:
        return self.semi_major_axis_km * (1.0 - self.eccentricity ** 2)

    @property
    def perigee_altitude_km(self) -> float:
        return self.semi_major_axis_km * (1.0 - self.eccentricity) - R_EARTH_EQ_KM

    @property
    def apogee_altitude_km(self) -> float:
        return self.semi_major_axis_km * (1.0 + self.eccentricity) - R_EARTH_EQ_KM

    def mean_motion_rad_s(self, mu_km3_s2: float = MU_EARTH_KM3_S2) -> float:
        return math.sqrt(mu_km3_s2 / self.semi_major_axis_km ** 3)

    def period_s(self, mu_km3_s2: float = MU_EARTH_KM3_S2) -> float:
        return 2.0 * math.pi / self.mean_motion_rad_s(mu_km3_s2)

    @property
    def mean_anomaly_deg(self) -> float:
        """Mean anomaly at epoch, in degrees."""
        return true_to_mean_anomaly_deg(self.true_anomaly_deg, self.eccentricity)

    def to_dict(self) -> dict:
        return asdict(self)

    # ------------------------------------------------------------------
    # Element <-> state-vector conversions
    # ------------------------------------------------------------------
    def to_state_vector(self, mu_km3_s2: float = MU_EARTH_KM3_S2):
        """Return ``(r_km, v_km_s)`` ECI vectors as length-3 numpy arrays."""
        p = self.semi_latus_rectum_km
        e = self.eccentricity
        nu = math.radians(self.true_anomaly_deg)

        r_mag = p / (1.0 + e * math.cos(nu))
        # Perifocal (PQW) frame
        r_pf = np.array([r_mag * math.cos(nu), r_mag * math.sin(nu), 0.0])
        v_scale = math.sqrt(mu_km3_s2 / p)
        v_pf = np.array([-v_scale * math.sin(nu), v_scale * (e + math.cos(nu)), 0.0])

        rot = _perifocal_to_eci_matrix(
            math.radians(self.raan_deg),
            math.radians(self.inclination_deg),
            math.radians(self.arg_perigee_deg),
        )
        return rot @ r_pf, rot @ v_pf

    def sample_orbit_km(self, num_points: int = 72,
                        mu_km3_s2: float = MU_EARTH_KM3_S2) -> np.ndarray:
        """One full revolution of ECI positions, shape ``(num_points, 3)``.

        Samples are spaced uniformly in **mean** anomaly, i.e. uniformly
        in time, starting from perigee.  Stepping through the returned
        array at a constant rate therefore traces the orbit at the right
        speed -- slow at apogee, fast at perigee -- which sampling in
        true anomaly would not.  The orbit is the two-body ellipse: no
        J2, so a sampled ring is a closed loop.  For an accurate
        trajectory over time use :func:`satsim.core.propagator.propagate_elements`.
        """
        if num_points < 3:
            raise ElementError("num_points must be at least 3")
        positions = np.empty((num_points, 3), dtype=float)
        for index in range(num_points):
            mean_anomaly = 360.0 * index / num_points
            sample = ClassicalElements(
                semi_major_axis_km=self.semi_major_axis_km,
                eccentricity=self.eccentricity,
                inclination_deg=self.inclination_deg,
                raan_deg=self.raan_deg,
                arg_perigee_deg=self.arg_perigee_deg,
                true_anomaly_deg=mean_to_true_anomaly_deg(
                    mean_anomaly, self.eccentricity
                ),
            )
            positions[index] = sample.to_state_vector(mu_km3_s2)[0]
        return positions

    @classmethod
    def from_state_vector(
        cls, r_km, v_km_s, mu_km3_s2: float = MU_EARTH_KM3_S2
    ) -> "ClassicalElements":
        """Recover classical elements from an ECI state vector.

        Degenerate geometries use the usual conventions: circular orbits
        take ``arg_perigee = 0`` with the anomaly measured from the node,
        and equatorial orbits take ``raan = 0`` with the node direction
        replaced by the inertial x-axis.
        """
        r = np.asarray(r_km, dtype=float)
        v = np.asarray(v_km_s, dtype=float)
        r_mag = float(np.linalg.norm(r))
        v_mag = float(np.linalg.norm(v))

        h = np.cross(r, v)
        h_mag = float(np.linalg.norm(h))
        if h_mag < _SMALL:
            raise ElementError("Degenerate (rectilinear) trajectory")
        h_hat = h / h_mag

        energy = 0.5 * v_mag ** 2 - mu_km3_s2 / r_mag
        if energy >= 0.0:
            raise ElementError("State vector describes an open (e >= 1) orbit")
        a = -mu_km3_s2 / (2.0 * energy)

        e_vec = (np.cross(v, h) / mu_km3_s2) - r / r_mag
        e = float(np.linalg.norm(e_vec))

        inc = math.acos(max(-1.0, min(1.0, h_hat[2])))

        # Node vector (points to the ascending node)
        n = np.cross([0.0, 0.0, 1.0], h)
        n_mag = float(np.linalg.norm(n))
        if n_mag < _SMALL:  # equatorial: use inertial x-axis as reference
            n_hat = np.array([1.0, 0.0, 0.0])
            raan = 0.0
        else:
            n_hat = n / n_mag
            raan = math.atan2(n_hat[1], n_hat[0])

        r_hat = r / r_mag
        if e < _SMALL:
            # Circular: anomaly measured from the node, perigee undefined.
            argp = 0.0
            nu = math.atan2(float(np.dot(np.cross(n_hat, r_hat), h_hat)),
                            float(np.dot(n_hat, r_hat)))
        else:
            e_hat = e_vec / e
            argp = math.atan2(float(np.dot(np.cross(n_hat, e_hat), h_hat)),
                              float(np.dot(n_hat, e_hat)))
            nu = math.atan2(float(np.dot(np.cross(e_hat, r_hat), h_hat)),
                            float(np.dot(e_hat, r_hat)))

        return cls(
            semi_major_axis_km=a,
            eccentricity=e,
            inclination_deg=math.degrees(inc),
            raan_deg=math.degrees(raan) % 360.0,
            arg_perigee_deg=math.degrees(argp) % 360.0,
            true_anomaly_deg=math.degrees(nu) % 360.0,
        )


# ----------------------------------------------------------------------
# Anomaly conversions
# ----------------------------------------------------------------------
def solve_kepler(mean_anomaly_rad: float, eccentricity: float,
                 tol: float = 1e-12, max_iter: int = 60) -> float:
    """Solve Kepler's equation ``M = E - e sin(E)`` for the eccentric
    anomaly ``E`` (radians) using Newton-Raphson iteration."""
    m = math.fmod(mean_anomaly_rad, 2.0 * math.pi)
    e = eccentricity
    # Standard starter: E ~= M for small e, pi otherwise.
    big_e = m if e < 0.8 else math.pi
    for _ in range(max_iter):
        f = big_e - e * math.sin(big_e) - m
        f_prime = 1.0 - e * math.cos(big_e)
        delta = f / f_prime
        big_e -= delta
        if abs(delta) < tol:
            return big_e
    raise RuntimeError("Kepler solver failed to converge (M=%r, e=%r)" % (m, e))


def mean_to_true_anomaly_deg(mean_anomaly_deg: float, eccentricity: float) -> float:
    """Convert mean anomaly to true anomaly (both in degrees)."""
    big_e = solve_kepler(math.radians(mean_anomaly_deg), eccentricity)
    nu = 2.0 * math.atan2(
        math.sqrt(1.0 + eccentricity) * math.sin(big_e / 2.0),
        math.sqrt(1.0 - eccentricity) * math.cos(big_e / 2.0),
    )
    return math.degrees(nu) % 360.0


def true_to_mean_anomaly_deg(true_anomaly_deg: float, eccentricity: float) -> float:
    """Convert true anomaly to mean anomaly (both in degrees)."""
    nu = math.radians(true_anomaly_deg)
    e = eccentricity
    big_e = 2.0 * math.atan2(
        math.sqrt(1.0 - e) * math.sin(nu / 2.0),
        math.sqrt(1.0 + e) * math.cos(nu / 2.0),
    )
    m = big_e - e * math.sin(big_e)
    return math.degrees(m) % 360.0


def _perifocal_to_eci_matrix(raan: float, inc: float, argp: float) -> np.ndarray:
    """Rotation matrix from the perifocal (PQW) frame to ECI:
    ``R3(-raan) @ R1(-inc) @ R3(-argp)``."""
    co, so = math.cos(raan), math.sin(raan)
    ci, si = math.cos(inc), math.sin(inc)
    cw, sw = math.cos(argp), math.sin(argp)
    return np.array([
        [co * cw - so * sw * ci, -co * sw - so * cw * ci, so * si],
        [so * cw + co * sw * ci, -so * sw + co * cw * ci, -co * si],
        [sw * si, cw * si, ci],
    ])
