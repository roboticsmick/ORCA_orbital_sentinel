/**
 * @file render.cpp
 * @brief Orthographic camera and compact round-panel renderer. See render.h.
 */

#include "render.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "coastline.h"
#include "config.h"
#include "font5x7.h"
#include "sgp4.h"

namespace {

const float PI_F = 3.14159265358979f;
const float DEG2RAD_F = PI_F / 180.0f;

/// Coastline dots lifted onto the sphere once at boot. Float, not double: these only
/// ever become pixel coordinates, and 2661 * 3 * 4 B = ~32 KB of SRAM already.
float g_coast[COAST_DOT_COUNT][3];
bool g_ready = false;

/// Deterministic star field, generated once (fixed seed => the same sky every boot).
int16_t g_stars[STAR_COUNT][2];

/// The home location in the Earth-fixed frame. Fixed, so resolved once.
float g_home[3];

/// Pixels per km, and the projected Earth radius. Set in sceneInit().
float g_scale = 0.0f;
float g_earthPx = 0.0f;

/// Panel centre.
const float CX = PANEL_W * 0.5f;
const float CY = PANEL_H * 0.5f;

/// Combined spin+tilt rotation, rebuilt once per frame.
struct Rot {
  float m[3][3];
};

/**
 * @brief Build the camera rotation for an azimuth: R = Rx(tilt) * Rz(azimuth).
 * @details Matches Camera.set_azimuth in camera.py.
 */
Rot makeRot(float azDeg) {
  float az = azDeg * DEG2RAD_F;
  float tilt = VIEW_TILT_DEG * DEG2RAD_F;
  float ca = cosf(az), sa = sinf(az);
  float ct = cosf(tilt), st = sinf(tilt);

  Rot r;
  r.m[0][0] = ca;        r.m[0][1] = -sa;       r.m[0][2] = 0.0f;
  r.m[1][0] = ct * sa;   r.m[1][1] = ct * ca;   r.m[1][2] = -st;
  r.m[2][0] = st * sa;   r.m[2][1] = st * ca;   r.m[2][2] = ct;
  return r;
}

/**
 * @brief Project an Earth-fixed point to a pixel. `depth` > 0 means the near hemisphere.
 * @details The camera sits at +Y looking back at the origin with +Z up. For a
 *          right-handed frame that makes screen-right equal to -X, not +X:
 *          right = view_dir x up = (-Y) x (Z) = -X.
 *
 *          Note this differs from camera.py, which uses +X for screen-right while
 *          still treating +Y as "towards the viewer". That combination draws the
 *          globe MIRRORED east-west - longitude increases to the left, so Perth
 *          renders east of Brisbane. The coastline is mirrored by the same amount,
 *          which is why it still reads as Earth at a glance. It only becomes obvious
 *          once you put a known city on the map. We do, so we fix it here.
 */
inline void project(const Rot &r, float x, float y, float z,
                    float &px, float &py, float &depth) {
  float rx = r.m[0][0] * x + r.m[0][1] * y + r.m[0][2] * z;
  float ry = r.m[1][0] * x + r.m[1][1] * y + r.m[1][2] * z;
  float rz = r.m[2][0] * x + r.m[2][1] * y + r.m[2][2] * z;
  px = CX - g_scale * rx;   // Screen right is -X (see above): east goes right.
  py = CY - g_scale * rz;   // Screen y grows downward; invert world z.
  depth = ry;
}

inline void putPixel(Canvas &c, int x, int y, uint16_t col) {
  if (x < 0 || y < 0 || x >= c.w || y >= c.h) {
    return;
  }
  c.px[y * c.w + x] = col;
}

/// True if a pixel falls inside the display's visible disc.
inline bool inDisc(int x, int y) {
  int dx = x - (int)CX;
  int dy = y - (int)CY;
  return (dx * dx + dy * dy) <= (PANEL_RADIUS * PANEL_RADIUS);
}

void fill(Canvas &c, uint16_t col) {
  int n = c.w * c.h;
  for (int i = 0; i < n; i++) {
    c.px[i] = col;
  }
}

void fillRect(Canvas &c, int x, int y, int w, int h, uint16_t col) {
  for (int j = 0; j < h; j++) {
    for (int i = 0; i < w; i++) {
      putPixel(c, x + i, y + j, col);
    }
  }
}

/// Midpoint circle outline (the Earth limb, and the home ping).
void drawCircle(Canvas &c, int cx, int cy, int radius, uint16_t col) {
  if (radius <= 0) {
    return;
  }
  int x = radius;
  int y = 0;
  int err = 1 - radius;
  while (x >= y) {
    putPixel(c, cx + x, cy + y, col);
    putPixel(c, cx + y, cy + x, col);
    putPixel(c, cx - y, cy + x, col);
    putPixel(c, cx - x, cy + y, col);
    putPixel(c, cx - x, cy - y, col);
    putPixel(c, cx - y, cy - x, col);
    putPixel(c, cx + y, cy - x, col);
    putPixel(c, cx + x, cy - y, col);
    y++;
    if (err < 0) {
      err += 2 * y + 1;
    } else {
      x--;
      err += 2 * (y - x) + 1;
    }
  }
}

/**
 * @brief Draw a satellite: a body with two solar panels on booms.
 * @details Eleven pixels wide, so it reads as a spacecraft rather than a dot at
 *          240x240 - but still small enough not to swamp the globe. Shape:
 *
 *              ##   ###   ##      <- panels, booms, body
 *              ##  #####  ##
 *              ##   ###   ##
 */
void drawSatellite(Canvas &c, int x, int y, uint16_t col) {
  fillRect(c, x - 1, y - 1, 3, 3, col);   // Body.
  putPixel(c, x - 2, y, col);             // Booms out to each panel.
  putPixel(c, x + 2, y, col);
  fillRect(c, x - 5, y - 2, 2, 5, col);   // Left solar panel.
  fillRect(c, x + 4, y - 2, 2, 5, col);   // Right solar panel.
}

/**
 * @brief Draw the marker for the viewer's own location: a dot.
 * @details Just a dot. The expanding ring around it is what draws the eye and what
 *          distinguishes it from a satellite - an icon here only adds clutter at
 *          240x240, and the amber already says "this one is not a spacecraft".
 */
void drawHome(Canvas &c, int x, int y, uint16_t col) {
  fillRect(c, x - 1, y - 1, 3, 3, col);
}

int textWidth(const char *s, int scale) {
  int n = (int)strlen(s);
  return n > 0 ? (n * FONT_ADVANCE - 1) * scale : 0;
}

/// Draw uppercase text with the 5x7 font, optionally pixel-doubled. Unsupported
/// characters render as blanks.
void drawText(Canvas &c, int x, int y, const char *s, uint16_t col, int scale) {
  if (scale < 1) {
    scale = 1;
  }
  for (; *s != '\0'; s++) {
    unsigned char ch = (unsigned char)*s;
    if (ch >= FONT_FIRST_CHAR && ch <= FONT_LAST_CHAR) {
      const uint8_t *g = FONT5X7[ch - FONT_FIRST_CHAR];
      for (int gx = 0; gx < FONT_WIDTH; gx++) {
        uint8_t bits = g[gx];
        for (int gy = 0; gy < FONT_HEIGHT; gy++) {
          if (bits & (1 << gy)) {
            if (scale == 1) {
              putPixel(c, x + gx, y + gy, col);
            } else {
              fillRect(c, x + gx * scale, y + gy * scale, scale, scale, col);
            }
          }
        }
      }
    }
    x += FONT_ADVANCE * scale;
  }
}

void drawTextCentered(Canvas &c, int y, const char *s, uint16_t col, int scale) {
  drawText(c, (int)CX - textWidth(s, scale) / 2, y, s, col, scale);
}

}  // namespace

