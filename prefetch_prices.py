"""
Price Cache Pre-Fetcher
========================

Bulk-downloads daily OHLCV prices for the entire universe and saves to
a single parquet file. After this runs once, all backtests can read
prices instantly from disk instead of hitting yfinance.

Result: Backtest runtime drops by ~90% for any backtest that scores
many tickers across many checkpoints.

Architecture:
    yfinance batch API → DataFrame with MultiIndex columns →
    Parquet file (~50-100 MB compressed)

Usage:
    python prefetch_prices.py [START_YEAR] [END_YEAR]

Defaults to 2005-present.
"""

import os
import sys
import json
import time
import warnings
from datetime import datetime, date, timedelta

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# Configuration
BATCH_SIZE = 50  # yfinance handles ~50-100 reliably; smaller is more robust
OUTPUT_FILE = "prices_cache.parquet"
START_YEAR_DEFAULT = 2005
RETRY_COUNT = 2
RETRY_SLEEP = 5


def get_universe():
    """Load the full quant universe (~1300 tickers)."""
    # Try fundamentals_cache.json first (this is what the quant backtest uses)
    if os.path.exists("fundamentals_cache.json"):
        try:
            with open("fundamentals_cache.json") as f:
                cache = json.load(f)
                # Try wrapped format first: {"tickers": {...}}
                if "tickers" in cache and isinstance(cache["tickers"], dict):
                    tickers = list(cache["tickers"].keys())
                    if tickers:
                        return tickers
                # Try flat format: {"AAPL": {...}, "MSFT": {...}}
                # All top-level keys that look like tickers (uppercase, short)
                tickers = [k for k in cache.keys()
                           if isinstance(k, str) and k.isupper() and 1 <= len(k) <= 6]
                if tickers:
                    return tickers
        except Exception as e:
            print(f"Could not load fundamentals_cache.json: {e}")

    # Try data_cache subdirectory
    if os.path.exists("data_cache/fundamentals_cache.json"):
        try:
            with open("data_cache/fundamentals_cache.json") as f:
                cache = json.load(f)
                if "tickers" in cache and isinstance(cache["tickers"], dict):
                    tickers = list(cache["tickers"].keys())
                    if tickers:
                        return tickers
                tickers = [k for k in cache.keys()
                           if isinstance(k, str) and k.isupper() and 1 <= len(k) <= 6]
                if tickers:
                    return tickers
        except Exception:
            pass

    # Try universe.json
    if os.path.exists("universe.json"):
        try:
            with open("universe.json") as f:
                tickers = json.load(f)
                if isinstance(tickers, list):
                    return [t for t in tickers if isinstance(t, str)]
                if isinstance(tickers, dict) and "tickers" in tickers:
                    return tickers["tickers"]
        except Exception:
            pass

    print("ERROR: Could not find ticker universe.")
    print("Looked for: fundamentals_cache.json, data_cache/fundamentals_cache.json, universe.json")
    sys.exit(1)


