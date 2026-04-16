"""
Advanced Screener with multi-filter support and fair value integration.
"""

import pandas as pd
import numpy as np
from fairvalue import compute_fair_value

FILTERABLE_METRICS = {
    "Valuation": [
        {"key": "forwardPE", "name": "Forward P/E", "type": "range", "default_min": 0, "default_max": 100, "step": 1.0},
        {"key": "trailingPE", "name": "Trailing P/E", "type": "range", "default_min": 0, "default_max": 100, "step": 1.0},
        {"key": "pegRatio", "name": "PEG Ratio", "type": "range", "default_min": 0, "default_max": 10, "step": 0.1},
        {"key": "priceToBook", "name": "Price / Book", "type": "range", "default_min": 0, "default_max": 50, "step": 0.5},
        {"key": "priceToSalesTrailing12Months", "name": "Price / Sales", "type": "range", "default_min": 0, "default_max": 50, "step": 0.5},
        {"key": "enterpriseToEbitda", "name": "EV / EBITDA", "type": "range", "default_min": 0, "default_max": 100, "step": 1.0},
    ],
    "Growth": [
        {"key": "revenueGrowth", "name": "Revenue Growth (QoQ)", "type": "pct_range", "default_min": -50, "default_max": 100, "step": 5.0},
        {"key": "earningsGrowth", "name": "Earnings Growth (QoQ)", "type": "pct_range", "default_min": -50, "default_max": 200, "step": 5.0},
        {"key": "earningsQuarterlyGrowth", "name": "Earnings Growth (YoY)", "type": "pct_range", "default_min": -50, "default_max": 200, "step": 5.0},
    ],
    "Profitability": [
        {"key": "grossMargins", "name": "Gross Margin", "type": "pct_range", "default_min": 0, "default_max": 100, "step": 5.0},
        {"key": "operatingMargins", "name": "Operating Margin", "type": "pct_range", "default_min": -50, "default_max": 100, "step": 5.0},
        {"key": "profitMargins", "name": "Net Margin", "type": "pct_range", "default_min": -50, "default_max": 100, "step": 5.0},
        {"key": "returnOnEquity", "name": "Return on Equity", "type": "pct_range", "default_min": -50, "default_max": 100, "step": 5.0},
    ],
    "Momentum": [
        {"key": "momentum_1m", "name": "1-Month Return", "type": "pct_range", "default_min": -50, "default_max": 100, "step": 5.0},
        {"key": "momentum_3m", "name": "3-Month Return", "type": "pct_range", "default_min": -50, "default_max": 200, "step": 5.0},
        {"key": "momentum_6m", "name": "6-Month Return", "type": "pct_range", "default_min": -50, "default_max": 200, "step": 5.0},
        {"key": "momentum_12m", "name": "12-Month Return", "type": "pct_range", "default_min": -50, "default_max": 300, "step": 10.0},
    ],
    "Other": [
        {"key": "marketCapB", "name": "Market Cap ($B)", "type": "range", "default_min": 1, "default_max": 5000, "step": 10.0},
        {"key": "currentPrice", "name": "Price ($)", "type": "range", "default_min": 0, "default_max": 5000, "step": 10.0},
        {"key": "analyst_count", "name": "# Analysts Covering", "type": "range", "default_min": 0, "default_max": 60, "step": 1.0},
    ],
}


def apply_advanced_filters(
    scored_df: pd.DataFrame,
    rating_filter: list[str] = None,
    sector_filter: list[str] = None,
    fair_value_filter: list[str] = None,
    metric_filters: dict = None,
    sort_by: str = "composite_score",
    sort_ascending: bool = False,
    max_results: int = 500,
) -> pd.DataFrame:
    if scored_df.empty: return pd.DataFrame()
    df = scored_df.copy()

    if rating_filter and "All" not in rating_filter:
        df = df[df["overall_rating"].isin(rating_filter)]

    if sector_filter and "All" not in sector_filter:
        df = df[df["sector"].isin(sector_filter)]

    if metric_filters:
        for mk, (mn, mx) in metric_filters.items():
            if mk not in df.columns: continue
            col = pd.to_numeric(df[mk], errors="coerce")
            is_pct = any(m["key"] == mk and m["type"] == "pct_range"
                for cm in FILTERABLE_METRICS.values() for m in cm)
            if is_pct: amn, amx = mn / 100, mx / 100
            else: amn, amx = mn, mx
            df = df[col.between(amn, amx, inclusive="both") | col.isna()]

    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=sort_ascending)

    return df.head(max_results)


def compute_fair_values_batch(scored_df: pd.DataFrame, tickers: list[str]) -> dict:
    """Compute fair values for up to 500 tickers."""
    results = {}
    for ticker in tickers[:500]:  # Increased from 100
        try:
            fv = compute_fair_value(ticker, scored_df)
            if "error" not in fv:
                results[ticker] = {"fair_value": fv["composite_fair_value"],
                    "premium_discount": fv["premium_discount_pct"], "verdict": fv["verdict"]}
            else:
                results[ticker] = {"fair_value": None, "premium_discount": None, "verdict": "N/A"}
        except Exception:
            results[ticker] = {"fair_value": None, "premium_discount": None, "verdict": "N/A"}
    return results


PRESET_SCREENS = {
    "Undervalued Strong Buys": {
        "description": "Strong Buy and Buy stocks that are Fairly Valued to Deeply Undervalued",
        "rating_filter": ["Strong Buy", "Buy"],
        "fair_value_filter": ["Deeply Undervalued", "Undervalued", "Fairly Valued"],
        "metric_filters": {}, "sort_by": "composite_score",
    },
    "Growth at Reasonable Price": {
        "description": "PEG 0.5-2.0 with at least 10% earnings growth",
        "rating_filter": [], "fair_value_filter": [],
        "metric_filters": {"pegRatio": (0.5, 2.0), "earningsGrowth": (10, 200)},
        "sort_by": "composite_score",
    },
    "Value Plays": {
        "description": "Low P/E (under 15x) with positive margins",
        "rating_filter": [], "fair_value_filter": [],
        "metric_filters": {"trailingPE": (1, 15), "profitMargins": (5, 100)},
        "sort_by": "composite_score",
    },
    "Momentum Leaders": {
        "description": "Positive returns across all timeframes",
        "rating_filter": [], "fair_value_filter": [],
        "metric_filters": {"momentum_1m": (0, 200), "momentum_3m": (5, 300), "momentum_6m": (10, 500)},
        "sort_by": "composite_score",
    },
    "High Quality Compounders": {
        "description": "High margins, strong ROE, consistent growth",
        "rating_filter": [], "fair_value_filter": [],
        "metric_filters": {"operatingMargins": (15, 100), "returnOnEquity": (15, 100), "revenueGrowth": (5, 200)},
        "sort_by": "composite_score",
    },
}
