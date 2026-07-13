"""!
@file config.py
@brief Central configuration: window, palette, timing, and data-source tunables.
@details
    All user-facing knobs live here so the rest of the package contains no magic
    numbers. Values are plain module-level constants (no runtime mutation), which
    keeps state flow trivial to reason about.

    This module is imported, not executed directly.
"""

# --- Window / rendering -----------------------------------------------------
WINDOW_W = 1000              #!< Window width in pixels.
WINDOW_H = 640               #!< Window height in pixels.
LOGICAL_SCALE = 2            #!< Downsample factor; scene is drawn at 1/N then upscaled (chunky pixels).
TARGET_FPS = 30              #!< Frame-rate cap.
GLOBE_RADIUS_FRAC = 0.30     #!< Earth radius as a fraction of min(window dimension).

# --- Simulation timing ------------------------------------------------------
TIME_ACCELERATION = 60.0     #!< Simulated seconds per real second (60 => one ISS orbit in ~90s).
SPIN_DEG_PER_SEC = 3.0       #!< Camera azimuth spin rate (visual only; does not alter physics).
VIEW_TILT_DEG = 18.0         #!< Fixed camera tilt so we look slightly down onto the northern hemisphere.

# --- Retro palette (R, G, B) ------------------------------------------------
COL_BACKGROUND = (4, 8, 6)
COL_STAR = (40, 60, 55)
COL_COAST = (0, 170, 120)        #!< Dotted continents (near side).
COL_COAST_FAR = (0, 55, 45)      #!< Continents on the far hemisphere (dimmed for depth).
COL_SAT = (90, 230, 255)         #!< Satellite dot (near side).
COL_SAT_FAR = (30, 70, 90)       #!< Satellite occluded/behind globe.
COL_ISS = (255, 190, 40)         #!< International Space Station marker.
COL_CSS = (255, 120, 60)         #!< Tiangong / Chinese Space Station marker.
COL_HUD = (0, 220, 150)          #!< Primary HUD text.
COL_HUD_DIM = (0, 110, 80)       #!< Secondary HUD text.
COL_ALERT = (255, 90, 70)        #!< Sentry / warning accents.
COL_GRID = (0, 40, 32)           #!< Optional graticule lines.

# --- Space stations ---------------------------------------------------------
# Crewed stations are drawn as a labelled cross rather than a dot. NORAD ids:
#   25544 -> ISS (ZARYA)      41.x deg-inclined ~420 km
#   48274 -> CSS (TIANHE)     Tiangong core module
STATION_LABELS = {25544: "ISS", 48274: "CSS"}
STATION_COLORS = {25544: COL_ISS, 48274: COL_CSS}
STATION_CROSS_ARM = 3            #!< Half-length of a station cross arm (logical px).

# --- Object filter (limits what is shown; also cuts per-frame work) ----------
# Any field left as None is ignored. Filtering runs once at load, so a tighter
# filter means fewer objects to propagate every frame -> a faster, lighter view.
FILTER_INCLUDE_IDS = None        #!< set of NORAD ids to keep exclusively, or None.
FILTER_EXCLUDE_IDS = frozenset() #!< set of NORAD ids to drop.
FILTER_NAME_CONTAINS = None      #!< keep only names containing this (case-insensitive).
FILTER_MIN_ALT_KM = None         #!< drop objects below this altitude.
FILTER_MAX_ALT_KM = None         #!< drop objects above this altitude.
FILTER_MAX_COUNT = None          #!< hard cap after other filters (keeps first N).

# --- Data sources -----------------------------------------------------------
# CelesTrak GP data. "visual" (~150 bright, well-spread objects) is the default:
# it looks good and is polite on bandwidth. Swap to "active", "starlink", or any
# CelesTrak group name for a denser swarm (mind their rate limits).
CELESTRAK_GROUP = "visual"
CELESTRAK_URL = (
    "https://celestrak.org/NORAD/elements/gp.php"
    "?GROUP={group}&FORMAT=tle"
)

# JPL CNEOS Sentry API (near-Earth object impact risk) for the side panel.
SENTRY_URL = "https://ssd-api.jpl.nasa.gov/sentry/"

# CelesTrak updates roughly every 2 hours and firewalls abusive pollers, so we
# never refresh faster than this. Sentry changes rarely; a daily cache is ample.
TLE_CACHE_TTL_S = 3 * 3600
SENTRY_CACHE_TTL_S = 24 * 3600
HTTP_TIMEOUT_S = 20

# NORAD catalog id of the ISS (ZARYA); used to highlight and label the station.
ISS_NORAD_ID = 25544

# Upper bound on tracked objects. A fixed cap keeps memory and per-frame work
# bounded regardless of how large a group the user selects.
MAX_OBJECTS = 2000

# --- Small / LCD display mode ------------------------------------------------
# Native panel resolution to render at. 240x240 suits common ST7789 TFTs; use
# 128x64 for an SSD1306 OLED (mono). SMALL_PREVIEW_SCALE only affects the
# desktop preview window, not the real panel.
SMALL_W = 240
SMALL_H = 240
SMALL_PREVIEW_SCALE = 3
SMALL_GROUP = "stations"         #!< CelesTrak group that contains ISS + CSS.
# Default small-screen view: just the two crewed stations.
SMALL_INCLUDE_IDS = frozenset({25544, 48274})
SMALL_TIME_ACCELERATION = 90.0   #!< Faster default: a station orbit in ~60 s.
