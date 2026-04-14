"""
Thesis Engine - Data-driven investment thesis analyzer.
Uses 20-year historical return correlations.
"""

import json
import os
import numpy as np
import pandas as pd

FACTORS = {
    "oil": {
        "factor_key": "oil", "name": "WTI Crude Oil",
        "description": "West Texas Intermediate crude oil futures. Measures energy commodity prices.",
        "keywords": ["oil","crude","petroleum","gasoline","gas price","opec","energy price","brent","wti","barrel","fuel price"],
        "examples": ["Oil prices will increase by 20%","OPEC will cut production","Crude oil will crash"],
        "typical_positive": "Energy E&P, oilfield services, refiners",
        "typical_negative": "Airlines, trucking, consumer discretionary",
    },
    "rates": {
        "factor_key": "rates_10y", "name": "10-Year Treasury Yield",
        "description": "US 10-year government bond yield. Key driver for banks, REITs, and growth stocks.",
        "keywords": ["interest rate","rate hike","rate cut","fed rate","treasury","yield","10 year","10-year","bond yield","hawkish","dovish","tightening","easing","fed funds","monetary policy"],
        "examples": ["Fed will cut rates","Interest rates will rise sharply","Bond yields will increase"],
        "typical_positive": "Banks, insurance, financials (when rising)",
        "typical_negative": "REITs, utilities, high-growth tech (when rising)",
    },
    "dollar": {
        "factor_key": "dollar", "name": "US Dollar Index (DXY)",
        "description": "Measures USD against a basket of major currencies. Impacts multinationals and commodities.",
        "keywords": ["dollar","usd","dxy","dollar index","currency","strong dollar","weak dollar","forex"],
        "examples": ["US dollar will weaken","Strong dollar ahead","DXY will fall"],
        "typical_positive": "Domestic-focused companies (when rising)",
        "typical_negative": "Multinationals, commodity producers (when rising)",
    },
    "volatility": {
        "factor_key": "vix", "name": "VIX Volatility Index",
        "description": "CBOE fear gauge. Measures expected market volatility. Spikes during crises.",
        "keywords": ["vix","volatility","fear","uncertainty","market crash","risk off","panic","sell off","selloff","correction","bear market","market decline"],
        "examples": ["Market volatility will spike","VIX will increase","A market crash is coming"],
        "typical_positive": "Defensive stocks, utilities, staples (when rising)",
        "typical_negative": "High-beta growth, cyclicals (when rising)",
    },
    "gold": {
        "factor_key": "gold", "name": "Gold",
        "description": "Gold futures. Traditional safe haven and inflation hedge.",
        "keywords": ["gold","precious metal","safe haven","gold price","gold rally","bullion"],
        "examples": ["Gold prices will rally","Safe haven demand will increase"],
        "typical_positive": "Gold miners (NEM), materials",
        "typical_negative": "Banks, cyclicals",
    },
    "bitcoin": {
        "factor_key": "bitcoin", "name": "Bitcoin",
        "description": "Bitcoin/USD price. Proxy for crypto and speculative risk appetite.",
        "keywords": ["bitcoin","btc","crypto","cryptocurrency","digital asset","ethereum","blockchain"],
        "examples": ["Bitcoin will rally to new highs","Crypto prices will crash"],
        "typical_positive": "COIN, MSTR, HOOD, IREN (when rising)",
        "typical_negative": "Defensive/staples (inverse correlation weak)",
    },
    "natgas": {
        "factor_key": "natgas", "name": "Natural Gas",
        "description": "Henry Hub natural gas futures. Impacts utilities, heating, and LNG producers.",
        "keywords": ["natural gas","natgas","lng","gas futures","henry hub","heating","natural gas price"],
        "examples": ["Natural gas prices will spike this winter","LNG demand will grow"],
        "typical_positive": "Natural gas producers, LNG exporters",
        "typical_negative": "Utilities (higher input costs), industrials",
    },
    "market": {
        "factor_key": "sp500", "name": "S&P 500 (Market Beta)",
        "description": "Broad US equity market. Measures systematic market risk exposure.",
        "keywords": ["market","s&p","sp500","s&p 500","broad market","equities","stock market","bull market","rally"],
        "examples": ["The market will rally 20%","A broad market decline is coming"],
        "typical_positive": "High-beta cyclicals, financials (when rising)",
        "typical_negative": "Low-beta defensives outperform (when falling)",
    },
}

