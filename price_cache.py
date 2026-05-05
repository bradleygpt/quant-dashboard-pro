"""
Price Cache Reader (Optimized)
================================

Provides fast historical price lookups by loading prices_cache.parquet
once at process startup, organized by ticker for O(1) access.

Key change vs prior version: pre-grouped dict of ticker -> DataFrame,
not row-range index. This is much faster for many small queries.

Module-level singleton state - loaded only once per process.
"""

import os
import sys
import warnings
from datetime import datetime, date

import pandas as pd

warnings.filterwarnings("ignore")

CACHE_FILE = "prices_cache.parquet"

# Module-level state - LOADED ONCE per Python process
_TICKER_DFS = None  # dict: ticker (uppercase) -> DataFrame indexed by date
_LOAD_ATTEMPTED = False
_LOAD_FAILED = False


def _ensure_loaded():
    """Load and pre-group prices into per-ticker DataFrames. ONCE per process."""
    global _TICKER_DFS, _LOAD_ATTEMPTED, _LOAD_FAILED

    if _LOAD_ATTEMPTED:
        return _TICKER_DFS is not None

    _LOAD_ATTEMPTED = True

    if not os.path.exists(CACHE_FILE):
        print(f"price_cache: {CACHE_FILE} not found - will use yfinance fallback", file=sys.stderr)
        _LOAD_FAILED = True
        return False

    try:
        print(f"price_cache: Loading {CACHE_FILE}...", file=sys.stderr)
        df = pd.read_parquet(CACHE_FILE)
        df["date"] = pd.to_datetime(df["date"])

        # Pre-group by ticker - massive speedup vs filtering on every call
        # This builds the dict ONCE: ticker -> DataFrame indexed by date
        ticker_groups = {}
        for ticker, group in df.groupby("ticker", sort=False):
            sorted_group = group.sort_values("date").set_index("date")
            ticker_groups[ticker.upper()] = sorted_group

        _TICKER_DFS = ticker_groups
        n_tickers = len(_TICKER_DFS)
        n_rows = len(df)
        print(f"price_cache: Loaded {n_rows:,} rows for {n_tickers} tickers (cached in memory)", file=sys.stderr)
        return True
    except Exception as e:
        print(f"price_cache: Failed to load - {e}", file=sys.stderr)
        _LOAD_FAILED = True
        return False


def get_prices(ticker, start_date, end_date):
    """
    Get historical prices for a ticker between dates.

    Returns a DataFrame with columns: Open, High, Low, Close, Adj Close, Volume
    indexed by date. Same schema as yf.Ticker.history().

    Returns None if no data.
    """
    _ensure_loaded()

    if _LOAD_FAILED or _TICKER_DFS is None:
        return _fetch_live(ticker, start_date, end_date)

    ticker_upper = ticker.upper()
    if ticker_upper not in _TICKER_DFS:
        # Not in cache - try live yfinance
        return _fetch_live(ticker, start_date, end_date)

    # Convert date inputs
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    # O(log n) slice using sorted DatetimeIndex
    ticker_df = _TICKER_DFS[ticker_upper]
    result = ticker_df.loc[start_dt:end_dt - pd.Timedelta(days=1)]

    if result.empty:
        return None

    # Rename columns to match yfinance schema
    result = result.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adj_close": "Adj Close",
        "volume": "Volume",
    })

    # Drop the ticker column (it's redundant since we keyed by it)
    if "ticker" in result.columns:
        result = result.drop(columns=["ticker"])

    return result[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]


def _fetch_live(ticker, start_date, end_date):
    """Fallback: hit yfinance directly (slow)."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(start=start_date, end=end_date, auto_adjust=False)
        if hist.empty:
            return None
        return hist
    except Exception:
        return None


def is_cache_available():
    return os.path.exists(CACHE_FILE)


def get_cache_info():
    _ensure_loaded()
    if _TICKER_DFS is None:
        return {"available": False}
    return {
        "available": True,
        "tickers": len(_TICKER_DFS),
        "size_mb": os.path.getsize(CACHE_FILE) / (1024 * 1024),
    }


if __name__ == "__main__":
    info = get_cache_info()
    print("Price Cache Info:")
    print(f"  Available: {info.get('available')}")
    if info.get("available"):
        print(f"  Tickers: {info.get('tickers')}")
        print(f"  Size: {info.get('size_mb'):.1f} MB")

    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
        df = get_prices(ticker, "2018-01-01", "2018-06-30")
        if df is not None:
            print(f"\nSample {ticker} 2018 H1:")
            print(df.head())
            print(f"\nRow count: {len(df)}")
        else:
            print(f"\nNo data for {ticker}")
