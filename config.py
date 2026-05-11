"""
Configuration for the Quantitative Strategy Dashboard.
"""

DEFAULT_MARKET_CAP_FLOOR_B = 10
MIN_MARKET_CAP_FLOOR_B = 1
MAX_MARKET_CAP_FLOOR_B = 50

# ── Pillar Weight Presets ──────────────────────────────────────────
# Backtested across 1996-2026 (121 quarterly rebalances, TOP25 selection,
# 1Q hold-and-reselect). 5-pillar dashboard tests on 4 pillars (V/G/P/M)
# because EPS Revisions history pre-2010 is unreliable. New presets set
# EPS Revisions to 0% - honest about what was tested.
#
#   m_heavy: V=0.05 G=0.15 P=0.00 M=0.80  → +30.12% CAGR  Sharpe 1.30
#   v_heavy: V=0.45 G=0.10 P=0.25 M=0.20  → +28.18% CAGR  Sharpe 1.35
#   equal:   each pillar 20%               → +26.27% CAGR  Sharpe 1.21

WEIGHT_PRESETS = {
    "m_heavy": {
        "label": "Growth/Momentum (highest CAGR)",
        "weights": {
            "Valuation": 0.05,
            "Growth": 0.15,
            "Profitability": 0.00,
            "Momentum": 0.80,
            "EPS Revisions": 0.00,
        },
        "backtest_cagr": 30.12,
        "backtest_sharpe": 1.30,
        "backtest_max_dd": -32.04,
    },
    "v_heavy": {
        "label": "Value/Quality (highest Sharpe)",
        "weights": {
            "Valuation": 0.45,
            "Growth": 0.10,
            "Profitability": 0.25,
            "Momentum": 0.20,
            "EPS Revisions": 0.00,
        },
        "backtest_cagr": 28.18,
        "backtest_sharpe": 1.35,
        "backtest_max_dd": -37.39,
    },
    "equal": {
        "label": "Equal weight (legacy)",
        "weights": {
            "Valuation": 0.20,
            "Growth": 0.20,
            "Profitability": 0.20,
            "Momentum": 0.20,
            "EPS Revisions": 0.20,
        },
        "backtest_cagr": 26.27,
        "backtest_sharpe": 1.21,
        "backtest_max_dd": -35.67,
    },
}

DEFAULT_PRESET = "m_heavy"
DEFAULT_PILLAR_WEIGHTS = WEIGHT_PRESETS[DEFAULT_PRESET]["weights"]

# ── Absolute Threshold Breadth Indicator ──────────────────────────
# Median quarterly TOP25 cutoff composite score across 1996-2026 history.
# When the count of stocks above this threshold contracts, market breadth
# is thinning. When it expands, breadth is broadening. Display in screener.
#
# Per-scheme thresholds (derived from backtest):
#   m_heavy: 10.617 (count median 153, range 35-246)
#   v_heavy:  8.723 (count median  25, range  0-76)

ABSOLUTE_THRESHOLDS = {
    "m_heavy": 10.617,
    "v_heavy": 8.723,
    "equal":    8.5,  # approximate, untested - placeholder for legacy
}

ABSOLUTE_THRESHOLD_STATS = {
    "m_heavy": {"median_count": 153, "min_count": 35, "max_count": 246, "mean_count": 156.2},
    "v_heavy": {"median_count": 25,  "min_count": 0,  "max_count": 76,  "mean_count": 28.9},
    "equal":   {"median_count": None, "min_count": None, "max_count": None, "mean_count": None},
}

