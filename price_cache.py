"""
Price Cache Reader (Optimized + IPO-aware)
============================================

Provides fast historical price lookups by loading prices_cache.parquet
once at process startup, organized by ticker for O(1) access.

Key features:
- Pre-grouped dict of ticker -> DataFrame for O(log n) date slicing
- Tracks each ticker's first available date (IPO/listing date)
- Skips pre-IPO date ranges silently (no yfinance fallback noise)
- Module-level singleton state - loaded only once per process

API:
    get_prices(ticker, start, end) -> DataFrame or None
    get_first_date(ticker) -> datetime or None  # for IPO-aware filtering
    is_listed_at(ticker, date) -> bool  # quick existence check
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
_TICKER_FIRST_DATES = None  # dict: ticker -> first date in cache (Timestamp)
_TICKER_LAST_DATES = None  # dict: ticker -> last date in cache (Timestamp)
_LOAD_ATTEMPTED = False
_LOAD_FAILED = False


def _ensure_loaded():
    """Load and pre-group prices into per-ticker DataFrames. ONCE per process."""
    global _TICKER_DFS, _TICKER_FIRST_DATES, _TICKER_LAST_DATES
    global _LOAD_ATTEMPTED, _LOAD_FAILED

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

        # Pre-group by ticker
        ticker_groups = {}
        first_dates = {}
        last_dates = {}

        for ticker, group in df.groupby("ticker", sort=False):
            sorted_group = group.sort_values("date").set_index("date")
            ticker_upper = ticker.upper()
            ticker_groups[ticker_upper] = sorted_group
            first_dates[ticker_upper] = sorted_group.index.min()
            last_dates[ticker_upper] = sorted_group.index.max()

        _TICKER_DFS = ticker_groups
        _TICKER_FIRST_DATES = first_dates
        _TICKER_LAST_DATES = last_dates

        n_tickers = len(_TICKER_DFS)
        n_rows = len(df)
        print(f"price_cache: Loaded {n_rows:,} rows for {n_tickers} tickers (cached in memory)", file=sys.stderr)
        return True
    except Exception as e:
        print(f"price_cache: Failed to load - {e}", file=sys.stderr)
        _LOAD_FAILED = True
        return False


def get_first_date(ticker):
    """Return first available date for ticker (its earliest data point)."""
    _ensure_loaded()
    if _TICKER_FIRST_DATES is None:
        return None
    return _TICKER_FIRST_DATES.get(ticker.upper())


def get_last_date(ticker):
    """Return last available date for ticker."""
    _ensure_loaded()
    if _TICKER_LAST_DATES is None:
        return None
    return _TICKER_LAST_DATES.get(ticker.upper())


def is_listed_at(ticker, target_date):
    """
    Returns True if ticker has data on or before target_date.

    Use this BEFORE calling expensive scoring functions to skip
    pre-IPO tickers entirely.
    """
    _ensure_loaded()
    if _TICKER_FIRST_DATES is None:
        return True  # Can't determine, assume yes (will fall back to yfinance)

    ticker_upper = ticker.upper()
    if ticker_upper not in _TICKER_FIRST_DATES:
        return False  # Not in cache at all

    first = _TICKER_FIRST_DATES[ticker_upper]
    target = pd.to_datetime(target_date)

    return first <= target


def get_prices(ticker, start_date, end_date):
    """
    Get historical prices for a ticker between dates.

    Returns DataFrame with columns: Open, High, Low, Close, Adj Close, Volume
    indexed by date. Same schema as yf.Ticker.history().

    Returns None if:
    - Ticker not in cache (no fallback - won't hit yfinance)
    - Date range is before ticker's first listed date
    - Date range has no data

    NOTE: This version does NOT fall back to yfinance for missing tickers
    or pre-IPO date ranges. This prevents log spam and slow runs when
    backtest universe contains tickers that hadn't IPO'd yet at checkpoint date.
    """
    _ensure_loaded()

    if _LOAD_FAILED or _TICKER_DFS is None:
        return _fetch_live(ticker, start_date, end_date)

    ticker_upper = ticker.upper()
    if ticker_upper not in _TICKER_DFS:
        return None  # Not in cache, do not fallback

    # Convert date inputs
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    # Quick check: if entire date range is before ticker's first date, return None silently
    first_date = _TICKER_FIRST_DATES[ticker_upper]
    if end_dt < first_date:
        return None  # Pre-IPO, silent fail

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

    # Drop the ticker column (redundant since we keyed by it)
    if "ticker" in result.columns:
        result = result.drop(columns=["ticker"])

    return result[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]


def _fetch_live(ticker, start_date, end_date):
    """Fallback ONLY when cache file isn't loaded at all."""
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


def get_listed_tickers_at(target_date, candidate_tickers=None):
    """
    Filter a list of tickers to those listed at target_date.

    Use this at the start of each backtest checkpoint to filter
    universe BEFORE running expensive scoring per ticker.

    Args:
        target_date: date to check (datetime or str)
        candidate_tickers: optional list to filter; if None, returns all listed

    Returns:
        list of tickers (uppercase) that have data on or before target_date
    """
    _ensure_loaded()
    if _TICKER_FIRST_DATES is None:
        return candidate_tickers or []

    target = pd.to_datetime(target_date)

    if candidate_tickers is None:
        candidate_tickers = list(_TICKER_FIRST_DATES.keys())

    return [
        t for t in candidate_tickers
        if t.upper() in _TICKER_FIRST_DATES
        and _TICKER_FIRST_DATES[t.upper()] <= target
    ]


if __name__ == "__main__":
    info = get_cache_info()
    print("Price Cache Info:")
    print(f"  Available: {info.get('available')}")
    if info.get("available"):
        print(f"  Tickers: {info.get('tickers')}")
        print(f"  Size: {info.get('size_mb'):.1f} MB")

    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
        first = get_first_date(ticker)
        last = get_last_date(ticker)
        print(f"\n{ticker} listed range: {first} to {last}")

        df = get_prices(ticker, "2018-01-01", "2018-06-30")
        if df is not None:
            print(f"\nSample {ticker} 2018 H1:")
            print(df.head())
            print(f"\nRow count: {len(df)}")
        else:
            print(f"\nNo data for {ticker} in 2018 H1")
