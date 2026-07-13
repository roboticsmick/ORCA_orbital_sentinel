"""!
@file render.py
@brief Retro-LCD renderer: chunky pixel globe, CRT scanlines, and HUD overlay.
@details
    The scene (stars, dotted coastline, satellite swarm) is drawn into a small
    logical surface for a deliberately chunky look, then nearest-neighbour upscaled
    to the window. Crisp monospace HUD text is composited on top at full resolution,
    and a pre-baked scanline layer finishes the CRT aesthetic.

    Depth handling: points on the far hemisphere are dimmed; satellites passing
    behind the Earth disk are further dimmed to sell the sphere.

    This module is imported, not executed directly.
"""

import numpy as np
import pygame

from . import config
from .propagate import EARTH_RADIUS_KM


class Renderer:
    """! @brief Owns the window, surfaces, fonts, and all drawing."""

    def __init__(self, logical_w, logical_h, fullscreen=False):
        """! @brief Create the window and cached surfaces/fonts.
            @param logical_w Logical (pre-upscale) width in pixels.
            @param logical_h Logical (pre-upscale) height in pixels.
            @param fullscreen Present at native display resolution (SDL scales
                   the fixed WINDOW_W/H surface up to fit, so HUD/scanline
                   layout math elsewhere is unaffected).
        """
        pygame.init()
        pygame.display.set_caption("ORCA ORBITAL SENTINEL")
        flags = (pygame.FULLSCREEN | pygame.SCALED) if fullscreen else 0
        self.window = pygame.display.set_mode(
            (config.WINDOW_W, config.WINDOW_H), flags)
        self.lw, self.lh = logical_w, logical_h
        self.scene = pygame.Surface((logical_w, logical_h))
        self.scanlines = self._build_scanlines()
        self.stars = self._build_stars()
        self.font = pygame.font.SysFont("dejavusansmono,monospace", 15)
        self.font_sm = pygame.font.SysFont("dejavusansmono,monospace", 12)
        self.font_lg = pygame.font.SysFont("dejavusansmono,monospace", 22, bold=True)

    def _build_scanlines(self):
        """! @brief Pre-render a translucent horizontal-line overlay (window size)."""
        layer = pygame.Surface((config.WINDOW_W, config.WINDOW_H), pygame.SRCALPHA)
        for y in range(0, config.WINDOW_H, 3):        # Bounded by window height.
            pygame.draw.line(layer, (0, 0, 0, 70), (0, y), (config.WINDOW_W, y))
        return layer

    def _build_stars(self):
        """! @brief Fixed sparse starfield as an array of (x, y) logical pixels."""
        rng = np.random.default_rng(7)
        n = (self.lw * self.lh) // 900
        xs = rng.integers(0, self.lw, n)
        ys = rng.integers(0, self.lh, n)
        return np.stack((xs, ys), axis=1)

    def _to_window(self, lx, ly):
        """! @brief Scale a logical coordinate to window space."""
        return int(lx * config.LOGICAL_SCALE), int(ly * config.LOGICAL_SCALE)

    def draw_frame(self, camera, coast_pts, sat_pts, station_rows,
                   neo_rows, hud):
        """! @brief Render one complete frame to the window.
            @param camera Camera projecting ECEF km -> logical pixels.
            @param coast_pts (N,3) coastline ECEF array (km).
            @param sat_pts (M,3) satellite ECEF array (km).
            @param station_rows List of (row_index, label, color) for crewed
                   stations to draw as labelled crosses.
            @param neo_rows Iterable of NeoRow for the Sentry panel.
            @param hud Dict of HUD fields (clock, counts, source, bands).
        """
        self.scene.fill(config.COL_BACKGROUND)
        r_earth_px = camera.earth_radius_px(EARTH_RADIUS_KM)

        self._draw_stars()
        self._draw_limb(r_earth_px)
        self._draw_cloud(coast_pts, camera, r_earth_px,
                         config.COL_COAST, config.COL_COAST_FAR, size=1)
        drawn_stations = self._draw_satellites(sat_pts, camera, r_earth_px,
                                               station_rows)

        # Upscale the chunky scene, then composite crisp overlays.
        pygame.transform.scale(self.scene, self.window.get_size(), self.window)
        self._draw_globe_labels(drawn_stations)
        self._draw_hud(hud, neo_rows)
        self.window.blit(self.scanlines, (0, 0))
        pygame.display.flip()

    def _draw_limb(self, r_earth_px):
        """! @brief Draw a faint circle at the Earth's silhouette (the limb)."""
        center = (int(self.lw / 2.0), int(self.lh / 2.0))
        pygame.draw.circle(self.scene, config.COL_GRID, center,
                           int(r_earth_px), 1)

    def _draw_stars(self):
        """! @brief Plot the static starfield onto the scene surface."""
        for x, y in self.stars:                       # Bounded: fixed star count.
            self.scene.set_at((int(x), int(y)), config.COL_STAR)

    def _draw_cloud(self, pts, camera, r_earth_px, near_col, far_col, size):
        """! @brief Project and plot a point cloud with front/back shading.
            @param pts (K,3) ECEF array (km).
            @param camera Active camera.
            @param r_earth_px Projected Earth radius (logical px).
            @param near_col Colour for the near hemisphere.
            @param far_col Colour for the far hemisphere.
            @param size Dot size in logical pixels.
        """
        if pts.shape[0] == 0:
            return
        px, py, depth = camera.project_many(pts)
        for i in range(px.shape[0]):                  # Bounded by cloud size (capped).
            col = near_col if depth[i] >= 0 else far_col
            self._dot(px[i], py[i], col, size)

    def _draw_satellites(self, pts, camera, r_earth_px, station_rows):
        """! @brief Plot satellites with globe occlusion; cross-mark stations.
            @param station_rows List of (row_index, label, color).
            @return Dict row_index -> (label, color, window_xy) for visible stations.
        """
        drawn = {}
        if pts.shape[0] == 0:
            return drawn
        station_map = {idx: (lbl, col) for idx, lbl, col in station_rows}
        px, py, depth = camera.project_many(pts)
        cx, cy = self.lw / 2.0, self.lh / 2.0
        for i in range(px.shape[0]):                  # Bounded by object cap.
            behind = depth[i] < 0
            radial = ((px[i] - cx) ** 2 + (py[i] - cy) ** 2) ** 0.5
            occluded = behind and radial < r_earth_px
            if i in station_map:
                label, col = station_map[i]
                if not occluded:
                    self._cross(px[i], py[i], col, config.STATION_CROSS_ARM)
                    drawn[i] = (label, col, self._to_window(px[i], py[i]))
                continue
            col = config.COL_SAT_FAR if occluded else config.COL_SAT
            self._dot(px[i], py[i], col, 1)
        return drawn

    def _cross(self, lx, ly, col, arm):
        """! @brief Draw a small plus-shaped marker on the scene surface."""
        x, y = int(lx), int(ly)
        pygame.draw.line(self.scene, col, (x - arm, y), (x + arm, y))
        pygame.draw.line(self.scene, col, (x, y - arm), (x, y + arm))

    def _dot(self, lx, ly, col, size):
        """! @brief Draw a small filled dot on the scene, clipped to bounds."""
        x, y = int(lx), int(ly)
        if x < 0 or y < 0 or x >= self.lw or y >= self.lh:
            return
        if size <= 1:
            self.scene.set_at((x, y), col)
        else:
            self.scene.fill(col, (x, y, size, size))

    def _draw_globe_labels(self, drawn_stations):
        """! @brief Draw a tag beside each visible station cross.
            @param drawn_stations Dict row_index -> (label, color, window_xy).
        """
        for _idx, (label, col, win) in drawn_stations.items():
            self._text(label[:16], (win[0] + 6, win[1] - 6),
                       self.font_sm, col)

    def _draw_hud(self, hud, neo_rows):
        """! @brief Composite the title, telemetry, NEO panel, and band bar."""
        self._text("ORCA ORBITAL SENTINEL", (14, 10),
                   self.font_lg, config.COL_HUD)
        self._text("LIVE SATELLITE + NEO TRACKING", (16, 36),
                   self.font_sm, config.COL_HUD_DIM)

        lines = (
            "UTC   {0}".format(hud["clock"]),
            "TRACK {0:>5d}   VIS {1:>5d}".format(hud["tracked"], hud["visible"]),
            "SRC   {0}".format(hud["source"]),
        )
        for i, line in enumerate(lines):              # Bounded: fixed line set.
            self._text(line, (16, 60 + i * 18), self.font_sm, config.COL_HUD)

        self._draw_neo_panel(neo_rows)
        self._draw_band_bar(hud["bands"])

    def _draw_neo_panel(self, neo_rows):
        """! @brief Right-aligned Sentry near-earth-object risk list."""
        x = config.WINDOW_W - 300
        self._text("SENTRY / NEO IMPACT RISK", (x, 10),
                   self.font_sm, config.COL_ALERT)
        header = "{0:<12}{1:>7}{2:>9}".format("DESIG", "D(km)", "P(imp)")
        self._text(header, (x, 30), self.font_sm, config.COL_HUD_DIM)
        for i, row in enumerate(neo_rows):            # Bounded by top_n.
            line = "{0:<12}{1:>7.3f}{2:>9.1e}".format(
                row.des[:12], row.diameter_km, row.impact_prob)
            self._text(line, (x, 48 + i * 16), self.font_sm, config.COL_HUD)

    def _draw_band_bar(self, bands):
        """! @brief Bottom bar with per-altitude-band object counts.
            @param bands Mapping of band label -> count.
        """
        y = config.WINDOW_H - 26
        x = 16
        for label, count in bands.items():            # Bounded: fixed band set.
            chunk = "{0} {1}".format(label, count)
            self._text(chunk, (x, y), self.font_sm, config.COL_HUD)
            x += 12 + self.font_sm.size(chunk)[0] + 18

    def _text(self, string, pos, font, col):
        """! @brief Blit a line of text at a window-space position."""
        self.window.blit(font.render(string, True, col), pos)
