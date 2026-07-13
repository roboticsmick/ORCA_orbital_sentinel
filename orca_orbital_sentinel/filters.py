"""!
@file filters.py
@brief Declarative filter that limits which tracked objects are displayed.
@details
    Filtering runs once, at load time, against each object's altitude at a chosen
    instant plus its NORAD id and name. Trimming the set here (rather than per
    frame) is what lets a focused view update faster: fewer objects to propagate
    every tick. Any criterion left as None is ignored.

    This module is imported, not executed directly.
"""

from collections import namedtuple

import numpy as np

from . import config
from .propagate import propagate_ecef, EARTH_RADIUS_KM

# Immutable filter specification. Empty/None fields are inactive.
Filter = namedtuple("Filter", (
    "include_ids", "exclude_ids", "name_contains",
    "min_alt_km", "max_alt_km", "max_count",
))


def from_config():
    """! @brief Build a Filter from the module-level config constants.
        @return Filter instance.
    """
    return Filter(
        include_ids=config.FILTER_INCLUDE_IDS,
        exclude_ids=config.FILTER_EXCLUDE_IDS or frozenset(),
        name_contains=config.FILTER_NAME_CONTAINS,
        min_alt_km=config.FILTER_MIN_ALT_KM,
        max_alt_km=config.FILTER_MAX_ALT_KM,
        max_count=config.FILTER_MAX_COUNT,
    )


def _passes(obj, alt_km, flt):
    """! @brief Test a single object against every active criterion.
        @param obj TrackedObject under test.
        @param alt_km Altitude at the evaluation instant (km).
        @param flt Filter spec.
        @return True if the object should be kept.
    """
    if flt.include_ids is not None and obj.norad not in flt.include_ids:
        return False
    if obj.norad in flt.exclude_ids:
        return False
    if flt.name_contains and flt.name_contains.lower() not in obj.name.lower():
        return False
    if flt.min_alt_km is not None and alt_km < flt.min_alt_km:
        return False
    if flt.max_alt_km is not None and alt_km > flt.max_alt_km:
        return False
    return True


def apply(objects, when, flt):
    """! @brief Return the subset of objects that satisfy the filter.
        @param objects List of TrackedObject.
        @param when UTC datetime used to evaluate altitude.
        @param flt Filter spec.
        @return Filtered list (order preserved, capped by max_count).
    """
    kept = []
    for obj in objects:                        # Bounded by MAX_OBJECTS.
        if flt.max_count is not None and len(kept) >= flt.max_count:
            break
        ecef = propagate_ecef(obj.satrec, when)
        if ecef is None:
            continue
        alt = float(np.linalg.norm(ecef)) - EARTH_RADIUS_KM
        if _passes(obj, alt, flt):
            kept.append(obj)
    return kept
