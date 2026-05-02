"""
Snapshot Service
================

Provides 1-week and 1-month historical comparisons for any indicator across the dashboard.

For PRICE-BASED indicators (yfinance tickers): pulls history directly, no storage needed.

For DERIVED indicators (Fear & Greed, Buffett, breadth, PGI): reads from
indicator_snapshots.json which is updated daily by GitHub Actions.

Usage:
    from snapshots import get_snapshot
    snap = get_snapshot('vix')
    # → {'current': 16.9, 'week_ago': 17.2, 'month_ago': 14.5,
    #    'wk_change_pct': -1.74, 'mo_change_pct': 16.55}

    snap = get_snapshot('fear_greed')
    # → {'current': 62, 'week_ago': 58, 'month_ago': 71,
    #    'wk_change_pct': 6.9, 'mo_change_pct': -12.7}
    # OR if no historical data yet:
    # → {'current': 62, 'week_ago': None, 'month_ago': None, '_status': 'no_history'}
"""

import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import streamlit as st


SNAPSHOT_FILE = "indicator_snapshots.json"

# Map of derived indicators we track (not price-based)
DERIVED_INDICATORS = {
    "fear_greed": "Fear & Greed Score (0-100)",
    "buffett_indicator": "Buffett Indicator (%)",
    "breadth_above_50sma": "% of Universe Above 50-SMA",
    "breadth_above_200sma": "% of Universe Above 200-SMA",
    "pgi": "PGI (Cash Position %)",
    "money_market_t": "Money Market Assets ($T)",
    "total_mkt_cap_t": "Total US Market Cap ($T)",
    "pullback_pressure": "Pullback Pressure Score (0-100)",
}

# Map of price-based indicators (use yfinance, no storage needed)
# Maps friendly name to yfinance ticker
PRICE_INDICATORS = {
    "spy": "SPY",
    "qqq": "QQQ",
    "dia": "DIA",
    "iwm": "IWM",
    "vix": "^VIX",
    "tnx": "^TNX",
    "irx": "^IRX",
    "tyx": "^TYX",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "russell2000": "^RUT",
    "gold": "GC=F",
    "oil": "CL=F",
    "btc": "BTC-USD",
    "eth": "ETH-USD",
    "dxy": "DX-Y.NYB",
}


def load_snapshot_history() -> Dict[str, Any]:
    """Load the indicator_snapshots.json file."""
    if not os.path.exists(SNAPSHOT_FILE):
        return {"snapshots": {}, "indicators": {}}
    try:
        with open(SNAPSHOT_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"snapshots": {}, "indicators": {}}


