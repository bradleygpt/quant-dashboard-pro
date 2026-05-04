"""
Regime-Aware Swing Trader Backtest
====================================

Architecture:
  Regime Detection Layer
  ├── Bull regime → Momentum/Breakout strategy
  ├── Bear regime → Mean-reversion strategy
  └── Transition → Cash (no trades)

Why this design:
  Traditional swing traders fail because they use ONE strategy across all market
  regimes. Mean-reversion strategies (buying pullbacks to EMAs) underperform in
  strong bull markets because winners blow past targets. Momentum/breakout
  strategies (buying new highs) get killed in bear markets because breakouts
  fail and reversal patterns dominate.

  This system detects regime monthly and routes to the appropriate strategy.
  The hypothesis: each strategy has a real edge in its native regime, and
  regime-correct execution should beat both buy-and-hold AND any single-style
  swing trader.

Regime detection:
  - Bull: SPY 50-day SMA > 200-day SMA by more than 1%
  - Bear: SPY 50-day SMA < 200-day SMA by more than 1%
  - Transition: within ±1% of crossover (high whipsaw risk - sit cash)

Bull strategy (momentum/breakout):
  - Entry signals: stock near 52-week high, strong RS vs SPY, above 50 EMA
  - Stops: 2.5x ATR (wider for breakout volatility)
  - Targets: NONE - trailing stop at 1.5x ATR below running high close
  - Hold: up to 21 days

Bear strategy (mean-reversion):
  - Entry signals: RSI<35, near 20 EMA from below, capitulation volume
  - Filter: skip stocks making new 52-week lows
  - Stops: 1.5x ATR (tight)
  - Target: 2x ATR fixed
  - Hold: max 7 days
"""

import os
import sys
import json
import time
import warnings
import math
from datetime import datetime, timedelta, date, timezone
from pathlib import Path

import pandas as pd
import numpy as np
import yfinance as yf

warnings.filterwarnings("ignore")

VARIANT_NAME = os.environ.get("VARIANT_NAME", "regime")
START_YEAR = int(os.environ.get("START_YEAR", "2005"))
TRAIN_END_YEAR = int(os.environ.get("TRAIN_END_YEAR", "2019"))
TOP_N = int(os.environ.get("TOP_N", "10"))
MAX_UNIVERSE_SIZE = 200

# Regime thresholds
REGIME_BULL_THRESHOLD = 0.01  # 1% above crossover for bull
REGIME_BEAR_THRESHOLD = -0.01  # 1% below crossover for bear

# Bull mode params
BULL_STOP_ATR = 2.5
BULL_TRAIL_ATR = 1.5
BULL_HOLD_DAYS = 21
BULL_MIN_SCORE = 50

# Bear mode params
BEAR_STOP_ATR = 1.5
BEAR_TARGET_ATR = 2.0
BEAR_HOLD_DAYS = 7
BEAR_MIN_SCORE = 50

OUTPUT_FILE = f"backtest_variant_{VARIANT_NAME}.json"


# ════════════════════════════════════════════════════════════════
# UNIVERSE & UTILITIES (mirrors build_backtest_optimizer.py)
# ════════════════════════════════════════════════════════════════

def get_universe_tickers(universe_file="universe.json"):
    if os.path.exists(universe_file):
        try:
            with open(universe_file) as f:
                tickers = json.load(f)
                return [t for t in tickers if t and isinstance(t, str)][:MAX_UNIVERSE_SIZE]
        except Exception:
            pass

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
    ][:MAX_UNIVERSE_SIZE]


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
    """Get historical prices using parquet cache (fast) with yfinance fallback."""
    try:
        from price_cache import get_prices
        hist = get_prices(ticker, start_date, end_date)
        if hist is not None and not hist.empty:
            return hist
    except ImportError:
        pass

    # Fallback
    try:
        df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# REGIME DETECTION
# ════════════════════════════════════════════════════════════════

