"""
Configuration for the Quantitative Strategy Dashboard.
"""

DEFAULT_MARKET_CAP_FLOOR_B = 10
MIN_MARKET_CAP_FLOOR_B = 1
MAX_MARKET_CAP_FLOOR_B = 50

DEFAULT_PILLAR_WEIGHTS = {
    "Valuation": 0.20,
    "Growth": 0.20,
    "Profitability": 0.20,
    "Momentum": 0.20,
    "EPS Revisions": 0.20,
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
