"""
Quant Buy Point Calculator.
Computes a data-driven buy-point price using:

1. Bollinger Band Lower (30%) - price at which stock is statistically oversold
2. Mean Reversion Target (25%) - 50-day SMA as equilibrium price
3. Support Level (20%) - recent trading floor from price history
4. Fair Value Discount (25%) - 10% below composite fair value

Also outputs:
- Current signal strength (how close is current price to buy point)
- Distance to buy point as percentage
- Bollinger Band position (0-100, where 0 = at/below lower band)
"""

import numpy as np
import pandas as pd
import yfinance as yf


def compute_buy_point(ticker: str, scored_df: pd.DataFrame = None, fair_value: float = None) -> dict:
    """
    Compute a quant buy point for a stock.
    Uses 1 year of daily price history for technical calculations.
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")

        if hist.empty or len(hist) < 50:
            return {"error": f"Insufficient price history for {ticker}."}

        close = hist["Close"].astype(float)
        current_price = float(close.iloc[-1])

        components = {}

        # ── Component 1: Bollinger Band Lower (30%) ────────────────
        bb = _bollinger_bands(close)
        if bb:
            components["Bollinger Lower Band"] = {
                "price": bb["lower"],
                "weight": 0.30,
                "description": f"20-day SMA minus 2 std devs. Current BB position: {bb['position']:.0f}/100",
            }

        # ── Component 2: Mean Reversion / 50-SMA (25%) ─────────────
        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        if sma50 and sma50 > 0:
            # Buy point is 5% below the 50-SMA (mean reversion target)
            mr_target = sma50 * 0.95
            components["Mean Reversion (50-SMA)"] = {
                "price": round(mr_target, 2),
                "weight": 0.25,
                "description": f"5% below 50-day SMA (${sma50:.2f}). Stocks tend to revert to this level.",
            }

        # ── Component 3: Support Level (20%) ───────────────────────
        support = _compute_support(close)
        if support:
            components["Support Level"] = {
                "price": support,
                "weight": 0.20,
                "description": "Recent price floor from 6-month lows and volume-weighted levels.",
            }

        # ── Component 4: Fair Value Discount (25%) ─────────────────
        if fair_value and fair_value > 0:
            # Buy point at 10% discount to fair value
            fv_buy = fair_value * 0.90
            components["Fair Value Discount"] = {
                "price": round(fv_buy, 2),
                "weight": 0.25,
                "description": f"10% below fair value (${fair_value:.2f}). Margin of safety.",
            }
        elif scored_df is not None and ticker in scored_df.index:
            # Try computing fair value
            try:
                from fairvalue import compute_fair_value
                fv_result = compute_fair_value(ticker, scored_df)
                if "error" not in fv_result:
                    fv = fv_result["composite_fair_value"]
                    fv_buy = fv * 0.90
                    components["Fair Value Discount"] = {
                        "price": round(fv_buy, 2),
                        "weight": 0.25,
                        "description": f"10% below fair value (${fv:.2f}). Margin of safety.",
                    }
            except Exception:
                pass

        if not components:
            return {"error": "Could not compute buy point components."}

        # ── Weighted Buy Point ─────────────────────────────────────
        total_w = sum(c["weight"] for c in components.values())
        buy_point = sum(c["price"] * c["weight"] for c in components.values()) / total_w

        # ── Signal Strength ────────────────────────────────────────
        distance_pct = ((current_price - buy_point) / buy_point) * 100

        if distance_pct <= 0:
            signal = "AT BUY POINT"
            signal_color = "#00C805"
            signal_score = 100
        elif distance_pct < 3:
            signal = "Near Buy Point"
            signal_color = "#8BC34A"
            signal_score = 85
        elif distance_pct < 8:
            signal = "Approaching"
            signal_color = "#FFC107"
            signal_score = 60
        elif distance_pct < 15:
            signal = "Above Buy Point"
            signal_color = "#FF9800"
            signal_score = 35
        else:
            signal = "Far from Buy Point"
            signal_color = "#FF5722"
            signal_score = 10

        # ── Additional Technical Context ───────────────────────────
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        rsi = _compute_rsi(close)

        technicals = {}
        if sma50:
            technicals["50-Day SMA"] = f"${sma50:.2f}"
            technicals["Price vs 50-SMA"] = f"{((current_price / sma50) - 1) * 100:+.1f}%"
        if sma200:
            technicals["200-Day SMA"] = f"${sma200:.2f}"
            technicals["Price vs 200-SMA"] = f"{((current_price / sma200) - 1) * 100:+.1f}%"
        if bb:
            technicals["Bollinger Upper"] = f"${bb['upper']:.2f}"
            technicals["Bollinger Lower"] = f"${bb['lower']:.2f}"
            technicals["BB Position"] = f"{bb['position']:.0f}/100"
        if rsi is not None:
            technicals["RSI (14)"] = f"{rsi:.1f}"
            if rsi < 30: technicals["RSI Signal"] = "Oversold"
            elif rsi > 70: technicals["RSI Signal"] = "Overbought"
            else: technicals["RSI Signal"] = "Neutral"

        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "buy_point": round(buy_point, 2),
            "distance_pct": round(distance_pct, 1),
            "signal": signal,
            "signal_color": signal_color,
            "signal_score": signal_score,
            "components": components,
            "technicals": technicals,
        }

    except Exception as e:
        return {"error": f"Error computing buy point: {str(e)}"}


def _bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0) -> dict | None:
    """Compute Bollinger Bands and current position within them."""
    if len(close) < window:
        return None

    sma = float(close.rolling(window).mean().iloc[-1])
    std = float(close.rolling(window).std().iloc[-1])

    if std <= 0:
        return None

    upper = sma + (num_std * std)
    lower = sma - (num_std * std)
    current = float(close.iloc[-1])

    # Position: 0 = at lower band, 50 = at SMA, 100 = at upper band
    if upper > lower:
        position = ((current - lower) / (upper - lower)) * 100
        position = max(0, min(100, position))
    else:
        position = 50

    return {
        "upper": round(upper, 2),
        "lower": round(lower, 2),
        "sma": round(sma, 2),
        "std": round(std, 2),
        "position": round(position, 1),
    }


def _compute_support(close: pd.Series) -> float | None:
    """Compute support level from recent price floors."""
    if len(close) < 60:
        return None

    # Use recent 6 months (~126 trading days)
    recent = close.iloc[-126:] if len(close) >= 126 else close

    # Support = average of the bottom 10th percentile prices
    q10 = recent.quantile(0.10)
    support_prices = recent[recent <= q10]

    if len(support_prices) > 0:
        support = float(support_prices.mean())
        return round(support, 2)

    return round(float(recent.min()), 2)


def _compute_rsi(close: pd.Series, periods: int = 14) -> float | None:
    """Compute RSI (Relative Strength Index)."""
    if len(close) < periods + 1:
        return None

    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=periods, min_periods=periods).mean().iloc[-1]
    avg_loss = loss.rolling(window=periods, min_periods=periods).mean().iloc[-1]

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return round(float(rsi), 1)


def compute_buy_points_batch(tickers: list[str], scored_df: pd.DataFrame = None) -> dict:
    """Compute buy points for multiple tickers."""
    results = {}
    for ticker in tickers:
        bp = compute_buy_point(ticker, scored_df)
        if "error" not in bp:
            results[ticker] = {
                "buy_point": bp["buy_point"],
                "distance_pct": bp["distance_pct"],
                "signal": bp["signal"],
                "signal_color": bp["signal_color"],
            }
        else:
            results[ticker] = {"buy_point": None, "distance_pct": None, "signal": "N/A", "signal_color": "#666"}
    return results