PILLAR_METRICS = {
    "Valuation": [
        ("forwardPE", "Forward P/E", False),
        ("trailingPE", "Trailing P/E", False),
        ("pegRatio", "PEG Ratio", False),
        ("priceToBook", "Price / Book", False),
        ("priceToSalesTrailing12Months", "Price / Sales", False),
        ("enterpriseToEbitda", "EV / EBITDA", False),
        ("enterpriseToRevenue", "EV / Revenue", False),
    ],
    "Growth": [
        ("revenueGrowth", "Revenue Growth (QoQ)", True),
        ("earningsGrowth", "Earnings Growth (QoQ)", True),
        ("revenueQuarterlyGrowth", "Revenue Growth (YoY)", True),
        ("earningsQuarterlyGrowth", "Earnings Growth (YoY)", True),
    ],
    "Profitability": [
        ("grossMargins", "Gross Margin", True),
        ("operatingMargins", "Operating Margin", True),
        ("profitMargins", "Net Margin", True),
        ("returnOnEquity", "Return on Equity", True),
        ("returnOnAssets", "Return on Assets", True),
    ],
    "Momentum": [
        ("momentum_1m", "1-Month Return", True),
        ("momentum_3m", "3-Month Return", True),
        ("momentum_6m", "6-Month Return", True),
        ("momentum_12m", "12-Month Return", True),
        ("momentum_vs_sma50", "Price vs 50-Day SMA", True),
        ("momentum_vs_sma200", "Price vs 200-Day SMA", True),
    ],
    "EPS Revisions": [
        ("analyst_mean_target_upside", "Mean Target Upside %", True),
        ("analyst_recommendation_score", "Analyst Rec Score (inv)", False),
        ("earnings_surprise_pct", "Last Earnings Surprise %", True),
        ("analyst_count", "# Covering Analysts", True),
    ],
}

GRADE_PERCENTILE_MAP = {
    "A+": (95, 100), "A": (85, 95), "A-": (75, 85),
    "B+": (65, 75), "B": (55, 65), "B-": (45, 55),
    "C+": (35, 45), "C": (25, 35), "C-": (15, 25),
    "D+": (10, 15), "D": (5, 10), "F": (0, 5),
}

GRADE_SCORES = {
    "A+": 12, "A": 11, "A-": 10,
    "B+": 9, "B": 8, "B-": 7,
    "C+": 6, "C": 5, "C-": 4,
    "D+": 3, "D": 2, "F": 1,
}

# ── Rating Thresholds ──────────────────────────────────────────────
# REBALANCED for ~12% Strong Buy, 13% Buy, 50% Hold, 13% Sell, 12% Strong Sell
# With sector-relative scoring, mean composite is ~7.0 with SD ~1.5
# These thresholds produce approximately 25% buy zone / 50% hold / 25% sell zone
OVERALL_RATING_MAP = {
    "Strong Buy": (9.0, 12.0),   # Top ~8-12%
    "Buy": (8.0, 9.0),           # Next ~12-17%
    "Hold": (6.0, 8.0),          # Middle ~45-55%
    "Sell": (5.0, 6.0),          # Next ~12-17%
    "Strong Sell": (0.0, 5.0),   # Bottom ~8-12%
}

RATING_COLORS = {
    "Strong Buy": "#00C805", "Buy": "#8BC34A", "Hold": "#FFC107",
    "Sell": "#FF5722", "Strong Sell": "#D32F2F",
}

GRADE_COLORS = {
    "A+": "#00C805", "A": "#00C805", "A-": "#4CAF50",
    "B+": "#8BC34A", "B": "#8BC34A", "B-": "#CDDC39",
    "C+": "#FFC107", "C": "#FFC107", "C-": "#FF9800",
    "D+": "#FF5722", "D": "#FF5722", "F": "#D32F2F",
}

SECTOR_OVERRIDES = {
    "FISV": {"sector": "Technology", "industry": "Information Technology Services"},
    "FIS": {"sector": "Technology", "industry": "Information Technology Services"},
    "GPN": {"sector": "Technology", "industry": "Information Technology Services"},
    "JKHY": {"sector": "Technology", "industry": "Information Technology Services"},
}

CACHE_DIR = "data_cache"
CACHE_EXPIRY_HOURS = 12
TICKER_LIST_CACHE_FILE = "ticker_universe.json"
FUNDAMENTALS_CACHE_FILE = "fundamentals_cache.json"
SCORES_CACHE_FILE = "scores_cache.json"
WATCHLIST_FILE = "watchlist.json"
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
