/**
 * @file simulate_main.cpp
 * @brief Live simulator: run the round-display firmware on a PC, in real time.
 * @details
 *     This is the firmware's loop() with the Arduino calls swapped out. It compiles the
 *     *real* render.cpp and sgp4.cpp, advances simulated time from the wall clock,
 *     spins the camera, propagates the stations, and streams finished RGB565 frames
 *     down stdout at TARGET_FPS - exactly as the .ino would push them over SPI.
 *
 *     simulate.py reads that stream and blits it into a window, so you can watch the
 *     panel animate on Windows/macOS/Linux with no XIAO plugged in.
 *
 *     The one honest gap: there is no Wi-Fi here, so it propagates the element sets
 *     baked into tle_fallback.h rather than fetching fresh ones from CelesTrak. Station
 *     phase will drift from reality as those elements age; everything else - geometry,
 *     projection, colours, timing, the ping - is what the panel does.
 *
 *     Usage: simulate [tz-offset-hours] [time-acceleration]
 */

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include <chrono>
#include <thread>

#include "config.h"
#include "host_util.h"
#include "render.h"
#include "sgp4.h"
#include "tle_fallback.h"

int main(int argc, char **argv) {
  double tzOff = (argc > 1) ? atof(argv[1]) : 10.0;
  // Default to the firmware's own TIME_ACCELERATION; override to fast-forward the
  // orbits without touching config.h.
  double accel = (argc > 2) ? atof(argv[2]) : (double)TIME_ACCELERATION;

  host::setBinaryStdout();

  Satrec iss, css;
  bool issOk = host::findTle(FALLBACK_TLE, ISS_NORAD_ID, iss);
  bool cssOk = host::findTle(FALLBACK_TLE, CSS_NORAD_ID, css);
  if (!issOk || !cssOk) {
    fprintf(stderr, "failed to parse baked-in TLEs\n");
    return 1;
  }

  static uint16_t fb[PANEL_W * PANEL_H];
  Canvas canvas = {fb, PANEL_W, PANEL_H};
  sceneInit();

  using clock_t_ = std::chrono::steady_clock;
  const auto start = clock_t_::now();
  auto last = start;

  // Real UTC now, as a Unix epoch. This is where simulated time starts.
  const double wallStart = (double)std::chrono::duration_cast<
      std::chrono::seconds>(
      std::chrono::system_clock::now().time_since_epoch()).count();

  double simEpoch = wallStart;
  float azimuth = 0.0f;

  const auto budget = std::chrono::milliseconds(1000 / TARGET_FPS);

  fprintf(stderr, "simulating %dx%d @ %d fps | tz UTC%+g | accel %gx\n",
          PANEL_W, PANEL_H, TARGET_FPS, tzOff, accel);

  for (;;) {
    const auto now = clock_t_::now();
    const float dt =
        std::chrono::duration<float>(now - last).count();
    last = now;

    // --- the firmware's loop(), verbatim in spirit -------------------------
    simEpoch += (double)dt * accel;
    azimuth = fmodf(azimuth + SPIN_DEG_PER_SEC * dt, 360.0f);

    Station st[2];
    st[0].color = COL_ISS;
    st[0].label = "ISS";
    st[0].valid = propagateEcef(iss, host::julianFromEpoch(simEpoch), st[0].ecef);
    st[1].color = COL_CSS;
    st[1].label = "CSS";
    st[1].valid = propagateEcef(css, host::julianFromEpoch(simEpoch), st[1].ecef);

    // The clock shows REAL wall time, never simulated time - same as the firmware.
    const double wallNow =
        wallStart + std::chrono::duration<double>(now - start).count();
    char timeStr[16];
    char dateStr[20];
    host::localStrings((long long)wallNow, tzOff,
                       timeStr, sizeof(timeStr), dateStr, sizeof(dateStr));

    const float elapsed =
        std::chrono::duration<float>(now - start).count();

    Scene scene;
    scene.stations = st;
    scene.nStations = 2;
    scene.azimuthDeg = azimuth;
    scene.homePulse = fmodf(elapsed / HOME_PING_PERIOD_S, 1.0f);
    scene.timeStr = timeStr;
    scene.dateStr = dateStr;

    renderFrame(canvas, scene);

    // --- push the frame (stdout stands in for the SPI bus) -----------------
    if (fwrite(fb, sizeof(uint16_t), PANEL_W * PANEL_H, stdout)
        != (size_t)(PANEL_W * PANEL_H)) {
      break;                     // Viewer closed the pipe: we are done.
    }
    if (fflush(stdout) != 0) {
      break;
    }

    const auto spent = clock_t_::now() - now;
    if (spent < budget) {
      std::this_thread::sleep_for(budget - spent);
    }
  }
  return 0;
}
