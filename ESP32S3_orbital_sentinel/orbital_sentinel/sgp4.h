/**
 * @file sgp4.h
 * @brief SGP4 orbit propagation plus TEME->ECEF and geodetic transforms.
 * @details
 *     A C++ port of the maths in orca_orbital_sentinel/propagate.py, which in turn
 *     delegates to the reference `sgp4` Python package. This is the standard
 *     Vallado SGP4 (WGS72), restricted to the **near-Earth** branch.
 *
 *     Restricting to near-Earth is a deliberate, safe simplification: the deep-space
 *     (SDP4) branch only applies to objects with an orbital period >= 225 minutes,
 *     and everything this firmware tracks - the ISS (~93 min) and the CSS (~92 min) -
 *     is comfortably below that. sgp4Init() reports an error for a deep-space element
 *     set rather than silently returning garbage.
 *
 *     Frame notes (identical to the desktop):
 *       - SGP4 returns position in the TEME frame (km).
 *       - Rotating TEME about the polar axis by GMST yields an Earth-fixed frame.
 *         Polar motion and the small TEME/TOD offset are ignored: negligible for a
 *         visualisation, and it keeps the transform cheap.
 *
 *     Doubles, not floats. The ESP32-S3 has no double-precision FPU, so this costs
 *     some cycles - but SGP4's Kepler solve and the GMST polynomial genuinely need
 *     the mantissa, and we only propagate two objects per frame.
 *
 *     No Arduino headers: also compiled by the host preview harness.
 */

#ifndef ORBITAL_SENTINEL_SGP4_H
#define ORBITAL_SENTINEL_SGP4_H

#include <stdint.h>

/// Earth mean equatorial radius (km); used to place coastline dots on a sphere.
extern const double EARTH_RADIUS_KM;

/// A propagator initialised from one two-line element set.
struct Satrec {
  int satnum;          //!< NORAD catalog id.
  int error;           //!< 0 = healthy; non-zero = last sgp4() failure code.
  double jdsatepoch;   //!< Julian date of the element-set epoch.

  // Mean elements at epoch (radians / radians-per-minute).
  double bstar, inclo, nodeo, ecco, argpo, mo, no_kozai, no_unkozai;

  // Precomputed SGP4 secular/periodic coefficients (see sgp4Init).
  double cc1, cc4, cc5, d2, d3, d4;
  double delmo, eta, argpdot, omgcof, sinmao, t2cof, t3cof, t4cof, t5cof;
  double x1mth2, x7thm1, mdot, nodedot, xlcof, xmcof, nodecf;
  double con41, aycof;
  int isimp;           //!< 1 = simplified drag model (very low perigee).
};

/**
 * @brief Parse the two data lines of a TLE into an initialised propagator.
 * @param line1 TLE line 1 (>= 69 chars, starts "1 ").
 * @param line2 TLE line 2 (>= 69 chars, starts "2 ").
 * @param sat   Output propagator.
 * @return true on success; false if the lines are malformed or the element set is
 *         deep-space (period >= 225 min), which this build does not support.
 */
bool twoline2rv(const char *line1, const char *line2, Satrec &sat);

/**
 * @brief Propagate to a time offset from the element-set epoch.
 * @param sat    Initialised propagator.
 * @param tsince Minutes since epoch (may be negative).
 * @param r      Output position in TEME (km).
 * @return true on success; false if SGP4 reports decay or divergence.
 */
bool sgp4(Satrec &sat, double tsince, double r[3]);

/**
 * @brief Julian date from a UTC calendar instant.
 * @return Julian date (days).
 */
double julianDate(int year, int month, int day, int hour, int minute, double sec);

/**
 * @brief Greenwich Mean Sidereal Time for a Julian date (IAU 1982 model).
 * @param jd Julian date.
 * @return GMST in radians, wrapped to [0, 2*pi).
 */
double gmstRad(double jd);

/**
 * @brief Rotate a TEME position into the Earth-fixed (ECEF) frame.
 * @param teme Position in TEME (km).
 * @param gmst Greenwich Mean Sidereal Time (radians).
 * @param ecef Output position in ECEF (km).
 */
void temeToEcef(const double teme[3], double gmst, double ecef[3]);

/**
 * @brief Propagate one satellite to a Julian date and return its ECEF position.
 * @param sat Initialised propagator.
 * @param jd  Target Julian date (UTC).
 * @param ecef Output ECEF position (km).
 * @return true on success.
 */
bool propagateEcef(Satrec &sat, double jd, double ecef[3]);

/**
 * @brief Convert a lon/lat pair to a unit vector on a sphere (Earth-fixed).
 */
void geodeticToEcefUnit(double lonDeg, double latDeg, double out[3]);

#endif  // ORBITAL_SENTINEL_SGP4_H
