"""
Factor Rotation Backtest
==========================

Tests the multi-factor approach used by AQR, Dimensional, Alpha Architect.

Five factors documented to provide persistent alpha:
  1. Value - cheap stocks (low P/E, P/B, EV/EBITDA)
  2. Momentum - 12-month return excluding most recent month
  3. Quality - high ROE, ROA, gross margins, low debt
  4. Size - smaller cap (with floor to avoid penny stocks)
  5. Low volatility - lower realized vol

Strategy:
  - Score every stock in universe across all factors monthly
  - Equal-weight portfolio of top 30 stocks (~top decile of liquid universe)
  - Hold for full month
  - Rebalance first of every month
  - Skip most recent month for momentum (avoid short-term reversal effect)

Reference: Berkin & Swedroe "Your Complete Guide to Factor-Based Investing"
"""

import os
import sys
import json
import time
import warnings
from datetime import datetime, timedelta, date, timezone

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

VARIANT_NAME = os.environ.get("VARIANT_NAME", "factor_rotation")
START_YEAR = int(os.environ.get("START_YEAR", "2005"))
TRAIN_END_YEAR = int(os.environ.get("TRAIN_END_YEAR", "2019"))
TOP_N = int(os.environ.get("TOP_N", "30"))
HOLD_DAYS = int(os.environ.get("HOLD_DAYS", "21"))

# Factor weights (equal weight by default, configurable)
W_VALUE = float(os.environ.get("W_VALUE", "0.25"))
W_MOMENTUM = float(os.environ.get("W_MOMENTUM", "0.25"))
W_QUALITY = float(os.environ.get("W_QUALITY", "0.25"))
W_LOWVOL = float(os.environ.get("W_LOWVOL", "0.25"))

# Universe filter
MAX_UNIVERSE_SIZE = int(os.environ.get("MAX_UNIVERSE_SIZE", "500"))

OUTPUT_FILE = f"backtest_variant_{VARIANT_NAME}.json"


# ════════════════════════════════════════════════════════════════
# UNIVERSE & DATA
# ════════════════════════════════════════════════════════════════

def get_universe_tickers():
    """Load full ticker universe from fundamentals cache."""
    if os.path.exists("fundamentals_cache.json"):
        try:
            with open("fundamentals_cache.json") as f:
                cache = json.load(f)
                if "tickers" in cache and isinstance(cache["tickers"], dict):
                    return list(cache["tickers"].keys())
                tickers = [k for k in cache.keys()
                           if isinstance(k, str) and k.isupper() and 1 <= len(k) <= 6]
                if tickers:
                    return tickers
        except Exception:
            pass

    # Fallback list
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]


def get_first_of_months(start_year=2005, end_year=None):
    if end_year is None:
        end_year = datetime.now().year
    dates = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            d = date(y, m, 1)
            if d <= datetime.now().date():
                dates.append(d)
    return dates


def fetch_historical_prices(ticker, start_date, end_date):
    """Use price cache if available, fallback to yfinance."""
    try:
        from price_cache import get_prices
        hist = get_prices(ticker, start_date, end_date)
        if hist is not None and not hist.empty:
            return hist
    except ImportError:
        pass

    try:
        import yfinance as yf
        df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# FACTOR COMPUTATIONS
# ════════════════════════════════════════════════════════════════

