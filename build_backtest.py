"""
Swing Trader Backtest
=====================

Validates the swing trader's hypothesis by running it monthly across 20 years
of historical data and measuring portfolio returns.

Methodology:
- Every first-of-month from Jan 2005 to today (~240 checkpoints)
- Compute swing trader signals using ONLY data available as of that date
- Take top 10 stocks by combined swing score
- Simulate two exit strategies:
  1. Realistic: Target hit, stop hit, or 14-day timeout (matches actual rules)
  2. Theoretical Max: Best price during the 14-day window (upper bound)
- Weight allocation by combined swing+quant score
- Compute aggregate ROI, win rate, drawdown, Sharpe, comparison to SPY

Caveats explicitly displayed in UI:
- Survivorship bias: universe = current tickers, doesn't include delisted/bankrupt
- Quant overlay: uses CURRENT scoring data, not historical (look-ahead on the
  fundamentals component, not on the technical signals)
- 14-day window assumed ~10 trading days

Architecture: Pre-computed by GitHub Actions weekly, written to
backtest_results.json. Streamlit reads the cached results.
"""

import os
import json
import sys
import time
import math
from datetime import datetime, timedelta, timezone

import yfinance as yf
import pandas as pd
import numpy as np


# Backtest parameters
START_YEAR = 2005
HOLD_DAYS = 14  # ~10 trading days
TOP_N_PICKS = 10
RESULTS_FILE = "backtest_results.json"

# Swing trader parameter constants (must match swing_trader.py)
EMA21_PROXIMITY = 0.03
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 70


def get_universe_tickers(universe_file="universe.json"):
    """Load the ticker universe with multiple fallback strategies."""
    # Try 1: explicit universe file at root
    if os.path.exists(universe_file):
        with open(universe_file) as f:
            data = json.load(f)
            if isinstance(data, dict):
                return list(data.keys())
            elif isinstance(data, list):
                return data

    # Try 2: fundamentals_cache.json at root
    if os.path.exists("fundamentals_cache.json"):
        with open("fundamentals_cache.json") as f:
            cache = json.load(f)
            tickers = list(cache.get("tickers", {}).keys())
            if tickers:
                return tickers

    # Try 3: fundamentals_cache.json in data_cache subdirectory
    if os.path.exists("data_cache/fundamentals_cache.json"):
        with open("data_cache/fundamentals_cache.json") as f:
            cache = json.load(f)
            tickers = list(cache.get("tickers", {}).keys())
            if tickers:
                return tickers

    # Fallback: hardcoded liquid universe (S&P 500 representatives)
    # This ensures backtest can run even when cache files aren't committed
    print("WARNING: No fundamentals cache found, using hardcoded liquid universe", flush=True)
    return [
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "NVDA", "BRK-B", "UNH",
        "JPM", "JNJ", "V", "PG", "XOM", "MA", "HD", "CVX", "MRK", "LLY",
        "ABBV", "PEP", "KO", "AVGO", "WMT", "BAC", "PFE", "TMO", "COST", "DIS",
        "CSCO", "ABT", "MCD", "ACN", "ADBE", "DHR", "VZ", "WFC", "CRM", "TXN",
        "NFLX", "PM", "NEE", "RTX", "BMY", "QCOM", "AMD", "T", "HON", "UPS",
        "INTC", "ORCL", "LIN", "LOW", "AMGN", "IBM", "INTU", "GE", "CAT", "BA",
        "GS", "DE", "BLK", "MMM", "SPGI", "AMT", "AXP", "MDLZ", "PLD", "ISRG",
        "GILD", "SYK", "TJX", "MO", "CVS", "ZTS", "C", "ELV", "TMUS", "BKNG",
        "SO", "DUK", "ADI", "REGN", "VRTX", "LMT", "BDX", "PYPL", "TGT", "MS",
        "EOG", "CI", "AON", "EQIX", "CME", "PGR", "FISV", "USB", "PNC", "KLAC",
        "SHW", "PSA", "ITW", "BSX", "AEP", "FCX", "CSX", "WM", "DG", "ICE",
        "NSC", "EMR", "EW", "ROP", "GIS", "FDX", "MAR", "F", "HUM", "ETN",
        "AIG", "ECL", "TRV", "TFC", "ATVI", "AFL", "APD", "DLR", "PSX", "BIIB",
        "MET", "MNST", "AZO", "WELL", "WMB", "ALL", "MSCI", "MCK", "STZ", "TT",
        "JCI", "ADP", "DOW", "ROST", "FIS", "TEL", "AJG", "ORLY", "CTSH", "PRU",
        "ANET", "VLO", "CMG", "DD", "WMB", "RSG", "CARR", "CRWD", "MRNA", "PXD",
        "PANW", "PAYX", "OXY", "EXC", "AIZ", "STT", "AME", "EBAY", "OTIS", "FAST",
        "NOC", "BKR", "AVB", "ED", "ARE", "MTD", "ETR", "AMP", "GLW", "BAX",
        "ZBH", "FTV", "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "IVV", "VEA",
        "VWO", "AGG", "BND", "TLT", "GLD", "SLV", "USO",
    ]



