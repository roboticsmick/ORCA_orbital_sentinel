/**
 * @file config.h
 * @brief Central configuration: panel, palette, clock, home location, data sources.
 * @details
 *     Mirrors orca_orbital_sentinel/config.py for the round-panel build, so the two
 *     implementations stay recognisably the same program. Names match the Python
 *     constants wherever a direct equivalent exists.
 *
 *     Deliberately free of Arduino headers: this file is included by both the
 *     firmware and the host preview harness (tools/preview).
 *
 *     THIS IS THE FILE TO EDIT to make the display your own - your city, your
 *     timezone, your colours.
 */

#ifndef ORBITAL_SENTINEL_CONFIG_H
#define ORBITAL_SENTINEL_CONFIG_H

#include <stdint.h>

// --- Panel ------------------------------------------------------------------
// The Seeed Round Display is a 240x240 GC9A01 with a circular bezel: the corners of
// the square framebuffer are physically not visible. PANEL_RADIUS is the usable
// disc, and all chrome is laid out inside it.
#define PANEL_W 240              //!< Panel width in pixels.
#define PANEL_H 240              //!< Panel height in pixels.
#define PANEL_RADIUS 120         //!< Visible disc radius (px). Corners are masked.

// Which way up the panel is mounted. Each step is 90 degrees:
//   0 = as-shipped (USB-C to the right)   2 = upside down
//   3 = 90 degrees anticlockwise          1 = 90 degrees clockwise
// This is a display-controller setting, so it rotates the whole image and costs
// nothing per frame. The panel is square and the bezel mask is symmetric, so no
// layout changes with it - only which edge the USB-C connector ends up on.
//
// 3 is confirmed anticlockwise on real hardware. If you want the other direction,
// 1 is its opposite.
//
// The host preview harness ignores this: it dumps the framebuffer before the panel
// applies the rotation, so previews always look like PANEL_ROTATION 0.
#define PANEL_ROTATION 3

#define TARGET_FPS 30            //!< Frame-rate cap.

// --- Your location ----------------------------------------------------------
// Your spot on the globe. It is drawn as a marker that pings - an expanding ring -
// whenever the Earth's rotation brings it round onto the visible hemisphere, so you
// can see when you are "under" the satellites.
//
// Get your coordinates from any maps app: south and west are NEGATIVE.
// Defaults to Brisbane, Australia. Drawn as a dot with an expanding ping ring - the
// ring is what catches the eye, so an icon or a label would only add clutter.
#define HOME_ENABLED 1
#define HOME_LAT -27.4698f       //!< Degrees north; negative for south.
#define HOME_LON 153.0251f       //!< Degrees east; negative for west.

// --- Your timezone ----------------------------------------------------------
// A POSIX TZ string. The panel is a clock, so this drives what you actually read.
// The sign is INVERTED from what you expect: UTC+10 is written "-10".
//
//   Brisbane (UTC+10, no DST)     "AEST-10"
//   Sydney/Melbourne (with DST)   "AEST-10AEDT,M10.1.0,M4.1.0/3"
//   UK                            "GMT0BST,M3.5.0/1,M10.5.0"
//   US Eastern                    "EST5EDT,M3.2.0,M11.1.0"
//   US Pacific                    "PST8PDT,M3.2.0,M11.1.0"
//   Central Europe                "CET-1CEST,M3.5.0,M10.5.0/3"
//   UTC (no conversion)           "UTC0"
#define TZ_POSIX "AEST-10"

// --- Simulation timing ------------------------------------------------------
// 1.0 = real time: the stations are where they actually are right now, and the
// clock you read agrees with the globe you see. Raise it (the desktop small-screen
// mode uses 90) for a fast "screensaver" orbit - about one pass a minute - but note
// that this decouples the globe from the clock, which keeps showing real wall time.
#define TIME_ACCELERATION 1.0f   //!< Simulated seconds per real second.
#define SPIN_DEG_PER_SEC 3.0f    //!< Cosmetic camera spin (does not alter physics).
#define VIEW_TILT_DEG 18.0f      //!< Fixed downward tilt onto the northern hemisphere.

// Earth radius as a fraction of the panel. Larger than the desktop's 0.30 because a
// round panel has no corners to fill and no side HUD to leave room for.
#define GLOBE_RADIUS_FRAC 0.34f

/// Seconds for one full home-marker ping (expanding ring).
#define HOME_PING_PERIOD_S 2.5f

