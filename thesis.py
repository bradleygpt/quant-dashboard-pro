"""
Thesis Engine - Data-driven investment thesis analyzer.
Uses actual historical correlations between stock returns and macro factors.
Every recommendation backed by a correlation coefficient.
"""

import json
import os
import numpy as np
import pandas as pd


# ── Factor Keyword Mapping ─────────────────────────────────────────

FACTOR_KEYWORDS = {
    "oil": {
        "keywords": ["oil", "crude", "petroleum", "gasoline", "gas price", "opec",
                      "energy price", "brent", "wti", "barrel", "fuel price"],
        "factor_key": "oil",
        "name": "WTI Crude Oil",
    },
    "rates": {
        "keywords": ["interest rate", "rate hike", "rate cut", "fed rate", "treasury",
                      "yield", "10 year", "10-year", "bond yield", "hawkish", "dovish",
                      "tightening", "easing", "fed funds", "monetary policy"],
        "factor_key": "rates_10y",
        "name": "10-Year Treasury Yield",
    },
    "dollar": {
        "keywords": ["dollar", "usd", "dxy", "dollar index", "currency",
                      "strong dollar", "weak dollar", "forex"],
        "factor_key": "dollar",
        "name": "US Dollar Index",
    },
    "volatility": {
        "keywords": ["vix", "volatility", "fear", "uncertainty", "market crash",
                      "risk off", "panic", "sell off", "selloff", "correction",
                      "bear market", "market decline"],
        "factor_key": "vix",
        "name": "VIX Volatility",
    },
    "gold": {
        "keywords": ["gold", "precious metal", "safe haven", "gold price",
                      "gold rally", "bullion"],
        "factor_key": "gold",
        "name": "Gold",
    },
    "bitcoin": {
        "keywords": ["bitcoin", "btc", "crypto", "cryptocurrency", "digital asset",
                      "ethereum", "blockchain"],
        "factor_key": "bitcoin",
        "name": "Bitcoin",
    },
    "natgas": {
        "keywords": ["natural gas", "natgas", "lng", "gas futures", "henry hub",
                      "heating", "natural gas price"],
        "factor_key": "natgas",
        "name": "Natural Gas",
    },
    "market": {
        "keywords": ["market", "s&p", "sp500", "s&p 500", "broad market", "equities",
                      "stock market", "bull market", "rally"],
        "factor_key": "sp500",
        "name": "S&P 500 (Market Beta)",
    },
}

BULLISH_KEYWORDS = ["up", "rise", "increase", "grow", "higher", "bull", "rally",
                     "surge", "boom", "strengthen", "accelerate", "expand", "gain",
                     "positive", "improvement"]

BEARISH_KEYWORDS = ["down", "fall", "decrease", "drop", "lower", "bear", "crash",
                     "decline", "weaken", "slow", "contract", "cut", "reduce",
                     "negative", "deteriorate", "collapse"]


# ── Load Correlation Data ──────────────────────────────────────────

CORRELATIONS_FILE = "correlations_cache.json"


def load_correlations() -> dict:
    if os.path.exists(CORRELATIONS_FILE):
        try:
            with open(CORRELATIONS_FILE, "r") as f:
                data = json.load(f)
                return data.get("correlations", {})
        except Exception:
            pass
    return {}


def load_correlation_metadata() -> dict:
    if os.path.exists(CORRELATIONS_FILE):
        try:
            with open(CORRELATIONS_FILE, "r") as f:
                data = json.load(f)
                return data.get("metadata", {})
        except Exception:
            pass
    return {}


def is_correlation_data_available() -> bool:
    return os.path.exists(CORRELATIONS_FILE) and os.path.getsize(CORRELATIONS_FILE) > 1000


# ── Thesis Parsing ─────────────────────────────────────────────────


