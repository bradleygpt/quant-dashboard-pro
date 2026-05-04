"""
Swing Trader Backtest Optimizer
================================

Runs the same backtest as build_backtest.py but with parameterizable
stop/target/hold/score parameters, and splits results into training
(2005-2019) and holdout (2020+) buckets for walk-forward validation.

Usage (via env vars or args):
    VARIANT_NAME=h1a STOP_ATR=1.5 TARGET_ATR=2.0 HOLD_DAYS=14 MIN_SCORE=50 TOP_N=10 \\
      python build_backtest_optimizer.py

Output: backtest_variant_<VARIANT_NAME>.json
"""

import os
import json
import sys
import time
import math
from datetime import datetime, timedelta, timezone

import yfinance as yf
import pandas as pd


# Configurable parameters from environment
VARIANT_NAME = os.environ.get("VARIANT_NAME", "baseline")
STOP_ATR_MULT = float(os.environ.get("STOP_ATR", "1.0"))
TARGET_ATR_MULT = float(os.environ.get("TARGET_ATR", "2.0"))
HOLD_DAYS = int(os.environ.get("HOLD_DAYS", "14"))
MIN_SCORE = int(os.environ.get("MIN_SCORE", "50"))
TOP_N = int(os.environ.get("TOP_N", "10"))
START_YEAR = int(os.environ.get("START_YEAR", "2005"))

# Walk-forward split year
TRAIN_END_YEAR = int(os.environ.get("TRAIN_END_YEAR", "2019"))

# Universe limit (matches baseline)
MAX_UNIVERSE_SIZE = 200

OUTPUT_FILE = f"backtest_variant_{VARIANT_NAME}.json"

# Constants from swing_trader logic
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 70


def get_universe_tickers(universe_file="universe.json"):
    """Load universe with fallback to hardcoded liquid stocks."""
    if os.path.exists(universe_file):
        with open(universe_file) as f:
            data = json.load(f)
            if isinstance(data, dict):
                return list(data.keys())
            elif isinstance(data, list):
                return data

    if os.path.exists("fundamentals_cache.json"):
        with open("fundamentals_cache.json") as f:
            cache = json.load(f)
            tickers = list(cache.get("tickers", {}).keys())
            if tickers:
                return tickers

    if os.path.exists("data_cache/fundamentals_cache.json"):
        with open("data_cache/fundamentals_cache.json") as f:
            cache = json.load(f)
            tickers = list(cache.get("tickers", {}).keys())
            if tickers:
                return tickers

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
        "ANET", "VLO", "CMG", "DD", "RSG", "CARR", "CRWD", "MRNA", "PXD",
        "PANW", "PAYX", "OXY", "EXC", "AIZ", "STT", "AME", "EBAY", "OTIS", "FAST",
        "NOC", "BKR", "AVB", "ED", "ARE", "MTD", "ETR", "AMP", "GLW", "BAX",
        "ZBH", "FTV",
    ]


def get_first_of_months(start_year=2005, end_year=None):
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
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=start_date, end=end_date, auto_adjust=False)
        if hist.empty:
            return None
        return hist
    except Exception:
        return None


