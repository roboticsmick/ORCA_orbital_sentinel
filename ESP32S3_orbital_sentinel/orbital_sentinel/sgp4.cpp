/**
 * @file sgp4.cpp
 * @brief Near-Earth SGP4 (WGS72) and the TEME->ECEF chain. See sgp4.h.
 */

#include "sgp4.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

const double EARTH_RADIUS_KM = 6378.137;

namespace {

const double PI = 3.14159265358979323846;
const double TAU = 2.0 * PI;
const double DEG2RAD = PI / 180.0;
const double X2O3 = 2.0 / 3.0;

// --- WGS72 gravity model ----------------------------------------------------
// SGP4 is defined against WGS72, not WGS84: TLEs are fitted with these constants,
// so using "better" ones would make the fit worse, not better.
const double MU = 398600.8;             // km^3 / s^2
const double RADIUS_EARTH_KM = 6378.135;
const double XKE = 60.0 / sqrt(RADIUS_EARTH_KM * RADIUS_EARTH_KM * RADIUS_EARTH_KM / MU);
const double J2 = 0.001082616;
const double J3 = -0.00000253881;
const double J4 = -0.00000165597;
const double J3OJ2 = J3 / J2;

/// Deep-space (SDP4) threshold: an orbital period of 225 minutes.
const double DEEP_SPACE_PERIOD_MIN = 225.0;

/// Parse a fixed-width field into a double. Returns 0.0 for an all-blank field.
double field(const char *line, int start, int len) {
  char buf[32];
  if (len >= (int)sizeof(buf)) {
    len = (int)sizeof(buf) - 1;
  }
  memcpy(buf, line + start, (size_t)len);
  buf[len] = '\0';
  return atof(buf);
}

/**
 * @brief Parse a TLE "implied decimal point, implied exponent" field.
 * @details Fields such as bstar are packed as e.g. " 86456-4", meaning
 *          0.86456e-4, with the leading decimal point and the 'e' both omitted.
 */
double impliedDecimal(const char *line, int start, int len) {
  char buf[32];
  if (len >= (int)sizeof(buf)) {
    len = (int)sizeof(buf) - 1;
  }
  memcpy(buf, line + start, (size_t)len);
  buf[len] = '\0';

  // Split the packed field into mantissa digits and a trailing signed exponent.
  char mant[32];
  int mi = 0;
  int expo = 0;
  int sign = 1;
  int i = 0;

  while (buf[i] == ' ') {
    i++;
  }
  if (buf[i] == '-') {
    sign = -1;
    i++;
  } else if (buf[i] == '+') {
    i++;
  }
  for (; buf[i] != '\0'; i++) {
    if (buf[i] >= '0' && buf[i] <= '9') {
      if (mi < (int)sizeof(mant) - 1) {
        mant[mi++] = buf[i];
      }
    } else if (buf[i] == '-' || buf[i] == '+') {
      expo = atoi(buf + i);   // atoi consumes the sign and the exponent digits.
      break;
    }
  }
  mant[mi] = '\0';
  if (mi == 0) {
    return 0.0;
  }
  return sign * atof(mant) * pow(10.0, (double)(expo - mi));
}

}  // namespace

double julianDate(int year, int month, int day, int hour, int minute, double sec) {
  return 367.0 * year
       - floor(7.0 * (year + floor((month + 9.0) / 12.0)) * 0.25)
       + floor(275.0 * month / 9.0)
       + day + 1721013.5
       + ((sec / 60.0 + minute) / 60.0 + hour) / 24.0;
}

double gmstRad(double jd) {
  double t = (jd - 2451545.0) / 36525.0;
  // Polynomial yields sidereal time in seconds; 240 seconds == 1 degree.
  double secs = 67310.54841
              + (876600.0 * 3600.0 + 8640184.812866) * t
              + 0.093104 * t * t
              - 6.2e-6 * t * t * t;
  double deg = fmod(secs / 240.0, 360.0);
  if (deg < 0.0) {
    deg += 360.0;
  }
  return deg * DEG2RAD;
}

