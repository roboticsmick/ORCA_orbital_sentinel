"""!
@file render_small.py
@brief Compact renderer that draws to a small native-resolution surface.
@details
    Produces a single Surface at the panel's real resolution (e.g. 240x240 for an
    ST7789 TFT) with no upscaling and no scanlines: on a physical low-resolution
    panel the chunkiness is intrinsic. It draws a mini dotted globe, the filtered
    objects, and labelled crosses for crewed stations, plus a one-line header and
    footer. The surface is returned, not shown; a DisplaySink handles output.

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
        rng = np.random.default_rng(3)
        n = (width * height) // 1400
        self.stars = np.stack((rng.integers(0, width, n),
                               rng.integers(0, height, n)), axis=1)

    def render(self, camera, coast_pts, sat_pts, station_rows, clock_str):
        """! @brief Draw one compact frame and return the panel Surface.
            @param camera Camera projecting ECEF km -> panel pixels.
            @param coast_pts (N,3) coastline ECEF array (km).
            @param sat_pts (M,3) satellite ECEF array (km).
            @param station_rows List of (row_index, label, color).
            @param clock_str Pre-formatted UTC string for the footer.
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
        self._draw_objects(camera, sat_pts, station_rows, r_earth_px, cx, cy)
        self._chrome(clock_str, len(station_rows))
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
        """! @brief Plot satellites as dots and stations as labelled crosses."""
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
                    self._cross(px[i], py[i], col, config.STATION_CROSS_ARM)
                    self.surface.blit(self.font.render(label, True, col),
                                      (int(px[i]) + 5, int(py[i]) - 6))
                continue
            if 0 <= px[i] < self.w and 0 <= py[i] < self.h:
                col = config.COL_SAT_FAR if occluded else config.COL_SAT
                self.surface.set_at((int(px[i]), int(py[i])), col)

    def _cross(self, lx, ly, col, arm):
        """! @brief Draw a small plus marker for a station."""
        x, y = int(lx), int(ly)
        pygame.draw.line(self.surface, col, (x - arm, y), (x + arm, y))
        pygame.draw.line(self.surface, col, (x, y - arm), (x, y + arm))

    def _chrome(self, clock_str, station_count):
        """! @brief Draw the minimal header and footer text."""
        self.surface.blit(self.font.render("ORCA", True, config.COL_HUD), (3, 2))
        footer = "{0}Z  OBJ {1}".format(clock_str, station_count)
        self.surface.blit(self.font.render(footer, True, config.COL_HUD_DIM),
                          (3, self.h - 14))
