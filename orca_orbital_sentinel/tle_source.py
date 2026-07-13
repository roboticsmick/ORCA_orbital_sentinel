"""!
@file tle_source.py
@brief Acquire orbital element sets: cached CelesTrak fetch with offline fallback.
@details
    Resolution order (first success wins):
      1. Fresh local cache (younger than TLE_CACHE_TTL_S) -- no network hit.
      2. Live CelesTrak GP download (then cached).
      3. Bundled fallback TLE file (stale but valid; keeps the app usable offline).
      4. Synthesised demo constellation via sgp4init (guarantees a populated globe).

    Caching is mandatory, not optional: CelesTrak refreshes roughly every two hours
    and firewalls pollers, so we never fetch faster than the configured TTL.

    This module is imported, not executed directly.
"""

import os
import time
from collections import namedtuple

import requests
from sgp4.api import Satrec, WGS72

from . import config
from .propagate import julian

# One tracked object: display name, NORAD id, propagator, and an ISS flag.
TrackedObject = namedtuple("TrackedObject", ("name", "norad", "satrec", "is_iss"))

_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".cache", "orca_orbital_sentinel"
)
_FALLBACK_PATH = os.path.join(
    os.path.dirname(__file__), "data", "fallback_tle.txt"
)


def _cache_file(group):
    """! @brief Absolute path of the on-disk cache for a CelesTrak group."""
    return os.path.join(_CACHE_DIR, "tle_{0}.txt".format(group))


def _read_fresh_cache(path, ttl_s):
    """! @brief Return cached text if present and younger than the TTL, else None.
        @param path Cache file path.
        @param ttl_s Maximum acceptable age in seconds.
        @return File text, or None.
    """
    if not os.path.exists(path):
        return None
    if (time.time() - os.path.getmtime(path)) > ttl_s:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _fetch_live(group):
    """! @brief Download a CelesTrak GP group in TLE format.
        @param group CelesTrak group name.
        @return Text on success, or None on any network/HTTP error.
    """
    url = config.CELESTRAK_URL.format(group=group)
    try:
        resp = requests.get(url, timeout=config.HTTP_TIMEOUT_S)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    text = resp.text.strip()
    # CelesTrak returns a short error string (not TLEs) for bad queries.
    if not text or "1 " not in text:
        return None
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_cache_file(group), "w", encoding="utf-8") as handle:
        handle.write(text)
    return text


def _parse_tle_text(text, limit):
    """! @brief Parse 3-line TLE blocks into TrackedObject records.
        @param text Raw TLE text (name / line1 / line2 repeating).
        @param limit Hard cap on returned objects (bounded work).
        @return List of TrackedObject.
    """
    objects = []
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    # Step in threes; stop at the cap to keep per-frame cost bounded.
    for i in range(0, len(lines) - 2, 3):
        if len(objects) >= limit:
            break
        name, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if not (l1.startswith("1 ") and l2.startswith("2 ")):
            continue
        try:
            satrec = Satrec.twoline2rv(l1, l2)
        except (ValueError, RuntimeError):
            continue
        norad = int(satrec.satnum)
        objects.append(TrackedObject(
            name=name.strip(),
            norad=norad,
            satrec=satrec,
            is_iss=(norad == config.ISS_NORAD_ID),
        ))
    return objects


def synthesize_demo(count, epoch_dt):
    """! @brief Build a plausible LEO swarm without any network or TLE text.
        @param count Number of satellites to create (>= 2).
        @param epoch_dt UTC datetime used as the element-set epoch.
        @return List of TrackedObject. The first two are the ISS and CSS with
                their real NORAD ids so station/filter logic works offline.
    @details Used for the offline preview and as a last-resort fallback so the
             globe (or a stations-only view) is never empty.
    """
    import math
    import random

    rng = random.Random(1234)                # Deterministic preview.
    mu = 398600.4418
    re = 6378.137
    jd, fr = julian(epoch_dt)
    epoch_days = (jd + fr) - 2433281.5       # Days since 1949-12-31 00:00 UT.

    def make(satnum, name, inc_deg, alt_km, is_iss):
        a = re + alt_km
        period_s = 2.0 * math.pi * math.sqrt(a ** 3 / mu)
        no_kozai = (86400.0 / period_s) * (2.0 * math.pi / 1440.0)  # rad/min.
        sat = Satrec()
        sat.sgp4init(
            WGS72, "i", satnum, epoch_days,
            0.0, 0.0, 0.0,                    # bstar, ndot, nddot.
            rng.uniform(0.0, 0.002),          # eccentricity.
            rng.uniform(0.0, 2.0 * math.pi),  # arg of perigee.
            math.radians(inc_deg),
            rng.uniform(0.0, 2.0 * math.pi),  # mean anomaly.
            no_kozai,
            rng.uniform(0.0, 2.0 * math.pi),  # RAAN.
        )
        return TrackedObject(name=name, norad=satnum, satrec=sat, is_iss=is_iss)

    # Real stations first, so include-id / station rendering has something to hit.
    objects = [
        make(25544, "ISS (ZARYA)", 51.64, 420.0, True),
        make(48274, "CSS (TIANHE)", 41.47, 385.0, False),
    ]
    inclinations = (51.6, 53.0, 63.4, 70.0, 87.4, 97.6)
    for idx in range(max(0, count - 2)):     # Bounded by caller.
        objects.append(make(
            90000 + idx,
            "DEMO-{0:04d}".format(idx),
            rng.choice(inclinations) + rng.uniform(-0.4, 0.4),
            rng.uniform(380.0, 1300.0),
            False,
        ))
    return objects


def load_objects(now_dt, allow_network=True, group=None):
    """! @brief Resolve the tracked-object list using the fallback chain.
        @param now_dt UTC datetime (epoch for any synthesised demo objects).
        @param allow_network If False, skip the live fetch (cache/fallback only).
        @param group CelesTrak group name; defaults to config.CELESTRAK_GROUP.
        @return (objects, source_label) where source_label describes the origin.
    """
    group = group or config.CELESTRAK_GROUP
    limit = config.MAX_OBJECTS

    cached = _read_fresh_cache(_cache_file(group), config.TLE_CACHE_TTL_S)
    if cached:
        parsed = _parse_tle_text(cached, limit)
        if parsed:
            return parsed, "cache:{0}".format(group)

    if allow_network:
        live = _fetch_live(group)
        if live:
            parsed = _parse_tle_text(live, limit)
            if parsed:
                return parsed, "celestrak:{0}".format(group)

    if os.path.exists(_FALLBACK_PATH):
        with open(_FALLBACK_PATH, "r", encoding="utf-8") as handle:
            parsed = _parse_tle_text(handle.read(), limit)
        if parsed:
            return parsed, "fallback-file"

    return synthesize_demo(min(limit, 450), now_dt), "synthesized-demo"
