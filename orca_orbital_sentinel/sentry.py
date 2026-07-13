"""!
@file sentry.py
@brief Fetch NASA/JPL Sentry near-Earth-object impact-risk rows for the HUD.
@details
    Queries the CNEOS Sentry API (summary mode), caches the JSON for a day, and
    returns a small, sorted list of the highest-probability objects. Purely
    decorative for the display, so any failure degrades gracefully to a short
    placeholder list rather than raising.

    Per JPL terms this is a low-rate, non-embedded client that checks the payload
    version and treats the data as best-effort.

    This module is imported, not executed directly.
"""

import json
import os
import time
from collections import namedtuple

import requests

from . import config

# One risk-table row reduced to what the panel needs.
NeoRow = namedtuple("NeoRow", ("des", "diameter_km", "impact_prob"))

_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "orca_orbital_sentinel")
_CACHE_PATH = os.path.join(_CACHE_DIR, "sentry.json")

# Shown when the live feed is unavailable; clearly flagged as offline sample data.
_PLACEHOLDER = (
    NeoRow("2023 DW", 0.05, 1.2e-3),
    NeoRow("1979 XB", 0.66, 8.9e-7),
    NeoRow("2000 SG344", 0.04, 2.7e-3),
    NeoRow("2010 RF12", 0.007, 1.0e-1),
    NeoRow("101955 Bennu", 0.49, 5.7e-4),
)


def _read_fresh_cache(ttl_s):
    """! @brief Return parsed cache JSON if young enough, else None."""
    if not os.path.exists(_CACHE_PATH):
        return None
    if (time.time() - os.path.getmtime(_CACHE_PATH)) > ttl_s:
        return None
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (ValueError, OSError):
        return None


def _fetch_live():
    """! @brief Download and cache the Sentry summary table.
        @return Parsed JSON dict, or None on failure.
    """
    try:
        resp = requests.get(config.SENTRY_URL, timeout=config.HTTP_TIMEOUT_S)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return None
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_CACHE_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return payload


def _rows_from_payload(payload, top_n):
    """! @brief Extract and sort risk rows from a Sentry payload.
        @param payload Parsed Sentry JSON.
        @param top_n Maximum rows to return.
        @return List of NeoRow sorted by descending impact probability.
    """
    data = payload.get("data") or []
    rows = []
    for item in data:                         # Bounded by API result size.
        try:
            rows.append(NeoRow(
                des=str(item.get("des", "?")),
                diameter_km=float(item.get("diameter") or 0.0),
                impact_prob=float(item.get("ip") or 0.0),
            ))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda r: r.impact_prob, reverse=True)
    return rows[:top_n]


def load_neo_rows(top_n=6, allow_network=True):
    """! @brief Resolve the NEO rows for the panel (cache -> live -> placeholder).
        @param top_n Number of rows to display.
        @param allow_network If False, skip the live fetch.
        @return (rows, source_label).
    """
    cached = _read_fresh_cache(config.SENTRY_CACHE_TTL_S)
    if cached:
        return _rows_from_payload(cached, top_n), "cache"

    if allow_network:
        live = _fetch_live()
        if live:
            return _rows_from_payload(live, top_n), "jpl-sentry"

    return list(_PLACEHOLDER[:top_n]), "placeholder"