def compute_swing_score_at_date(ticker, target_date, lookback_days=180,
                                  stop_atr_mult=1.0, target_atr_mult=2.0):
    """Compute swing score AS OF target_date with parameterized stop/target."""
    try:
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

        ema_21 = close.ewm(span=21, adjust=False).mean()
        ema_21_val = float(ema_21.iloc[-1])
        dist_from_ema21 = (price - ema_21_val) / ema_21_val

        ema_21_5d_ago = float(ema_21.iloc[-6]) if len(ema_21) > 5 else ema_21_val
        ema_slope = (ema_21_val - ema_21_5d_ago) / ema_21_5d_ago

        sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price

        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.001)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

        avg_volume = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
        recent_volume = float(volume.iloc[-1])
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else (high.iloc[-1] - low.iloc[-1])
        atr_pct = atr_14 / price if price > 0 else 0.02

        score = 0
        if -0.005 < dist_from_ema21 < 0.02:
            score += 25
        elif abs(dist_from_ema21) < 0.05:
            score += 18
        elif dist_from_ema21 > 0:
            score += max(0, 15 - int(dist_from_ema21 * 100))
        else:
            score += max(0, 10 + int(dist_from_ema21 * 200))

        if ema_slope > 0.005:
            score += 20
        elif ema_slope > 0:
            score += 12
        elif ema_slope > -0.005:
            score += 5

        if price > sma_50:
            score += 10

        if RSI_OVERSOLD < rsi_val < 55:
            score += 15
        elif 55 <= rsi_val < 65:
            score += 10
        elif rsi_val < RSI_OVERSOLD:
            score += 8
        elif rsi_val < RSI_OVERBOUGHT:
            score += 5

        if volume_ratio > 1.5:
            score += 10
        elif volume_ratio > 1.0:
            score += 5

        # Parameterized target/stop
        target_pct = atr_pct * target_atr_mult
        stop_pct = atr_pct * stop_atr_mult
        target_price = price * (1 + target_pct)
        stop_price = price * (1 - stop_pct)

        return {
            "ticker": ticker,
            "as_of_date": target_date.strftime("%Y-%m-%d"),
            "price": price,
            "swing_score": score,
            "target_price": target_price,
            "stop_price": stop_price,
            "target_pct": target_pct,
            "stop_pct": stop_pct,
        }
    except Exception:
        return None


