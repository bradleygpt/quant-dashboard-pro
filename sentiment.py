"""
Market Sentiment Dashboard module.
Tracks major indexes, distance from ATH, and composite Fear/Greed gauge.

Free indicators (live):
- VIX level and historical context
- Market breadth from scored universe (50/200 SMA, momentum)
- S&P 500 distance from ATH
- Buffett Indicator (Total Market Cap / GDP approximation)

Indicators requiring paid data (coming soon):
- S&P 500 Put/Call Ratio (CBOE subscription)
- AAII Sentiment Survey
- CNN Fear & Greed Index
- NAAIM Exposure Index
- Consumer Confidence Index
- NFIB Small Business Optimism
- Margin Debt Levels
- Mutual Fund/ETF Cash Flows
- News/Social Media Sentiment
- FOMC Rate Decision Probability (CME FedWatch)
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime


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


def fetch_index_data() -> list[dict]:
    """Fetch current price and all-time high for each major index."""
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
            distance_pct = ((current_price - all_time_high) / all_time_high) * 100

            price_1d = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current_price
            price_5d = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else current_price
            price_1m = float(hist["Close"].iloc[-22]) if len(hist) >= 22 else current_price
            price_3m = float(hist["Close"].iloc[-66]) if len(hist) >= 66 else current_price

            current_year = datetime.now().year
            ytd_data = hist[hist.index.year == current_year]
            price_ytd = float(ytd_data["Close"].iloc[0]) if not ytd_data.empty else current_price

            results.append({
                "name": name, "ticker": info["ticker"], "category": info["category"],
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

        percentile = ((current - low_1y) / (high_1y - low_1y)) * 100 if high_1y > low_1y else 50

        if current < 12:
            level, score = "Extreme Complacency", 95
        elif current < 16:
            level, score = "Low Volatility", 80
        elif current < 20:
            level, score = "Normal", 55
        elif current < 25:
            level, score = "Elevated Caution", 35
        elif current < 30:
            level, score = "High Fear", 20
        elif current < 40:
            level, score = "Extreme Fear", 10
        else:
            level, score = "Panic", 2

        return {
            "current": round(current, 2), "avg_1y": round(avg_1y, 2),
            "high_1y": round(high_1y, 2), "low_1y": round(low_1y, 2),
            "percentile_1y": round(percentile, 1), "level": level, "score": score,
        }
    except Exception:
        return {}


def fetch_buffett_indicator() -> dict:
    """
    Buffett Indicator: Total US Stock Market Cap / GDP.
    Uses Wilshire 5000 as market cap proxy.
    GDP updated quarterly from BEA (hardcoded, update manually each quarter).
    """
    try:
        # US GDP (nominal, annualized, in trillions) - update quarterly
        # Source: BEA. As of Q4 2025 estimate
        US_GDP_TRILLIONS = 29.7  # Update this quarterly

        # Wilshire 5000 Total Market Index as proxy
        w5000 = yf.Ticker("^W5000")
        hist = w5000.history(period="5y")

        if hist.empty:
            # Fallback: use S&P 500 market cap approximation
            sp = yf.Ticker("^GSPC")
            sp_hist = sp.history(period="5y")
            if sp_hist.empty:
                return {}
            current_level = float(sp_hist["Close"].iloc[-1])
            # S&P 500 total market cap ~ level * $13.5B (rough multiplier)
            total_market_cap_t = current_level * 13.5 / 1000
        else:
            current_level = float(hist["Close"].iloc[-1])
            # Wilshire 5000 level * ~$1.2B per point (approximate)
            total_market_cap_t = current_level * 1.2 / 1000

        ratio = (total_market_cap_t / US_GDP_TRILLIONS) * 100

        if ratio > 200:
            level, score = "Significantly Overvalued Market", 10
        elif ratio > 150:
            level, score = "Overvalued Market", 30
        elif ratio > 120:
            level, score = "Fairly Valued Market", 50
        elif ratio > 90:
            level, score = "Undervalued Market", 70
        else:
            level, score = "Significantly Undervalued Market", 90

        return {
            "ratio": round(ratio, 1),
            "total_market_cap_t": round(total_market_cap_t, 1),
            "gdp_t": US_GDP_TRILLIONS,
            "level": level,
            "score": score,
        }
    except Exception:
        return {}


def compute_market_breadth(scored_df: pd.DataFrame) -> dict:
    """Compute market breadth indicators from the scored universe."""
    if scored_df.empty:
        return {}

    n = len(scored_df)

    def pct_positive(col_name):
        if col_name in scored_df.columns:
            vals = scored_df[col_name].dropna()
            return (vals > 0).sum() / len(vals) * 100 if len(vals) > 0 else 50
        return 50

    pct_above_50 = pct_positive("momentum_vs_sma50")
    pct_above_200 = pct_positive("momentum_vs_sma200")
    pct_positive_1m = pct_positive("momentum_1m")
    pct_positive_3m = pct_positive("momentum_3m")

    if "overall_rating" in scored_df.columns:
        buy_pct = len(scored_df[scored_df["overall_rating"].isin(["Strong Buy", "Buy"])]) / n * 100
        sell_pct = len(scored_df[scored_df["overall_rating"].isin(["Sell", "Strong Sell"])]) / n * 100
    else:
        buy_pct, sell_pct = 50, 10

    breadth_score = (pct_above_50 * 0.3 + pct_above_200 * 0.3 + pct_positive_1m * 0.2 + pct_positive_3m * 0.2)

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


def compute_fear_greed(vix_data: dict, breadth_data: dict, index_data: list, buffett_data: dict = None) -> dict:
    """
    Composite Fear/Greed score from available free indicators.

    Components (weighted):
    1. VIX Level (25%) - inverted: low VIX = greed
    2. % Above 50 SMA (20%) - market breadth
    3. % Above 200 SMA (15%) - longer-term breadth
    4. 1-Month Momentum Breadth (15%) - short-term breadth
    5. S&P 500 Distance from ATH (15%) - market level
    6. Buffett Indicator (10%) - market valuation vs GDP

    Score: 0 = Extreme Fear, 100 = Extreme Greed
    """
    components = []

    # 1. VIX Score (inverted)
    vix_score = vix_data.get("score", 50) if vix_data else 50
    components.append({
        "name": "VIX Level", "score": vix_score, "weight": 0.25,
        "value": f"{vix_data.get('current', 'N/A')}", "interpretation": vix_data.get("level", "N/A")
    })

    # 2. % Above 50-day SMA
    pct_50 = breadth_data.get("pct_above_50sma", 50) if breadth_data else 50
    components.append({
        "name": "Stocks Above 50-Day SMA", "score": pct_50, "weight": 0.20,
        "value": f"{pct_50:.0f}%",
        "interpretation": "Bullish" if pct_50 > 60 else "Bearish" if pct_50 < 40 else "Neutral"
    })

    # 3. % Above 200-day SMA
    pct_200 = breadth_data.get("pct_above_200sma", 50) if breadth_data else 50
    components.append({
        "name": "Stocks Above 200-Day SMA", "score": pct_200, "weight": 0.15,
        "value": f"{pct_200:.0f}%",
        "interpretation": "Bullish" if pct_200 > 60 else "Bearish" if pct_200 < 40 else "Neutral"
    })

    # 4. 1-Month Momentum Breadth
    mom_score = breadth_data.get("pct_positive_1m", 50) if breadth_data else 50
    components.append({
        "name": "1-Month Momentum Breadth", "score": mom_score, "weight": 0.15,
        "value": f"{mom_score:.0f}%",
        "interpretation": "Bullish" if mom_score > 60 else "Bearish" if mom_score < 40 else "Neutral"
    })

    # 5. S&P 500 Distance from ATH
    sp_distance = 0
    for idx in index_data:
        if idx["name"] == "S&P 500":
            sp_distance = idx["distance_from_ath_pct"]
            break
    sp_score = max(0, min(100, 100 + (sp_distance * 3.33)))
    components.append({
        "name": "S&P 500 vs All-Time High", "score": round(sp_score, 1), "weight": 0.15,
        "value": f"{sp_distance:+.1f}%",
        "interpretation": "Near ATH" if sp_distance > -5 else "Correction" if sp_distance > -15 else "Bear Market"
    })

    # 6. Buffett Indicator
    buff_score = 50
    buff_value = "N/A"
    buff_interp = "N/A"
    if buffett_data and buffett_data.get("ratio"):
        buff_score = buffett_data.get("score", 50)
        buff_value = f"{buffett_data['ratio']:.0f}%"
        buff_interp = buffett_data.get("level", "N/A")
    components.append({
        "name": "Buffett Indicator (Mkt Cap/GDP)", "score": buff_score, "weight": 0.10,
        "value": buff_value, "interpretation": buff_interp
    })

    composite = sum(c["score"] * c["weight"] for c in components)
    composite = round(max(0, min(100, composite)), 1)

    if composite >= 80:
        classification, color = "Extreme Greed", "#00C805"
    elif composite >= 60:
        classification, color = "Greed", "#8BC34A"
    elif composite >= 45:
        classification, color = "Neutral", "#FFC107"
    elif composite >= 25:
        classification, color = "Fear", "#FF5722"
    else:
        classification, color = "Extreme Fear", "#D32F2F"

    return {
        "score": composite, "classification": classification,
        "color": color, "components": components,
    }


# ── Coming Soon Indicators ─────────────────────────────────────────

COMING_SOON_INDICATORS = [
    {"name": "S&P 500 Put/Call Ratio", "source": "CBOE", "description": "Actual S&P 500 options put/call ratio. Requires CBOE data subscription. Currently approximated via VIX.", "type": "options", "status": "Needs paid data"},
    {"name": "FOMC Rate Decision Probability", "source": "CME FedWatch", "description": "Probability of rate cut/hike at next FOMC meeting. Derived from Fed Funds futures. Rate cuts generally bullish for equities.", "type": "monetary", "status": "Needs futures data"},
    {"name": "AAII Sentiment Survey", "source": "aaii.com", "description": "Weekly poll of individual investors. High bearish readings are contrarian bullish.", "type": "survey", "status": "Needs web scraper"},
    {"name": "CNN Fear & Greed Index", "source": "CNN Business", "description": "Composite of 7 market indicators (0-100 scale).", "type": "composite", "status": "Needs web scraper"},
    {"name": "NAAIM Exposure Index", "source": "naaim.org", "description": "Active investment managers' equity exposure level.", "type": "survey", "status": "Needs web scraper"},
    {"name": "Consumer Confidence Index", "source": "Conference Board", "description": "Household optimism regarding the economy.", "type": "economic", "status": "Needs paid data"},
    {"name": "NFIB Small Business Optimism", "source": "nfib.com", "description": "Small business owner sentiment.", "type": "economic", "status": "Needs web scraper"},
    {"name": "Margin Debt Levels", "source": "FINRA", "description": "NYSE margin debt. High levels = speculation near tops.", "type": "flow", "status": "Monthly data, needs scraper"},
    {"name": "Mutual Fund/ETF Cash Flows", "source": "ICI", "description": "Fund inflows vs outflows indicating risk appetite.", "type": "flow", "status": "Needs paid data"},
    {"name": "News/Social Media Sentiment", "source": "NLP Analysis", "description": "AI-powered sentiment from news and social media.", "type": "alternative", "status": "Needs NLP infrastructure"},
]


# ── Potential Growth Indicator (PGI) ───────────────────────────────
# Inspired by Motley Fool's framework: measures the ratio of money market
# assets to total US stock market cap. Higher PGI = more cash on sidelines
# = more fear = contrarian buy signal.
#
# PGI = Money Market Fund Assets / Total US Stock Market Cap
# Historical range: ~8-20% (spiked to 47% during 2009 crisis)
# Above 11.5%: eager to invest (others are fearful)
# 9.5-11.5%: neutral
# Below 9.5%: cautious (others are greedy)

def compute_pgi() -> dict:
    """
    Compute the Potential Growth Indicator.
    Uses Wilshire 5000 as total market cap proxy and estimates money market
    assets from publicly available data.

    Since FRED API requires a key, we use a simplified approach:
    - Total US market cap from Wilshire 5000 (yfinance: ^W5000)
    - Money market estimate: ~$6.7T as of early 2026 (updated manually)
    """
    try:
        # Wilshire 5000 Total Market Index
        w5000 = yf.Ticker("^W5000")
        hist = w5000.history(period="5d")
        if hist.empty:
            return None

        # Wilshire 5000 value represents total US market cap in billions
        # The index level * ~1.2 approximates total market cap in $B
        w5000_level = float(hist["Close"].iloc[-1])
        # Wilshire 5000 full cap in trillions (index ~48000 = ~$48T market cap)
        total_mkt_cap_t = w5000_level / 1000

        # Money market fund assets (updated periodically)
        # Source: ICI, Federal Reserve. As of early 2026 ~$6.7T
        # This should be updated manually when new data is available
        money_market_t = 6.7  # Trillions

        pgi = (money_market_t / total_mkt_cap_t) * 100 if total_mkt_cap_t > 0 else 0

        # Interpretation
        if pgi > 11.5:
            level = "Eager to Invest"
            interpretation = "High cash on sidelines. Others are fearful. Contrarian bullish."
            color = "#22C55E"
            score = min(100, (pgi - 8) * 5)  # Higher PGI = higher score (more bullish)
        elif pgi > 9.5:
            level = "Neutral"
            interpretation = "Cash levels are in a normal range. Neither extreme fear nor greed."
            color = "#EAB308"
            score = 50
        else:
            level = "Cautious"
            interpretation = "Low cash on sidelines. Others are greedy. Be more selective."
            color = "#F97316"
            score = max(0, pgi * 5)

        return {
            "pgi": round(pgi, 2),
            "level": level,
            "interpretation": interpretation,
            "color": color,
            "score": round(score),
            "money_market_t": money_market_t,
            "total_mkt_cap_t": round(total_mkt_cap_t, 1),
            "note": "Money market assets updated manually (~$6.7T as of early 2026). Update sentiment.py when new ICI data is released.",
        }
    except Exception:
        return None

