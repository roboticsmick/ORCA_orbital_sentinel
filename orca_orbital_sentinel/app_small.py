"""!
@file app_small.py
@brief Compact small-screen application: stations-focused view for LCD/OLED panels.
@details
    Loads the station group, filters it to the configured NORAD ids (default: the
    ISS and the Chinese CSS/Tiangong), and drives the SmallRenderer into whatever
    DisplaySink is selected (desktop preview or a real SPI panel). Because the set
    is tiny, the loop is light and time can run faster (SMALL_TIME_ACCELERATION).

    Example:
        python -m orca_orbital_sentinel --small                # desktop preview window
        ORCA_DISPLAY=spi python -m orca_orbital_sentinel --small   # real SPI panel
        ORCA_OFFLINE=1 python -m orca_orbital_sentinel --small     # no network
"""

import datetime as _dt

import pygame

from . import config
from . import filters
from . import hardware
from . import tle_source
from .app import _propagate_all, _utc_now, home_ecef, local_clock_strings, \
    ping_phase
from .camera import Camera
from .coastline import load_coastline_points
from .propagate import EARTH_RADIUS_KM
from .render_small import SmallRenderer


def _station_filter():
    """! @brief Filter restricting the view to the configured station ids.
        @return Filter instance keyed on SMALL_INCLUDE_IDS.
    """
    base = filters.from_config()
    return base._replace(include_ids=config.SMALL_INCLUDE_IDS)


def run_small(allow_network=True):
    """! @brief Run the compact station view until the user quits.
        @param allow_network If False, use cache/fallback/demo data only.
    """
    now = _utc_now()
    objects, source = tle_source.load_objects(
        now, allow_network, group=config.SMALL_GROUP)
    objects = filters.apply(objects, now, _station_filter())
    coast = load_coastline_points()

    scale = config.GLOBE_RADIUS_FRAC * min(config.SMALL_W, config.SMALL_H) \
        / EARTH_RADIUS_KM
    camera = Camera(config.SMALL_W / 2.0, config.SMALL_H / 2.0,
                    scale, config.VIEW_TILT_DEG)
    renderer = SmallRenderer(config.SMALL_W, config.SMALL_H)
    sink = hardware.make_sink()
    clock = pygame.time.Clock()
    home = home_ecef()

    sim_time = now
    azimuth = 0.0
    running = True

    while running:
        real_dt = clock.tick(config.TARGET_FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_ESCAPE, pygame.K_q):
                running = False

        sim_time += _dt.timedelta(
            seconds=real_dt * config.SMALL_TIME_ACCELERATION)
        azimuth = (azimuth + config.SPIN_DEG_PER_SEC * real_dt) % 360.0
        camera.set_azimuth(azimuth)

        pts, station_rows, _bands = _propagate_all(objects, sim_time)
        local_time, local_date = local_clock_strings()
        surface = renderer.render(
            camera, coast, pts, station_rows,
            sim_time.strftime("%H:%M:%S"),
            home_ecef=home, home_pulse=ping_phase(),
            local_time=local_time, local_date=local_date)
        sink.show(surface)

    sink.close()
    return 0