void temeToEcef(const double teme[3], double gmst, double ecef[3]) {
  double c = cos(gmst);
  double s = sin(gmst);
  // Earth-fixed = R3(gmst) . r_teme
  ecef[0] = c * teme[0] + s * teme[1];
  ecef[1] = -s * teme[0] + c * teme[1];
  ecef[2] = teme[2];
}

void geodeticToEcefUnit(double lonDeg, double latDeg, double out[3]) {
  double lon = lonDeg * DEG2RAD;
  double lat = latDeg * DEG2RAD;
  double cl = cos(lat);
  out[0] = cl * cos(lon);
  out[1] = cl * sin(lon);
  out[2] = sin(lat);
}

bool twoline2rv(const char *line1, const char *line2, Satrec &sat) {
  if (line1 == nullptr || line2 == nullptr) {
    return false;
  }
  if (strlen(line1) < 69 || strlen(line2) < 69) {
    return false;
  }
  if (line1[0] != '1' || line2[0] != '2') {
    return false;
  }

  memset(&sat, 0, sizeof(sat));
  sat.satnum = (int)field(line1, 2, 5);

  int epochyr = (int)field(line1, 18, 2);
  double epochdays = field(line1, 20, 12);
  sat.bstar = impliedDecimal(line1, 53, 8);

  // TLE year is two-digit: 57..99 => 19xx, 00..56 => 20xx.
  int year = (epochyr < 57) ? epochyr + 2000 : epochyr + 1900;

  // epochdays is a day-of-year with a fraction, where Jan 1 00:00 == day 1.0.
  sat.jdsatepoch = julianDate(year, 1, 1, 0, 0, 0.0) + (epochdays - 1.0);

  sat.inclo = field(line2, 8, 8) * DEG2RAD;
  sat.nodeo = field(line2, 17, 8) * DEG2RAD;
  sat.ecco = field(line2, 26, 7) * 1.0e-7;   // Leading "0." is implied.
  sat.argpo = field(line2, 34, 8) * DEG2RAD;
  sat.mo = field(line2, 43, 8) * DEG2RAD;
  sat.no_kozai = field(line2, 52, 11) * TAU / 1440.0;  // rev/day -> rad/min.

  if (sat.no_kozai <= 0.0 || sat.ecco < 0.0 || sat.ecco >= 1.0) {
    return false;
  }

  // --- initl: recover the un-Kozai'd mean motion ----------------------------
  double eccsq = sat.ecco * sat.ecco;
  double omeosq = 1.0 - eccsq;
  double rteosq = sqrt(omeosq);
  double cosio = cos(sat.inclo);
  double cosio2 = cosio * cosio;

  double ak = pow(XKE / sat.no_kozai, X2O3);
  double d1 = 0.75 * J2 * (3.0 * cosio2 - 1.0) / (rteosq * omeosq);
  double del = d1 / (ak * ak);
  // Brouwer/Kozai series: a0 = a1 * (1 - d/3 - d^2 - 134/81 d^3). Getting the
  // d^2 coefficient wrong is invisible at epoch but drifts secularly.
  double adel = ak * (1.0 - del * del
                      - del * (1.0 / 3.0 + 134.0 * del * del / 81.0));
  del = d1 / (adel * adel);
  sat.no_unkozai = sat.no_kozai / (1.0 + del);

  // Deep-space element sets need SDP4, which this build omits on purpose.
  if (TAU / sat.no_unkozai >= DEEP_SPACE_PERIOD_MIN) {
    return false;
  }

  double ao = pow(XKE / sat.no_unkozai, X2O3);
  double sinio = sin(sat.inclo);
  double po = ao * omeosq;
  double con42 = 1.0 - 5.0 * cosio2;
  sat.con41 = -con42 - cosio2 - cosio2;
  double posq = po * po;
  double rp = ao * (1.0 - sat.ecco);

  // --- sgp4init: drag / gravity coefficients --------------------------------
  double ss = 78.0 / RADIUS_EARTH_KM + 1.0;
  double qzms2t = pow(((120.0 - 78.0) / RADIUS_EARTH_KM), 4.0);

  double sfour = ss;
  double qzms24 = qzms2t;
  double perige = (rp - 1.0) * RADIUS_EARTH_KM;

  // A very low perigee gets a modified atmospheric-drag boundary.
  if (perige < 156.0) {
    sfour = perige - 78.0;
    if (perige < 98.0) {
      sfour = 20.0;
    }
    qzms24 = pow(((120.0 - sfour) / RADIUS_EARTH_KM), 4.0);
    sfour = sfour / RADIUS_EARTH_KM + 1.0;
  }

  double pinvsq = 1.0 / posq;
  double tsi = 1.0 / (ao - sfour);
  sat.eta = ao * sat.ecco * tsi;
  double etasq = sat.eta * sat.eta;
  double eeta = sat.ecco * sat.eta;
  double psisq = fabs(1.0 - etasq);
  double coef = qzms24 * pow(tsi, 4.0);
  double coef1 = coef / pow(psisq, 3.5);

  double cc2 = coef1 * sat.no_unkozai
             * (ao * (1.0 + 1.5 * etasq + eeta * (4.0 + etasq))
                + 0.375 * J2 * tsi / psisq * sat.con41
                  * (8.0 + 3.0 * etasq * (8.0 + etasq)));
  sat.cc1 = sat.bstar * cc2;

  double cc3 = 0.0;
  if (sat.ecco > 1.0e-4) {
    cc3 = -2.0 * coef * tsi * J3OJ2 * sat.no_unkozai * sinio / sat.ecco;
  }
  sat.x1mth2 = 1.0 - cosio2;
  sat.cc4 = 2.0 * sat.no_unkozai * coef1 * ao * omeosq
          * (sat.eta * (2.0 + 0.5 * etasq)
             + sat.ecco * (0.5 + 2.0 * etasq)
             - J2 * tsi / (ao * psisq)
               * (-3.0 * sat.con41
                    * (1.0 - 2.0 * eeta + etasq * (1.5 - 0.5 * eeta))
                  + 0.75 * sat.x1mth2
                    * (2.0 * etasq - eeta * (1.0 + etasq))
                    * cos(2.0 * sat.argpo)));
  sat.cc5 = 2.0 * coef1 * ao * omeosq
          * (1.0 + 2.75 * (etasq + eeta) + eeta * etasq);

  double cosio4 = cosio2 * cosio2;
  double temp1 = 1.5 * J2 * pinvsq * sat.no_unkozai;
  double temp2 = 0.5 * temp1 * J2 * pinvsq;
  double temp3 = -0.46875 * J4 * pinvsq * pinvsq * sat.no_unkozai;

  sat.mdot = sat.no_unkozai
           + 0.5 * temp1 * rteosq * sat.con41
           + 0.0625 * temp2 * rteosq
             * (13.0 - 78.0 * cosio2 + 137.0 * cosio4);
  sat.argpdot = -0.5 * temp1 * con42
              + 0.0625 * temp2 * (7.0 - 114.0 * cosio2 + 395.0 * cosio4)
              + temp3 * (3.0 - 36.0 * cosio2 + 49.0 * cosio4);
  double xhdot1 = -temp1 * cosio;
  sat.nodedot = xhdot1
              + (0.5 * temp2 * (4.0 - 19.0 * cosio2)
                 + 2.0 * temp3 * (3.0 - 7.0 * cosio2)) * cosio;

  sat.omgcof = sat.bstar * cc3 * cos(sat.argpo);
  sat.xmcof = 0.0;
  if (sat.ecco > 1.0e-4) {
    sat.xmcof = -X2O3 * coef * sat.bstar / eeta;
  }
  sat.nodecf = 3.5 * omeosq * xhdot1 * sat.cc1;
  sat.t2cof = 1.5 * sat.cc1;

  // Guard the 1/(1+cosio) singularity for a near-180-degree (retrograde) orbit.
  if (fabs(cosio + 1.0) > 1.5e-12) {
    sat.xlcof = -0.25 * J3OJ2 * sinio * (3.0 + 5.0 * cosio) / (1.0 + cosio);
  } else {
    sat.xlcof = -0.25 * J3OJ2 * sinio * (3.0 + 5.0 * cosio) / 1.5e-12;
  }
  sat.aycof = -0.5 * J3OJ2 * sinio;

  double delmotemp = 1.0 + sat.eta * cos(sat.mo);
  sat.delmo = delmotemp * delmotemp * delmotemp;
  sat.sinmao = sin(sat.mo);
  sat.x7thm1 = 7.0 * cosio2 - 1.0;

  // Below ~220 km the higher-order drag terms are dropped (the "simplified" model).
  sat.isimp = (rp < (220.0 / RADIUS_EARTH_KM + 1.0)) ? 1 : 0;

  if (sat.isimp != 1) {
    double cc1sq = sat.cc1 * sat.cc1;
    sat.d2 = 4.0 * ao * tsi * cc1sq;
    double temp = sat.d2 * tsi * sat.cc1 / 3.0;
    sat.d3 = (17.0 * ao + sfour) * temp;
    sat.d4 = 0.5 * temp * ao * tsi
           * (221.0 * ao + 31.0 * sfour) * sat.cc1;
    sat.t3cof = sat.d2 + 2.0 * cc1sq;
    sat.t4cof = 0.25 * (3.0 * sat.d3
                        + sat.cc1 * (12.0 * sat.d2 + 10.0 * cc1sq));
    sat.t5cof = 0.2 * (3.0 * sat.d4
                       + 12.0 * sat.cc1 * sat.d3
                       + 6.0 * sat.d2 * sat.d2
                       + 15.0 * cc1sq * (2.0 * sat.d2 + cc1sq));
  }

  sat.error = 0;
  return true;
}

