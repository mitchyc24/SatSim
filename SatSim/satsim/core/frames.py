"""Coordinate frame transformations built on astropy.

* ECI (GCRS) <-> ECEF (ITRS) rotation for satellite positions
* ECEF <-> WGS-84 geodetic coordinates (ground tracks, station siting)

astropy is configured to never download IERS Earth-orientation data at
runtime, so SatSim works fully offline.  The bundled IERS tables give
sub-arcsecond rotation accuracy, which is far below the geometric error
budget of a viability study.
"""

from __future__ import annotations

import warnings
from datetime import datetime

import numpy as np
from astropy import units as u
from astropy.coordinates import GCRS, ITRS, CartesianRepresentation, EarthLocation
from astropy.time import Time
from astropy.utils import iers
from astropy.utils.exceptions import AstropyWarning

# Work offline: use the IERS tables bundled with astropy instead of
# fetching finals2000A.all from the network on first use.
iers.conf.auto_download = False
try:  # not present in every supported astropy version
    iers.conf.iers_degraded_accuracy = "ignore"
except Exception:  # pragma: no cover
    pass


def time_grid(epoch: datetime, times_s: np.ndarray) -> Time:
    """Build an astropy UTC time array for offsets (s) from ``epoch``."""
    return Time(epoch, scale="utc") + np.asarray(times_s, dtype=float) * u.s


def eci_to_ecef_km(r_eci_km: np.ndarray, times: Time) -> np.ndarray:
    """Rotate ECI (GCRS) positions into ECEF (ITRS).

    Parameters
    ----------
    r_eci_km : ndarray, shape (N, 3)
    times : astropy.time.Time, length N (or scalar for N == 1)
    """
    r = np.atleast_2d(np.asarray(r_eci_km, dtype=float))
    rep = CartesianRepresentation(r[:, 0] * u.km, r[:, 1] * u.km, r[:, 2] * u.km)
    with warnings.catch_warnings():
        # Bundled IERS tables trigger extrapolation warnings for recent
        # dates; accuracy loss is negligible for this application.
        warnings.simplefilter("ignore", AstropyWarning)
        gcrs = GCRS(rep, obstime=times)
        itrs = gcrs.transform_to(ITRS(obstime=times))
    return itrs.cartesian.xyz.to_value(u.km).T.reshape(-1, 3)


def ecef_to_geodetic(r_ecef_km: np.ndarray):
    """Convert ECEF positions to WGS-84 geodetic coordinates.

    Returns ``(lat_deg, lon_deg, height_km)`` arrays, longitude wrapped
    to (-180, 180].
    """
    r = np.atleast_2d(np.asarray(r_ecef_km, dtype=float))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AstropyWarning)
        loc = EarthLocation.from_geocentric(
            r[:, 0] * u.km, r[:, 1] * u.km, r[:, 2] * u.km
        )
        geodetic = loc.geodetic
    lat = np.atleast_1d(geodetic.lat.to_value(u.deg))
    lon = np.atleast_1d(geodetic.lon.to_value(u.deg))
    lon = ((lon + 180.0) % 360.0) - 180.0
    height = np.atleast_1d(geodetic.height.to_value(u.km))
    return lat, lon, height


def geodetic_to_ecef_km(latitude_deg: float, longitude_deg: float,
                        altitude_m: float) -> np.ndarray:
    """WGS-84 geodetic coordinates to an ECEF position vector (km)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AstropyWarning)
        loc = EarthLocation.from_geodetic(
            lon=longitude_deg * u.deg,
            lat=latitude_deg * u.deg,
            height=altitude_m * u.m,
        )
        return np.array([
            loc.x.to_value(u.km),
            loc.y.to_value(u.km),
            loc.z.to_value(u.km),
        ])