def compute_momentum_score(ticker, target_date):
    """
    12-month momentum excluding most recent month.
    Returns the 12-1 month return as a percentile-rankable raw value.
    """
    try:
        # Need price 13 months ago and 1 month ago
        start = (target_date - timedelta(days=420)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")

        hist = fetch_historical_prices(ticker, start, end)
        if hist is None or len(hist) < 200:
            return None

        close = hist["Close"].astype(float)

        # Most recent close (excluding last 21 trading days = 1 month)
        if len(close) < 21:
            return None
        excluding_last_month = close.iloc[-21]

        # 12 months ago
        if len(close) < 252:
            return None
        twelve_mo_ago = close.iloc[-252]

        if twelve_mo_ago <= 0:
            return None

        return (excluding_last_month / twelve_mo_ago) - 1
    except Exception:
        return None


def compute_volatility_score(ticker, target_date):
    """
    Realized volatility over past 60 days.
    LOWER is better for low-vol factor.
    Returns daily volatility.
    """
    try:
        start = (target_date - timedelta(days=120)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")

        hist = fetch_historical_prices(ticker, start, end)
        if hist is None or len(hist) < 60:
            return None

        close = hist["Close"].astype(float)
        returns = close.pct_change().dropna()
        if len(returns) < 30:
            return None

        return float(returns.std())
    except Exception:
        return None


def compute_value_score(ticker, target_date):
    """
    Value score from EDGAR fundamentals at point-in-time.
    Uses TTM Net Income / Market Cap as earnings yield (inverse P/E).
    Higher = better (cheaper).
    """
    try:
        from edgar_fundamentals import get_fundamentals_at_date
        fundies = get_fundamentals_at_date(ticker, target_date)

        if not fundies or fundies.get("data_quality_score", 0) < 30:
            return None

        ttm_ni = fundies.get("ttm_net_income")
        shares = fundies.get("shares_outstanding")

        if ttm_ni is None or shares is None or shares <= 0:
            return None

        # Get current market cap via price
        start = (target_date - timedelta(days=10)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")
        hist = fetch_historical_prices(ticker, start, end)

        if hist is None or hist.empty:
            return None

        price = float(hist["Close"].iloc[-1])
        market_cap = price * shares

        if market_cap <= 0:
            return None

        # Earnings yield = TTM NI / Market Cap (inverse P/E)
        return ttm_ni / market_cap
    except Exception:
        return None


def compute_quality_score(ticker, target_date):
    """
    Quality score: high ROE (Net Income / Stockholders Equity).
    Higher = better.
    """
    try:
        from edgar_fundamentals import get_fundamentals_at_date
        fundies = get_fundamentals_at_date(ticker, target_date)

        if not fundies or fundies.get("data_quality_score", 0) < 30:
            return None

        ttm_ni = fundies.get("ttm_net_income")
        equity = fundies.get("stockholders_equity")

        if ttm_ni is None or equity is None or equity <= 0:
            return None

        return ttm_ni / equity
    except Exception:
        return None


def compute_market_cap(ticker, target_date):
    """For size factor and liquidity filter."""
    try:
        from edgar_fundamentals import get_fundamentals_at_date
        fundies = get_fundamentals_at_date(ticker, target_date)

        if not fundies:
            return None

        shares = fundies.get("shares_outstanding")
        if shares is None or shares <= 0:
            return None

        start = (target_date - timedelta(days=10)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")
        hist = fetch_historical_prices(ticker, start, end)

        if hist is None or hist.empty:
            return None

        price = float(hist["Close"].iloc[-1])
        return price * shares
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# SCORING & PORTFOLIO CONSTRUCTION
# ════════════════════════════════════════════════════════════════

def percentile_rank(values, value):
    """Given a value and a list of values, return its percentile rank 0-1."""
    if not values:
        return 0.5
    valid = [v for v in values if v is not None]
    if not valid:
        return 0.5
    below = sum(1 for v in valid if v < value)
    return below / len(valid)


def score_universe_at_date(universe, target_date):
    """
    Score every ticker in universe across all factors.
    Returns list of dicts with factor scores and composite.
    """
    print(f"  Scoring {len(universe)} tickers...", flush=True)
    raw_scores = []

    for ticker in universe:
        # Compute raw factor values
        mom = compute_momentum_score(ticker, target_date)
        vol = compute_volatility_score(ticker, target_date)
        val = compute_value_score(ticker, target_date)
        qual = compute_quality_score(ticker, target_date)
        mcap = compute_market_cap(ticker, target_date)

        # Need at least price-based factors
        if mom is None and vol is None:
            continue

        # Liquidity filter: market cap > $1B
        if mcap is None or mcap < 1e9:
            continue

        raw_scores.append({
            "ticker": ticker,
            "momentum_raw": mom,
            "volatility_raw": vol,
            "value_raw": val,
            "quality_raw": qual,
            "market_cap": mcap,
        })

    if not raw_scores:
        return []

    # Convert raw factors to percentile ranks (0-1, higher is better)
    momentum_values = [s["momentum_raw"] for s in raw_scores if s["momentum_raw"] is not None]
    volatility_values = [s["volatility_raw"] for s in raw_scores if s["volatility_raw"] is not None]
    value_values = [s["value_raw"] for s in raw_scores if s["value_raw"] is not None]
    quality_values = [s["quality_raw"] for s in raw_scores if s["quality_raw"] is not None]

    for s in raw_scores:
        # Higher momentum = higher rank (good)
        s["momentum_pct"] = percentile_rank(momentum_values, s["momentum_raw"]) if s["momentum_raw"] is not None else 0.5
        # LOWER volatility = higher rank (good - low vol factor)
        s["volatility_pct"] = 1 - percentile_rank(volatility_values, s["volatility_raw"]) if s["volatility_raw"] is not None else 0.5
        # Higher value (earnings yield) = higher rank (good - cheap stocks)
        s["value_pct"] = percentile_rank(value_values, s["value_raw"]) if s["value_raw"] is not None else 0.5
        # Higher quality (ROE) = higher rank (good)
        s["quality_pct"] = percentile_rank(quality_values, s["quality_raw"]) if s["quality_raw"] is not None else 0.5

        # Composite score: weighted average of percentile ranks
        s["composite_score"] = (
            W_MOMENTUM * s["momentum_pct"] +
            W_LOWVOL * s["volatility_pct"] +
            W_VALUE * s["value_pct"] +
            W_QUALITY * s["quality_pct"]
        )

    # Sort by composite descending
    raw_scores.sort(key=lambda x: x["composite_score"], reverse=True)
    return raw_scores


# ════════════════════════════════════════════════════════════════
# TRADE SIMULATION
# ════════════════════════════════════════════════════════════════

def simulate_hold(ticker, entry_date, hold_days):
    """
    Buy at entry_date open, sell at entry_date + hold_days close.
    Returns realized pct return or None.
    """
    try:
        end_date = entry_date + timedelta(days=hold_days + 7)
        hist = fetch_historical_prices(
            ticker,
            entry_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
        if hist is None or len(hist) < 2:
            return None

        hist = hist.head(hold_days)
        if len(hist) < 2:
            return None

        entry_price = float(hist["Close"].iloc[0])
        exit_price = float(hist["Close"].iloc[-1])

        if entry_price <= 0:
            return None

        return ((exit_price - entry_price) / entry_price) * 100
    except Exception:
        return None


def fetch_spy_return(start_date, hold_days):
    return simulate_hold("SPY", start_date, hold_days)


# ════════════════════════════════════════════════════════════════
# MONTHLY BACKTEST
# ════════════════════════════════════════════════════════════════

def run_monthly_backtest(checkpoint_date, universe, top_n, hold_days):
    """Score universe, pick top N, equal weight, simulate one month hold."""

    base_result = {
        "date": checkpoint_date.strftime("%Y-%m-%d"),
        "n_qualified": 0,
        "top_picks": [],
        "portfolio_return": None,
        "spy_return_pct": None,
    }

    scored = score_universe_at_date(universe, checkpoint_date)
    base_result["n_qualified"] = len(scored)

    if len(scored) < top_n:
        # Not enough data this period
        base_result["spy_return_pct"] = fetch_spy_return(checkpoint_date, hold_days)
        return base_result

    top = scored[:top_n]

    # Equal weight
    weight = 1.0 / len(top)
    portfolio_returns = []
    detailed = []

    for stock in top:
        ret = simulate_hold(stock["ticker"], checkpoint_date, hold_days)
        if ret is not None:
            portfolio_returns.append(ret * weight)
            detailed.append({
                "ticker": stock["ticker"],
                "composite_score": stock["composite_score"],
                "momentum_pct": stock["momentum_pct"],
                "value_pct": stock["value_pct"],
                "quality_pct": stock["quality_pct"],
                "volatility_pct": stock["volatility_pct"],
                "weight": weight,
                "return_pct": ret,
            })

    if portfolio_returns:
        base_result["portfolio_return"] = sum(portfolio_returns)
    base_result["top_picks"] = detailed
    base_result["spy_return_pct"] = fetch_spy_return(checkpoint_date, hold_days)

    return base_result


# ════════════════════════════════════════════════════════════════
# AGGREGATION
# ════════════════════════════════════════════════════════════════

def aggregate_metrics(monthly_results):
    valid = [m for m in monthly_results if m.get("portfolio_return") is not None]

    if not valid:
        return {"n_periods": len(monthly_results), "n_valid": 0}

    returns = [m["portfolio_return"] for m in valid]
    spy_returns = [m["spy_return_pct"] for m in valid if m.get("spy_return_pct") is not None]

    cum = 1.0
    cum_spy = 1.0
    for m in monthly_results:
        if m.get("portfolio_return") is not None:
            cum *= (1 + m["portfolio_return"] / 100)
        if m.get("spy_return_pct") is not None:
            cum_spy *= (1 + m["spy_return_pct"] / 100)

    n_total = len(monthly_results)
    years = n_total / 12

    wins = [r for r in returns if r > 0]
    win_rate = (len(wins) / len(returns)) * 100 if returns else 0

    # Drawdown
    peak = 1.0
    max_dd = 0.0
    cur = 1.0
    for m in monthly_results:
        if m.get("portfolio_return") is not None:
            cur *= (1 + m["portfolio_return"] / 100)
        if cur > peak:
            peak = cur
        dd = (cur - peak) / peak
        if dd < max_dd:
            max_dd = dd

    annualized = (cum ** (1/years) - 1) * 100 if years > 0 else 0
    spy_annualized = (cum_spy ** (1/years) - 1) * 100 if years > 0 and cum_spy > 0 else 0

    return {
        "n_periods": n_total,
        "n_valid": len(valid),
        "win_rate_pct": round(win_rate, 2),
        "avg_return_pct": round(sum(returns)/len(returns), 3),
        "compounded_pct": round((cum - 1)*100, 2),
        "compounded_spy_pct": round((cum_spy - 1)*100, 2),
        "annualized_pct": round(annualized, 2),
        "spy_annualized_pct": round(spy_annualized, 2),
        "edge_vs_spy_annualized": round(annualized - spy_annualized, 2),
        "max_drawdown_pct": round(max_dd*100, 2),
    }


def split_train_holdout(monthly_results, train_end_year):
    train = [m for m in monthly_results if int(m["date"][:4]) <= train_end_year]
    holdout = [m for m in monthly_results if int(m["date"][:4]) > train_end_year]
    return train, holdout


def main():
    print(f"Factor Rotation Backtest: {VARIANT_NAME}", flush=True)
    print(f"Factors: Value({W_VALUE}) Momentum({W_MOMENTUM}) Quality({W_QUALITY}) LowVol({W_LOWVOL})", flush=True)
    print(f"Universe limit: {MAX_UNIVERSE_SIZE}, Top N: {TOP_N}, Hold: {HOLD_DAYS} days", flush=True)
    print(flush=True)

    universe = get_universe_tickers()[:MAX_UNIVERSE_SIZE]
    print(f"Universe: {len(universe)} tickers", flush=True)

    checkpoints = get_first_of_months(start_year=START_YEAR)
    print(f"Checkpoints: {len(checkpoints)}", flush=True)
    print(flush=True)

    monthly_results = []
    for i, cp in enumerate(checkpoints):
        result = run_monthly_backtest(cp, universe, TOP_N, HOLD_DAYS)
        monthly_results.append(result)

        nq = result.get("n_qualified", 0)
        ret = result.get("portfolio_return")
        spy = result.get("spy_return_pct")
        ret_str = f"{ret:+.2f}%" if ret is not None else "n/a"
        spy_str = f"{spy:+.2f}%" if spy is not None else "n/a"
        print(f"[{i+1}/{len(checkpoints)}] {cp}: scored={nq}, ret={ret_str}, spy={spy_str}", flush=True)

    train, holdout = split_train_holdout(monthly_results, TRAIN_END_YEAR)

    output = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "variant_name": VARIANT_NAME,
        "parameters": {
            "factor_weights": {
                "value": W_VALUE, "momentum": W_MOMENTUM,
                "quality": W_QUALITY, "lowvol": W_LOWVOL,
            },
            "top_n": TOP_N,
            "hold_days": HOLD_DAYS,
            "max_universe": MAX_UNIVERSE_SIZE,
            "train_end_year": TRAIN_END_YEAR,
            "start_year": START_YEAR,
        },
        "aggregate_full": aggregate_metrics(monthly_results),
        "aggregate_train": aggregate_metrics(train),
        "aggregate_holdout": aggregate_metrics(holdout),
        "monthly_results": monthly_results,
        "n_train_periods": len(train),
        "n_holdout_periods": len(holdout),
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, default=str, indent=2)

    print(flush=True)
    print(f"Wrote {OUTPUT_FILE}", flush=True)

    full = output["aggregate_full"]
    print()
    print("=" * 70)
    print("FULL PERIOD SUMMARY")
    print("=" * 70)
    print(f"Compounded: {full.get('compounded_pct')}% vs SPY {full.get('compounded_spy_pct')}%")
    print(f"Annualized: {full.get('annualized_pct')}% vs SPY {full.get('spy_annualized_pct')}%")
    print(f"Edge: {full.get('edge_vs_spy_annualized')}%")
    print(f"Win rate: {full.get('win_rate_pct')}%")
    print(f"Max drawdown: {full.get('max_drawdown_pct')}%")


if __name__ == "__main__":
    main()
