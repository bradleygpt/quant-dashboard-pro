"""
Configuration for the Quantitative Strategy Dashboard.
"""

DEFAULT_MARKET_CAP_FLOOR_B = 10
MIN_MARKET_CAP_FLOOR_B = 1
MAX_MARKET_CAP_FLOOR_B = 50

# ── Pillar Weight Presets ──────────────────────────────────────────
# Each preset validated 1996-2026, 121 quarterly rebalances, TOP25 1Q reselect.
# CAGR varies by MC floor — see ARCHITECTURE.md for full backtest matrix.
#
#   No-floor universe:  equal=+26.27%  m_heavy=+30.12%  v_heavy=+28.18%
#   $1B+ universe:      equal=+14.42%  m_heavy=+14.67%  (mature_bull=+16.63%)
#   $10B+ universe:     equal=+12.51%  m_heavy=+11.27%
#
# equal is the safest default — it works across all universes. m_heavy delivers
# higher CAGR but only when no MC floor is applied (small-cap exposure required).
# v_heavy was backtested only at no-floor; performance at filtered universes unknown.

WEIGHT_PRESETS = {
    "equal": {
        "label": "Equal weight (validated, default)",
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
        "backtest_universe": "Full universe (no MC floor), 1996-2026",
        "validated_at_floor": True,
    },
    "m_heavy": {
        "label": "Growth/Momentum (no-floor optimal)",
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
        "backtest_universe": "Full universe (no MC floor), 1996-2026",
        "validated_at_floor": True,
    },
    "v_heavy": {
        "label": "Value/Quality (no-floor only)",
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
        "backtest_universe": "Full universe (no MC floor), 1996-2026",
        "validated_at_floor": True,
    },
}

DEFAULT_PRESET = "equal"
DEFAULT_PILLAR_WEIGHTS = WEIGHT_PRESETS[DEFAULT_PRESET]["weights"]

# ── Absolute Threshold Breadth Indicator ──────────────────────────
# Median quarterly TOP25 cutoff composite score across 1996-2026 history.
# When the count of stocks above this threshold contracts, market breadth
# is thinning. When it expands, breadth is broadening.

ABSOLUTE_THRESHOLDS = {
    "equal":   8.5,
    "m_heavy": 10.617,
    "v_heavy": 8.723,
}

ABSOLUTE_THRESHOLD_STATS = {
    "equal":   {"median_count": None, "min_count": None, "max_count": None, "mean_count": None},
    "m_heavy": {"median_count": 153, "min_count": 35, "max_count": 246, "mean_count": 156.2},
    "v_heavy": {"median_count": 25,  "min_count": 0,  "max_count": 76,  "mean_count": 28.9},
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

# ── Rating Thresholds (LEGACY DEFAULT — fallback for ranks 26+ and ETFs) ──
# Strong Buy+ and Strong Buy tiers for ranks 1-25 are now assigned by
# _classify_top25_tier() in scoring.py based on price vs Fair Value and
# Quant Buy Point. High composite score alone does NOT grant Strong Buy
# status — value-relative-to-price is the gate.
OVERALL_RATING_MAP = {
    "Strong Buy+": (9.0, 12.0),  # Informational only — actual assignment via QBP/FV
    "Strong Buy": (9.0, 12.0),   # Top ~8-12% (legacy score band, now overridden)
    "Buy": (8.0, 9.0),           # Next ~12-17%
    "Hold": (6.0, 8.0),          # Middle ~45-55%
    "Sell": (5.0, 6.0),          # Next ~12-17%
    "Strong Sell": (0.0, 5.0),   # Bottom ~8-12%
}

# ── Per-Preset Rating Maps (LEGACY — for ranks 26+ only) ──────────────
# Each weight scheme produces a different composite distribution. These maps
# calibrate Hold/Sell/Strong Sell thresholds per preset. TOP25 is now classified
# via QBP/FV in scoring.py, so Strong Buy+/Strong Buy/Buy thresholds here are
# informational only.

RATING_MAPS_PER_PRESET = {
    "equal": {
        "Strong Buy+": (9.0, 12.0),
        "Strong Buy": (9.0, 12.0),
        "Buy": (8.0, 9.0),
        "Hold": (6.0, 8.0),
        "Sell": (5.0, 6.0),
        "Strong Sell": (0.0, 5.0),
    },
    "m_heavy": {
        "Strong Buy+": (11.0, 12.0),
        "Strong Buy": (11.0, 12.0),
        "Buy": (10.617, 11.0),
        "Hold": (8.5, 10.617),
        "Sell": (7.0, 8.5),
        "Strong Sell": (0.0, 7.0),
    },
    "v_heavy": {
        "Strong Buy+": (9.0, 12.0),
        "Strong Buy": (9.0, 12.0),
        "Buy": (8.723, 9.0),
        "Hold": (6.5, 8.723),
        "Sell": (5.0, 6.5),
        "Strong Sell": (0.0, 5.0),
    },
}


def get_rating_map(preset_name: str = None) -> dict:
    """Return the rating threshold map for the given preset.
    Falls back to OVERALL_RATING_MAP if preset is None or unknown."""
    if preset_name and preset_name in RATING_MAPS_PER_PRESET:
        return RATING_MAPS_PER_PRESET[preset_name]
    return OVERALL_RATING_MAP


RATING_COLORS = {
    "Strong Buy+": "#00FF00",      # Bright lime green — top conviction (at FV AND QBP)
    "Strong Buy": "#00C805",       # Vivid green — at FV
    "Buy": "#8BC34A",              # Light green
    "Hold": "#FFC107",             # Amber
    "Sell": "#FF5722",             # Orange-red
    "Strong Sell": "#D32F2F",      # Deep red
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