void sceneInit() {
  // Pixels per km, from the Earth radius as a fraction of the panel.
  int minDim = (PANEL_W < PANEL_H) ? PANEL_W : PANEL_H;
  g_scale = (float)(GLOBE_RADIUS_FRAC * minDim / EARTH_RADIUS_KM);
  g_earthPx = (float)(EARTH_RADIUS_KM * g_scale);

  // Lift each baked lon/lat dot onto the sphere, once.
  for (int i = 0; i < COAST_DOT_COUNT; i++) {
    double u[3];
    geodeticToEcefUnit(COAST_DOTS[i][0] / 100.0, COAST_DOTS[i][1] / 100.0, u);
    g_coast[i][0] = (float)(u[0] * EARTH_RADIUS_KM);
    g_coast[i][1] = (float)(u[1] * EARTH_RADIUS_KM);
    g_coast[i][2] = (float)(u[2] * EARTH_RADIUS_KM);
  }

  // The home location is fixed in the Earth-fixed frame, so it never needs
  // recomputing - only re-projecting as the camera spins.
  double h[3];
  geodeticToEcefUnit(HOME_LON, HOME_LAT, h);
  g_home[0] = (float)(h[0] * EARTH_RADIUS_KM);
  g_home[1] = (float)(h[1] * EARTH_RADIUS_KM);
  g_home[2] = (float)(h[2] * EARTH_RADIUS_KM);

  // A simple LCG keeps the star field identical between the host preview and the
  // panel without depending on either platform's rand().
  uint32_t s = STAR_SEED;
  int placed = 0;
  while (placed < STAR_COUNT) {
    s = s * 1664525u + 1013904223u;
    int x = (int)((s >> 16) % PANEL_W);
    s = s * 1664525u + 1013904223u;
    int y = (int)((s >> 16) % PANEL_H);
    if (!inDisc(x, y)) {
      continue;   // Off the visible disc; place one that can actually be seen.
    }
    g_stars[placed][0] = (int16_t)x;
    g_stars[placed][1] = (int16_t)y;
    placed++;
  }
  g_ready = true;
}

