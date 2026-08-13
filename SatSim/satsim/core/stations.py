"""Ground station geometry: topocentric look angles from a site to a
satellite (azimuth, elevation, slant range).

This module is pure computation -- persistence lives in
:mod:`satsim.models`, which converts stored rows into
:class:`StationGeometry` instances before analysis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .frames import geodetic_to_ecef_km


class StationError(ValueError):
    """Raised when ground-station parameters are invalid."""


@dataclass
class StationGeometry:
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0
    min_elevation_deg: float = 5.0

    _ecef_km: np.ndarray = field(default=None, repr=False, compare=False)

    def validate(self) -> "StationGeometry":
        if not (-90.0 <= self.latitude_deg <= 90.0):
            raise StationError("Latitude must be in [-90, 90] deg")
        if not (-180.0 <= self.longitude_deg <= 180.0):
            raise StationError("Longitude must be in [-180, 180] deg")
        if not (0.0 <= self.min_elevation_deg < 90.0):
            raise StationError("Minimum elevation must be in [0, 90) deg")
        return self

    @property
    def ecef_km(self) -> np.ndarray:
        """Station position in ECEF (km), computed lazily and cached."""
        if self._ecef_km is None:
            self._ecef_km = geodetic_to_ecef_km(
                self.latitude_deg, self.longitude_deg, self.altitude_m
            )
        return self._ecef_km

    @property
    def enu_basis(self) -> np.ndarray:
        """Rows are the East, North, Up unit vectors in ECEF."""
        lat = math.radians(self.latitude_deg)
        lon = math.radians(self.longitude_deg)
        sin_lat, cos_lat = math.sin(lat), math.cos(lat)
        sin_lon, cos_lon = math.sin(lon), math.cos(lon)
        return np.array([
            [-sin_lon, cos_lon, 0.0],
            [-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat],
            [cos_lat * cos_lon, cos_lat * sin_lon, sin_lat],
        ])

    def look_angles(self, r_ecef_km: np.ndarray):
        """Topocentric look angles from the station to each position.

        Parameters
        ----------
        r_ecef_km : ndarray, shape (N, 3)
            Satellite positions in ECEF.

        Returns
        -------
        (azimuth_deg, elevation_deg, slant_range_km) : 1-D arrays
            Azimuth measured clockwise from North, in [0, 360).
        """
        r = np.atleast_2d(np.asarray(r_ecef_km, dtype=float))
        rho = r - self.ecef_km
        enu = rho @ self.enu_basis.T
        slant_range = np.linalg.norm(enu, axis=1)
        elevation = np.degrees(np.arcsin(
            np.clip(enu[:, 2] / slant_range, -1.0, 1.0)
        ))
        azimuth = np.degrees(np.arctan2(enu[:, 0], enu[:, 1])) % 360.0
        return azimuth, elevation, slant_range
