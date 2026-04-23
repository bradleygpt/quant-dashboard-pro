"""
IBD Swing Trader Module
Identifies short-term swing trade candidates using methodology inspired by
IBD SwingTrader and CAN SLIM principles.

Core approach:
- Combine fundamental quality (from our 5-pillar scores) with technical setups
- Focus on stocks bouncing off support with volume confirmation
- Provide structured trade plans with entry, profit target (5-10%), and stop-loss (3-5%)

Key technical indicators:
1. 21-day EMA (primary trend line for swing trades)
2. Volume analysis (institutional buying/selling)
3. Regression channel (optimal buy/sell zones)
4. Relative Strength vs S&P 500
5. Price action patterns (pullback to support, breakout)
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime


# ── Swing Trade Configuration ──────────────────────────────────────

SWING_CONFIG = {
    # Trade parameters
    "profit_target_pct": 0.075,      # 7.5% default profit target (5-10% range)
    "stop_loss_pct": 0.04,           # 4% default stop loss (3-5% range)
    "min_composite_score": 6.5,      # Minimum quant score to qualify
    "min_market_cap_b": 2.0,         # $2B+ only (no micro-caps for swings)
    "max_results": 25,               # Top candidates to return

    # Technical thresholds
    "ema_21_proximity_pct": 0.03,    # Within 3% of 21-EMA = near support
    "volume_surge_ratio": 1.3,       # 30%+ above average = institutional interest
    "rsi_oversold": 35,              # RSI below this = oversold bounce candidate
    "rsi_overbought": 70,            # RSI above this = avoid
    "min_rs_percentile": 50,         # Relative strength vs S&P 500 (top half)
}


def compute_swing_signals(ticker, scored_df):
    """
    Compute swing trade technical signals for a single stock.
    Returns dict with all technical data and a composite swing score.
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo")
        if hist.empty or len(hist) < 50:
            return None

        close = hist["Close"].astype(float)
        volume = hist["Volume"].astype(float)
        high = hist["High"].astype(float)
        low = hist["Low"].astype(float)
        price = float(close.iloc[-1])

        # ── 21-Day EMA (primary swing trend line) ──────────────────
        ema_21 = close.ewm(span=21, adjust=False).mean()
        ema_21_val = float(ema_21.iloc[-1])
        dist_from_ema21 = (price - ema_21_val) / ema_21_val

        # EMA slope (is the trend up?)
        ema_21_5d_ago = float(ema_21.iloc[-6]) if len(ema_21) > 5 else ema_21_val
        ema_slope = (ema_21_val - ema_21_5d_ago) / ema_21_5d_ago

        # ── 50-Day and 10-Day SMAs ─────────────────────────────────
        sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        sma_10 = float(close.rolling(10).mean().iloc[-1]) if len(close) >= 10 else None

        # ── Volume Analysis ────────────────────────────────────────
        avg_vol_50 = float(volume.rolling(50).mean().iloc[-1]) if len(volume) >= 50 else float(volume.mean())
        recent_vol = float(volume.iloc[-1])
        vol_5d_avg = float(volume.iloc[-5:].mean())
        volume_ratio = vol_5d_avg / avg_vol_50 if avg_vol_50 > 0 else 1.0

        # Up-volume vs down-volume (last 10 days)
        price_changes = close.diff()
        up_vol = volume[price_changes > 0].iloc[-10:].sum() if len(volume) >= 10 else 0
        down_vol = volume[price_changes < 0].iloc[-10:].sum() if len(volume) >= 10 else 1
        up_down_vol_ratio = up_vol / down_vol if down_vol > 0 else 1.0

        # ── RSI (14-day) ───────────────────────────────────────────
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss
        rsi = float(100 - (100 / (1 + rs.iloc[-1]))) if not np.isnan(rs.iloc[-1]) else 50

        # ── Regression Channel (20-day) ────────────────────────────
        if len(close) >= 20:
            y = close.iloc[-20:].values
            x = np.arange(20)
            coeffs = np.polyfit(x, y, 1)
            trend_line = np.polyval(coeffs, x)
            residuals = y - trend_line
            std_dev = np.std(residuals)
            channel_upper = float(trend_line[-1] + 2 * std_dev)
            channel_lower = float(trend_line[-1] - 2 * std_dev)
            channel_mid = float(trend_line[-1])
            channel_position = (price - channel_lower) / (channel_upper - channel_lower) if (channel_upper - channel_lower) > 0 else 0.5
        else:
            channel_upper = channel_lower = channel_mid = price
            channel_position = 0.5

        # ── Recent Price Action ────────────────────────────────────
        high_20d = float(high.iloc[-20:].max())
        low_20d = float(low.iloc[-20:].min())
        pct_from_20d_high = (price - high_20d) / high_20d
        pct_from_20d_low = (price - low_20d) / low_20d

        # Pullback detection: stock pulled back 3-8% from recent high
        is_pullback = -0.08 <= pct_from_20d_high <= -0.02

        # Bounce detection: price closed above previous day and near 21-EMA
        prev_close = float(close.iloc[-2]) if len(close) >= 2 else price
        is_bouncing = price > prev_close and abs(dist_from_ema21) < 0.03

        # ── Composite Swing Score (0-100) ──────────────────────────
        score = 0

        # 1. Proximity to 21-EMA (25 pts) - best when slightly above or touching
        if -0.01 <= dist_from_ema21 <= 0.02:
            score += 25  # Right at or just above 21-EMA = prime setup
        elif -0.03 <= dist_from_ema21 <= 0.04:
            score += 18  # Close to 21-EMA
        elif dist_from_ema21 > 0.04:
            score += max(0, 12 - int(dist_from_ema21 * 100))  # Extended above
        else:
            score += max(0, 10 + int(dist_from_ema21 * 200))  # Below 21-EMA

        # 2. EMA slope / trend direction (20 pts)
        if ema_slope > 0.005:
            score += 20  # Strong uptrend
        elif ema_slope > 0:
            score += 15  # Mild uptrend
        elif ema_slope > -0.005:
            score += 8   # Flat
        else:
            score += 0   # Downtrend

        # 3. Volume confirmation (15 pts)
        if volume_ratio > 1.5 and up_down_vol_ratio > 1.2:
            score += 15  # High volume + buying pressure
        elif volume_ratio > 1.2:
            score += 10
        elif up_down_vol_ratio > 1.0:
            score += 7
        else:
            score += 3

        # 4. RSI positioning (15 pts)
        if 35 <= rsi <= 55:
            score += 15  # Oversold bounce zone
        elif 55 < rsi <= 65:
            score += 10  # Neutral
        elif rsi < 35:
            score += 8   # Deeply oversold (risky but high reward)
        elif rsi > 70:
            score += 0   # Overbought = avoid
        else:
            score += 5

        # 5. Pullback/bounce pattern (15 pts)
        if is_pullback and is_bouncing:
            score += 15  # Ideal: pulled back and now bouncing
        elif is_pullback:
            score += 10  # Pulled back, waiting for bounce
        elif is_bouncing:
            score += 8   # Bouncing but not from a clean pullback
        else:
            score += 3

        # 6. Channel position (10 pts) - best near lower channel
        if channel_position < 0.3:
            score += 10  # Near lower band
        elif channel_position < 0.5:
            score += 7   # Below midline
        elif channel_position < 0.7:
            score += 4   # Above midline
        else:
            score += 1   # Near upper band (extended)

        # ── Setup Classification ───────────────────────────────────
        if score >= 75:
            setup = "A+ Setup"
            setup_color = "#22C55E"
        elif score >= 60:
            setup = "Strong Setup"
            setup_color = "#84CC16"
        elif score >= 45:
            setup = "Developing"
            setup_color = "#EAB308"
        elif score >= 30:
            setup = "Weak"
            setup_color = "#F97316"
        else:
            setup = "Avoid"
            setup_color = "#EF4444"

        # ── Trade Plan ─────────────────────────────────────────────
        # Entry: current price (or slightly below for limit orders)
        entry_price = price
        # Profit target: 5-10% based on volatility
        atr_14 = float((high - low).rolling(14).mean().iloc[-1]) if len(high) >= 14 else price * 0.02
        atr_pct = atr_14 / price
        profit_target_pct = max(0.05, min(0.10, atr_pct * 3))
        target_price = round(entry_price * (1 + profit_target_pct), 2)
        # Stop loss: 3-5% based on support levels
        stop_loss_pct = max(0.03, min(0.05, atr_pct * 1.5))
        stop_price = round(entry_price * (1 - stop_loss_pct), 2)
        # Risk/reward ratio
        reward = target_price - entry_price
        risk = entry_price - stop_price
        risk_reward = round(reward / risk, 2) if risk > 0 else 0

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "swing_score": score,
            "setup": setup,
            "setup_color": setup_color,

            # Trade plan
            "entry_price": round(entry_price, 2),
            "target_price": target_price,
            "target_pct": round(profit_target_pct * 100, 1),
            "stop_price": stop_price,
            "stop_pct": round(stop_loss_pct * 100, 1),
            "risk_reward": risk_reward,

            # Technical indicators
            "ema_21": round(ema_21_val, 2),
            "dist_from_ema21_pct": round(dist_from_ema21 * 100, 2),
            "ema_slope": round(ema_slope * 100, 3),
            "sma_50": round(sma_50, 2) if sma_50 else None,
            "sma_10": round(sma_10, 2) if sma_10 else None,
            "rsi_14": round(rsi, 1),
            "volume_ratio": round(volume_ratio, 2),
            "up_down_vol_ratio": round(up_down_vol_ratio, 2),
            "channel_position": round(channel_position * 100, 1),
            "channel_upper": round(channel_upper, 2),
            "channel_lower": round(channel_lower, 2),
            "pct_from_20d_high": round(pct_from_20d_high * 100, 1),

            # Pattern flags
            "is_pullback": is_pullback,
            "is_bouncing": is_bouncing,
            "trend": "Uptrend" if ema_slope > 0.002 else "Flat" if ema_slope > -0.002 else "Downtrend",
        }
    except Exception as e:
        return None


