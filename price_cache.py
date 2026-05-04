"""
Price Cache Reader
====================

Provides fast historical price lookups by loading prices_cache.parquet
once at startup and slicing in memory.

Used by backtests to avoid hitting yfinance for every ticker × checkpoint.

Drop-in replacement for yfinance-based price fetches:
    from price_cache import get_prices

    df = get_prices("AAPL", "2018-01-01", "2018-06-30")
    # Returns DataFrame with columns: open, high, low, close, adj_close, volume
    # Indexed by date, identical schema to yf.Ticker.history()

Falls back to live yfinance if cache file not present (graceful degradation).
"""

import os
import sys
import warnings
from datetime import datetime, date

import pandas as pd

warnings.filterwarnings("ignore")

CACHE_FILE = "prices_cache.parquet"

# Module-level cache - loaded once on first call
_PRICES_DF = None
_TICKER_INDEX = None  # Maps ticker to row range for fast slicing


def _load_cache():
    """Lazy-load the parquet file once."""
    global _PRICES_DF, _TICKER_INDEX

    if _PRICES_DF is not None:
        return _PRICES_DF

    if not os.path.exists(CACHE_FILE):
        print(f"WARNING: {CACHE_FILE} not found - falling back to yfinance", file=sys.stderr)
        return None

    print(f"Loading price cache from {CACHE_FILE}...", file=sys.stderr)
    df = pd.read_parquet(CACHE_FILE)

    # Ensure date is datetime
    df["date"] = pd.to_datetime(df["date"])

    # Sort if not already sorted
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    print(f"Loaded {len(df):,} rows for {df['ticker'].nunique()} tickers", file=sys.stderr)

    _PRICES_DF = df

    # Build ticker → row range index for fast slicing
    _TICKER_INDEX = {}
    for ticker in df["ticker"].unique():
        ticker_rows = df[df["ticker"] == ticker]
        if len(ticker_rows) > 0:
            _TICKER_INDEX[ticker] = (ticker_rows.index.min(), ticker_rows.index.max())

    return _PRICES_DF


def get_prices(ticker, start_date, end_date):
    """
    Get historical prices for a ticker between dates.

    Returns a DataFrame with the same shape as yf.Ticker.history():
        - Date index (datetime)
        - Columns: Open, High, Low, Close, Adj Close, Volume

    Returns None if no data available.
    """
    df = _load_cache()

    if df is None:
        # Fallback: hit yfinance live
        return _fetch_live(ticker, start_date, end_date)

    # Convert date strings to datetime
    if isinstance(start_date, str):
        start_dt = pd.to_datetime(start_date)
    else:
        start_dt = pd.to_datetime(start_date)

    if isinstance(end_date, str):
        end_dt = pd.to_datetime(end_date)
    else:
        end_dt = pd.to_datetime(end_date)

    # Slice for this ticker
    ticker_upper = ticker.upper()
    if ticker_upper in _TICKER_INDEX:
        start_idx, end_idx = _TICKER_INDEX[ticker_upper]
        ticker_df = df.iloc[start_idx:end_idx + 1]
    else:
        # Ticker not in cache, try fallback
        return _fetch_live(ticker, start_date, end_date)

    # Filter by date range
    mask = (ticker_df["date"] >= start_dt) & (ticker_df["date"] < end_dt)
    result = ticker_df[mask].copy()

    if result.empty:
        return None

    # Reshape to match yfinance schema (capitalized column names, date as index)
    result = result.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adj_close": "Adj Close",
        "volume": "Volume",
    })

    result = result.set_index("date")
    result = result[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]

    return result


def _fetch_live(ticker, start_date, end_date):
    """Fallback: hit yfinance directly."""
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
    """Check if cache is available (for diagnostic logging)."""
    return os.path.exists(CACHE_FILE)


def get_cache_info():
    """Return summary stats about the cache."""
    df = _load_cache()
    if df is None:
        return {"available": False}
    return {
        "available": True,
        "rows": len(df),
        "tickers": df["ticker"].nunique(),
        "date_min": df["date"].min().strftime("%Y-%m-%d"),
        "date_max": df["date"].max().strftime("%Y-%m-%d"),
        "size_mb": os.path.getsize(CACHE_FILE) / (1024 * 1024),
    }


if __name__ == "__main__":
    # Diagnostic mode
    info = get_cache_info()
    print("Price Cache Info:")
    print(f"  Available: {info.get('available')}")
    if info.get("available"):
        print(f"  Rows: {info.get('rows'):,}")
        print(f"  Tickers: {info.get('tickers')}")
        print(f"  Date range: {info.get('date_min')} to {info.get('date_max')}")
        print(f"  Size: {info.get('size_mb'):.1f} MB")

    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
        df = get_prices(ticker, "2018-01-01", "2018-06-30")
        if df is not None:
            print(f"\nSample {ticker} 2018 H1:")
            print(df.head())
            print(f"\nRow count: {len(df)}")
