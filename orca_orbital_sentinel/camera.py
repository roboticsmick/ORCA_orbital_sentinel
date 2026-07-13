"""!
@file camera.py
@brief Orthographic camera that projects Earth-fixed points to screen pixels.
@details
    The camera sits at +Y looking toward the origin. A point is first spun about
    the polar axis (visual-only azimuth) and tilted about X, then projected
    orthographically: screen-x from world-x, screen-y from world-z, with world-y
    acting as depth (larger y == nearer the viewer).

    A point on the far hemisphere whose projected radius falls inside the Earth
    disk is considered occluded, which is what gives the swarm its 3D read.

    This module is imported, not executed directly.
"""

import math
import numpy as np


class Camera:
    """! @brief Immutable-per-frame projector from ECEF km to screen pixels."""

    def __init__(self, cx, cy, scale_px_per_km, tilt_deg):
        """! @brief Build a camera.
            @param cx Screen-space centre x (pixels).
            @param cy Screen-space centre y (pixels).
            @param scale_px_per_km Pixels per kilometre (sets globe size).
            @param tilt_deg Fixed downward tilt about the X axis (degrees).
        """
        self.cx = float(cx)
        self.cy = float(cy)
        self.scale = float(scale_px_per_km)
        self._tilt = math.radians(tilt_deg)
        self._az = 0.0
        self._rot = np.eye(3)          # Combined spin+tilt matrix, refreshed per frame.
        self.set_azimuth(0.0)

    def set_azimuth(self, az_deg):
        """! @brief Set the current spin angle and rebuild the rotation matrix.
            @param az_deg Azimuth about the polar axis (degrees).
        """
        self._az = math.radians(az_deg)
        ca, sa = math.cos(self._az), math.sin(self._az)
        ct, st = math.cos(self._tilt), math.sin(self._tilt)
        rz = np.array(((ca, -sa, 0.0), (sa, ca, 0.0), (0.0, 0.0, 1.0)))
        rx = np.array(((1.0, 0.0, 0.0), (0.0, ct, -st), (0.0, st, ct)))
        self._rot = rx @ rz

    def project(self, ecef_km):
        """! @brief Project an ECEF position to a screen pixel with depth.
            @param ecef_km Length-3 ECEF vector (km).
            @return Tuple (px, py, depth) where depth>0 means the near hemisphere.
        """
        p = self._rot @ ecef_km
        px = self.cx + self.scale * p[0]
        py = self.cy - self.scale * p[2]     # Screen y grows downward; invert world z.
        return px, py, float(p[1])

    def project_many(self, pts_km):
        """! @brief Vectorised projection of an (N,3) array of ECEF points.
            @param pts_km numpy array shape (N,3) in km.
            @return Tuple (px[N], py[N], depth[N]) numpy arrays.
        """
        p = pts_km @ self._rot.T                 # (N,3) rotated into camera frame.
        px = self.cx + self.scale * p[:, 0]
        py = self.cy - self.scale * p[:, 2]
        return px, py, p[:, 1]

    def earth_radius_px(self, earth_radius_km):
        """! @brief Convenience: projected Earth radius in pixels.
            @param earth_radius_km Earth radius (km).
            @return Radius in pixels.
        """
        return earth_radius_km * self.scale
