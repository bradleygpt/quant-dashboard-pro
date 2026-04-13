"""
Market Sentiment Dashboard module.
Tracks major indexes, distance from all-time highs, and sentiment indicators.
Builds a composite Fear/Greed gauge from available free data sources.

Free data sources used:
- VIX (^VIX) via yfinance
- Major indexes via yfinance
- Market breadth computed from scored universe
- Put/Call ratio approximated from VIX level
- Momentum breadth from scored universe

Indicators that need paid APIs (marked as "coming soon"):
- AAII Sentiment Survey
- CNN Fear & Greed (official)
- NAAIM Survey
- Consumer Confidence Index
- NFIB Small Business Optimism
- Margin Debt levels
- News/Social Media Sentiment
"""

import json
import os
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime


# ── Index Definitions ──────────────────────────────────────────────

MARKET_INDEXES = {
    "S&P 500": {"ticker": "^GSPC", "category": "equity"},
    "Nasdaq Composite": {"ticker": "^IXIC", "category": "equity"},
    "Dow Jones": {"ticker": "^DJI", "category": "equity"},
    "Russell 2000": {"ticker": "^RUT", "category": "equity"},
    "Gold": {"ticker": "GC=F", "category": "commodity"},
    "Silver": {"ticker": "SI=F", "category": "commodity"},
    "Crude Oil (WTI)": {"ticker": "CL=F", "category": "commodity"},
    "Natural Gas": {"ticker": "NG=F", "category": "commodity"},
    "Bitcoin": {"ticker": "BTC-USD", "category": "crypto"},
    "US Dollar Index": {"ticker": "DX-Y.NYB", "category": "currency"},
}

SENTIMENT_CACHE_FILE = "sentiment_cache.json"


# ── Index Data Fetching ────────────────────────────────────────────


def fetch_index_data() -> list[dict]:
    """
    Fetch current price and all-time high for each major index.
    Returns list of dicts with name, price, ATH, distance from ATH, etc.
    """
    results = []

    for name, info in MARKET_INDEXES.items():
        try:
            ticker = yf.Ticker(info["ticker"])
            hist = ticker.history(period="max")

            if hist.empty or len(hist) < 2:
                continue

            current_price = float(hist["Close"].iloc[-1])
            all_time_high = float(hist["Close"].max())
            ath_date = hist["Close"].idxmax()

            # Distance from ATH
            distance_pct = ((current_price - all_time_high) / all_time_high) * 100

            # Recent performance
            price_1d = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current_price
            price_5d = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else current_price
            price_1m = float(hist["Close"].iloc[-22]) if len(hist) >= 22 else current_price
            price_3m = float(hist["Close"].iloc[-66]) if len(hist) >= 66 else current_price
            price_ytd = float(hist["Close"].iloc[0]) if len(hist) >= 1 else current_price

            # YTD: find first trading day of current year
            current_year = datetime.now().year
            ytd_data = hist[hist.index.year == current_year]
            if not ytd_data.empty:
                price_ytd = float(ytd_data["Close"].iloc[0])

            results.append({
                "name": name,
                "ticker": info["ticker"],
                "category": info["category"],
                "current_price": round(current_price, 2),
                "all_time_high": round(all_time_high, 2),
                "ath_date": str(ath_date.date()) if hasattr(ath_date, 'date') else str(ath_date)[:10],
                "distance_from_ath_pct": round(distance_pct, 2),
                "change_1d_pct": round((current_price / price_1d - 1) * 100, 2),
                "change_5d_pct": round((current_price / price_5d - 1) * 100, 2),
                "change_1m_pct": round((current_price / price_1m - 1) * 100, 2),
                "change_3m_pct": round((current_price / price_3m - 1) * 100, 2),
                "change_ytd_pct": round((current_price / price_ytd - 1) * 100, 2),
            })

        except Exception:
            continue

    return results


# ── VIX Analysis ───────────────────────────────────────────────────


