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

    def __init__(self, fullscreen=False):
        """! @brief Create the window and cached surfaces/fonts.
            @param fullscreen Present at the monitor's native resolution.
        @details The renderer owns its own size, and exposes the logical (pre-upscale)
                 scene size as `lw`/`lh` so the caller can build a matching camera.

                 Fullscreen deliberately does NOT use pygame.SCALED. SCALED would
                 letterbox the fixed WINDOW_W x WINDOW_H surface to preserve its
                 aspect ratio, and SDL fills those bars with pure black (0,0,0) -
                 which does not match COL_BACKGROUND (a near-black green), so they
                 show up as mismatched columns down the sides. Taking the native
                 resolution and sizing the scene to it means there are no bars at all.
        """
        pygame.init()
        pygame.display.set_caption("ORCA ORBITAL SENTINEL")

        if fullscreen:
            sizes = pygame.display.get_desktop_sizes()
            size = sizes[0] if sizes else (config.WINDOW_W, config.WINDOW_H)
            self.window = pygame.display.set_mode(size, pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode(
                (config.WINDOW_W, config.WINDOW_H))

        # Trust the surface, not what we asked for: a window manager may hand back
        # something slightly different.
        self.win_w, self.win_h = self.window.get_size()
        self.lw = max(1, self.win_w // config.LOGICAL_SCALE)
        self.lh = max(1, self.win_h // config.LOGICAL_SCALE)

        # HUD text and its anchors are authored against WINDOW_H and scaled from
        # there. Without this, going fullscreen on a big monitor would leave the
        # chrome at its windowed pixel size - a postage-stamp HUD on a 4K screen -
        # because, unlike pygame.SCALED, presenting at the native resolution does not
        # magnify anything for us.
        self.ui = self.win_h / float(config.WINDOW_H)

        self.scene = pygame.Surface((self.lw, self.lh))
        self.scanlines = self._build_scanlines()
        self.stars = self._build_stars()
        self.font = pygame.font.SysFont(
            "dejavusansmono,monospace", self._s(15))
        self.font_sm = pygame.font.SysFont(
            "dejavusansmono,monospace", self._s(12))
        self.font_lg = pygame.font.SysFont(
            "dejavusansmono,monospace", self._s(22), bold=True)
        self.font_clock = pygame.font.SysFont(
            "dejavusansmono,monospace", self._s(config.CLOCK_FONT_PX), bold=True)
        self.font_date = pygame.font.SysFont(
            "dejavusansmono,monospace", self._s(config.DATE_FONT_PX))

    def _s(self, value):
        """! @brief Scale a HUD length authored at WINDOW_H to the real display."""
        return max(1, int(round(value * self.ui)))

    def _build_scanlines(self):
        """! @brief Pre-render a translucent horizontal-line overlay (window size)."""
        layer = pygame.Surface((self.win_w, self.win_h), pygame.SRCALPHA)
        for y in range(0, self.win_h, 3):             # Bounded by window height.
            pygame.draw.line(layer, (0, 0, 0, 70), (0, y), (self.win_w, y))
        return layer

    def _build_stars(self):
        """! @brief Fixed sparse starfield as an array of (x, y) logical pixels."""
        rng = np.random.default_rng(7)
        n = (self.lw * self.lh) // 900
        xs = rng.integers(0, self.lw, n)
        ys = rng.integers(0, self.lh, n)
        return np.stack((xs, ys), axis=1)

    def _to_window(self, lx, ly):
        """! @brief Scale a logical coordinate to window space.
        @details Derived from the real surface size rather than LOGICAL_SCALE, because
                 integer division above means the scene may not tile the window exactly
                 (e.g. a 1080-px-high screen at scale 2 gives a 540-px scene, but an
                 odd height would not).
        """
        return (int(lx * self.win_w / self.lw),
                int(ly * self.win_h / self.lh))

    def draw_frame(self, camera, coast_pts, sat_pts, station_rows,
                   neo_rows, hud, home_ecef=None, home_pulse=0.0):
        """! @brief Render one complete frame to the window.
            @param camera Camera projecting ECEF km -> logical pixels.
            @param coast_pts (N,3) coastline ECEF array (km).
            @param sat_pts (M,3) satellite ECEF array (km).
            @param station_rows List of (row_index, label, color) for crewed
                   stations to draw as labelled satellites.
            @param neo_rows Iterable of NeoRow for the Sentry panel.
            @param hud Dict of HUD fields (clock, counts, source, bands, and the
                   local_time / local_date strings for the big readout).
            @param home_ecef Length-3 ECEF vector for the viewer's location, or
                   None to omit the home marker.
            @param home_pulse Ping animation phase in [0, 1).
        """
        self.scene.fill(config.COL_BACKGROUND)
        r_earth_px = camera.earth_radius_px(EARTH_RADIUS_KM)

        self._draw_stars()
        self._draw_limb(r_earth_px)
        self._draw_cloud(coast_pts, camera, r_earth_px,
                         config.COL_COAST, config.COL_COAST_FAR, size=1)
        self._draw_home(camera, home_ecef, home_pulse)
        drawn_stations = self._draw_satellites(sat_pts, camera, r_earth_px,
                                               station_rows)

        # Upscale the chunky scene, then composite crisp overlays.
        pygame.transform.scale(self.scene, self.window.get_size(), self.window)
        self._draw_globe_labels(drawn_stations)
        self._draw_clock(hud)
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
        """! @brief Plot satellites with globe occlusion; icon-mark crewed stations.
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
                    self._satellite(px[i], py[i], col)
                    drawn[i] = (label, col, self._to_window(px[i], py[i]))
                continue
            col = config.COL_SAT_FAR if occluded else config.COL_SAT
            self._dot(px[i], py[i], col, 1)
        return drawn

    def _satellite(self, lx, ly, col):
        """! @brief Draw a satellite: a body with two solar panels on booms.
        @details Eleven logical pixels wide, so it reads as a spacecraft rather
                 than a dot, and matches the ESP32 build's marker exactly:

                     ##   ###   ##
                     ##  #####  ##
                     ##   ###   ##
        """
        x, y = int(lx), int(ly)
        self.scene.fill(col, (x - 1, y - 1, 3, 3))    # Body.
        self.scene.fill(col, (x - 2, y, 1, 1))        # Booms out to each panel.
        self.scene.fill(col, (x + 2, y, 1, 1))
        self.scene.fill(col, (x - 5, y - 2, 2, 5))    # Left solar panel.
        self.scene.fill(col, (x + 4, y - 2, 2, 5))    # Right solar panel.

    def _draw_home(self, camera, home_ecef, pulse):
        """! @brief Draw the home marker (a dot) and its ping while it faces the viewer.
            @param home_ecef Length-3 ECEF vector (km), or None.
            @param pulse Ping phase in [0, 1).
        @details The home point sits ON the sphere, so "visible" is simply the near
                 hemisphere - no disk-occlusion test is needed.

                 Just a dot: the expanding ring is what draws the eye and what tells
                 it apart from a satellite. The ring starts tight on the dot and grows
                 outward, which is what makes it read as a ping rather than a throb.
        """
        if home_ecef is None:
            return
        px, py, depth = camera.project(home_ecef)
        if depth < 0:
            return
        pygame.draw.circle(self.scene, config.COL_HOME_PING,
                           (int(px), int(py)), int(3 + pulse * 9.0), 1)
        self.scene.fill(config.COL_HOME, (int(px) - 1, int(py) - 1, 3, 3))

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
        """! @brief Draw a tag beside each visible station icon.
            @param drawn_stations Dict row_index -> (label, color, window_xy).
        @details Offset clear of the 11-px satellite body so the label never sits on
                 the solar panels.
        """
        # 7 logical px clears the satellite body; convert with the real upscale
        # factor rather than LOGICAL_SCALE, which may not divide the display evenly.
        offset = int(7 * self.win_w / self.lw)
        for _idx, (label, col, win) in drawn_stations.items():
            self._text(label[:16], (win[0] + offset, win[1] - self._s(6)),
                       self.font_sm, col)

    def _draw_clock(self, hud):
        """! @brief Draw the big local time and date, centred above the globe.
        @details Always REAL wall-clock time in the local timezone, even when
                 TIME_ACCELERATION is running the orbits fast: a clock that lies is
                 useless. `hud["clock"]` (simulated UTC) stays in the telemetry block
                 for anyone who wants to see what the physics is actually using.
        """
        if not config.CLOCK_ENABLED:
            return
        time_str = hud.get("local_time")
        date_str = hud.get("local_date")
        if not time_str:
            return

        cx = self.win_w // 2
        surf = self.font_clock.render(time_str, True, config.COL_CLOCK)
        self.window.blit(surf, (cx - surf.get_width() // 2, self._s(18)))

        if date_str:
            dsurf = self.font_date.render(date_str, True, config.COL_DATE)
            self.window.blit(
                dsurf,
                (cx - dsurf.get_width() // 2, self._s(22) + surf.get_height()))

    def _draw_hud(self, hud, neo_rows):
        """! @brief Composite the title, telemetry, NEO panel, and band bar."""
        self._text("ORCA ORBITAL SENTINEL", (self._s(14), self._s(10)),
                   self.font_lg, config.COL_HUD)
        self._text("LIVE SATELLITE + NEO TRACKING", (self._s(16), self._s(36)),
                   self.font_sm, config.COL_HUD_DIM)

        lines = (
            "UTC   {0}".format(hud["clock"]),
            "TRACK {0:>5d}   VIS {1:>5d}".format(hud["tracked"], hud["visible"]),
            "SRC   {0}".format(hud["source"]),
        )
        for i, line in enumerate(lines):              # Bounded: fixed line set.
            self._text(line, (self._s(16), self._s(60 + i * 18)),
                       self.font_sm, config.COL_HUD)

        self._draw_neo_panel(neo_rows)
        self._draw_band_bar(hud["bands"])

    def _draw_neo_panel(self, neo_rows):
        """! @brief Right-aligned Sentry near-earth-object risk list."""
        x = self.win_w - self._s(300)
        self._text("SENTRY / NEO IMPACT RISK", (x, self._s(10)),
                   self.font_sm, config.COL_ALERT)
        header = "{0:<12}{1:>7}{2:>9}".format("DESIG", "D(km)", "P(imp)")
        self._text(header, (x, self._s(30)), self.font_sm, config.COL_HUD_DIM)
        for i, row in enumerate(neo_rows):            # Bounded by top_n.
            line = "{0:<12}{1:>7.3f}{2:>9.1e}".format(
                row.des[:12], row.diameter_km, row.impact_prob)
            self._text(line, (x, self._s(48 + i * 16)),
                       self.font_sm, config.COL_HUD)

    def _draw_band_bar(self, bands):
        """! @brief Bottom bar with per-altitude-band object counts.
            @param bands Mapping of band label -> count.
        """
        y = self.win_h - self._s(26)
        x = self._s(16)
        for label, count in bands.items():            # Bounded: fixed band set.
            chunk = "{0} {1}".format(label, count)
            self._text(chunk, (x, y), self.font_sm, config.COL_HUD)
            x += self._s(30) + self.font_sm.size(chunk)[0]

    def _text(self, string, pos, font, col):
        """! @brief Blit a line of text at a window-space position."""
        self.window.blit(font.render(string, True, col), pos)