// --- Theme ------------------------------------------------------------------
// 0 = RETRO      phosphor green on near-black. The original CRT look.
// 1 = CYBERPUNK  hot pink and cyan on deep navy. Neon-noir.
//
// Compile-time, so the unused palette costs nothing in flash. (The host preview
// harness takes --theme and passes -DORCA_THEME here, so you can compare the two
// without reflashing.)
#ifndef ORCA_THEME
#define ORCA_THEME 1
#endif

#define THEME_RETRO 0
#define THEME_CYBERPUNK 1

// RGB565() converts 8-bit-per-channel to the panel's 16-bit format; the low bits are
// dropped, which is why the preview harness quantises identically - what you see in
// tools/preview is what the panel shows.
#define RGB565(r, g, b) \
  ((uint16_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))

#if ORCA_THEME == THEME_CYBERPUNK

// Neon-noir. The "far side" tones are the same hues crushed towards the background,
// so the sphere still reads as a sphere - depth comes from value, not from hue.
#define COL_BACKGROUND RGB565(9, 24, 51)     //!< #091833 deep navy.
#define COL_STAR       RGB565(70, 100, 150)  //!< Cool haze, sits behind the neon.
#define COL_COAST      RGB565(255, 0, 122)   //!< #ff007a hot pink.
#define COL_COAST_FAR  RGB565(92, 16, 62)    //!< Hot pink crushed toward the navy.
#define COL_GRID       RGB565(60, 30, 75)    //!< Earth limb circle: faint violet.
#define COL_LED        RGB565(52, 237, 243)  //!< #34edf3 cyan.
#define COL_HOME       RGB565(255, 234, 0)   //!< #ffea00 yellow.
#define COL_HOME_PING  RGB565(140, 128, 10)  //!< Yellow, dimmed for the ring.

#else  // THEME_RETRO

#define COL_BACKGROUND RGB565(4, 8, 6)
#define COL_STAR       RGB565(40, 60, 55)
#define COL_COAST      RGB565(0, 170, 120)   //!< Continents, near side.
#define COL_COAST_FAR  RGB565(0, 55, 45)     //!< Continents, far hemisphere (dimmed).
#define COL_GRID       RGB565(0, 40, 32)     //!< Earth limb circle.
#define COL_LED        RGB565(220, 240, 255) //!< Pale blue.
#define COL_HOME       RGB565(255, 190, 40)  //!< Amber.
#define COL_HOME_PING  RGB565(150, 110, 20)  //!< Dimmer: the expanding ring.

#endif  // ORCA_THEME

// One "LED" colour shared by the clock, the date, and both stations, so the whole
// readout reads as a single instrument. The stations are told apart by their labels,
// not their colour. Give COL_ISS / COL_CSS distinct values if you would rather tell
// them apart at a glance.
#define COL_CLOCK      COL_LED               //!< The big time readout.
#define COL_DATE       COL_LED               //!< The date line.
#define COL_ISS        COL_LED               //!< International Space Station.
#define COL_CSS        COL_LED               //!< Tiangong / Chinese Space Station.

// --- Tracked objects --------------------------------------------------------
// SMALL_INCLUDE_IDS in config.py: the two crewed stations. Hundreds of on-device SGP4
// propagations per frame will not hold frame-rate on an S3, so the round build tracks
// exactly these and draws them as labelled satellites.
#define ISS_NORAD_ID 25544
#define CSS_NORAD_ID 48274
#define MAX_OBJECTS 4            //!< Hard cap on tracked objects (bounds per-frame work).

// --- Clock chrome -----------------------------------------------------------
#define CLOCK_TEXT_SCALE 2       //!< Time readout: 2x the 5x7 font => a clear 10x14.
#define DATE_TEXT_SCALE 1        //!< Date line: the base 5x7.

// --- Star field -------------------------------------------------------------
#define STAR_COUNT 41            //!< (PANEL_W * PANEL_H) / 1400, as in render_small.py.
#define STAR_SEED 3u             //!< Fixed seed => the same sky every boot.

// --- Data sources -----------------------------------------------------------
// CelesTrak's "stations" group is a handful of TLEs (a few KB), so the S3 can hold and
// parse it comfortably. CelesTrak refreshes roughly every 2 hours and firewalls
// abusive pollers: do not lower TLE_REFRESH_S without reason.
#define CELESTRAK_URL \
  "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"
#define TLE_REFRESH_S (6 * 3600)  //!< Seconds between live refetches (6 h).
#define HTTP_TIMEOUT_MS 15000

#define SNTP_SERVER_1 "pool.ntp.org"
#define SNTP_SERVER_2 "time.nist.gov"

#endif  // ORBITAL_SENTINEL_CONFIG_H