def scan_swing_candidates(scored_df, max_scan=150, min_score=6.5, min_mcap=2.0):
    """
    Scan the scored universe for swing trade candidates.
    Pre-filters by quant score and market cap, then computes technicals.

    Strategy: We want stocks that are fundamentally strong (high quant score)
    AND technically set up for a short-term move (near 21-EMA, good volume, etc.)
    """
    # Pre-filter: fundamentally strong stocks only
    candidates = scored_df[
        (scored_df["composite_score"] >= min_score) &
        (scored_df["marketCapB"] >= min_mcap) &
        (scored_df["sector"] != "ETF") &
        (scored_df.get("type", "stock") != "etf")
    ].sort_values("composite_score", ascending=False).head(max_scan)

    if candidates.empty:
        return []

    results = []
    total = len(candidates)
    for i, ticker in enumerate(candidates.index):
        signal = compute_swing_signals(ticker, scored_df)
        if signal and signal["swing_score"] >= 30:
            # Add quant data
            row = scored_df.loc[ticker]
            signal["shortName"] = row.get("shortName", ticker)
            signal["sector"] = row.get("sector", "Unknown")
            signal["composite_score"] = row.get("composite_score", 0)
            signal["overall_rating"] = row.get("overall_rating", "Hold")
            signal["marketCapB"] = row.get("marketCapB", 0)

            # Combined score: 60% swing technical + 40% quant fundamental
            quant_normalized = (signal["composite_score"] / 12) * 100
            signal["combined_score"] = round(0.6 * signal["swing_score"] + 0.4 * quant_normalized, 1)

            results.append(signal)

    # Sort by combined score (best setups first)
    results.sort(key=lambda x: x["combined_score"], reverse=True)
    return results[:SWING_CONFIG["max_results"]]