def detect_regime(target_date):
    """
    Classify market regime as of target_date using SPY 50/200 SMA.

    Returns: 'bull', 'bear', 'transition', or None on data error
    """
    try:
        start = (target_date - timedelta(days=300)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")

        spy = fetch_historical_prices("SPY", start, end)
        if spy is None or len(spy) < 200:
            return None

        close = spy["Close"].astype(float)
        sma_50 = close.rolling(50).mean().iloc[-1]
        sma_200 = close.rolling(200).mean().iloc[-1]

        if pd.isna(sma_50) or pd.isna(sma_200) or sma_200 == 0:
            return None

        diff_pct = (sma_50 - sma_200) / sma_200

        if diff_pct > REGIME_BULL_THRESHOLD:
            return "bull"
        elif diff_pct < REGIME_BEAR_THRESHOLD:
            return "bear"
        else:
            return "transition"
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# BULL STRATEGY: MOMENTUM / BREAKOUT
# ════════════════════════════════════════════════════════════════

def compute_bull_score(ticker, target_date):
    """
    Score for bull regime - rewards momentum, breakouts, relative strength.

    Factors:
      - Distance from 52-week high (closer = better)
      - 6-month price return (higher = better, momentum confirmation)
      - Relative strength vs SPY over 60 days
      - Above 50 EMA in confirmed uptrend
      - Volume support on recent action
    """
    try:
        # Need 1 year of data for 52-week high and 6-month return
        start = (target_date - timedelta(days=400)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")

        hist = fetch_historical_prices(ticker, start, end)
        if hist is None or len(hist) < 200:
            return None

        close = hist["Close"].astype(float)
        high = hist["High"].astype(float)
        low = hist["Low"].astype(float)
        volume = hist["Volume"].astype(float)

        price = float(close.iloc[-1])

        # 52-week high and distance
        high_52w = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
        dist_from_52w_high_pct = (high_52w - price) / high_52w  # positive = below high

        # 6-month return
        six_mo_idx = max(0, len(close) - 126)
        six_mo_ago_price = float(close.iloc[six_mo_idx])
        six_mo_return = (price / six_mo_ago_price) - 1 if six_mo_ago_price > 0 else 0

        # Relative strength vs SPY (60-day)
        spy_hist = fetch_historical_prices("SPY", start, end)
        rel_strength = 1.0
        if spy_hist is not None and len(spy_hist) >= 60:
            spy_close = spy_hist["Close"].astype(float)
            sixty_idx = max(0, len(close) - 60)
            stock_60d_ret = (price / float(close.iloc[sixty_idx])) - 1
            spy_60d_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[max(0, len(spy_close) - 60)])) - 1
            if abs(spy_60d_ret) > 0.001:
                rel_strength = (1 + stock_60d_ret) / (1 + spy_60d_ret)

        # 50 EMA and trend confirmation
        ema_50 = close.ewm(span=50, adjust=False).mean()
        ema_50_val = float(ema_50.iloc[-1])
        above_ema_50 = price > ema_50_val

        # 50 EMA slope (rising = real uptrend)
        ema_50_20d_ago = float(ema_50.iloc[-21]) if len(ema_50) > 20 else ema_50_val
        ema_slope = (ema_50_val - ema_50_20d_ago) / ema_50_20d_ago if ema_50_20d_ago > 0 else 0

        # Volume support
        avg_volume_50d = float(volume.tail(50).mean()) if len(volume) >= 50 else float(volume.mean())
        recent_volume_5d = float(volume.tail(5).mean())
        volume_ratio = recent_volume_5d / avg_volume_50d if avg_volume_50d > 0 else 1.0

        # ATR for stop sizing
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(high.iloc[-1] - low.iloc[-1])
        atr_pct = atr_14 / price if price > 0 else 0.02

        # ── SCORING ────────────────────────────────────────────────
        score = 0

        # Proximity to 52-week high (closer = stronger)
        if dist_from_52w_high_pct < 0.03:  # within 3%
            score += 30
        elif dist_from_52w_high_pct < 0.07:  # within 7%
            score += 22
        elif dist_from_52w_high_pct < 0.15:  # within 15%
            score += 12
        elif dist_from_52w_high_pct < 0.25:
            score += 5
        # else: too far from highs, no points

        # 6-month return (momentum confirmation)
        if six_mo_return > 0.30:
            score += 20
        elif six_mo_return > 0.15:
            score += 15
        elif six_mo_return > 0.05:
            score += 8
        elif six_mo_return > 0:
            score += 3
        # negative 6-mo = no points

        # Relative strength
        if rel_strength > 1.20:  # 20% outperforming SPY
            score += 20
        elif rel_strength > 1.10:
            score += 15
        elif rel_strength > 1.00:
            score += 8

        # Trend confirmation
        if above_ema_50 and ema_slope > 0.01:
            score += 15
        elif above_ema_50:
            score += 8

        # Volume support
        if volume_ratio > 1.3:
            score += 10
        elif volume_ratio > 1.0:
            score += 5

        # Compute stop and trailing config (no fixed target in bull mode)
        stop_pct = atr_pct * BULL_STOP_ATR
        stop_price = price * (1 - stop_pct)

        # Synthetic "target" set very high so it never triggers (we use trailing)
        target_price = price * 10  # effectively infinite

        return {
            "ticker": ticker,
            "as_of_date": target_date.strftime("%Y-%m-%d"),
            "price": price,
            "swing_score": score,
            "target_price": target_price,
            "stop_price": stop_price,
            "stop_pct": stop_pct,
            "atr_pct": atr_pct,
            "regime": "bull",
            "rel_strength": rel_strength,
            "dist_from_52w_high": dist_from_52w_high_pct,
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# BEAR STRATEGY: MEAN REVERSION
# ════════════════════════════════════════════════════════════════

def compute_bear_score(ticker, target_date):
    """
    Score for bear regime - rewards oversold conditions, capitulation,
    quality stocks bouncing from short-term washouts.

    Factors:
      - RSI < 35 (oversold)
      - Near 20 EMA from below (pullback magnitude appropriate)
      - Volume capitulation (1.5x+ avg)
      - NOT making new 52-week lows (avoid catching falling knives)
    """
    try:
        start = (target_date - timedelta(days=400)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")

        hist = fetch_historical_prices(ticker, start, end)
        if hist is None or len(hist) < 100:
            return None

        close = hist["Close"].astype(float)
        high = hist["High"].astype(float)
        low = hist["Low"].astype(float)
        volume = hist["Volume"].astype(float)

        price = float(close.iloc[-1])

        # 52-week low filter - skip if making new lows
        low_52w = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())
        if price <= low_52w * 1.02:  # within 2% of low
            return None  # Don't catch falling knives

        # RSI 14
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.001)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

        # 20 EMA proximity
        ema_20 = close.ewm(span=20, adjust=False).mean()
        ema_20_val = float(ema_20.iloc[-1])
        below_ema_20_pct = (ema_20_val - price) / ema_20_val if ema_20_val > 0 else 0

        # Volume
        avg_volume_20d = float(volume.tail(20).mean()) if len(volume) >= 20 else float(volume.mean())
        recent_volume = float(volume.iloc[-1])
        volume_ratio = recent_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0

        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(high.iloc[-1] - low.iloc[-1])
        atr_pct = atr_14 / price if price > 0 else 0.02

        # ── SCORING ────────────────────────────────────────────────
        score = 0

        # Oversold (lower RSI = better in bear regime)
        if rsi_val < 25:
            score += 30
        elif rsi_val < 35:
            score += 22
        elif rsi_val < 45:
            score += 10
        elif rsi_val < 55:
            score += 3

        # Pullback magnitude (we want stocks 1-3 ATR below 20 EMA)
        below_in_atr = below_ema_20_pct / atr_pct if atr_pct > 0 else 0
        if 1.0 <= below_in_atr <= 3.0:
            score += 25
        elif 0.5 <= below_in_atr < 1.0:
            score += 15
        elif 3.0 < below_in_atr <= 5.0:
            score += 12  # deeper pullback OK but riskier

        # Volume capitulation
        if volume_ratio > 2.0:
            score += 20
        elif volume_ratio > 1.5:
            score += 15
        elif volume_ratio > 1.2:
            score += 8

        # Not too far below 52-week high (means stock had quality recently)
        high_52w = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
        dist_from_high = (high_52w - price) / high_52w
        if dist_from_high < 0.20:
            score += 15
        elif dist_from_high < 0.30:
            score += 8

        # Stop and target
        stop_pct = atr_pct * BEAR_STOP_ATR
        target_pct = atr_pct * BEAR_TARGET_ATR
        stop_price = price * (1 - stop_pct)
        target_price = price * (1 + target_pct)

        return {
            "ticker": ticker,
            "as_of_date": target_date.strftime("%Y-%m-%d"),
            "price": price,
            "swing_score": score,
            "target_price": target_price,
            "stop_price": stop_price,
            "stop_pct": stop_pct,
            "target_pct": target_pct,
            "atr_pct": atr_pct,
            "regime": "bear",
            "rsi": rsi_val,
            "below_ema_20_atr": below_in_atr,
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# TRADE SIMULATION (with regime-aware exit logic)
# ════════════════════════════════════════════════════════════════

def simulate_trade(ticker, entry_date, entry_price, target_price, stop_price,
                   hold_days, atr_pct=None, use_trailing_stop=False, trail_atr_mult=1.5):
    """Simulate trade with optional trailing stop (used in bull mode)."""
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

        if use_trailing_stop and atr_pct is not None:
            running_high_close = entry_price
            trail_active = False
            activation_price = entry_price * (1 + atr_pct)
            trail_distance = trail_atr_mult * atr_pct

            for i, (dt, row) in enumerate(hist.iterrows()):
                day_high = float(row["High"])
                day_low = float(row["Low"])
                day_close = float(row["Close"])

                if not trail_active and day_low <= stop_price:
                    realistic_exit_price = stop_price
                    realistic_exit_reason = "stop"
                    break

                if not trail_active and day_high >= activation_price:
                    trail_active = True
                    running_high_close = day_close

                if trail_active:
                    if day_close > running_high_close:
                        running_high_close = day_close

                    trail_stop_price = running_high_close * (1 - trail_distance)
                    if day_low <= trail_stop_price:
                        realistic_exit_price = trail_stop_price
                        realistic_exit_reason = "trail_stop"
                        break

            realistic_return = ((realistic_exit_price - entry_price) / entry_price) * 100

        else:
            # Fixed target/stop (bear mode)
            for i, (dt, row) in enumerate(hist.iterrows()):
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
    """Get SPY's return over the same hold window for benchmark."""
    try:
        end_date = start_date + timedelta(days=hold_days + 5)
        hist = fetch_historical_prices("SPY", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if hist is None or len(hist) < 2:
            return None
        hist = hist.head(hold_days)
        if len(hist) < 2:
            return None
        first_close = float(hist["Close"].iloc[0])
        last_close = float(hist["Close"].iloc[-1])
        return ((last_close - first_close) / first_close) * 100
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# MONTHLY BACKTEST: detect regime, route, execute
# ════════════════════════════════════════════════════════════════

def run_monthly_backtest(checkpoint_date, universe, top_n):
    """Run one monthly checkpoint with regime-aware strategy routing."""

    # Detect regime
    regime = detect_regime(checkpoint_date)

    base_result = {
        "date": checkpoint_date.strftime("%Y-%m-%d"),
        "regime": regime,
        "n_qualified": 0,
        "top_picks": [],
        "portfolio_return_realistic": None,
        "portfolio_return_max": None,
        "spy_return_pct": None,
    }

    if regime is None:
        return base_result

    if regime == "transition":
        # Sit cash - record SPY for benchmark but no trades
        base_result["spy_return_pct"] = fetch_spy_return(checkpoint_date, BULL_HOLD_DAYS)
        return base_result

    # Pick strategy and parameters based on regime
    if regime == "bull":
        score_fn = compute_bull_score
        hold_days = BULL_HOLD_DAYS
        min_score = BULL_MIN_SCORE
        use_trailing = True
        trail_mult = BULL_TRAIL_ATR
    else:  # bear
        score_fn = compute_bear_score
        hold_days = BEAR_HOLD_DAYS
        min_score = BEAR_MIN_SCORE
        use_trailing = False
        trail_mult = 1.5

    # Score all candidates
    candidates = []
    for ticker in universe:
        result = score_fn(ticker, checkpoint_date)
        if result and result["swing_score"] >= min_score:
            candidates.append(result)

    base_result["n_qualified"] = len(candidates)

    if not candidates:
        base_result["spy_return_pct"] = fetch_spy_return(checkpoint_date, hold_days)
        return base_result

    # Top N by swing score
    top = sorted(candidates, key=lambda x: x["swing_score"], reverse=True)[:top_n]

    # Score-weighted allocation
    total_score = sum(c["swing_score"] for c in top)
    weights = [c["swing_score"] / total_score for c in top] if total_score > 0 else [1.0 / len(top)] * len(top)

    realistic_returns = []
    max_returns = []
    detailed = []

    for c, w in zip(top, weights):
        sim = simulate_trade(
            c["ticker"], checkpoint_date, c["price"],
            c["target_price"], c["stop_price"], hold_days,
            atr_pct=c.get("atr_pct"),
            use_trailing_stop=use_trailing,
            trail_atr_mult=trail_mult,
        )
        if sim:
            realistic_returns.append(sim["realistic_return_pct"] * w)
            max_returns.append(sim["max_return_pct"] * w)
            detailed.append({
                "ticker": c["ticker"],
                "swing_score": c["swing_score"],
                "regime": regime,
                "weight": w,
                "realistic_return_pct": sim["realistic_return_pct"],
                "realistic_exit_reason": sim["realistic_exit_reason"],
                "max_return_pct": sim["max_return_pct"],
            })

    base_result["top_picks"] = detailed
    base_result["portfolio_return_realistic"] = sum(realistic_returns) if realistic_returns else None
    base_result["portfolio_return_max"] = sum(max_returns) if max_returns else None
    base_result["spy_return_pct"] = fetch_spy_return(checkpoint_date, hold_days)

    return base_result


# ════════════════════════════════════════════════════════════════
# AGGREGATION & ANALYSIS
# ════════════════════════════════════════════════════════════════

def aggregate_metrics(monthly_results):
    """Compute aggregate metrics across a list of monthly results."""
    valid = [m for m in monthly_results if m.get("portfolio_return_realistic") is not None]
    cash_months = [m for m in monthly_results if m.get("portfolio_return_realistic") is None and m.get("regime") == "transition"]

    # Compounded return: cash months count as 0% for portfolio
    cum_realistic = 1.0
    cum_max = 1.0
    cum_spy = 1.0
    cum_spy_full = 1.0  # would-be true buy-and-hold (reuses same window data)

    valid_with_cash = []
    for m in monthly_results:
        if m.get("portfolio_return_realistic") is not None:
            cum_realistic *= (1 + m["portfolio_return_realistic"] / 100)
            cum_max *= (1 + m.get("portfolio_return_max", 0) / 100)
            valid_with_cash.append("trade")
        else:
            # Cash month - 0% return for portfolio
            valid_with_cash.append("cash")
        if m.get("spy_return_pct") is not None:
            cum_spy *= (1 + m["spy_return_pct"] / 100)

    n_total = len(monthly_results)
    n_traded = len([x for x in valid_with_cash if x == "trade"])
    n_cash = len([x for x in valid_with_cash if x == "cash"])

    if not valid:
        return {
            "n_total_periods": n_total,
            "n_traded_periods": n_traded,
            "n_cash_periods": n_cash,
            "compounded_realistic_pct": None,
            "compounded_spy_pct": None,
        }

    realistic_returns = [m["portfolio_return_realistic"] for m in valid]
    spy_returns = [m["spy_return_pct"] for m in valid if m.get("spy_return_pct") is not None]

    # Win rate
    wins = [r for r in realistic_returns if r > 0]
    win_rate = (len(wins) / len(realistic_returns)) * 100 if realistic_returns else 0

    # Drawdown
    peak = 1.0
    max_dd = 0.0
    cum = 1.0
    for m in monthly_results:
        if m.get("portfolio_return_realistic") is not None:
            cum *= (1 + m["portfolio_return_realistic"] / 100)
        if cum > peak:
            peak = cum
        dd = (cum - peak) / peak
        if dd < max_dd:
            max_dd = dd

    # Annualized
    years = n_total / 12
    annualized = (cum_realistic ** (1 / years) - 1) * 100 if years > 0 else 0
    spy_annualized = (cum_spy ** (1 / years) - 1) * 100 if years > 0 and cum_spy > 0 else 0

    # Regime breakdown
    regime_counts = {"bull": 0, "bear": 0, "transition": 0, "none": 0}
    regime_returns = {"bull": [], "bear": []}
    for m in monthly_results:
        r = m.get("regime") or "none"
        regime_counts[r] = regime_counts.get(r, 0) + 1
        if r in ("bull", "bear") and m.get("portfolio_return_realistic") is not None:
            regime_returns[r].append(m["portfolio_return_realistic"])

    return {
        "n_total_periods": n_total,
        "n_traded_periods": n_traded,
        "n_cash_periods": n_cash,
        "n_valid": len(valid),
        "win_rate_pct": round(win_rate, 2),
        "avg_return_pct": round(sum(realistic_returns) / len(realistic_returns), 3) if realistic_returns else 0,
        "median_return_pct": round(sorted(realistic_returns)[len(realistic_returns) // 2], 3) if realistic_returns else 0,
        "compounded_realistic_pct": round((cum_realistic - 1) * 100, 2),
        "compounded_max_pct": round((cum_max - 1) * 100, 2),
        "compounded_spy_pct": round((cum_spy - 1) * 100, 2),
        "annualized_pct": round(annualized, 2),
        "spy_annualized_pct": round(spy_annualized, 2),
        "edge_vs_spy_annualized": round(annualized - spy_annualized, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "regime_counts": regime_counts,
        "bull_avg_return": round(sum(regime_returns["bull"]) / len(regime_returns["bull"]), 3) if regime_returns["bull"] else None,
        "bear_avg_return": round(sum(regime_returns["bear"]) / len(regime_returns["bear"]), 3) if regime_returns["bear"] else None,
    }


def split_train_holdout(monthly_results, train_end_year):
    train = [m for m in monthly_results if int(m["date"][:4]) <= train_end_year]
    holdout = [m for m in monthly_results if int(m["date"][:4]) > train_end_year]
    return train, holdout


def main():
    print(f"Regime-Aware Backtest: {VARIANT_NAME}", flush=True)
    print(f"Start year: {START_YEAR}, Train through: {TRAIN_END_YEAR}", flush=True)
    print(f"Bull params: stop={BULL_STOP_ATR}x ATR, trail={BULL_TRAIL_ATR}x ATR, hold={BULL_HOLD_DAYS}d", flush=True)
    print(f"Bear params: stop={BEAR_STOP_ATR}x ATR, target={BEAR_TARGET_ATR}x ATR, hold={BEAR_HOLD_DAYS}d", flush=True)
    print(flush=True)

    universe = get_universe_tickers()
    print(f"Universe size: {len(universe)}", flush=True)

    checkpoint_dates = get_first_of_months(start_year=START_YEAR)
    print(f"Total checkpoints: {len(checkpoint_dates)}", flush=True)
    print(flush=True)

    monthly_results = []
    for i, cp_date in enumerate(checkpoint_dates):
        result = run_monthly_backtest(cp_date, universe, TOP_N)
        monthly_results.append(result)

        regime = result.get("regime") or "n/a"
        nq = result.get("n_qualified", 0)
        ret = result.get("portfolio_return_realistic")
        spy = result.get("spy_return_pct")
        ret_str = f"{ret:+.2f}%" if ret is not None else "cash"
        spy_str = f"{spy:+.2f}%" if spy is not None else "n/a"
        print(f"[{i+1}/{len(checkpoint_dates)}] {cp_date}: regime={regime}, picks={nq}, ret={ret_str}, spy={spy_str}", flush=True)

    train, holdout = split_train_holdout(monthly_results, TRAIN_END_YEAR)

    output = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "variant_name": VARIANT_NAME,
        "parameters": {
            "regime_bull_threshold": REGIME_BULL_THRESHOLD,
            "regime_bear_threshold": REGIME_BEAR_THRESHOLD,
            "bull_stop_atr": BULL_STOP_ATR,
            "bull_trail_atr": BULL_TRAIL_ATR,
            "bull_hold_days": BULL_HOLD_DAYS,
            "bear_stop_atr": BEAR_STOP_ATR,
            "bear_target_atr": BEAR_TARGET_ATR,
            "bear_hold_days": BEAR_HOLD_DAYS,
            "top_n_picks": TOP_N,
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
    print(flush=True)

    full = output["aggregate_full"]
    print("=" * 70, flush=True)
    print("FULL PERIOD SUMMARY", flush=True)
    print("=" * 70, flush=True)
    print(f"Compounded: {full.get('compounded_realistic_pct')}% vs SPY {full.get('compounded_spy_pct')}%", flush=True)
    print(f"Annualized: {full.get('annualized_pct')}% vs SPY {full.get('spy_annualized_pct')}%", flush=True)
    print(f"Edge: {full.get('edge_vs_spy_annualized')}%", flush=True)
    print(f"Win rate: {full.get('win_rate_pct')}%", flush=True)
    print(f"Max drawdown: {full.get('max_drawdown_pct')}%", flush=True)
    print(f"Regime: {full.get('regime_counts')}", flush=True)
    print(f"Bull avg: {full.get('bull_avg_return')}%, Bear avg: {full.get('bear_avg_return')}%", flush=True)


if __name__ == "__main__":
    main()