def save_snapshot_today(indicator_name: str, value: float) -> bool:
    """
    Save today's value for a derived indicator.

    Called by build_indicator_snapshots.py (run via GitHub Actions daily).
    Should NOT be called from Streamlit UI directly.
    """
    history = load_snapshot_history()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if indicator_name not in history["snapshots"]:
        history["snapshots"][indicator_name] = {}

    history["snapshots"][indicator_name][today] = value

    # Cleanup: keep only last 90 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    history["snapshots"][indicator_name] = {
        d: v for d, v in history["snapshots"][indicator_name].items()
        if d >= cutoff_str
    }

    history["last_updated_utc"] = datetime.now(timezone.utc).isoformat()

    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(history, f, indent=2)
    return True


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_price_snapshot(ticker: str) -> Optional[Dict]:
    """Fetch current/1W/1M for a price-based indicator from yfinance."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="2mo")
        if hist.empty or len(hist) < 22:
            return None
        close = hist["Close"].dropna()
        if close.empty:
            return None

        current = float(close.iloc[-1])
        week_idx = max(0, len(close) - 6)
        month_idx = max(0, len(close) - 22)
        week_ago = float(close.iloc[week_idx])
        month_ago = float(close.iloc[month_idx])

        return {
            "current": current,
            "week_ago": week_ago,
            "month_ago": month_ago,
            "wk_change_pct": ((current / week_ago) - 1) * 100 if week_ago else 0,
            "mo_change_pct": ((current / month_ago) - 1) * 100 if month_ago else 0,
            "_source": "yfinance",
        }
    except Exception as e:
        return {"_status": "error", "_error": str(e)[:100]}


def _get_derived_snapshot(indicator_name: str, current_value: float) -> Dict:
    """
    Get 1W/1M snapshot for a derived indicator from the JSON history file.

    current_value is passed in because the live "current" value is computed
    by the calling tab, not stored as today's snapshot yet.
    """
    history = load_snapshot_history()
    snapshots = history.get("snapshots", {}).get(indicator_name, {})

    today = datetime.now(timezone.utc)
    week_ago_date = today - timedelta(days=7)
    month_ago_date = today - timedelta(days=30)

    # Find closest match for week ago and month ago
    def find_closest(target_date: datetime) -> Optional[float]:
        target_str = target_date.strftime("%Y-%m-%d")
        # Sort dates in snapshots
        dates = sorted(snapshots.keys())
        if not dates:
            return None

        # Find the date closest to target (within 2 days tolerance)
        closest = None
        min_diff = float('inf')
        for d in dates:
            try:
                d_dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                diff = abs((d_dt - target_date).total_seconds())
                if diff < min_diff:
                    min_diff = diff
                    closest = d
            except Exception:
                continue

        # Only return if within 3 days
        if closest and min_diff <= 3 * 86400:
            return snapshots[closest]
        return None

    week_ago_value = find_closest(week_ago_date)
    month_ago_value = find_closest(month_ago_date)

    n_snapshots = len(snapshots)

    if week_ago_value is None and month_ago_value is None:
        return {
            "current": current_value,
            "week_ago": None,
            "month_ago": None,
            "wk_change_pct": None,
            "mo_change_pct": None,
            "_status": "no_history",
            "_history_days": n_snapshots,
            "_source": "snapshots_history",
        }

    wk_change = None
    mo_change = None
    if week_ago_value and current_value:
        wk_change = ((current_value / week_ago_value) - 1) * 100 if week_ago_value else 0
    if month_ago_value and current_value:
        mo_change = ((current_value / month_ago_value) - 1) * 100 if month_ago_value else 0

    return {
        "current": current_value,
        "week_ago": week_ago_value,
        "month_ago": month_ago_value,
        "wk_change_pct": wk_change,
        "mo_change_pct": mo_change,
        "_history_days": n_snapshots,
        "_source": "snapshots_history",
    }


def get_snapshot(indicator_name: str, current_value: Optional[float] = None) -> Optional[Dict]:
    """
    Get the 1W/1M snapshot for any indicator.

    Args:
        indicator_name: name of indicator (e.g., 'vix', 'fear_greed', 'spy')
        current_value: required for DERIVED indicators (computed by caller).
                       Ignored for PRICE indicators (fetched from yfinance).

    Returns dict with current/week_ago/month_ago/changes, or None if unavailable.
    """
    # Price-based indicator
    if indicator_name in PRICE_INDICATORS:
        ticker = PRICE_INDICATORS[indicator_name]
        return _fetch_price_snapshot(ticker)

    # Derived indicator
    if indicator_name in DERIVED_INDICATORS:
        if current_value is None:
            return {
                "_status": "missing_current",
                "_error": f"current_value required for derived indicator '{indicator_name}'",
            }
        return _get_derived_snapshot(indicator_name, current_value)

    return {"_status": "unknown_indicator", "_error": f"Unknown indicator: {indicator_name}"}


def render_snapshot_metric(label: str, snapshot: Dict, format_str: str = "{:.2f}", suffix: str = ""):
    """
    Render a Streamlit metric with current value + 1W/1M comparison as a caption.

    Used by tab modules to display snapshot-aware indicators consistently.
    """
    if not snapshot or snapshot.get("_status") in ("error", "unknown_indicator"):
        st.metric(label, "—", snapshot.get("_error", "n/a") if snapshot else "n/a")
        return

    current = snapshot.get("current")
    if current is None:
        st.metric(label, "—", "n/a")
        return

    current_str = format_str.format(current) + suffix
    wk_pct = snapshot.get("wk_change_pct")
    mo_pct = snapshot.get("mo_change_pct")

    if wk_pct is not None and mo_pct is not None:
        delta_str = f"1W: {wk_pct:+.2f}% | 1M: {mo_pct:+.2f}%"
    elif wk_pct is not None:
        delta_str = f"1W: {wk_pct:+.2f}%"
    elif mo_pct is not None:
        delta_str = f"1M: {mo_pct:+.2f}%"
    else:
        days = snapshot.get("_history_days", 0)
        delta_str = f"Building history ({days} days)"

    st.metric(label, current_str, delta_str)