void renderFrame(Canvas &c, const Scene &s) {
  if (!g_ready) {
    sceneInit();
  }

  fill(c, COL_BACKGROUND);
  Rot rot = makeRot(s.azimuthDeg);

  for (int i = 0; i < STAR_COUNT; i++) {
    putPixel(c, g_stars[i][0], g_stars[i][1], COL_STAR);
  }
  drawCircle(c, (int)CX, (int)CY, (int)g_earthPx, COL_GRID);

  // --- coastline: front/back shading gives the sphere its depth --------------
  for (int i = 0; i < COAST_DOT_COUNT; i++) {
    float px, py, depth;
    project(rot, g_coast[i][0], g_coast[i][1], g_coast[i][2], px, py, depth);
    putPixel(c, (int)px, (int)py,
             (depth >= 0.0f) ? COL_COAST : COL_COAST_FAR);
  }

#if HOME_ENABLED
  // --- your location: pings while the Earth's rotation holds it in view ------
  {
    float px, py, depth;
    project(rot, g_home[0], g_home[1], g_home[2], px, py, depth);
    if (depth >= 0.0f) {          // On the near hemisphere: visible.
      // An expanding, one-shot-per-cycle ring. It reads as a radar ping precisely
      // because it starts tight on the dot and grows outward, rather than pulsing
      // in place.
      int r = 3 + (int)(s.homePulse * 9.0f);
      drawCircle(c, (int)px, (int)py, r, COL_HOME_PING);
      drawHome(c, (int)px, (int)py, COL_HOME);
    }
  }
#endif

  // --- stations: satellites, hidden when behind the globe --------------------
  for (int i = 0; i < s.nStations; i++) {
    if (!s.stations[i].valid) {
      continue;
    }
    float px, py, depth;
    project(rot, (float)s.stations[i].ecef[0], (float)s.stations[i].ecef[1],
            (float)s.stations[i].ecef[2], px, py, depth);

    // Occluded == on the far side *and* projecting inside the Earth disk.
    float dx = px - CX;
    float dy = py - CY;
    bool behind = depth < 0.0f;
    bool occluded = behind && (dx * dx + dy * dy) < (g_earthPx * g_earthPx);
    if (occluded) {
      continue;
    }
    drawSatellite(c, (int)px, (int)py, s.stations[i].color);
    // Clear of the 11 px body so the label never sits on the solar panels.
    drawText(c, (int)px + 8, (int)py - 3, s.stations[i].label,
             s.stations[i].color, 1);
  }

  // --- clock ----------------------------------------------------------------
  // Centred, not corner-anchored like the desktop: a round bezel has no corners.
  // The time is the headline - this is a clock you can read across a room - so it
  // gets the doubled font; the date sits quietly underneath the globe.
  if (s.timeStr != nullptr) {
    drawTextCentered(c, 14, s.timeStr, COL_CLOCK, CLOCK_TEXT_SCALE);
  }
  if (s.dateStr != nullptr) {
    drawTextCentered(c, PANEL_H - 26, s.dateStr, COL_DATE, DATE_TEXT_SCALE);
  }

  // --- round bezel ----------------------------------------------------------
  // The corners of the square framebuffer are not physically visible. Masking them
  // costs little and means the host preview shows exactly what the panel shows.
  for (int y = 0; y < c.h; y++) {
    for (int x = 0; x < c.w; x++) {
      if (!inDisc(x, y)) {
        c.px[y * c.w + x] = COL_BACKGROUND;
      }
    }
  }
}
