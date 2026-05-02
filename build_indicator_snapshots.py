"""
Build Indicator Snapshots
=========================

Runs daily via GitHub Actions. Captures today's value for all derived indicators
(Fear & Greed, Buffett, breadth, PGI, etc.) and appends to indicator_snapshots.json.

The dashboard's snapshot service reads this file to compute 1W/1M comparisons
for derived indicators. Price-based indicators don't need this — they pull
from yfinance directly.

Usage:
    python build_indicator_snapshots.py
"""

import os
import sys
import json
from datetime import datetime, timezone

import requests
import yfinance as yf
import pandas as pd


def fetch_fear_greed_score():
    """
    Fetch Fear & Greed score from alternative.me crypto API as a proxy.

    Note: alternative.me is the BTC fear/greed index, not the CNN equity one.
    For now we use this as a sentiment proxy. CNN's index requires scraping
    or paid API access.
    """
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("data") and len(data["data"]) > 0:
                return float(data["data"][0]["value"])
    except Exception:
        pass
    return None


def fetch_vix_value():
    """Get current VIX (also stored as a snapshot for trend tracking)."""
    try:
        vix = yf.Ticker("^VIX").history(period="2y")
        if not vix.empty:
            return float(vix["Close"].dropna().iloc[-1])
    except Exception:
        pass
    return None


def fetch_buffett_indicator():
    """
    Buffett Indicator = Total US Market Cap / GDP

    Approximation: Wilshire 5000 (^W5000) is roughly total US market cap.
    GDP estimate comes from FRED (or hardcoded approximation).
    """
    try:
        wilshire = yf.Ticker("^W5000").history(period="5d")
        if wilshire.empty:
            return None, None
        # Wilshire 5000 reports in points where 1 point ≈ $1B market cap
        total_mkt_cap_t = float(wilshire["Close"].iloc[-1]) / 1000  # to trillions

        # US GDP estimate (annualized, approximate)
        # As of 2026 this is approximately $28.5T
        # For better accuracy, fetch from FRED API if available
        gdp_t = 28.5  # Approximation

        ratio = (total_mkt_cap_t / gdp_t) * 100  # percent
        return ratio, total_mkt_cap_t
    except Exception:
        return None, None


def fetch_breadth_metrics():
    """
    Compute % of major index stocks above 50-SMA and 200-SMA.

    Uses fundamentals_cache.json if available, falls back to fetching SPY components.
    """
    try:
        # Try fundamentals cache first
        for path in ["fundamentals_cache.json", "data_cache/fundamentals_cache.json"]:
            if os.path.exists(path):
                with open(path) as f:
                    cache = json.load(f)
                tickers_data = cache.get("tickers", {})
                if not tickers_data:
                    continue

                above_50 = 0
                above_200 = 0
                total = 0
                for ticker, data in tickers_data.items():
                    price = data.get("currentPrice") or data.get("regularMarketPrice")
                    sma_50 = data.get("fiftyDayAverage")
                    sma_200 = data.get("twoHundredDayAverage")
                    if price and sma_50:
                        total += 1
                        if price > sma_50:
                            above_50 += 1
                        if sma_200 and price > sma_200:
                            above_200 += 1

                if total > 0:
                    return (above_50 / total) * 100, (above_200 / total) * 100
    except Exception:
        pass

    return None, None


def main():
    print(f"[{datetime.now().isoformat()}] Starting indicator snapshot capture")

    # Load existing snapshots
    snapshot_file = "indicator_snapshots.json"
    if os.path.exists(snapshot_file):
        with open(snapshot_file) as f:
            history = json.load(f)
    else:
        history = {"snapshots": {}, "indicators": {}}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Track what we captured today
    captured = []
    failed = []

    # Fear & Greed
    fg = fetch_fear_greed_score()
    if fg is not None:
        history["snapshots"].setdefault("fear_greed", {})[today] = fg
        captured.append(f"fear_greed: {fg:.1f}")
    else:
        failed.append("fear_greed")

    # VIX
    vix = fetch_vix_value()
    if vix is not None:
        history["snapshots"].setdefault("vix", {})[today] = vix
        captured.append(f"vix: {vix:.2f}")
    else:
        failed.append("vix")

    # Buffett Indicator + Total Market Cap
    buffett, mkt_cap = fetch_buffett_indicator()
    if buffett is not None:
        history["snapshots"].setdefault("buffett_indicator", {})[today] = buffett
        captured.append(f"buffett_indicator: {buffett:.1f}%")
    else:
        failed.append("buffett_indicator")

    if mkt_cap is not None:
        history["snapshots"].setdefault("total_mkt_cap_t", {})[today] = mkt_cap
        captured.append(f"total_mkt_cap_t: ${mkt_cap:.2f}T")

    # Breadth
    breadth_50, breadth_200 = fetch_breadth_metrics()
    if breadth_50 is not None:
        history["snapshots"].setdefault("breadth_above_50sma", {})[today] = breadth_50
        captured.append(f"breadth_above_50sma: {breadth_50:.1f}%")
    else:
        failed.append("breadth_above_50sma")

    if breadth_200 is not None:
        history["snapshots"].setdefault("breadth_above_200sma", {})[today] = breadth_200
        captured.append(f"breadth_above_200sma: {breadth_200:.1f}%")
    else:
        failed.append("breadth_above_200sma")

    # Cleanup: keep only last 90 days for each indicator
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    for ind_name in list(history["snapshots"].keys()):
        history["snapshots"][ind_name] = {
            d: v for d, v in history["snapshots"][ind_name].items()
            if d >= cutoff
        }

    history["last_updated_utc"] = datetime.now(timezone.utc).isoformat()
    history["last_capture_date"] = today

    with open(snapshot_file, "w") as f:
        json.dump(history, f, indent=2)

    print(f"[{datetime.now().isoformat()}] Captured: {', '.join(captured) if captured else 'none'}")
    if failed:
        print(f"[{datetime.now().isoformat()}] Failed: {', '.join(failed)}")

    # Print history depth
    for ind_name, snapshots in history["snapshots"].items():
        print(f"  {ind_name}: {len(snapshots)} days of history")

    # Exit non-zero if we captured nothing at all
    if not captured:
        print("ERROR: No indicators captured", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
