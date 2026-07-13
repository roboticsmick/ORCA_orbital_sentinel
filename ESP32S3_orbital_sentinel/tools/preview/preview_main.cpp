/**
 * @file preview_main.cpp
 * @brief Host harness: render panel frames on a PC, without a XIAO or a display.
 * @details
 *     Compiles the firmware's *actual* render.cpp and sgp4.cpp - not a mock-up - so the
 *     output is what the panel will show: same SGP4 positions, same orthographic
 *     projection, same palette, same RGB565 quantisation, same round bezel mask. If it
 *     looks wrong here, it will look wrong on the hardware.
 *
 *     The one thing this does differently is the local-time conversion. The firmware
 *     uses TZ_POSIX with the ESP32's libc; here we take a plain UTC offset in hours, so
 *     the preview does not depend on the host's timezone database. Both then hand
 *     ready-made strings to the same pure renderer.
 *
 *     Writes raw RGB565 frames to stdout; build_preview.py turns them into PNGs.
 *
 *     Usage: preview <iso-utc> <frames> <sim-seconds-per-frame> [azimuth] [utc-offset-h]
 *            preview 2026-07-13T04:21:07 4 900 0 10
 */

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "config.h"
#include "render.h"
#include "sgp4.h"
#include "tle_fallback.h"

namespace {

const char *MONTHS[12] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};

/// Locate a NORAD id in TLE text and initialise its propagator.
bool findTle(const char *text, int norad, Satrec &out) {
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

/// Parse "YYYY-MM-DDTHH:MM:SS" into a UTC Julian date.
double parseIsoJd(const char *iso) {
  int y = 2026, mo = 7, d = 13, h = 0, mi = 0, s = 0;
  sscanf(iso, "%d-%d-%dT%d:%d:%d", &y, &mo, &d, &h, &mi, &s);
  return julianDate(y, mo, d, h, mi, (double)s);
}

/// Break a Unix epoch into UTC calendar fields (no host timezone involved).
void utcFields(long long epoch, int &Y, int &M, int &D, int &h, int &m, int &s) {
  long long days = epoch / 86400;
  long long rem = epoch % 86400;
  if (rem < 0) {
    rem += 86400;
    days -= 1;
  }
  h = (int)(rem / 3600);
  m = (int)((rem % 3600) / 60);
  s = (int)(rem % 60);

  // Civil-from-days (Howard Hinnant's algorithm).
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

}  // namespace

int main(int argc, char **argv) {
  const char *iso = (argc > 1) ? argv[1] : "2026-07-13T04:21:07";
  int frames = (argc > 2) ? atoi(argv[2]) : 1;
  double step = (argc > 3) ? atof(argv[3]) : 0.0;   // Simulated seconds per frame.
  double az0 = (argc > 4) ? atof(argv[4]) : 0.0;    // Starting camera spin (deg).
  double tzOff = (argc > 5) ? atof(argv[5]) : 10.0; // Local = UTC + this, in hours.

  Satrec iss, css;
  if (!findTle(FALLBACK_TLE, ISS_NORAD_ID, iss) ||
      !findTle(FALLBACK_TLE, CSS_NORAD_ID, css)) {
    fprintf(stderr, "failed to parse baked-in TLEs\n");
    return 1;
  }

  static uint16_t fb[PANEL_W * PANEL_H];
  Canvas c = {fb, PANEL_W, PANEL_H};
  sceneInit();

  double jd0 = parseIsoJd(iso);

  for (int f = 0; f < frames; f++) {
    double jd = jd0 + (step * f) / 86400.0;

    // Match the firmware: the cosmetic spin advances with real time, and at the
    // default TIME_ACCELERATION of 1.0 that is the same as simulated time.
    float az = (float)fmod(
        az0 + (step * f / TIME_ACCELERATION) * SPIN_DEG_PER_SEC, 360.0);

    Station st[2];
    st[0].color = COL_ISS;
    st[0].label = "ISS";
    st[0].valid = propagateEcef(iss, jd, st[0].ecef);
    st[1].color = COL_CSS;
    st[1].label = "CSS";
    st[1].valid = propagateEcef(css, jd, st[1].ecef);

    // The panel shows LOCAL time; apply the offset before formatting.
    long long utcEpoch = (long long)((jd - 2440587.5) * 86400.0 + 0.5);
    long long localEpoch = utcEpoch + (long long)(tzOff * 3600.0);
    int Y, M, D, h, m, s;
    utcFields(localEpoch, Y, M, D, h, m, s);

    char timeStr[16];
    char dateStr[20];
    snprintf(timeStr, sizeof(timeStr), "%02d:%02d:%02d", h, m, s);
    snprintf(dateStr, sizeof(dateStr), "%02d %s %04d", D, MONTHS[(M - 1) % 12], Y);

    Scene sc;
    sc.stations = st;
    sc.nStations = 2;
    sc.azimuthDeg = az;
    // Walk the ping through its cycle across a multi-frame render so the animation
    // is visible in a sequence rather than frozen.
    sc.homePulse = (float)fmod(0.35 + 0.27 * f, 1.0);
    sc.timeStr = timeStr;
    sc.dateStr = dateStr;

    renderFrame(c, sc);
    fwrite(fb, sizeof(uint16_t), PANEL_W * PANEL_H, stdout);

    fprintf(stderr, "frame %d  az %6.2f  %s %s  ISS %s  CSS %s\n",
            f, az, timeStr, dateStr,
            st[0].valid ? "ok" : "ERR", st[1].valid ? "ok" : "ERR");
  }
  return 0;
}
