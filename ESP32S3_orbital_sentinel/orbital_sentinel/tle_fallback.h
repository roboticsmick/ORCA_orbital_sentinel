/**
 * @file tle_fallback.h
 * @brief Baked-in element sets so the globe is never empty.
 * @details
 *     The last link in the same fallback chain the desktop uses (tle_source.py):
 *
 *         fresh NVS cache -> live CelesTrak fetch -> these baked-in TLEs
 *
 *     Used when there is no Wi-Fi, no cached download, and no working DNS. SGP4
 *     accuracy decays roughly a few km/day away from the epoch, so a station drawn
 *     from a months-old element set is visibly wrong in phase but still traces a
 *     plausible orbit - much better than a blank screen.
 *
 *     Refresh these occasionally:
 *         curl "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"
 *
 *     Captured 2026-07-13 from CelesTrak.
 */

#ifndef ORBITAL_SENTINEL_TLE_FALLBACK_H
#define ORBITAL_SENTINEL_TLE_FALLBACK_H

static const char *FALLBACK_TLE =
  "ISS (ZARYA)\n"
  "1 25544U 98067A   26194.12129675  .00004316  00000+0  86456-4 0  9991\n"
  "2 25544  51.6304 171.7447 0006685 289.3803  70.6462 15.48996109575778\n"
  "CSS (TIANHE)\n"
  "1 48274U 21035A   26193.33050829  .00000806  00000+0  14701-4 0  9997\n"
  "2 48274  41.4686 169.1964 0002428 290.9815  69.0763 15.58035041297092\n";

#endif  // ORBITAL_SENTINEL_TLE_FALLBACK_H
