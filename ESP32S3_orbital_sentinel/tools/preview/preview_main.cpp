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
#include "host_util.h"
#include "render.h"
#include "sgp4.h"
#include "tle_fallback.h"

namespace {

/// Parse "YYYY-MM-DDTHH:MM:SS" into a UTC Julian date.
double parseIsoJd(const char *iso) {
  int y = 2026, mo = 7, d = 13, h = 0, mi = 0, s = 0;
  sscanf(iso, "%d-%d-%dT%d:%d:%d", &y, &mo, &d, &h, &mi, &s);
  return julianDate(y, mo, d, h, mi, (double)s);
}

}  // namespace

int main(int argc, char **argv) {
  const char *iso = (argc > 1) ? argv[1] : "2026-07-13T04:21:07";
  int frames = (argc > 2) ? atoi(argv[2]) : 1;
  double step = (argc > 3) ? atof(argv[3]) : 0.0;   // Simulated seconds per frame.
  double az0 = (argc > 4) ? atof(argv[4]) : 0.0;    // Starting camera spin (deg).
  double tzOff = (argc > 5) ? atof(argv[5]) : 10.0; // Local = UTC + this, in hours.

  host::setBinaryStdout();   // Windows: stop text mode mangling the frame bytes.

  Satrec iss, css;
  if (!host::findTle(FALLBACK_TLE, ISS_NORAD_ID, iss) ||
      !host::findTle(FALLBACK_TLE, CSS_NORAD_ID, css)) {
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
    char timeStr[16];
    char dateStr[20];
    host::localStrings(utcEpoch, tzOff,
                       timeStr, sizeof(timeStr), dateStr, sizeof(dateStr));

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
