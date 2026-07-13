"""!
@file app.py
@brief Application entry point: wires data, the simulation loop, and rendering.
@details
    Loads the tracked-object set and Sentry rows once at startup, then runs a fixed
    loop: advance simulated time (accelerated), propagate every object to ECEF,
    derive HUD statistics, spin the camera, and draw. Physics uses real UTC scaled
    by TIME_ACCELERATION; the camera spin is cosmetic and never affects positions.

    Example:
        python -m orca_orbital_sentinel
        python run.py
        ORCA_OFFLINE=1 python run.py       # skip network; cache/fallback only
"""

import datetime as _dt
import os
import sys

import numpy as np
import pygame

from . import config
from .camera import Camera
from .coastline import load_coastline_points
from . import filters
from .propagate import propagate_ecef, geodetic_to_ecef_unit, EARTH_RADIUS_KM
from .render import Renderer
from . import sentry
from . import tle_source


def _utc_now():
    """! @brief Current UTC as a timezone-naive datetime (SGP4 convention)."""
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def home_ecef():
    """! @brief The configured home location as an ECEF vector, or None.
        @return numpy [x, y, z] in km at the Earth's surface, or None if disabled.
    """
    if not config.HOME_ENABLED:
        return None
    return geodetic_to_ecef_unit(config.HOME_LON, config.HOME_LAT) \
        * EARTH_RADIUS_KM


def local_clock_strings():
    """! @brief Real wall-clock time and date in the machine's local timezone.
        @return Tuple (time_str, date_str), e.g. ("15:32:47", "13 JUL 2026").
    @details Deliberately NOT the simulated clock: TIME_ACCELERATION may be running
             the orbits far ahead of real time, but the readout a person checks has
             to be true.
    """
    now = _dt.datetime.now()
    return now.strftime("%H:%M:%S"), now.strftime("%d %b %Y").upper()


def ping_phase():
    """! @brief Home-marker ping phase in [0, 1), driven by real elapsed time."""
    period = max(0.1, config.HOME_PING_PERIOD_S)
    return (_dt.datetime.now().timestamp() % period) / period


def _classify_bands(alt_km):
    """! @brief Map an altitude to a coarse orbital band label.
        @param alt_km Altitude above mean Earth radius (km).
        @return One of "LEO", "MEO", "GEO", "OTHER".
    """
    if alt_km < 2000.0:
        return "LEO"
    if alt_km < 34000.0:
        return "MEO"
    if alt_km < 37000.0:
        return "GEO"
    return "OTHER"


def _propagate_all(objects, sim_dt):
    """! @brief Propagate every object; build parallel position/meta structures.
        @param objects List of TrackedObject.
        @param sim_dt Simulated UTC datetime.
        @return (pts, station_rows, bands) where pts is an (M,3) array and
                station_rows is a list of (row_index, label, color).
    """
    positions = []
    station_rows = []
    bands = {"LEO": 0, "MEO": 0, "GEO": 0, "OTHER": 0}

    for obj in objects:                            # Bounded by MAX_OBJECTS.
        ecef = propagate_ecef(obj.satrec, sim_dt)
        if ecef is None:
            continue
        row = len(positions)
        if obj.norad in config.STATION_LABELS:
            station_rows.append((
                row,
                config.STATION_LABELS[obj.norad],
                config.STATION_COLORS.get(obj.norad, config.COL_ISS),
            ))
        bands[_classify_bands(float(np.linalg.norm(ecef)) - EARTH_RADIUS_KM)] += 1
        positions.append(ecef)

    pts = np.asarray(positions, dtype=np.float64) if positions \
        else np.zeros((0, 3), dtype=np.float64)
    return pts, station_rows, bands


def build_context(allow_network):
    """! @brief Assemble the static scene inputs (objects, coastline, NEO rows).
        @param allow_network If False, skip all live fetches.
        @return Dict with keys: objects, source, coast, neo_rows, neo_source.
    """
    now = _utc_now()
    objects, source = tle_source.load_objects(now, allow_network)
    objects = filters.apply(objects, now, filters.from_config())
    neo_rows, neo_source = sentry.load_neo_rows(allow_network=allow_network)
    return {
        "objects": objects,
        "source": source,
        "coast": load_coastline_points(),
        "neo_rows": neo_rows,
        "neo_source": neo_source,
    }


def run(allow_network=True, fullscreen=False, screensaver=False):
    """! @brief Start the display and run until the user quits.
        @param allow_network If False, run purely from cache/fallback/demo data.
        @param fullscreen Present at native display resolution.
        @param screensaver Exit immediately on any key press or mouse activity,
               instead of Space toggling pause (for use as an idle-time visual).
    """
    ctx = build_context(allow_network)

    # The renderer sizes itself: in fullscreen it takes the monitor's native
    # resolution (rather than letterboxing a fixed 1000x640 surface, which would
    # leave pure-black bars that do not match COL_BACKGROUND). So the camera has to
    # be built from the size it actually chose, not from the config constants.
    renderer = Renderer(fullscreen=fullscreen or screensaver)
    lw, lh = renderer.lw, renderer.lh
    scale = config.GLOBE_RADIUS_FRAC * min(lw, lh) / EARTH_RADIUS_KM

    camera = Camera(lw / 2.0, lh / 2.0, scale, config.VIEW_TILT_DEG)
    clock = pygame.time.Clock()
    home = home_ecef()

    sim_time = _utc_now()
    azimuth = 0.0
    paused = False
    running = True

    while running:
        real_dt = clock.tick(config.TARGET_FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif screensaver and event.type in (
                    pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION):
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused

        if not paused:
            sim_time += _dt.timedelta(
                seconds=real_dt * config.TIME_ACCELERATION)
            azimuth = (azimuth + config.SPIN_DEG_PER_SEC * real_dt) % 360.0

        camera.set_azimuth(azimuth)
        pts, station_rows, bands = _propagate_all(ctx["objects"], sim_time)

        visible = 0
        if pts.shape[0] > 0:
            _px, _py, depth = camera.project_many(pts)
            visible = int(np.count_nonzero(depth >= 0.0))

        local_time, local_date = local_clock_strings()
        hud = {
            "clock": sim_time.strftime("%Y-%m-%d %H:%M:%S"),
            "local_time": local_time,
            "local_date": local_date,
            "tracked": len(ctx["objects"]),
            "visible": visible,
            "source": ctx["source"],
            "bands": bands,
        }
        renderer.draw_frame(camera, ctx["coast"], pts, station_rows,
                            ctx["neo_rows"], hud,
                            home_ecef=home, home_pulse=ping_phase())

    pygame.quit()


def main():
    """! @brief CLI wrapper: honours --small, --fullscreen, --screensaver, ORCA_OFFLINE."""
    allow_network = os.environ.get("ORCA_OFFLINE", "0") != "1"
    screensaver = "--screensaver" in sys.argv \
        or os.environ.get("ORCA_SCREENSAVER", "0") == "1"
    fullscreen = screensaver or "--fullscreen" in sys.argv \
        or os.environ.get("ORCA_FULLSCREEN", "0") == "1"
    if "--small" in sys.argv:
        from .app_small import run_small
        return run_small(allow_network=allow_network)
    run(allow_network=allow_network, fullscreen=fullscreen, screensaver=screensaver)
    return 0


if __name__ == "__main__":
    sys.exit(main())