BULLISH_KEYWORDS = ["up","rise","increase","grow","higher","bull","rally","surge","boom","strengthen","accelerate","expand","gain","positive","improvement","spike","soar"]
BEARISH_KEYWORDS = ["down","fall","decrease","drop","lower","bear","crash","decline","weaken","slow","contract","cut","reduce","negative","deteriorate","collapse","plunge","tank"]

CORRELATIONS_FILE = "correlations_cache.json"


def load_correlations() -> dict:
    if os.path.exists(CORRELATIONS_FILE):
        try:
            with open(CORRELATIONS_FILE, "r") as f:
                return json.load(f).get("correlations", {})
        except Exception:
            pass
    return {}


def load_correlation_metadata() -> dict:
    if os.path.exists(CORRELATIONS_FILE):
        try:
            with open(CORRELATIONS_FILE, "r") as f:
                return json.load(f).get("metadata", {})
        except Exception:
            pass
    return {}


def is_correlation_data_available() -> bool:
    return os.path.exists(CORRELATIONS_FILE) and os.path.getsize(CORRELATIONS_FILE) > 1000


def get_factor_documentation() -> list[dict]:
    """Return documentation for all supported factors."""
    docs = []
    for fid, f in FACTORS.items():
        docs.append({
            "name": f["name"],
            "description": f["description"],
            "keywords": ", ".join(f["keywords"][:5]) + "...",
            "examples": f["examples"],
            "typical_positive": f["typical_positive"],
            "typical_negative": f["typical_negative"],
        })
    return docs


def parse_thesis(thesis_text: str) -> dict:
    text = thesis_text.lower().strip()
    matched_factor = None
    best_score = 0
    matched_kws = []
    for fid, finfo in FACTORS.items():
        score = 0
        kws = []
        for kw in finfo["keywords"]:
            if kw in text:
                score += len(kw.split())
                kws.append(kw)
        if score > best_score:
            best_score = score
            matched_factor = finfo
            matched_kws = kws
    if not matched_factor:
        return {"matched": False}
    direction = "up"
    bull_score = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
    bear_score = sum(1 for kw in BEARISH_KEYWORDS if kw in text)
    if bear_score > bull_score:
        direction = "down"
    return {
        "matched": True,
        "factor_key": matched_factor["factor_key"],
        "factor_name": matched_factor["name"],
        "direction": direction,
        "matched_keywords": matched_kws,
        "description": matched_factor["description"],
    }


