"""
FRED API wrapper for free macro data.

Single source for all FRED-driven data in the dashboard:
- Money market fund AUM (replaces hardcoded $6.7T in compute_pgi)
- Federal Funds target rate range
- FOMC dot plot (Summary of Economic Projections)
- Treasury yields, CPI, unemployment, ISM (already covered by macro.py;
  this module is for the new/refreshed signals).

Free, official Federal Reserve Bank of St. Louis data. Requires FRED_API_KEY
in Streamlit secrets. Falls back gracefully if key missing or API unreachable.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

# Streamlit cache for responses (1-hour TTL per series - FRED updates are infrequent)
try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


FRED_BASE_URL = "https://api.stlouisfed.org/fred"


def _get_api_key() -> Optional[str]:
    """Return the FRED API key from Streamlit secrets or env var. None if missing."""
    if _HAS_STREAMLIT:
        try:
            return st.secrets.get("FRED_API_KEY")
        except Exception:
            pass
    return os.environ.get("FRED_API_KEY")


def is_fred_available() -> bool:
    """Cheap check: do we have an API key configured?"""
    return _get_api_key() is not None


def _fred_request(endpoint: str, params: Dict) -> Optional[Dict]:
    """Low-level FRED API request. Returns parsed JSON or None on failure."""
    api_key = _get_api_key()
    if not api_key:
        return None
    params = {**params, "api_key": api_key, "file_type": "json"}
    url = f"{FRED_BASE_URL}/{endpoint}"
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


# Cache wrappers (Streamlit-only; falls back to plain function if no Streamlit)
if _HAS_STREAMLIT:
    _cache_data = st.cache_data(ttl=3600, show_spinner=False)
else:
    def _cache_data(fn):
        return fn


# ───────────────────────────────────────────────────────────────
# Series-specific helpers
# ───────────────────────────────────────────────────────────────

@_cache_data
def get_latest_observation(series_id: str) -> Optional[Dict]:
    """Fetch the most recent value for a FRED series.

    Returns: {value: float, date: str (YYYY-MM-DD), series_id: str} or None.
    """
    result = _fred_request(
        "series/observations",
        {"series_id": series_id, "sort_order": "desc", "limit": 1},
    )
    if not result:
        return None
    observations = result.get("observations", [])
    if not observations:
        return None
    obs = observations[0]
    try:
        val = float(obs["value"])
    except (ValueError, KeyError):
        return None
    return {"value": val, "date": obs.get("date", ""), "series_id": series_id}


@_cache_data
def get_money_market_total_t() -> Optional[Dict]:
    """Total money market fund financial assets (trillions USD).

    Uses series MMMFFAQ027S — Money Market Funds; Total Financial Assets.
    FRED publishes this in MILLIONS of dollars (despite some FRED docs being
    ambiguous about the unit). Convert millions -> trillions = divide by 1e6.

    Sanity check: ICI reports total MMF AUM at ~$7-8T as of Q4 2025/Q1 2026.
    If get_money_market_total_t() returns a value < $1T or > $20T, the unit
    is wrong and something needs to be re-examined.

    Returns: {value_t: float, date: str, raw_millions: float} or None.
    """
    obs = get_latest_observation("MMMFFAQ027S")
    if not obs:
        return None
    raw_millions = obs["value"]
    return {
        "value_t": round(raw_millions / 1_000_000.0, 2),  # millions -> trillions
        "raw_millions": raw_millions,
        "date": obs["date"],
    }


@_cache_data
def get_fed_funds_target_upper() -> Optional[Dict]:
    """Federal Funds Target Range — Upper Limit (DFEDTARU).

    Returns: {value: float, date: str} where value is the upper bound (e.g., 4.50).
    """
    return get_latest_observation("DFEDTARU")


@_cache_data
def get_fed_funds_target_lower() -> Optional[Dict]:
    """Federal Funds Target Range — Lower Limit (DFEDTARL).

    Returns: {value: float, date: str} where value is the lower bound (e.g., 4.25).
    """
    return get_latest_observation("DFEDTARL")


@_cache_data
def get_fed_funds_target_range() -> Optional[Dict]:
    """Combined upper + lower for the Fed Funds target range.

    Returns: {lower: float, upper: float, range_str: str, date: str} or None.
    """
    upper = get_fed_funds_target_upper()
    lower = get_fed_funds_target_lower()
    if not upper or not lower:
        return None
    return {
        "lower": lower["value"],
        "upper": upper["value"],
        "range_str": f"{lower['value']:.2f}%-{upper['value']:.2f}%",
        "date": upper["date"],
    }


# ───────────────────────────────────────────────────────────────
# FOMC Summary of Economic Projections (Dot Plot)
# ───────────────────────────────────────────────────────────────

# SEP median projections — these are the consensus dots from the Fed's
# Summary of Economic Projections, released quarterly. Each series shows the
# median FOMC participant's projection for the year-end Fed funds rate
# in the indicated year. FRED maintains these as long-running series.

# Series IDs for SEP Median Fed Funds Rate Projections:
#   FEDTARMD = Median (current year)
#   FEDTARMDLR = Median (longer run)
# Year-specific series IDs need to be derived dynamically — these change
# each year. We use the published "Median target rate, year-end" series.

# More reliable approach: pull the published SEP series.
# Key FRED series for the dot plot:
#   FEDFUNDS — Effective Fed Funds Rate (historical actual)
#   DFEDTARU/DFEDTARL — Current target range (used above)
#   FEDTARMD — Median target federal funds rate projection (year-end of current year)
#   FEDTARMDLR — Median longer-run target federal funds rate projection
#
# For multi-year dot plot, the Fed publishes individual series like:
#   PCETRIM12M1YPCT — example projection series (varies)
# These don't have stable IDs across SEP releases.

# Pragmatic approach: pull the median current-year and longer-run dots,
# plus the latest target range. For richer multi-year forecasts, fall back to
# a hardcoded snapshot of the latest SEP (updated quarterly).


@_cache_data
def get_sep_dot_plot() -> Optional[Dict]:
    """Fetch SEP median projection data from FRED, with hardcoded fallback.

    Returns a dict structured for plotting:
      {
        "year_labels": ["2026", "2027", "2028", "Longer Run"],
        "median_values": [3.75, 3.25, 2.75, 2.75],
        "current_target": 4.375,  # midpoint of current target range
        "source": "FRED" | "hardcoded_snapshot",
        "as_of": "2026-03-19",  # date of underlying SEP release
      }

    Even with FRED key, multi-year SEP dot projections aren't all available
    as clean time series — only the current year median (FEDTARMD) and
    longer-run median (FEDTARMDLR) are. The intermediate years (Year+1, Year+2)
    require fetching from the SEP PDF tables which is fragile. So we use
    FRED for what's clean, hardcoded for the rest, and clearly label the source.
    """
    # Try FRED for the clean series
    current_year_median = get_latest_observation("FEDTARMD")
    longer_run_median = get_latest_observation("FEDTARMDLR")
    target_range = get_fed_funds_target_range()

    if current_year_median and longer_run_median and target_range:
        current_year = datetime.now().year
        # Hardcoded intermediate years (Year+1, Year+2) — update after each SEP release.
        # These reflect the March 19, 2026 SEP median dots.
        intermediate_dots = {
            current_year + 1: 3.25,  # Year+1 median
            current_year + 2: 2.75,  # Year+2 median
        }
        year_labels = [
            str(current_year),
            str(current_year + 1),
            str(current_year + 2),
            "Longer Run",
        ]
        median_values = [
            current_year_median["value"],
            intermediate_dots[current_year + 1],
            intermediate_dots[current_year + 2],
            longer_run_median["value"],
        ]
        return {
            "year_labels": year_labels,
            "median_values": median_values,
            "current_target": (target_range["lower"] + target_range["upper"]) / 2.0,
            "current_target_range": target_range["range_str"],
            "source": "FRED (intermediate years from latest SEP snapshot)",
            "as_of": current_year_median["date"],
        }

    # FRED unavailable — fall back to a hardcoded snapshot of the latest SEP.
    # UPDATE QUARTERLY when new SEP is released (typically March/June/Sept/Dec).
    # As of March 19, 2026 FOMC meeting SEP.
    return {
        "year_labels": ["2026", "2027", "2028", "Longer Run"],
        "median_values": [3.75, 3.25, 2.75, 2.75],
        "current_target": 4.375,
        "current_target_range": "4.25%-4.50%",
        "source": "hardcoded_snapshot (FRED unavailable)",
        "as_of": "2026-03-19",
    }
