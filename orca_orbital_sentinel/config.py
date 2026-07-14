"""!
@file config.py
@brief Central configuration: window, palette, timing, and data-source tunables.
@details
    All user-facing knobs live here so the rest of the package contains no magic
    numbers. Values are plain module-level constants (no runtime mutation), which
    keeps state flow trivial to reason about.

    This module is imported, not executed directly.
"""

import os

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

# --- Themes -----------------------------------------------------------------
# Pick a palette. Override without editing this file:  ORCA_THEME=cyberpunk python run.py
#
#   "retro"     phosphor green on near-black. The original CRT look.
#   "cyberpunk" hot pink and cyan on deep navy. Neon-noir.
#
# A theme is just a dict of the COL_* names below, so adding a third is a matter of
# copying one and changing the values - no renderer code knows a theme exists.
THEME = os.environ.get("ORCA_THEME", "retro").strip().lower()

THEMES = {
    # ---------------------------------------------------------------- retro --
    "retro": {
        "BACKGROUND": (4, 8, 6),
        "STAR": (40, 60, 55),
        "COAST": (0, 170, 120),      # Dotted continents (near side).
        "COAST_FAR": (0, 55, 45),    # Far hemisphere, dimmed for depth.
        "SAT": (90, 230, 255),       # Generic satellite dot (near side).
        "SAT_FAR": (30, 70, 90),     # Satellite occluded behind the globe.
        "HUD": (0, 220, 150),        # Primary HUD text.
        "HUD_DIM": (0, 110, 80),     # Secondary HUD text.
        "ALERT": (255, 90, 70),      # Sentry / warning accents.
        "GRID": (0, 40, 32),         # The Earth's limb circle.
        "LED": (220, 240, 255),      # Clock, date, and both crewed stations.
        "HOME": (255, 190, 40),      # Your location: amber.
        "HOME_PING": (150, 110, 20),  # The expanding ring, dimmer than the dot.
    },
    # ------------------------------------------------------------ cyberpunk --
    # Neon-noir: hot pink continents, cyan readout, magenta-purple alerts, and a
    # yellow home marker, all on deep navy. The "far side" tones are the same hues
    # crushed towards the background, so the sphere still reads as a sphere - depth
    # comes from value, not from hue.
    "cyberpunk": {
        "BACKGROUND": (9, 24, 51),    # #091833
        "STAR": (70, 100, 150),       # Cool haze, so stars sit behind the neon.
        "COAST": (255, 0, 122),       # #ff007a hot pink.
        "COAST_FAR": (92, 16, 62),    # Hot pink crushed toward the navy.
        "SAT": (0, 255, 179),         # #00ffb3 neon green.
        "SAT_FAR": (10, 90, 78),      # Neon green, far side.
        "HUD": (255, 0, 122),         # #ff007a.
        "HUD_DIM": (150, 30, 95),     # Muted pink for secondary text.
        "ALERT": (167, 0, 255),       # #a700ff magenta-purple.
        "GRID": (60, 30, 75),         # Limb circle: a faint violet.
        "LED": (52, 237, 243),        # #34edf3 cyan: clock, date, stations.
        "HOME": (255, 234, 0),        # #ffea00 yellow.
        "HOME_PING": (140, 128, 10),  # Yellow, dimmed for the ring.
    },
}

if THEME not in THEMES:
    raise ValueError(
        "Unknown ORCA_THEME {0!r}; expected one of {1}".format(
            THEME, ", ".join(sorted(THEMES))))

_P = THEMES[THEME]

# --- Palette (R, G, B) ------------------------------------------------------
# Resolved from the active theme. The renderers only ever see these names, which is
# why a theme swap needs no changes anywhere else.
COL_BACKGROUND = _P["BACKGROUND"]
COL_STAR = _P["STAR"]
COL_COAST = _P["COAST"]          #!< Dotted continents (near side).
COL_COAST_FAR = _P["COAST_FAR"]  #!< Continents on the far hemisphere (dimmed for depth).
COL_SAT = _P["SAT"]              #!< Satellite dot (near side).
COL_SAT_FAR = _P["SAT_FAR"]      #!< Satellite occluded/behind globe.
COL_HUD = _P["HUD"]              #!< Primary HUD text.
COL_HUD_DIM = _P["HUD_DIM"]      #!< Secondary HUD text.
COL_ALERT = _P["ALERT"]          #!< Sentry / warning accents.
COL_GRID = _P["GRID"]            #!< The Earth's limb circle.

# One "LED" colour shared by the clock, the date, and both crewed stations, so the
# readout reads as a single instrument. The stations are told apart by their labels,
# not their colour; give COL_ISS/COL_CSS distinct values to tell them apart at a
# glance instead.
COL_LED = _P["LED"]
COL_CLOCK = COL_LED              #!< Big local-time readout above the globe.
COL_DATE = COL_LED               #!< Date line under the clock.
COL_ISS = COL_LED                #!< International Space Station marker.
COL_CSS = COL_LED                #!< Tiangong / Chinese Space Station marker.

# Your location: a colour used for nothing else, so it never reads as "a satellite".
COL_HOME = _P["HOME"]
COL_HOME_PING = _P["HOME_PING"]  #!< Dimmer: the expanding ring.

# --- Space stations ---------------------------------------------------------
# Crewed stations are drawn as a labelled satellite (body + solar panels) rather than
# a dot. NORAD ids:
#   25544 -> ISS (ZARYA)      51.6 deg-inclined ~420 km
#   48274 -> CSS (TIANHE)     Tiangong core module
STATION_LABELS = {25544: "ISS", 48274: "CSS"}
STATION_COLORS = {25544: COL_ISS, 48274: COL_CSS}

# --- Your location ----------------------------------------------------------
# Marked on the globe with a dot that pings - an expanding ring - whenever the Earth's
# rotation brings it onto the visible hemisphere. Set HOME_ENABLED to False to turn it
# off. South and west are NEGATIVE. Defaults to Brisbane, Australia.
HOME_ENABLED = True
HOME_LAT = -27.4698              #!< Degrees north; negative for south.
HOME_LON = 153.0251              #!< Degrees east; negative for west.
HOME_PING_PERIOD_S = 2.5         #!< Seconds for one full expanding ring.

# --- Clock ------------------------------------------------------------------
# The big local date/time above the globe. This always reads REAL wall-clock time in
# your machine's local timezone, even when TIME_ACCELERATION runs the orbits fast -
# a clock that lies is useless.
CLOCK_ENABLED = True
CLOCK_FONT_PX = 46               #!< Time readout height.
DATE_FONT_PX = 18                #!< Date line height.

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
