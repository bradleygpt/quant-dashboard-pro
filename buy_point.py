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

Performance: Accepts optional pre-fetched price_history DataFrame to avoid yfinance
calls. When called in batch from scoring.py, callers should pass histories from
prices_cache.parquet via price_cache.get_prices().
"""

import numpy as np
import pandas as pd
import yfinance as yf


def compute_buy_point(ticker: str, scored_df: pd.DataFrame = None, fair_value: float = None,
                       price_history: pd.DataFrame = None,
                       current_price: float = None) -> dict:
    """
    Compute a quant buy point for a stock.
    Uses 1 year of daily price history for technical calculations.

    Args:
        ticker: Stock ticker symbol.
        scored_df: Optional scored universe DataFrame (used to compute fair value if needed).
        fair_value: Optional pre-computed fair value (skips internal FV computation).
        price_history: Optional pre-fetched DataFrame with columns including 'close' (lowercase)
                       or 'Close' (yfinance style). If None, fetches live from yfinance.
                       Pass this to avoid yfinance HTTP calls when running in batch.
        current_price: Optional override for current price. If provided, used INSTEAD of
                       close.iloc[-1] (which is the last daily close from price_history
                       or yfinance). Pass this to ensure FV and QBP share a single price
                       source on the dashboard (prevents ~5% drift between live yfinance
                       current vs daily-close history).
    """
    try:
        # Use pre-fetched history if provided, else fetch live from yfinance
        if price_history is not None and len(price_history) > 0:
            # Handle either 'close' (parquet) or 'Close' (yfinance) column naming
            if "close" in price_history.columns:
                close = price_history["close"].astype(float).reset_index(drop=True)
            elif "Close" in price_history.columns:
                close = price_history["Close"].astype(float).reset_index(drop=True)
            else:
                return {"error": f"price_history missing 'close' or 'Close' column for {ticker}"}
        else:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")
            if hist.empty or len(hist) < 50:
                return {"error": f"Insufficient price history for {ticker}."}
            close = hist["Close"].astype(float)

        if len(close) < 50:
            return {"error": f"Insufficient price history for {ticker} (need >=50 rows, got {len(close)})."}

        # Use explicit current_price override if provided; otherwise use last close
        # from price history. This is the FIX for the FV/QBP price mismatch bug:
        # when called from the dashboard, app.py passes the same current_price to
        # both compute_fair_value and compute_buy_point so they show identical prices.
        if current_price is not None and current_price > 0:
            current_price = float(current_price)
        else:
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
            fv_buy = fair_value * 0.90
            components["Fair Value Discount"] = {
                "price": round(fv_buy, 2),
                "weight": 0.25,
                "description": f"10% below fair value (${fair_value:.2f}). Margin of safety.",
            }
        elif scored_df is not None and ticker in scored_df.index:
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

        total_w = sum(c["weight"] for c in components.values())
        buy_point = sum(c["price"] * c["weight"] for c in components.values()) / total_w

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
    if len(close) < window:
        return None
    sma = float(close.rolling(window).mean().iloc[-1])
    std = float(close.rolling(window).std().iloc[-1])
    if std <= 0:
        return None
    upper = sma + (num_std * std)
    lower = sma - (num_std * std)
    current = float(close.iloc[-1])
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
    if len(close) < 60:
        return None
    recent = close.iloc[-126:] if len(close) >= 126 else close
    q10 = recent.quantile(0.10)
    support_prices = recent[recent <= q10]
    if len(support_prices) > 0:
        support = float(support_prices.mean())
        return round(support, 2)
    return round(float(recent.min()), 2)


def _compute_rsi(close: pd.Series, periods: int = 14) -> float | None:
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


def compute_buy_points_batch(tickers: list[str], scored_df: pd.DataFrame = None,
                              price_histories: dict = None) -> dict:
    """Compute buy points for multiple tickers.

    Args:
        tickers: List of ticker symbols.
        scored_df: Optional scored DataFrame for fair-value lookup.
        price_histories: Optional dict {ticker: DataFrame} of pre-fetched price histories.
                         Pass this to avoid yfinance HTTP calls in batch.
    """
    results = {}
    for ticker in tickers:
        ph = (price_histories or {}).get(ticker)
        bp = compute_buy_point(ticker, scored_df, price_history=ph)
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