bool sgp4(Satrec &sat, double tsince, double r[3]) {
  sat.error = 0;

  // --- secular gravity and atmospheric drag ---------------------------------
  double xmdf = sat.mo + sat.mdot * tsince;
  double argpdf = sat.argpo + sat.argpdot * tsince;
  double nodedf = sat.nodeo + sat.nodedot * tsince;
  double argpm = argpdf;
  double mm = xmdf;
  double t2 = tsince * tsince;
  double nodem = nodedf + sat.nodecf * t2;
  double tempa = 1.0 - sat.cc1 * tsince;
  double tempe = sat.bstar * sat.cc4 * tsince;
  double templ = sat.t2cof * t2;

  if (sat.isimp != 1) {
    double delomg = sat.omgcof * tsince;
    double delmtemp = 1.0 + sat.eta * cos(xmdf);
    double delm = sat.xmcof * (delmtemp * delmtemp * delmtemp - sat.delmo);
    double temp = delomg + delm;
    mm = xmdf + temp;
    argpm = argpdf - temp;
    double t3 = t2 * tsince;
    double t4 = t3 * tsince;
    tempa = tempa - sat.d2 * t2 - sat.d3 * t3 - sat.d4 * t4;
    tempe = tempe + sat.bstar * sat.cc5 * (sin(mm) - sat.sinmao);
    templ = templ + sat.t3cof * t3
          + t4 * (sat.t4cof + tsince * sat.t5cof);
  }

  double nm = sat.no_unkozai;
  double em = sat.ecco;
  double inclm = sat.inclo;

  if (nm <= 0.0) {
    sat.error = 2;
    return false;
  }

  double am = pow(XKE / nm, X2O3) * tempa * tempa;
  nm = XKE / pow(am, 1.5);
  em -= tempe;

  // A mean eccentricity outside [0, 1) means the element set has decayed away.
  if (em >= 1.0 || em < -0.001) {
    sat.error = 1;
    return false;
  }
  if (em < 1.0e-6) {
    em = 1.0e-6;
  }

  mm += sat.no_unkozai * templ;
  double xlm = mm + argpm + nodem;

  nodem = fmod(nodem, TAU);
  argpm = fmod(argpm, TAU);
  xlm = fmod(xlm, TAU);
  mm = fmod(xlm - argpm - nodem, TAU);

  double sinim = sin(inclm);
  double cosim = cos(inclm);

  // --- long-period periodics ------------------------------------------------
  double axnl = em * cos(argpm);
  double temp = 1.0 / (am * (1.0 - em * em));
  double aynl = em * sin(argpm) + temp * sat.aycof;
  double xl = mm + argpm + nodem + temp * sat.xlcof * axnl;

  // --- solve Kepler's equation ----------------------------------------------
  double u = fmod(xl - nodem, TAU);
  double eo1 = u;
  double tem5 = 9999.9;
  double sineo1 = 0.0;
  double coseo1 = 0.0;

  // Newton-Raphson, capped at 10 iterations (Vallado): converges in 2-3 for a
  // near-circular LEO orbit, and the cap keeps the frame time bounded regardless.
  for (int ktr = 1; ktr <= 10 && fabs(tem5) >= 1.0e-12; ktr++) {
    sineo1 = sin(eo1);
    coseo1 = cos(eo1);
    tem5 = 1.0 - coseo1 * axnl - sineo1 * aynl;
    tem5 = (u - aynl * coseo1 + axnl * sineo1 - eo1) / tem5;
    if (fabs(tem5) >= 0.95) {
      tem5 = (tem5 > 0.0) ? 0.95 : -0.95;
    }
    eo1 += tem5;
  }

  // --- short-period preliminary quantities ----------------------------------
  double ecose = axnl * coseo1 + aynl * sineo1;
  double esine = axnl * sineo1 - aynl * coseo1;
  double el2 = axnl * axnl + aynl * aynl;
  double pl = am * (1.0 - el2);

  if (pl < 0.0) {
    sat.error = 4;
    return false;
  }

  double rl = am * (1.0 - ecose);
  double rdotl = sqrt(am) * esine / rl;
  double rvdotl = sqrt(pl) / rl;
  double betal = sqrt(1.0 - el2);
  temp = esine / (1.0 + betal);
  double sinu = am / rl * (sineo1 - aynl - axnl * temp);
  double cosu = am / rl * (coseo1 - axnl + aynl * temp);
  double su = atan2(sinu, cosu);
  double sin2u = (cosu + cosu) * sinu;
  double cos2u = 1.0 - 2.0 * sinu * sinu;

  temp = 1.0 / pl;
  double temp1 = 0.5 * J2 * temp;
  double temp2 = temp1 * temp;

  // --- update for short-period periodics ------------------------------------
  double mrt = rl * (1.0 - 1.5 * temp2 * betal * sat.con41)
             + 0.5 * temp1 * sat.x1mth2 * cos2u;
  su -= 0.25 * temp2 * sat.x7thm1 * sin2u;
  double xnode = nodem + 1.5 * temp2 * cosim * sin2u;
  double xinc = inclm + 1.5 * temp2 * cosim * sinim * cos2u;

  // --- orientation vectors --------------------------------------------------
  double sinsu = sin(su);
  double cossu = cos(su);
  double snod = sin(xnode);
  double cnod = cos(xnode);
  double sini = sin(xinc);
  double cosi = cos(xinc);
  double xmx = -snod * cosi;
  double xmy = cnod * cosi;
  double ux = xmx * sinsu + cnod * cossu;
  double uy = xmy * sinsu + snod * cossu;
  double uz = sini * sinsu;

  // mrt < 1 Earth radius => the object has re-entered.
  if (mrt < 1.0) {
    sat.error = 6;
    return false;
  }

  r[0] = mrt * ux * RADIUS_EARTH_KM;
  r[1] = mrt * uy * RADIUS_EARTH_KM;
  r[2] = mrt * uz * RADIUS_EARTH_KM;
  return true;
}

bool propagateEcef(Satrec &sat, double jd, double ecef[3]) {
  double tsince = (jd - sat.jdsatepoch) * 1440.0;   // Days -> minutes.
  double teme[3];
  if (!sgp4(sat, tsince, teme)) {
    return false;
  }
  temeToEcef(teme, gmstRad(jd), ecef);
  return true;
}
