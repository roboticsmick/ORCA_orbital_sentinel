/**
 * @file host_util.h
 * @brief Helpers shared by the host preview and simulator harnesses.
 * @details
 *     Host-side only. None of this is compiled into the firmware - it exists so that
 *     preview_main.cpp and simulate_main.cpp can share TLE lookup, calendar maths, and
 *     the Windows binary-stdout fix without duplicating them.
 */

#ifndef ORBITAL_SENTINEL_HOST_UTIL_H
#define ORBITAL_SENTINEL_HOST_UTIL_H

#include <stdio.h>
#include <string.h>

#include "sgp4.h"

#if defined(_WIN32)
#include <fcntl.h>
#include <io.h>
#endif

namespace host {

static const char *MONTHS[12] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                 "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};

/**
 * @brief Put stdout into binary mode (Windows only; a no-op elsewhere).
 * @details We stream raw RGB565 frames down stdout. On Windows the C runtime opens
 *          stdout in TEXT mode by default, which rewrites every 0x0A byte as 0x0D 0x0A
 *          - silently corrupting any frame whose pixel data happens to contain a
 *          newline byte, and shifting every frame after it. The current palettes happen
 *          not to produce 0x0A, which means this bug would lie dormant until someone
 *          picked a slightly different colour. Not a trap worth leaving.
 */
inline void setBinaryStdout() {
#if defined(_WIN32)
  _setmode(_fileno(stdout), _O_BINARY);
#endif
}

/// Locate a NORAD id in TLE text and initialise its propagator.
inline bool findTle(const char *text, int norad, Satrec &out) {
  char want[8];
  snprintf(want, sizeof(want), "%5d", norad);
  const char *p = text;
  while (p != nullptr && *p != '\0') {
    if (p[0] == '1' && p[1] == ' ' && strncmp(p + 2, want, 5) == 0) {
      const char *nl = strchr(p, '\n');
      if (nl == nullptr) {
        return false;
      }
      char l1[80], l2[80];
      size_t n1 = (size_t)(nl - p);
      const char *s2 = nl + 1;
      const char *nl2 = strchr(s2, '\n');
      size_t n2 = (nl2 != nullptr) ? (size_t)(nl2 - s2) : strlen(s2);
      if (n1 >= sizeof(l1) || n2 >= sizeof(l2)) {
        return false;
      }
      memcpy(l1, p, n1);
      l1[n1] = '\0';
      memcpy(l2, s2, n2);
      l2[n2] = '\0';
      return twoline2rv(l1, l2, out);
    }
    p = strchr(p, '\n');
    if (p != nullptr) {
      p++;
    }
  }
  return false;
}

/**
 * @brief Break a Unix epoch into UTC calendar fields.
 * @details Hand-rolled (Howard Hinnant's civil-from-days) rather than gmtime_r, so the
 *          harness never depends on the host's timezone database - the caller applies
 *          its own offset. Keeps the preview reproducible on any machine.
 */
inline void utcFields(long long epoch, int &Y, int &M, int &D,
                      int &h, int &m, int &s) {
  long long days = epoch / 86400;
  long long rem = epoch % 86400;
  if (rem < 0) {
    rem += 86400;
    days -= 1;
  }
  h = (int)(rem / 3600);
  m = (int)((rem % 3600) / 60);
  s = (int)(rem % 60);

  long long z = days + 719468;
  long long era = (z >= 0 ? z : z - 146096) / 146097;
  long long doe = z - era * 146097;
  long long yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  long long y = yoe + era * 400;
  long long doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  long long mp = (5 * doy + 2) / 153;
  long long dd = doy - (153 * mp + 2) / 5 + 1;
  long long mm = mp + (mp < 10 ? 3 : -9);
  Y = (int)(y + (mm <= 2 ? 1 : 0));
  M = (int)mm;
  D = (int)dd;
}

/**
 * @brief Format the panel's clock strings for a UTC epoch and a local offset.
 * @param utcEpoch Seconds since 1970-01-01 UTC.
 * @param tzOffsetHours Hours to add for local time (Brisbane = 10).
 */
inline void localStrings(long long utcEpoch, double tzOffsetHours,
                         char *timeStr, size_t timeLen,
                         char *dateStr, size_t dateLen) {
  long long local = utcEpoch + (long long)(tzOffsetHours * 3600.0);
  int Y, M, D, h, m, s;
  utcFields(local, Y, M, D, h, m, s);
  snprintf(timeStr, timeLen, "%02d:%02d:%02d", h, m, s);
  snprintf(dateStr, dateLen, "%02d %s %04d", D, MONTHS[(M - 1) % 12], Y);
}

/// Julian date from a Unix epoch (seconds).
inline double julianFromEpoch(double epochSec) {
  return epochSec / 86400.0 + 2440587.5;
}

}  // namespace host

#endif  // ORBITAL_SENTINEL_HOST_UTIL_H