def chunk_list(lst, size):
    """Split a list into chunks of given size."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def download_batch(tickers, start_date, end_date):
    """Download a batch of tickers via yfinance. Returns DataFrame or None."""
    for attempt in range(RETRY_COUNT):
        try:
            df = yf.download(
                tickers=tickers,
                start=start_date,
                end=end_date,
                progress=False,
                auto_adjust=False,
                group_by="ticker",
                threads=True,
            )
            if df is not None and not df.empty:
                return df
        except Exception as e:
            print(f"  Batch download attempt {attempt + 1} failed: {str(e)[:80]}")
            if attempt < RETRY_COUNT - 1:
                time.sleep(RETRY_SLEEP)

    return None


def normalize_to_long_format(batch_df, batch_tickers):
    """
    Convert yfinance multi-ticker output to long format:
        date, ticker, open, high, low, close, volume, adj_close

    Long format is more flexible than wide format for downstream use.
    """
    rows = []

    if isinstance(batch_df.columns, pd.MultiIndex):
        # Multi-ticker format: columns are (ticker, field)
        for ticker in batch_tickers:
            if ticker not in batch_df.columns.get_level_values(0):
                continue
            try:
                ticker_df = batch_df[ticker].dropna(how="all")
                for idx, row in ticker_df.iterrows():
                    rows.append({
                        "date": idx,
                        "ticker": ticker,
                        "open": row.get("Open"),
                        "high": row.get("High"),
                        "low": row.get("Low"),
                        "close": row.get("Close"),
                        "adj_close": row.get("Adj Close"),
                        "volume": row.get("Volume"),
                    })
            except Exception as e:
                print(f"  Could not parse {ticker}: {str(e)[:60]}")
    else:
        # Single-ticker format: columns are (field) directly
        ticker = batch_tickers[0] if len(batch_tickers) == 1 else "UNKNOWN"
        for idx, row in batch_df.dropna(how="all").iterrows():
            rows.append({
                "date": idx,
                "ticker": ticker,
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "adj_close": row.get("Adj Close"),
                "volume": row.get("Volume"),
            })

    return rows


def main():
    start_year = int(sys.argv[1]) if len(sys.argv) > 1 else START_YEAR_DEFAULT
    end_year = int(sys.argv[2]) if len(sys.argv) > 2 else datetime.now().year

    start_date = f"{start_year}-01-01"
    end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    print("Price Cache Pre-Fetcher")
    print("=" * 60)
    print(f"Date range: {start_date} to {end_date}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    # Load universe
    universe = get_universe()
    print(f"Universe size: {len(universe)} tickers")
    print(f"Will batch in groups of {BATCH_SIZE}")
    print()

    # Check if cache already exists
    if os.path.exists(OUTPUT_FILE):
        existing_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
        print(f"WARNING: {OUTPUT_FILE} already exists ({existing_size_mb:.1f} MB)")
        response = input("Overwrite? (y/N): ").strip().lower()
        if response != "y":
            print("Aborted.")
            sys.exit(0)
        print()

    # Download in batches
    all_rows = []
    failed_tickers = []
    batches = list(chunk_list(universe, BATCH_SIZE))

    start_time = time.time()

    for batch_idx, batch in enumerate(batches, 1):
        elapsed = time.time() - start_time
        eta_per_batch = elapsed / batch_idx if batch_idx > 0 else 0
        eta_remaining = eta_per_batch * (len(batches) - batch_idx)

        print(f"[Batch {batch_idx}/{len(batches)}] Downloading {len(batch)} tickers... "
              f"(elapsed: {elapsed:.0f}s, eta: {eta_remaining:.0f}s)")

        batch_df = download_batch(batch, start_date, end_date)

        if batch_df is None or batch_df.empty:
            print(f"  ✗ Batch failed entirely - {len(batch)} tickers will be retried individually")
            # Retry one by one
            for ticker in batch:
                single_df = download_batch([ticker], start_date, end_date)
                if single_df is not None and not single_df.empty:
                    rows = normalize_to_long_format(single_df, [ticker])
                    all_rows.extend(rows)
                    print(f"    {ticker}: ✓ ({len(rows)} rows)")
                else:
                    failed_tickers.append(ticker)
                    print(f"    {ticker}: ✗ failed")
                time.sleep(0.5)
        else:
            rows = normalize_to_long_format(batch_df, batch)
            all_rows.extend(rows)
            successful = len(set(r["ticker"] for r in rows))
            print(f"  ✓ Got {successful}/{len(batch)} tickers, {len(rows):,} rows so far")

            # Track which tickers in this batch had no data
            successful_tickers = set(r["ticker"] for r in rows)
            for t in batch:
                if t not in successful_tickers:
                    failed_tickers.append(t)

        # Be polite between batches
        time.sleep(1.0)

    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("DOWNLOAD COMPLETE")
    print("=" * 60)
    print(f"Total time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"Total rows: {len(all_rows):,}")
    print(f"Successful tickers: {len(set(r['ticker'] for r in all_rows))}")
    print(f"Failed tickers: {len(failed_tickers)}")
    if failed_tickers:
        print(f"  Sample failures: {failed_tickers[:10]}")

    if not all_rows:
        print("ERROR: No data downloaded. Aborting.")
        sys.exit(1)

    # Convert to DataFrame and save
    print()
    print("Converting to DataFrame...")
    df = pd.DataFrame(all_rows)

    # Ensure correct types
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "adj_close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    # Sort for fast lookups
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    print(f"DataFrame shape: {df.shape}")
    print(f"Memory size: {df.memory_usage(deep=True).sum() / (1024*1024):.1f} MB")

    # Save to parquet
    print(f"\nSaving to {OUTPUT_FILE}...")
    df.to_parquet(OUTPUT_FILE, compression="snappy", index=False)

    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"Saved: {file_size_mb:.1f} MB")

    # Save failed tickers list for reference
    if failed_tickers:
        with open("failed_tickers.json", "w") as f:
            json.dump(failed_tickers, f, indent=2)
        print(f"Saved failed_tickers.json ({len(failed_tickers)} tickers)")

    print()
    print("=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print(f"1. git add {OUTPUT_FILE}")
    print(f"2. git commit -m 'chore: pre-fetched price cache for fast backtests'")
    print(f"3. git push")
    print(f"4. Update backtests to read from {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
