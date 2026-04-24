"""
Advanced Screener module.
Multi-filter stock screening with fair value integration and custom metric ranges.
Includes preset screens inspired by institutional portfolio strategy frameworks.
"""

import pandas as pd
import numpy as np
from fairvalue import compute_fair_value


# ── Available Filter Metrics ───────────────────────────────────────

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
    scored_df,
    rating_filter=None,
    sector_filter=None,
    fair_value_filter=None,
    metric_filters=None,
    sort_by="composite_score",
    sort_ascending=False,
    max_results=500,
):
    if scored_df.empty:
        return pd.DataFrame()

    df = scored_df.copy()

    if rating_filter and "All" not in rating_filter:
        df = df[df["overall_rating"].isin(rating_filter)]

    if sector_filter and "All" not in sector_filter:
        df = df[df["sector"].isin(sector_filter)]

    if metric_filters:
        for metric_key, (min_val, max_val) in metric_filters.items():
            if metric_key not in df.columns:
                continue
            col = pd.to_numeric(df[metric_key], errors="coerce")
            is_pct = any(
                m["key"] == metric_key and m["type"] == "pct_range"
                for cat_metrics in FILTERABLE_METRICS.values()
                for m in cat_metrics
            )
            if is_pct:
                actual_min = min_val / 100
                actual_max = max_val / 100
            else:
                actual_min = min_val
                actual_max = max_val
            df = df[col.between(actual_min, actual_max, inclusive="both") | col.isna()]

    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=sort_ascending)

    return df.head(max_results)


def compute_fair_values_batch(scored_df, tickers):
    results = {}
    for ticker in tickers:
        try:
            fv = compute_fair_value(ticker, scored_df)
            if "error" not in fv:
                results[ticker] = {
                    "fair_value": fv["composite_fair_value"],
                    "premium_discount": fv["premium_discount_pct"],
                    "verdict": fv["verdict"],
                }
            else:
                results[ticker] = {"fair_value": None, "premium_discount": None, "verdict": "N/A"}
        except Exception:
            results[ticker] = {"fair_value": None, "premium_discount": None, "verdict": "N/A"}
    return results


# ── Preset Screens ─────────────────────────────────────────────────

PRESET_SCREENS = {
    "Undervalued Strong Buys": {
        "description": "Strong Buy and Buy rated stocks that are Fairly Valued to Deeply Undervalued",
        "rating_filter": ["Strong Buy", "Buy"],
        "fair_value_filter": ["Deeply Undervalued", "Undervalued", "Fairly Valued"],
        "metric_filters": {},
        "sort_by": "composite_score",
    },
    "Foundational Stocks": {
        "description": "Large-cap, highly profitable, well-covered companies that anchor a portfolio. Inspired by long-term buy-and-hold philosophy: wide moats, consistent execution, analyst consensus.",
        "rating_filter": ["Strong Buy", "Buy", "Hold"],
        "fair_value_filter": [],
        "metric_filters": {
            "marketCapB": (50, 5000),
            "operatingMargins": (15, 100),
            "returnOnEquity": (12, 100),
            "analyst_count": (15, 60),
        },
        "sort_by": "composite_score",
    },
    "Growth at Reasonable Price": {
        "description": "PEG ratio 0.5-2.0 with at least 10% earnings growth. Classic GARP strategy.",
        "rating_filter": [],
        "fair_value_filter": [],
        "metric_filters": {
            "pegRatio": (0.5, 2.0),
            "earningsGrowth": (10, 200),
        },
        "sort_by": "composite_score",
    },
    "Value Plays": {
        "description": "Low P/E (under 15x) with positive margins. Deep value hunting.",
        "rating_filter": [],
        "fair_value_filter": [],
        "metric_filters": {
            "trailingPE": (1, 15),
            "profitMargins": (5, 100),
        },
        "sort_by": "composite_score",
    },
    "Momentum Leaders": {
        "description": "Top momentum stocks with positive returns across all timeframes.",
        "rating_filter": [],
        "fair_value_filter": [],
        "metric_filters": {
            "momentum_1m": (0, 200),
            "momentum_3m": (5, 300),
            "momentum_6m": (10, 500),
        },
        "sort_by": "composite_score",
    },
    "High Quality Compounders": {
        "description": "High margins, strong ROE, and consistent growth. Companies that reinvest profits effectively.",
        "rating_filter": [],
        "fair_value_filter": [],
        "metric_filters": {
            "operatingMargins": (15, 100),
            "returnOnEquity": (15, 100),
            "revenueGrowth": (5, 200),
        },
        "sort_by": "composite_score",
    },
    "Dividend Candidates": {
        "description": "Profitable, reasonably valued stocks suitable for income. Stable earners with payout capacity.",
        "rating_filter": ["Strong Buy", "Buy", "Hold"],
        "fair_value_filter": [],
        "metric_filters": {
            "trailingPE": (5, 25),
            "profitMargins": (5, 100),
            "returnOnEquity": (10, 100),
        },
        "sort_by": "composite_score",
    },
    "Aggressive Growth": {
        "description": "High-growth, high-momentum stocks for aggressive portfolios. Higher risk, higher potential reward. Small/mid-cap bias.",
        "rating_filter": ["Strong Buy", "Buy"],
        "fair_value_filter": [],
        "metric_filters": {
            "revenueGrowth": (20, 200),
            "momentum_3m": (10, 300),
            "marketCapB": (2, 100),
        },
        "sort_by": "composite_score",
    },
    "Cautious / Defensive": {
        "description": "Large-cap, profitable, lower-volatility stocks for cautious portfolios. Focus on capital preservation with steady returns.",
        "rating_filter": ["Strong Buy", "Buy", "Hold"],
        "fair_value_filter": [],
        "metric_filters": {
            "marketCapB": (50, 5000),
            "profitMargins": (10, 100),
            "trailingPE": (5, 30),
        },
        "sort_by": "composite_score",
    },
}
