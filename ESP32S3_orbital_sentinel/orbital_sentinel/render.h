/**
 * @file render.h
 * @brief Orthographic camera and the compact round-panel renderer.
 * @details
 *     The C++ counterpart of camera.py + render_small.py. Draws a whole frame into a
 *     plain RGB565 buffer and never touches the display itself, which is what lets the
 *     host preview harness (tools/preview) produce pixel-identical output to the panel:
 *     same projection, same palette, same 16-bit quantisation.
 *
 *     Camera model (unchanged from the desktop): the viewer sits at +Y looking at the
 *     origin. A point is spun about the polar axis (cosmetic azimuth), tilted about X,
 *     then projected orthographically - screen x from world x, screen y from world z,
 *     with world y as depth. A point on the far hemisphere whose projected radius falls
 *     inside the Earth disk is occluded, which is what gives the scene its 3D read.
 *
 *     The renderer is *pure*: it takes a fully-resolved Scene and draws it. Anything
 *     platform-shaped - reading the clock, converting to local time - happens in the
 *     caller, so the firmware and the preview harness can each do it their own way and
 *     still produce the same pixels.
 *
 *     No Arduino headers: also compiled by the host preview harness.
 */

#ifndef ORBITAL_SENTINEL_RENDER_H
#define ORBITAL_SENTINEL_RENDER_H

#include <stdint.h>

/// A plain RGB565 framebuffer. `px` is row-major, `w * h` entries.
struct Canvas {
  uint16_t *px;
  int w;
  int h;
};

/// One tracked object, drawn as a labelled satellite.
struct Station {
  double ecef[3];      //!< Earth-fixed position (km).
  uint16_t color;      //!< Body/label colour (RGB565).
  const char *label;   //!< Short label, uppercase (e.g. "ISS").
  bool valid;          //!< False if propagation failed; the station is skipped.
};

/// Everything needed to draw one frame. Fully resolved by the caller.
struct Scene {
  const Station *stations;
  int nStations;

  float azimuthDeg;    //!< Cosmetic camera spin about the polar axis.

  /// Ping animation phase for the home marker, 0..1. Wrap it yourself.
  float homePulse;

  const char *timeStr; //!< Big readout, already in LOCAL time (e.g. "14:32:07").
  const char *dateStr; //!< Small line, already local (e.g. "13 JUL 2026").
};

/**
 * @brief Build the static scene: coastline ECEF cloud, star field, home position.
 * @details Call once at boot. Lifts each baked lon/lat dot onto the sphere so the
 *          per-frame path is a rotate-and-project over a flat float array. The home
 *          location is fixed in the Earth-fixed frame, so it is resolved here too.
 */
void sceneInit();

/**
 * @brief Draw one complete frame into `c`.
 * @param c Target framebuffer (expected PANEL_W x PANEL_H).
 * @param s The scene to draw.
 */
void renderFrame(Canvas &c, const Scene &s);

#endif  // ORBITAL_SENTINEL_RENDER_H