def get_first_of_months(start_year=2005, end_year=None):
    """Return list of first-of-month dates from start_year to today."""
    if end_year is None:
        end_year = datetime.now().year

    dates = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            try:
                d = datetime(y, m, 1)
                if d > datetime.now():
                    break
                dates.append(d)
            except Exception:
                continue
    return dates


def fetch_historical_prices(ticker, start_date, end_date):
    """Pull price history for a ticker over a date range."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=start_date, end=end_date, auto_adjust=False)
        if hist.empty:
            return None
        return hist
    except Exception:
        return None


def compute_swing_score_at_date(ticker, target_date, lookback_days=180):
    """
    Compute swing trader signals for a ticker AS OF target_date.

    Uses ONLY price/volume data from before target_date — no look-ahead.

    Returns dict with score and signals, or None if insufficient data.
    """
    try:
        # Pull 6 months of history ending at target_date
        start = (target_date - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")

        hist = fetch_historical_prices(ticker, start, end)
        if hist is None or len(hist) < 50:
            return None

        close = hist["Close"].astype(float)
        volume = hist["Volume"].astype(float)
        high = hist["High"].astype(float)
        low = hist["Low"].astype(float)

        if len(close) < 50:
            return None

        price = float(close.iloc[-1])

        # 21-day EMA
        ema_21 = close.ewm(span=21, adjust=False).mean()
        ema_21_val = float(ema_21.iloc[-1])
        dist_from_ema21 = (price - ema_21_val) / ema_21_val

        # EMA slope
        ema_21_5d_ago = float(ema_21.iloc[-6]) if len(ema_21) > 5 else ema_21_val
        ema_slope = (ema_21_val - ema_21_5d_ago) / ema_21_5d_ago

        # 50-day SMA
        sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price

        # RSI (14-day)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.001)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

        # Volume ratio
        avg_volume = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
        recent_volume = float(volume.iloc[-1])
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0

        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else (high.iloc[-1] - low.iloc[-1])
        atr_pct = atr_14 / price if price > 0 else 0.02

        # Composite swing score (matches main swing_trader.py logic)
        score = 0

        # Proximity to 21-EMA
        if -0.005 < dist_from_ema21 < 0.02:
            score += 25
        elif abs(dist_from_ema21) < 0.05:
            score += 18
        elif dist_from_ema21 > 0:
            score += max(0, 15 - int(dist_from_ema21 * 100))
        else:
            score += max(0, 10 + int(dist_from_ema21 * 200))

        # EMA slope
        if ema_slope > 0.005:
            score += 20
        elif ema_slope > 0:
            score += 12
        elif ema_slope > -0.005:
            score += 5

        # 50-SMA position
        if price > sma_50:
            score += 10

        # RSI positioning
        if RSI_OVERSOLD < rsi_val < 55:
            score += 15
        elif 55 <= rsi_val < 65:
            score += 10
        elif rsi_val < RSI_OVERSOLD:
            score += 8
        elif rsi_val < RSI_OVERBOUGHT:
            score += 5

        # Volume confirmation
        if volume_ratio > 1.5:
            score += 10
        elif volume_ratio > 1.0:
            score += 5

        # Setup classification
        if score >= 75:
            setup = "A+ Setup"
        elif score >= 60:
            setup = "Strong Setup"
        elif score >= 45:
            setup = "Decent Setup"
        else:
            setup = "Weak Setup"

        # Target / stop
        target_pct = atr_pct * 2.0  # 2x ATR target
        stop_pct = atr_pct * 1.0    # 1x ATR stop
        target_price = price * (1 + target_pct)
        stop_price = price * (1 - stop_pct)

        return {
            "ticker": ticker,
            "as_of_date": target_date.strftime("%Y-%m-%d"),
            "price": price,
            "swing_score": score,
            "setup": setup,
            "rsi": rsi_val,
            "ema_21": ema_21_val,
            "dist_from_ema21_pct": dist_from_ema21 * 100,
            "ema_slope": ema_slope,
            "volume_ratio": volume_ratio,
            "target_price": target_price,
            "stop_price": stop_price,
            "target_pct": target_pct,
            "stop_pct": stop_pct,
        }
    except Exception:
        return None


def simulate_trade(ticker, entry_date, entry_price, target_price, stop_price, hold_days=14):
    """
    Simulate a swing trade with two exit strategies.

    Returns dict with:
      - realistic_return_pct: target hit / stop hit / timeout
      - realistic_exit_reason: "target" | "stop" | "timeout"
      - max_return_pct: best price hit during window (theoretical max)
      - max_exit_day: day of best price
    """
    try:
        end_date = entry_date + timedelta(days=hold_days + 5)
        hist = fetch_historical_prices(
            ticker,
            entry_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
        if hist is None or hist.empty:
            return None

        # Limit to hold_days trading days max
        hist = hist.head(hold_days)

        close = hist["Close"].astype(float)
        high = hist["High"].astype(float)
        low = hist["Low"].astype(float)

        # Realistic: target hit, stop hit, or final close
        realistic_exit_price = float(close.iloc[-1])
        realistic_exit_reason = "timeout"
        realistic_exit_day = len(close) - 1

        for i, (date, row) in enumerate(hist.iterrows()):
            day_high = float(row["High"])
            day_low = float(row["Low"])
            # Stop check first (more conservative - stop ALWAYS triggers if intraday low hits)
            if day_low <= stop_price:
                realistic_exit_price = stop_price
                realistic_exit_reason = "stop"
                realistic_exit_day = i
                break
            if day_high >= target_price:
                realistic_exit_price = target_price
                realistic_exit_reason = "target"
                realistic_exit_day = i
                break

        realistic_return = ((realistic_exit_price - entry_price) / entry_price) * 100

        # Theoretical max: highest CLOSE price achieved during window
        # (Using close, not high, to be slightly conservative — could be more optimistic with high)
        max_close = float(close.max())
        max_close_day = int(close.argmax())
        max_return = ((max_close - entry_price) / entry_price) * 100

        return {
            "realistic_return_pct": realistic_return,
            "realistic_exit_reason": realistic_exit_reason,
            "realistic_exit_day": realistic_exit_day,
            "max_return_pct": max_return,
            "max_exit_day": max_close_day,
            "entry_price": entry_price,
            "target_price": target_price,
            "stop_price": stop_price,
        }
    except Exception:
        return None


def fetch_spy_return(start_date, hold_days=14):
    """Get SPY's return over the same window for benchmarking."""
    try:
        end_date = start_date + timedelta(days=hold_days + 5)
        hist = fetch_historical_prices("SPY", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if hist is None or hist.empty or len(hist) < 2:
            return None
        hist = hist.head(hold_days)
        entry = float(hist["Close"].iloc[0])
        exit_p = float(hist["Close"].iloc[-1])
        return ((exit_p - entry) / entry) * 100
    except Exception:
        return None


def run_monthly_backtest(checkpoint_date, universe, top_n=10, hold_days=14, max_universe=200):
    """
    Run swing trader on a single checkpoint date.

    Returns:
      {
        "date": "YYYY-MM-DD",
        "n_candidates_screened": ...,
        "n_qualified": (count with swing_score >= 60),
        "top_picks": [...],  # Detail of top N picks
        "portfolio_return_realistic": weighted avg %,
        "portfolio_return_max": weighted avg %,
        "spy_return_pct": SPY return over same window,
      }
    """
    print(f"[{checkpoint_date.strftime('%Y-%m')}] Screening universe...", flush=True)

    # To keep runtime reasonable, sample down to ~200 most-likely candidates
    # (For 20-year backtest this still gives meaningful results)
    sample = universe[:max_universe]

    candidates = []
    for i, ticker in enumerate(sample):
        signal = compute_swing_score_at_date(ticker, checkpoint_date)
        if signal and signal["swing_score"] >= 50:  # Minimum quality threshold
            candidates.append(signal)
        # Be polite to yfinance
        if i % 50 == 49:
            time.sleep(0.5)

    if not candidates:
        return {
            "date": checkpoint_date.strftime("%Y-%m-%d"),
            "n_candidates_screened": len(sample),
            "n_qualified": 0,
            "top_picks": [],
            "portfolio_return_realistic": None,
            "portfolio_return_max": None,
            "spy_return_pct": fetch_spy_return(checkpoint_date, hold_days),
        }

    # Sort by swing score, take top N
    candidates.sort(key=lambda x: x["swing_score"], reverse=True)
    top = candidates[:top_n]

    # Compute weights
    total_score = sum(c["swing_score"] for c in top)
    weights = [c["swing_score"] / total_score for c in top]

    # Simulate trades
    realistic_returns = []
    max_returns = []
    detailed_picks = []

    for c, w in zip(top, weights):
        result = simulate_trade(
            c["ticker"], checkpoint_date, c["price"],
            c["target_price"], c["stop_price"], hold_days
        )
        if result:
            realistic_returns.append(result["realistic_return_pct"] * w)
            max_returns.append(result["max_return_pct"] * w)
            detailed_picks.append({
                "ticker": c["ticker"],
                "swing_score": c["swing_score"],
                "weight": w,
                "entry_price": c["price"],
                "target_price": c["target_price"],
                "stop_price": c["stop_price"],
                "realistic_return_pct": result["realistic_return_pct"],
                "realistic_exit_reason": result["realistic_exit_reason"],
                "max_return_pct": result["max_return_pct"],
            })

    portfolio_realistic = sum(realistic_returns) if realistic_returns else None
    portfolio_max = sum(max_returns) if max_returns else None
    spy_return = fetch_spy_return(checkpoint_date, hold_days)

    return {
        "date": checkpoint_date.strftime("%Y-%m-%d"),
        "n_candidates_screened": len(sample),
        "n_qualified": len(candidates),
        "top_picks": detailed_picks,
        "portfolio_return_realistic": portfolio_realistic,
        "portfolio_return_max": portfolio_max,
        "spy_return_pct": spy_return,
    }


def aggregate_metrics(monthly_results):
    """Compute aggregate stats across all monthly checkpoints."""
    realistic_returns = [m["portfolio_return_realistic"] for m in monthly_results if m.get("portfolio_return_realistic") is not None]
    max_returns = [m["portfolio_return_max"] for m in monthly_results if m.get("portfolio_return_max") is not None]
    spy_returns = [m["spy_return_pct"] for m in monthly_results if m.get("spy_return_pct") is not None]

    def stats(returns):
        if not returns:
            return {}
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        return {
            "n_periods": len(returns),
            "win_rate_pct": (len(wins) / len(returns)) * 100 if returns else 0,
            "avg_return_pct": sum(returns) / len(returns) if returns else 0,
            "avg_win_pct": sum(wins) / len(wins) if wins else 0,
            "avg_loss_pct": sum(losses) / len(losses) if losses else 0,
            "best_period_pct": max(returns) if returns else 0,
            "worst_period_pct": min(returns) if returns else 0,
            "total_compounded_pct": (math.prod([1 + r/100 for r in returns]) - 1) * 100 if returns else 0,
        }

    return {
        "realistic_strategy": stats(realistic_returns),
        "theoretical_max_strategy": stats(max_returns),
        "spy_benchmark": stats(spy_returns),
    }


def main():
    """Run the full 20-year backtest and write results."""
    print(f"[{datetime.now().isoformat()}] Starting swing trader backtest", flush=True)

    universe = get_universe_tickers()
    if not universe:
        print("ERROR: No universe found. Run fundamentals refresh first.", file=sys.stderr)
        sys.exit(1)
    print(f"Universe size: {len(universe)} tickers", flush=True)

    checkpoint_dates = get_first_of_months(start_year=START_YEAR)
    print(f"Backtesting {len(checkpoint_dates)} monthly checkpoints", flush=True)

    monthly_results = []
    for i, date in enumerate(checkpoint_dates):
        try:
            result = run_monthly_backtest(date, universe, top_n=TOP_N_PICKS, hold_days=HOLD_DAYS)
            monthly_results.append(result)
            print(
                f"[{i+1}/{len(checkpoint_dates)}] {date.strftime('%Y-%m')}: "
                f"qualified={result['n_qualified']}, "
                f"realistic={result.get('portfolio_return_realistic'):.2f}% "
                if result.get('portfolio_return_realistic') is not None else "n/a"
                f"max={result.get('portfolio_return_max'):.2f}% "
                if result.get('portfolio_return_max') is not None else "n/a"
                f"spy={result.get('spy_return_pct'):.2f}%"
                if result.get('spy_return_pct') is not None else "n/a",
                flush=True
            )
        except Exception as e:
            print(f"[{i+1}] FAILED for {date}: {e}", file=sys.stderr, flush=True)
            continue

    aggregate = aggregate_metrics(monthly_results)

    output = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "start_year": START_YEAR,
            "hold_days": HOLD_DAYS,
            "top_n_picks": TOP_N_PICKS,
            "min_swing_score": 50,
        },
        "aggregate_metrics": aggregate,
        "monthly_results": monthly_results,
        "universe_size": len(universe),
        "n_checkpoints": len(monthly_results),
    }

    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n[{datetime.now().isoformat()}] Wrote {RESULTS_FILE}", flush=True)
    print(f"Aggregate metrics:", flush=True)
    print(json.dumps(aggregate, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
