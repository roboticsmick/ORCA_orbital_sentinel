"""!
@file render_small.py
@brief Compact renderer that draws to a small native-resolution surface.
@details
    Produces a single Surface at the panel's real resolution (e.g. 240x240 for an
    ST7789 TFT) with no upscaling and no scanlines: on a physical low-resolution
    panel the chunkiness is intrinsic. It draws a mini dotted globe, the filtered
    objects, labelled satellite icons for crewed stations, a home marker that pings,
    and a centred local clock/date. Chrome is centred rather than corner-anchored so
    the same layout survives on a round bezel, which has no corners.

    The surface is returned, not shown; a DisplaySink handles output.

    This module is imported, not executed directly.
"""

import numpy as np
import pygame

from . import config
from .propagate import EARTH_RADIUS_KM


class SmallRenderer:
    """! @brief Renders the compact view into an offscreen Surface."""

    def __init__(self, width, height, coast_stride=2):
        """! @brief Prepare surface, fonts, and a decimated star field.
            @param width Panel width in pixels.
            @param height Panel height in pixels.
            @param coast_stride Keep every Nth coastline dot (declutter tiny screens).
        """
        pygame.init()
        pygame.font.init()
        self.w, self.h = width, height
        self.surface = pygame.Surface((width, height))
        self.coast_stride = max(1, int(coast_stride))
        self.font = pygame.font.SysFont("dejavusansmono,monospace", 11)
        # The panel is a clock first, so the time gets a font you can read across
        # a room; the date stays quiet underneath.
        self.font_clock = pygame.font.SysFont(
            "dejavusansmono,monospace", 24, bold=True)
        rng = np.random.default_rng(3)
        n = (width * height) // 1400
        self.stars = np.stack((rng.integers(0, width, n),
                               rng.integers(0, height, n)), axis=1)

    def render(self, camera, coast_pts, sat_pts, station_rows, clock_str,
               home_ecef=None, home_pulse=0.0, local_time=None,
               local_date=None):
        """! @brief Draw one compact frame and return the panel Surface.
            @param camera Camera projecting ECEF km -> panel pixels.
            @param coast_pts (N,3) coastline ECEF array (km).
            @param sat_pts (M,3) satellite ECEF array (km).
            @param station_rows List of (row_index, label, color).
            @param clock_str Pre-formatted UTC string (unused when local_time is set).
            @param home_ecef Length-3 ECEF vector for the viewer's location, or None.
            @param home_pulse Ping animation phase in [0, 1).
            @param local_time Real local time for the headline readout ("15:32:47").
            @param local_date Real local date for the sub-line ("13 JUL 2026").
            @return pygame.Surface at panel resolution.
        """
        surf = self.surface
        surf.fill(config.COL_BACKGROUND)
        r_earth_px = camera.earth_radius_px(EARTH_RADIUS_KM)
        cx, cy = self.w / 2.0, self.h / 2.0

        for x, y in self.stars:                        # Bounded: fixed count.
            surf.set_at((int(x), int(y)), config.COL_STAR)
        pygame.draw.circle(surf, config.COL_GRID, (int(cx), int(cy)),
                           int(r_earth_px), 1)

        self._draw_coast(camera, coast_pts)
        self._draw_home(camera, home_ecef, home_pulse)
        self._draw_objects(camera, sat_pts, station_rows, r_earth_px, cx, cy)
        self._chrome(local_time or clock_str, local_date)
        return surf

    def _draw_coast(self, camera, coast_pts):
        """! @brief Plot decimated coastline dots with front/back shading."""
        if coast_pts.shape[0] == 0:
            return
        pts = coast_pts[::self.coast_stride]
        px, py, depth = camera.project_many(pts)
        for i in range(px.shape[0]):                   # Bounded by decimated size.
            if 0 <= px[i] < self.w and 0 <= py[i] < self.h:
                col = config.COL_COAST if depth[i] >= 0 else config.COL_COAST_FAR
                self.surface.set_at((int(px[i]), int(py[i])), col)

    def _draw_objects(self, camera, pts, station_rows, r_earth_px, cx, cy):
        """! @brief Plot satellites as dots and stations as labelled satellites."""
        if pts.shape[0] == 0:
            return
        station_map = {idx: (lbl, col) for idx, lbl, col in station_rows}
        px, py, depth = camera.project_many(pts)
        for i in range(px.shape[0]):                   # Bounded by object cap.
            behind = depth[i] < 0
            radial = ((px[i] - cx) ** 2 + (py[i] - cy) ** 2) ** 0.5
            occluded = behind and radial < r_earth_px
            if i in station_map:
                label, col = station_map[i]
                if not occluded:
                    self._satellite(px[i], py[i], col)
                    self.surface.blit(self.font.render(label, True, col),
                                      (int(px[i]) + 8, int(py[i]) - 6))
                continue
            if 0 <= px[i] < self.w and 0 <= py[i] < self.h:
                col = config.COL_SAT_FAR if occluded else config.COL_SAT
                self.surface.set_at((int(px[i]), int(py[i])), col)

    def _satellite(self, lx, ly, col):
        """! @brief Draw a satellite: a body with two solar panels on booms."""
        x, y = int(lx), int(ly)
        self.surface.fill(col, (x - 1, y - 1, 3, 3))   # Body.
        self.surface.fill(col, (x - 2, y, 1, 1))       # Booms.
        self.surface.fill(col, (x + 2, y, 1, 1))
        self.surface.fill(col, (x - 5, y - 2, 2, 5))   # Left solar panel.
        self.surface.fill(col, (x + 4, y - 2, 2, 5))   # Right solar panel.

    def _draw_home(self, camera, home_ecef, pulse):
        """! @brief Draw the home marker (a dot) and its ping while it faces the viewer.
        @details The home point sits ON the sphere, so the near hemisphere is all the
                 visibility test needed - no disk-occlusion check.

                 Just a dot: the expanding ring is what draws the eye and what tells it
                 apart from a satellite.
        """
        if home_ecef is None:
            return
        px, py, depth = camera.project(home_ecef)
        if depth < 0:
            return
        pygame.draw.circle(self.surface, config.COL_HOME_PING,
                           (int(px), int(py)), int(3 + pulse * 9.0), 1)
        self.surface.fill(config.COL_HOME, (int(px) - 1, int(py) - 1, 3, 3))

    def _chrome(self, time_str, date_str):
        """! @brief Draw the centred clock and date.
        @details Centred, not corner-anchored: this layout also has to survive on a
                 round bezel, where there are no corners.
        """
        cx = self.w // 2
        tsurf = self.font_clock.render(time_str, True, config.COL_CLOCK)
        self.surface.blit(tsurf, (cx - tsurf.get_width() // 2, 6))
        if date_str:
            dsurf = self.font.render(date_str, True, config.COL_DATE)
            self.surface.blit(dsurf,
                              (cx - dsurf.get_width() // 2, self.h - 18))
