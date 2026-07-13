"""!
@file coastline.py
@brief Load the bundled coastline and expose it as an ECEF point cloud.
@details
    The data file `data/coastline.json` is a decimated, evenly resampled version of
    the public-domain Natural Earth 110m coastline. At import we convert every
    (lon, lat) dot once into a fixed (N, 3) array of Earth-fixed points scaled to
    the Earth radius, ready for vectorised projection each frame.

    This module is imported, not executed directly.
"""

import json
import os
import numpy as np

from .propagate import geodetic_to_ecef_unit, EARTH_RADIUS_KM

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "coastline.json")


def load_coastline_points():
    """! @brief Load coastline dots as an ECEF point cloud at Earth radius.
        @return numpy array shape (N, 3) in km. Empty (0,3) array if data missing.
    """
    if not os.path.exists(_DATA_PATH):
        return np.zeros((0, 3), dtype=np.float64)

    with open(_DATA_PATH, "r", encoding="utf-8") as handle:
        polylines = json.load(handle)

    pts = []
    for line in polylines:                    # Bounded: fixed bundled dataset.
        for lon, lat in line:
            pts.append(geodetic_to_ecef_unit(lon, lat) * EARTH_RADIUS_KM)

    if not pts:
        return np.zeros((0, 3), dtype=np.float64)
    return np.asarray(pts, dtype=np.float64)
