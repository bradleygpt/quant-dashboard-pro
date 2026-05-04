"""
EDGAR Cache Pre-Fetcher
========================

Fetches companyfacts JSON for every ticker in the universe and saves to
edgar_cache/ directory. Once committed to git, the workflow reads from
cache instead of hitting SEC API every run.

Result: Quant backtest runtime drops from ~5 hours to ~1 hour.

Usage:
    python prefetch_edgar_cache.py

This is a ONE-TIME script. Run locally, commit edgar_cache/ to repo,
done. Re-run periodically (every 6-12 months) to refresh the cache
with newly filed earnings reports.
"""

import os
import sys
import time
import json
from datetime import datetime

# Import our existing fetcher
from edgar_fundamentals import fetch_companyfacts, get_cik_for_ticker, _load_ticker_cik_map, CACHE_DIR


def get_universe():
    """Get the same universe used by build_quant_backtest.py."""
    # Try to load from universe.json if it exists
    if os.path.exists("universe.json"):
        try:
            with open("universe.json") as f:
                tickers = json.load(f)
                return [t for t in tickers if t and isinstance(t, str)][:200]
        except Exception:
            pass

    # Fallback: same hardcoded list as build_quant_backtest.py
    return [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK.B",
        "JPM", "JNJ", "V", "PG", "UNH", "HD", "MA", "BAC", "DIS", "ADBE",
        "NFLX", "CRM", "PFE", "KO", "PEP", "TMO", "ABT", "CSCO", "ABBV",
        "ACN", "MCD", "WMT", "COST", "CVX", "DHR", "LLY", "NKE", "TXN",
        "QCOM", "ORCL", "VZ", "IBM", "PM", "HON", "AMGN", "LIN", "BMY",
        "AVGO", "INTC", "NEE", "MDT", "T", "AMT", "UPS", "PYPL", "LOW",
        "SBUX", "INTU", "BLK", "AMD", "GS", "RTX", "AXP", "DE", "BA",
        "BKNG", "GILD", "C", "MMM", "GE", "NOW", "EL", "CAT", "ISRG",
        "MO", "CHTR", "MS", "CB", "VRTX", "USB", "ZTS", "REGN", "MMC",
        "TGT", "PNC", "EOG", "TJX", "CCI", "SO", "DUK", "FDX", "ITW",
        "AON", "BDX", "ATVI", "F", "GM", "EMR", "ETN", "ADI", "PSA",
        "FIS", "EW", "ICE",
    ][:200]


def main():
    print("EDGAR Cache Pre-Fetcher", flush=True)
    print("=" * 60, flush=True)

    # Ensure cache dir exists
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)
        print(f"Created cache directory: {CACHE_DIR}", flush=True)
    else:
        print(f"Cache directory exists: {CACHE_DIR}", flush=True)

    # Load ticker → CIK map first
    print("\nLoading ticker → CIK map from SEC...", flush=True)
    cik_map = _load_ticker_cik_map()
    print(f"Loaded {len(cik_map)} ticker mappings", flush=True)

    universe = get_universe()
    print(f"\nUniverse size: {len(universe)} tickers", flush=True)
    print(f"Pre-fetching companyfacts JSON for each...\n", flush=True)

    success_count = 0
    cached_count = 0
    failed_count = 0
    no_cik_count = 0

    start_time = time.time()

    for i, ticker in enumerate(universe, 1):
        cache_file = os.path.join(CACHE_DIR, f"{ticker.upper()}_facts.json")

        # Skip if already cached
        if os.path.exists(cache_file):
            cached_count += 1
            print(f"[{i}/{len(universe)}] {ticker}: already cached", flush=True)
            continue

        cik = get_cik_for_ticker(ticker)
        if not cik:
            no_cik_count += 1
            print(f"[{i}/{len(universe)}] {ticker}: NO CIK (skipping)", flush=True)
            continue

        try:
            facts = fetch_companyfacts(ticker, cik)
            if facts:
                # Verify it actually saved
                if os.path.exists(cache_file):
                    file_size_mb = os.path.getsize(cache_file) / (1024 * 1024)
                    success_count += 1
                    print(f"[{i}/{len(universe)}] {ticker}: ✓ fetched ({file_size_mb:.1f} MB)", flush=True)
                else:
                    failed_count += 1
                    print(f"[{i}/{len(universe)}] {ticker}: ✗ data returned but cache file missing", flush=True)
            else:
                failed_count += 1
                print(f"[{i}/{len(universe)}] {ticker}: ✗ no data returned", flush=True)
        except Exception as e:
            failed_count += 1
            print(f"[{i}/{len(universe)}] {ticker}: ✗ error: {str(e)[:80]}", flush=True)

    elapsed = time.time() - start_time

    # Summary
    print("\n" + "=" * 60, flush=True)
    print("PRE-FETCH SUMMARY", flush=True)
    print("=" * 60, flush=True)
    print(f"Already cached: {cached_count}", flush=True)
    print(f"Newly fetched:  {success_count}", flush=True)
    print(f"No CIK found:   {no_cik_count}", flush=True)
    print(f"Failed:         {failed_count}", flush=True)
    print(f"Elapsed time:   {elapsed:.1f}s ({elapsed/60:.1f} min)", flush=True)

    # Cache directory size
    total_size = 0
    file_count = 0
    for f in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, f)
        if os.path.isfile(path):
            total_size += os.path.getsize(path)
            file_count += 1
    print(f"\nCache directory: {file_count} files, {total_size / (1024*1024):.1f} MB total", flush=True)

    print(f"\nNext steps:", flush=True)
    print(f"1. git add {CACHE_DIR}/", flush=True)
    print(f"2. git commit -m 'chore: pre-fetched EDGAR companyfacts cache'", flush=True)
    print(f"3. git push", flush=True)
    print(f"4. Re-trigger quant backtest workflow - will run in ~1 hour instead of 5+", flush=True)


if __name__ == "__main__":
    main()