def analyze_portfolio_impact(
    thesis_factor_key: str,
    thesis_direction: str,
    portfolio_holdings: list[dict],
    scored_df: pd.DataFrame,
) -> list[dict]:
    """For each portfolio holding, show its correlation to the thesis factor."""
    correlations = load_correlations()
    if not correlations or not portfolio_holdings:
        return []
    results = []
    for h in portfolio_holdings:
        ticker = h.get("ticker", "").upper()
        shares = h.get("shares", 0)
        price = 0
        name = ticker
        if ticker in scored_df.index:
            price = scored_df.loc[ticker].get("currentPrice", 0)
            name = scored_df.loc[ticker].get("shortName", ticker)
        market_value = shares * price if price else 0
        corr = None
        beta = None
        impact = "Unknown"
        impact_color = "#666"
        if ticker in correlations and thesis_factor_key in correlations[ticker]:
            cd = correlations[ticker][thesis_factor_key]
            corr = cd["correlation"]
            beta = cd["beta"]
            effective_corr = corr if thesis_direction == "up" else -corr
            if effective_corr > 0.15:
                impact = "Benefits"
                impact_color = "#00C805"
            elif effective_corr > 0.05:
                impact = "Slight Benefit"
                impact_color = "#8BC34A"
            elif effective_corr > -0.05:
                impact = "Neutral"
                impact_color = "#FFC107"
            elif effective_corr > -0.15:
                impact = "Slight Risk"
                impact_color = "#FF5722"
            else:
                impact = "At Risk"
                impact_color = "#D32F2F"
        results.append({
            "ticker": ticker, "name": name, "shares": shares,
            "market_value": round(market_value, 2),
            "correlation": round(corr, 4) if corr is not None else None,
            "beta": round(beta, 4) if beta is not None else None,
            "impact": impact, "impact_color": impact_color,
        })
    results.sort(key=lambda x: abs(x["correlation"] or 0), reverse=True)
    return results


def get_thesis_results(
    thesis_text: str,
    scored_df: pd.DataFrame,
    max_results: int = 25,
) -> dict:
    correlations = load_correlations()
    metadata = load_correlation_metadata()
    if not correlations:
        return {"matched": False, "error": "no_data", "message": "Correlation data not found. Run build_correlations.py locally and upload correlations_cache.json."}
    parsed = parse_thesis(thesis_text)
    if not parsed.get("matched"):
        return {"matched": False, "error": "no_theme", "message": "Could not identify a macro factor in your thesis. See the factor guide."}
    factor_key = parsed["factor_key"]
    direction = parsed["direction"]
    factor_name = parsed["factor_name"]
    ticker_corrs = []
    for ticker, factor_data in correlations.items():
        if factor_key in factor_data:
            ticker_corrs.append({
                "ticker": ticker,
                "correlation": factor_data[factor_key]["correlation"],
                "beta": factor_data[factor_key]["beta"],
                "r_squared": factor_data[factor_key]["r_squared"],
                "days_used": factor_data[factor_key].get("days_used", 0),
            })
    if not ticker_corrs:
        return {"matched": False, "error": "no_factor_data", "message": f"No data for: {factor_name}"}
    corr_df = pd.DataFrame(ticker_corrs).set_index("ticker")
    if direction == "up":
        bullish_df = corr_df.nlargest(max_results, "correlation")
        bearish_df = corr_df.nsmallest(max_results, "correlation")
    else:
        bullish_df = corr_df.nsmallest(max_results, "correlation")
        bearish_df = corr_df.nlargest(max_results, "correlation")
    def enrich(df):
        if scored_df.empty or df.empty: return df
        enriched = df.copy()
        for col in ["shortName","sector","composite_score","overall_rating","currentPrice","marketCapB"]:
            if col in scored_df.columns:
                enriched[col] = scored_df.reindex(enriched.index).get(col)
        return enriched
    bullish_enriched = enrich(bullish_df)
    bearish_enriched = enrich(bearish_df)
    bullish_top = pd.DataFrame()
    if not bullish_enriched.empty and "overall_rating" in bullish_enriched.columns:
        bullish_top = bullish_enriched[bullish_enriched["overall_rating"].isin(["Strong Buy", "Buy"])]
    return {
        "matched": True, "factor_key": factor_key, "factor_name": factor_name,
        "direction": direction, "description": parsed.get("description", ""),
        "thesis_summary": f"If {factor_name} goes {direction}, these stocks are most affected based on 20-year historical return correlations.",
        "matched_keywords": parsed["matched_keywords"],
        "num_tickers_analyzed": len(corr_df),
        "avg_correlation": round(corr_df["correlation"].mean(), 4),
        "computed_at": metadata.get("computed_at", "Unknown"),
        "bullish_all": bullish_enriched, "bullish_top_rated": bullish_top,
        "bearish_all": bearish_enriched,
    }