def get_swing_methodology():
    """Return explanation of the swing trade methodology for the UI."""
    return {
        "title": "IBD-Inspired Swing Trader",
        "summary": "Identifies short-term trade candidates by combining fundamental quality (5-pillar quant score) with technical swing setups. Targets 5-10% gains over 3-10 trading days.",
        "components": [
            {"name": "21-Day EMA Proximity", "weight": "25%",
             "description": "Best setups occur when price is at or just above the 21-day exponential moving average. This is the primary trend line for swing trades."},
            {"name": "Trend Direction", "weight": "20%",
             "description": "The 21-EMA must be sloping upward, confirming the stock is in an uptrend. We buy strength, not dips in downtrends."},
            {"name": "Volume Confirmation", "weight": "15%",
             "description": "Above-average volume with more up-volume than down-volume signals institutional buying. Volume ratio > 1.3x = institutional interest."},
            {"name": "RSI Positioning", "weight": "15%",
             "description": "RSI between 35-55 is the sweet spot for swing entries. Oversold enough for a bounce but not in free-fall."},
            {"name": "Pullback + Bounce Pattern", "weight": "15%",
             "description": "Ideal entry: stock has pulled back 3-8% from a recent high and is now showing a reversal (closing higher). This is 'buying strength' not 'buying the dip'."},
            {"name": "Regression Channel", "weight": "10%",
             "description": "20-day regression channel identifies where price sits within its normal range. Best entries are near the lower channel band."},
        ],
        "trade_plan": {
            "entry": "At current price when setup score >= 60",
            "profit_target": "5-10% (scaled by ATR volatility)",
            "stop_loss": "3-5% below entry (scaled by ATR)",
            "holding_period": "3-10 trading days typical",
            "risk_reward": "Minimum 1.5:1 risk/reward ratio preferred",
        },
        "filters": {
            "min_quant_score": "6.5/12 (Hold or better)",
            "min_market_cap": "$2B+",
            "excluded": "ETFs, micro-caps, downtrending stocks",
        },
    }
