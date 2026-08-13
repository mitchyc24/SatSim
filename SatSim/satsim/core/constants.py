"""Physical and astrodynamic constants used throughout SatSim.

All internal computations use kilometres, seconds, and radians unless a
name explicitly says otherwise (``_deg``, ``_m`` ...).
"""

# Earth gravitational parameter (WGS-84), km^3 / s^2
MU_EARTH_KM3_S2 = 398600.4418

# Earth equatorial radius (WGS-84), km
R_EARTH_EQ_KM = 6378.137

# Earth polar flattening (WGS-84)
EARTH_FLATTENING = 1.0 / 298.257223563

# Second zonal harmonic of Earth's gravity field (oblateness)
J2_EARTH = 1.08262668e-3

# Mean sidereal rotation rate of Earth, rad/s
EARTH_ROTATION_RATE_RAD_S = 7.2921158553e-5

SECONDS_PER_DAY = 86400.0