def parse_thesis(thesis_text: str) -> dict:
    text = thesis_text.lower().strip()

    matched_factor = None
    best_score = 0
    matched_kws = []

    for factor_id, factor_info in FACTOR_KEYWORDS.items():
        score = 0
        kws = []
        for kw in factor_info["keywords"]:
            if kw in text:
                score += len(kw.split())
                kws.append(kw)
        if score > best_score:
            best_score = score
            matched_factor = factor_info
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
    }


# ── Thesis Results ─────────────────────────────────────────────────


def get_thesis_results(
    thesis_text: str,
    scored_df: pd.DataFrame,
    max_results: int = 25,
) -> dict:
    correlations = load_correlations()
    metadata = load_correlation_metadata()

    if not correlations:
        return {
            "matched": False,
            "error": "no_data",
            "message": "Correlation data not found. Run build_correlations.py locally and upload correlations_cache.json to the repo.",
        }

    parsed = parse_thesis(thesis_text)

    if not parsed.get("matched"):
        return {
            "matched": False,
            "error": "no_theme",
            "message": "Could not identify a macro factor in your thesis. Try mentioning specific factors.",
            "available_factors": [
                "Oil / crude oil prices",
                "Interest rates / treasury yields",
                "US Dollar strength",
                "Market volatility (VIX)",
                "Gold prices",
                "Bitcoin / crypto prices",
                "Natural gas prices",
                "Broad market / S&P 500",
            ],
        }

    factor_key = parsed["factor_key"]
    direction = parsed["direction"]
    factor_name = parsed["factor_name"]

    ticker_corrs = []
    for ticker, factor_data in correlations.items():
        if factor_key in factor_data:
            corr = factor_data[factor_key]["correlation"]
            beta = factor_data[factor_key]["beta"]
            r_sq = factor_data[factor_key]["r_squared"]
            days = factor_data[factor_key].get("days_used", 0)
            ticker_corrs.append({
                "ticker": ticker,
                "correlation": corr,
                "beta": beta,
                "r_squared": r_sq,
                "days_used": days,
            })

    if not ticker_corrs:
        return {
            "matched": False,
            "error": "no_factor_data",
            "message": f"No correlation data for: {factor_name}",
        }

    corr_df = pd.DataFrame(ticker_corrs).set_index("ticker")

    if direction == "up":
        bullish_df = corr_df.nlargest(max_results, "correlation")
        bearish_df = corr_df.nsmallest(max_results, "correlation")
    else:
        bullish_df = corr_df.nsmallest(max_results, "correlation")
        bearish_df = corr_df.nlargest(max_results, "correlation")

    def enrich(df):
        if scored_df.empty or df.empty:
            return df
        enriched = df.copy()
        for col in ["shortName", "sector", "composite_score", "overall_rating", "currentPrice", "marketCapB"]:
            if col in scored_df.columns:
                enriched[col] = scored_df.reindex(enriched.index).get(col)
        return enriched

    bullish_enriched = enrich(bullish_df)
    bearish_enriched = enrich(bearish_df)

    bullish_top = pd.DataFrame()
    if not bullish_enriched.empty and "overall_rating" in bullish_enriched.columns:
        bullish_top = bullish_enriched[
            bullish_enriched["overall_rating"].isin(["Strong Buy", "Buy"])
        ]

    lookback = metadata.get("lookback", "Unknown")
    window = metadata.get("window_days", "Unknown")

    return {
        "matched": True,
        "factor_key": factor_key,
        "factor_name": factor_name,
        "direction": direction,
        "thesis_summary": f"If {factor_name} goes {direction}, these stocks are most affected based on {lookback} historical return correlations.",
        "matched_keywords": parsed["matched_keywords"],
        "num_tickers_analyzed": len(corr_df),
        "avg_correlation": round(corr_df["correlation"].mean(), 4),
        "computed_at": metadata.get("computed_at", "Unknown"),
        "bullish_all": bullish_enriched,
        "bullish_top_rated": bullish_top,
        "bearish_all": bearish_enriched,
    }