def fetch_vix_data() -> dict:
    """Fetch VIX current level and historical context."""
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="2y")

        if hist.empty:
            return {}

        current = float(hist["Close"].iloc[-1])
        avg_1y = float(hist["Close"].iloc[-252:].mean()) if len(hist) >= 252 else float(hist["Close"].mean())
        high_1y = float(hist["Close"].iloc[-252:].max()) if len(hist) >= 252 else float(hist["Close"].max())
        low_1y = float(hist["Close"].iloc[-252:].min()) if len(hist) >= 252 else float(hist["Close"].min())

        # VIX percentile (where does current sit in 1-year range)
        percentile = ((current - low_1y) / (high_1y - low_1y)) * 100 if high_1y > low_1y else 50

        # VIX sentiment interpretation
        if current < 12:
            level = "Extreme Complacency"
            sentiment = "extreme_greed"
            score = 95
        elif current < 16:
            level = "Low Volatility"
            sentiment = "greed"
            score = 80
        elif current < 20:
            level = "Normal"
            sentiment = "neutral"
            score = 55
        elif current < 25:
            level = "Elevated Caution"
            sentiment = "fear"
            score = 35
        elif current < 30:
            level = "High Fear"
            sentiment = "high_fear"
            score = 20
        elif current < 40:
            level = "Extreme Fear"
            sentiment = "extreme_fear"
            score = 10
        else:
            level = "Panic"
            sentiment = "panic"
            score = 2

        return {
            "current": round(current, 2),
            "avg_1y": round(avg_1y, 2),
            "high_1y": round(high_1y, 2),
            "low_1y": round(low_1y, 2),
            "percentile_1y": round(percentile, 1),
            "level": level,
            "sentiment": sentiment,
            "score": score,  # 0=max fear, 100=max greed
        }

    except Exception:
        return {}


# ── Market Breadth ─────────────────────────────────────────────────


def compute_market_breadth(scored_df: pd.DataFrame) -> dict:
    """
    Compute market breadth indicators from the scored universe.
    - % of stocks above 50-day SMA
    - % of stocks above 200-day SMA
    - % of stocks with positive 1-month momentum
    - High-Low index (% at 52-week highs vs lows)
    - Advance-Decline ratio
    """
    if scored_df.empty:
        return {}

    n = len(scored_df)

    # % above 50-day SMA
    sma50_col = "momentum_vs_sma50"
    if sma50_col in scored_df.columns:
        above_50 = scored_df[sma50_col].dropna()
        pct_above_50 = (above_50 > 0).sum() / len(above_50) * 100 if len(above_50) > 0 else 50
    else:
        pct_above_50 = 50

    # % above 200-day SMA
    sma200_col = "momentum_vs_sma200"
    if sma200_col in scored_df.columns:
        above_200 = scored_df[sma200_col].dropna()
        pct_above_200 = (above_200 > 0).sum() / len(above_200) * 100 if len(above_200) > 0 else 50
    else:
        pct_above_200 = 50

    # % with positive 1-month return
    mom_1m_col = "momentum_1m"
    if mom_1m_col in scored_df.columns:
        mom_1m = scored_df[mom_1m_col].dropna()
        pct_positive_1m = (mom_1m > 0).sum() / len(mom_1m) * 100 if len(mom_1m) > 0 else 50
    else:
        pct_positive_1m = 50

    # % with positive 3-month return
    mom_3m_col = "momentum_3m"
    if mom_3m_col in scored_df.columns:
        mom_3m = scored_df[mom_3m_col].dropna()
        pct_positive_3m = (mom_3m > 0).sum() / len(mom_3m) * 100 if len(mom_3m) > 0 else 50
    else:
        pct_positive_3m = 50

    # Rating distribution as sentiment
    if "overall_rating" in scored_df.columns:
        buy_pct = len(scored_df[scored_df["overall_rating"].isin(["Strong Buy", "Buy"])]) / n * 100
        sell_pct = len(scored_df[scored_df["overall_rating"].isin(["Sell", "Strong Sell"])]) / n * 100
    else:
        buy_pct = 50
        sell_pct = 10

    # Breadth score (0=bearish, 100=bullish)
    breadth_score = (pct_above_50 * 0.3 + pct_above_200 * 0.3 +
                     pct_positive_1m * 0.2 + pct_positive_3m * 0.2)

    return {
        "pct_above_50sma": round(pct_above_50, 1),
        "pct_above_200sma": round(pct_above_200, 1),
        "pct_positive_1m": round(pct_positive_1m, 1),
        "pct_positive_3m": round(pct_positive_3m, 1),
        "buy_pct": round(buy_pct, 1),
        "sell_pct": round(sell_pct, 1),
        "breadth_score": round(breadth_score, 1),
        "num_stocks": n,
    }


# ── Composite Fear/Greed Score ─────────────────────────────────────