def simulate_trade(ticker, entry_date, entry_price, target_price, stop_price, hold_days):
    try:
        end_date = entry_date + timedelta(days=hold_days + 5)
        hist = fetch_historical_prices(
            ticker,
            entry_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
        if hist is None or hist.empty:
            return None

        hist = hist.head(hold_days)

        close = hist["Close"].astype(float)
        high = hist["High"].astype(float)
        low = hist["Low"].astype(float)

        realistic_exit_price = float(close.iloc[-1])
        realistic_exit_reason = "timeout"

        for i, (date, row) in enumerate(hist.iterrows()):
            day_high = float(row["High"])
            day_low = float(row["Low"])
            if day_low <= stop_price:
                realistic_exit_price = stop_price
                realistic_exit_reason = "stop"
                break
            if day_high >= target_price:
                realistic_exit_price = target_price
                realistic_exit_reason = "target"
                break

        realistic_return = ((realistic_exit_price - entry_price) / entry_price) * 100

        max_close = float(close.max())
        max_return = ((max_close - entry_price) / entry_price) * 100

        return {
            "realistic_return_pct": realistic_return,
            "realistic_exit_reason": realistic_exit_reason,
            "max_return_pct": max_return,
        }
    except Exception:
        return None


def fetch_spy_return(start_date, hold_days):
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


def run_monthly_backtest(checkpoint_date, universe, top_n, hold_days, min_score,
                         stop_atr_mult, target_atr_mult, max_universe=200):
    sample = universe[:max_universe]
    candidates = []
    for i, ticker in enumerate(sample):
        signal = compute_swing_score_at_date(
            ticker, checkpoint_date,
            stop_atr_mult=stop_atr_mult,
            target_atr_mult=target_atr_mult,
        )
        if signal and signal["swing_score"] >= min_score:
            candidates.append(signal)
        if i % 50 == 49:
            time.sleep(0.5)

    if not candidates:
        return {
            "date": checkpoint_date.strftime("%Y-%m-%d"),
            "n_qualified": 0,
            "top_picks": [],
            "portfolio_return_realistic": None,
            "portfolio_return_max": None,
            "spy_return_pct": fetch_spy_return(checkpoint_date, hold_days),
        }

    candidates.sort(key=lambda x: x["swing_score"], reverse=True)
    top = candidates[:top_n]

    total_score = sum(c["swing_score"] for c in top)
    weights = [c["swing_score"] / total_score for c in top]

    realistic_returns = []
    max_returns = []
    detailed = []

    for c, w in zip(top, weights):
        sim = simulate_trade(c["ticker"], checkpoint_date, c["price"],
                             c["target_price"], c["stop_price"], hold_days)
        if sim:
            realistic_returns.append(sim["realistic_return_pct"] * w)
            max_returns.append(sim["max_return_pct"] * w)
            detailed.append({
                "ticker": c["ticker"],
                "swing_score": c["swing_score"],
                "weight": w,
                "realistic_return_pct": sim["realistic_return_pct"],
                "realistic_exit_reason": sim["realistic_exit_reason"],
                "max_return_pct": sim["max_return_pct"],
            })

    return {
        "date": checkpoint_date.strftime("%Y-%m-%d"),
        "n_qualified": len(candidates),
        "top_picks": detailed,
        "portfolio_return_realistic": sum(realistic_returns) if realistic_returns else None,
        "portfolio_return_max": sum(max_returns) if max_returns else None,
        "spy_return_pct": fetch_spy_return(checkpoint_date, hold_days),
    }


def aggregate_metrics(monthly_results):
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


def split_train_holdout(monthly_results, train_end_year):
    """Split monthly results into training and holdout periods."""
    train = []
    holdout = []
    for m in monthly_results:
        date = m.get("date", "")
        if date and len(date) >= 4:
            year = int(date[:4])
            if year <= train_end_year:
                train.append(m)
            else:
                holdout.append(m)
    return train, holdout


def main():
    print(f"[{datetime.now().isoformat()}] Starting OPTIMIZER variant: {VARIANT_NAME}", flush=True)
    print(f"  Parameters:", flush=True)
    print(f"    STOP_ATR_MULT: {STOP_ATR_MULT}", flush=True)
    print(f"    TARGET_ATR_MULT: {TARGET_ATR_MULT}", flush=True)
    print(f"    HOLD_DAYS: {HOLD_DAYS}", flush=True)
    print(f"    MIN_SCORE: {MIN_SCORE}", flush=True)
    print(f"    TOP_N: {TOP_N}", flush=True)
    print(f"    Train end year: {TRAIN_END_YEAR}", flush=True)

    universe = get_universe_tickers()
    if not universe:
        print("ERROR: No universe", file=sys.stderr)
        sys.exit(1)

    checkpoint_dates = get_first_of_months(start_year=START_YEAR)

    monthly_results = []
    for i, date in enumerate(checkpoint_dates):
        try:
            result = run_monthly_backtest(
                date, universe,
                top_n=TOP_N, hold_days=HOLD_DAYS, min_score=MIN_SCORE,
                stop_atr_mult=STOP_ATR_MULT, target_atr_mult=TARGET_ATR_MULT,
            )
            monthly_results.append(result)
            real = result.get('portfolio_return_realistic')
            real_str = f"{real:+.2f}%" if real is not None else "n/a"
            print(f"[{i+1}/{len(checkpoint_dates)}] {date.strftime('%Y-%m')}: qualified={result['n_qualified']}, realistic={real_str}", flush=True)
        except Exception as e:
            print(f"[{i+1}] FAILED for {date}: {e}", file=sys.stderr, flush=True)
            continue

    # Split train/holdout
    train_results, holdout_results = split_train_holdout(monthly_results, TRAIN_END_YEAR)

    output = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "variant_name": VARIANT_NAME,
        "parameters": {
            "stop_atr_mult": STOP_ATR_MULT,
            "target_atr_mult": TARGET_ATR_MULT,
            "hold_days": HOLD_DAYS,
            "min_score": MIN_SCORE,
            "top_n_picks": TOP_N,
            "train_end_year": TRAIN_END_YEAR,
            "start_year": START_YEAR,
        },
        "aggregate_full": aggregate_metrics(monthly_results),
        "aggregate_train": aggregate_metrics(train_results),
        "aggregate_holdout": aggregate_metrics(holdout_results),
        "monthly_results": monthly_results,
        "n_train_periods": len(train_results),
        "n_holdout_periods": len(holdout_results),
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n[{datetime.now().isoformat()}] Wrote {OUTPUT_FILE}", flush=True)
    print(f"\n=== TRAINING ({TRAIN_END_YEAR} and earlier) ===", flush=True)
    print(json.dumps(output["aggregate_train"], indent=2, default=str), flush=True)
    print(f"\n=== HOLDOUT ({TRAIN_END_YEAR + 1}+) ===", flush=True)
    print(json.dumps(output["aggregate_holdout"], indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
