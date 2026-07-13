"""!
@file propagate.py
@brief SGP4 orbit propagation plus TEME->ECEF and geodetic transforms.
@details
    Turns orbital element sets into Earth-Centred-Earth-Fixed (ECEF) positions so
    that satellites and the (fixed) coastline share one coordinate frame. All heavy
    lifting is delegated to the reference SGP4 implementation in the `sgp4` package.

    Frame notes:
      - SGP4 returns position in the TEME frame (km).
      - Rotating TEME about the polar axis by GMST yields an Earth-fixed frame.
        Polar motion and the small TEME/TOD offset are ignored: negligible for a
        visualisation, and it keeps the transform allocation-free and cheap.

    This module is imported, not executed directly.
"""

import math
import numpy as np
from sgp4.api import Satrec, jday

# Earth mean equatorial radius (km); used to place coastline dots on a sphere.
EARTH_RADIUS_KM = 6378.137

# Two-pi, cached to avoid recomputing inside per-object loops.
_TAU = 2.0 * math.pi


def julian(dt):
    """! @brief Split a UTC datetime into the (jd, fr) pair SGP4 expects.
        @param dt Timezone-naive UTC datetime.
        @return Tuple (julian_day, fractional_day).
    """
    return jday(dt.year, dt.month, dt.day, dt.hour, dt.minute,
                dt.second + dt.microsecond * 1e-6)


def gmst_rad(jd, fr):
    """! @brief Greenwich Mean Sidereal Time for a Julian date (IAU 1982 model).
        @param jd Integer-ish Julian day.
        @param fr Fractional day.
        @return GMST in radians, wrapped to [0, 2*pi).
    """
    t = (jd + fr - 2451545.0) / 36525.0
    # Polynomial gives sidereal time in seconds; 240 seconds == 1 degree.
    sec = (67310.54841
           + (876600.0 * 3600.0 + 8640184.812866) * t
           + 0.093104 * t * t
           - 6.2e-6 * t * t * t)
    deg = (sec / 240.0) % 360.0
    return math.radians(deg)


def teme_to_ecef(r_teme, gmst):
    """! @brief Rotate a TEME position into an Earth-fixed frame.
        @param r_teme Length-3 position vector in TEME (km).
        @param gmst Greenwich Mean Sidereal Time (radians).
        @return numpy array [x, y, z] in ECEF (km).
    """
    c, s = math.cos(gmst), math.sin(gmst)
    x, y, z = r_teme
    # Earth-fixed = R3(gmst) . r_teme
    return np.array((c * x + s * y,
                     -s * x + c * y,
                     z), dtype=np.float64)


def propagate_ecef(satrec, dt):
    """! @brief Propagate one satellite to a UTC instant and return ECEF position.
        @param satrec An sgp4 Satrec object.
        @param dt Timezone-naive UTC datetime.
        @return numpy [x, y, z] in km, or None if SGP4 reports an error.
    """
    jd, fr = julian(dt)
    err, r_teme, _v = satrec.sgp4(jd, fr)
    if err != 0:                      # Non-zero => propagation failure; skip cleanly.
        return None
    return teme_to_ecef(r_teme, gmst_rad(jd, fr))


def geodetic_to_ecef_unit(lon_deg, lat_deg):
    """! @brief Convert a lon/lat pair to a unit vector on a sphere.
        @param lon_deg Longitude in degrees.
        @param lat_deg Latitude in degrees.
        @return numpy unit vector [x, y, z] (Earth-fixed, radius 1).
    """
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    cl = math.cos(lat)
    return np.array((cl * math.cos(lon),
                     cl * math.sin(lon),
                     math.sin(lat)), dtype=np.float64)


def altitude_km(ecef_km):
    """! @brief Height above the mean Earth radius for an ECEF position.
        @param ecef_km Length-3 ECEF vector (km).
        @return Altitude in km (may be negative for decayed/invalid states).
    """
    return float(np.linalg.norm(ecef_km)) - EARTH_RADIUS_KM