def compute_fear_greed(vix_data: dict, breadth_data: dict, index_data: list) -> dict:
    """
    Build a composite Fear/Greed score from available free indicators.

    Components (weighted):
    1. VIX Level (25%) - inverted: low VIX = greed, high VIX = fear
    2. Market Breadth - % above 50 SMA (20%)
    3. Market Breadth - % above 200 SMA (15%)
    4. Market Momentum - % positive 1-month (15%)
    5. S&P 500 distance from ATH (15%)
    6. Put/Call proxy from VIX (10%)

    Score: 0 = Extreme Fear, 100 = Extreme Greed
    """
    components = []

    # 1. VIX Score (inverted)
    vix_score = vix_data.get("score", 50) if vix_data else 50
    components.append({"name": "VIX Level", "score": vix_score, "weight": 0.25,
                       "value": f"{vix_data.get('current', 'N/A')}", "interpretation": vix_data.get("level", "N/A")})

    # 2. % Above 50-day SMA
    pct_50 = breadth_data.get("pct_above_50sma", 50) if breadth_data else 50
    components.append({"name": "Stocks Above 50-Day SMA", "score": pct_50, "weight": 0.20,
                       "value": f"{pct_50:.0f}%", "interpretation": "Bullish" if pct_50 > 60 else "Bearish" if pct_50 < 40 else "Neutral"})

    # 3. % Above 200-day SMA
    pct_200 = breadth_data.get("pct_above_200sma", 50) if breadth_data else 50
    components.append({"name": "Stocks Above 200-Day SMA", "score": pct_200, "weight": 0.15,
                       "value": f"{pct_200:.0f}%", "interpretation": "Bullish" if pct_200 > 60 else "Bearish" if pct_200 < 40 else "Neutral"})

    # 4. 1-Month Momentum Breadth
    mom_score = breadth_data.get("pct_positive_1m", 50) if breadth_data else 50
    components.append({"name": "1-Month Momentum Breadth", "score": mom_score, "weight": 0.15,
                       "value": f"{mom_score:.0f}%", "interpretation": "Bullish" if mom_score > 60 else "Bearish" if mom_score < 40 else "Neutral"})

    # 5. S&P 500 Distance from ATH
    sp_distance = 0
    for idx in index_data:
        if idx["name"] == "S&P 500":
            sp_distance = idx["distance_from_ath_pct"]
            break
    # Convert: 0% from ATH = 100 score, -30% from ATH = 0 score
    sp_score = max(0, min(100, 100 + (sp_distance * 3.33)))
    components.append({"name": "S&P 500 vs All-Time High", "score": round(sp_score, 1), "weight": 0.15,
                       "value": f"{sp_distance:+.1f}%", "interpretation": "Near ATH" if sp_distance > -5 else "Correction" if sp_distance > -15 else "Bear Market"})

    # 6. Put/Call Proxy (derived from VIX)
    vix_current = vix_data.get("current", 20) if vix_data else 20
    # VIX < 15 suggests low put buying (greed), VIX > 30 suggests heavy put buying (fear)
    pc_score = max(0, min(100, (40 - vix_current) * 4))
    components.append({"name": "Put/Call Proxy", "score": round(pc_score, 1), "weight": 0.10,
                       "value": f"VIX-derived", "interpretation": "Low puts" if pc_score > 60 else "High puts" if pc_score < 40 else "Normal"})

    # Weighted composite
    composite = sum(c["score"] * c["weight"] for c in components)
    composite = round(max(0, min(100, composite)), 1)

    # Classification
    if composite >= 80:
        classification = "Extreme Greed"
        color = "#00C805"
    elif composite >= 60:
        classification = "Greed"
        color = "#8BC34A"
    elif composite >= 45:
        classification = "Neutral"
        color = "#FFC107"
    elif composite >= 25:
        classification = "Fear"
        color = "#FF5722"
    else:
        classification = "Extreme Fear"
        color = "#D32F2F"

    return {
        "score": composite,
        "classification": classification,
        "color": color,
        "components": components,
    }


# ── Coming Soon Indicators ─────────────────────────────────────────

COMING_SOON_INDICATORS = [
    {"name": "AAII Sentiment Survey", "source": "aaii.com", "description": "Weekly poll of individual investors' bullish/bearish outlook", "type": "survey"},
    {"name": "CNN Fear & Greed Index", "source": "CNN Business", "description": "Composite of 7 market indicators (0-100 scale)", "type": "composite"},
    {"name": "NAAIM Exposure Index", "source": "naaim.org", "description": "Active investment managers' equity exposure", "type": "survey"},
    {"name": "Consumer Confidence Index", "source": "Conference Board", "description": "Household optimism regarding the economy", "type": "economic"},
    {"name": "NFIB Small Business Optimism", "source": "nfib.com", "description": "Small business owner sentiment", "type": "economic"},
    {"name": "Margin Debt Levels", "source": "FINRA", "description": "NYSE margin debt indicating leverage/speculation", "type": "flow"},
    {"name": "Mutual Fund/ETF Cash Flows", "source": "ICI", "description": "Fund inflows vs outflows indicating risk appetite", "type": "flow"},
    {"name": "News/Social Media Sentiment", "source": "NLP Analysis", "description": "AI-powered sentiment from news and social media", "type": "alternative"},
]
