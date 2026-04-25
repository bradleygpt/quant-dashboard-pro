"""
ETF Center Module
Three sections:
1. Portfolio Builder - Risk-based ETF allocation suggestions
2. ETF Comparison Tool - Side-by-side comparison
3. Sector ETF Map - Which ETF for which sector tilt
"""

import json
import os
import pandas as pd
import numpy as np


# ══════════════════════════════════════════════════════════════════
# Section 1: Portfolio Builder Templates
# ══════════════════════════════════════════════════════════════════

PORTFOLIO_TEMPLATES = {
    "Cautious": {
        "description": "Capital preservation with steady income. Suited for retirees or near-retirees with low risk tolerance.",
        "risk_score": 3,  # Out of 10
        "expected_annual_return": "5-7%",
        "max_drawdown_estimate": "15-20%",
        "allocations": [
            {"category": "US Total Bond Market", "etf": "BND", "alt": "AGG", "weight": 40,
             "purpose": "Income and stability"},
            {"category": "US Large-Cap Core", "etf": "IVV", "alt": "VOO", "weight": 25,
             "purpose": "Conservative equity exposure"},
            {"category": "US Large-Cap Value", "etf": "VTV", "alt": "SCHV", "weight": 15,
             "purpose": "Defensive equity tilt"},
            {"category": "Dividend Stocks", "etf": "VYM", "alt": "VIG", "weight": 10,
             "purpose": "Income generation"},
            {"category": "International Developed", "etf": "VEA", "alt": "SCHF", "weight": 10,
             "purpose": "Geographic diversification"},
        ],
    },
    "Moderate": {
        "description": "Balanced growth and income. Suited for mid-career investors with 10-20 year horizon.",
        "risk_score": 6,
        "expected_annual_return": "7-9%",
        "max_drawdown_estimate": "25-35%",
        "allocations": [
            {"category": "US Total Stock Market", "etf": "VTI", "alt": "ITOT", "weight": 35,
             "purpose": "Broad US equity core"},
            {"category": "US Large-Cap Growth", "etf": "VUG", "alt": "SCHG", "weight": 15,
             "purpose": "Growth tilt"},
            {"category": "US Mid-Cap", "etf": "VO", "alt": "IJH", "weight": 10,
             "purpose": "Mid-cap diversification"},
            {"category": "US Small-Cap", "etf": "IJR", "alt": "VB", "weight": 5,
             "purpose": "Small-cap exposure"},
            {"category": "International Developed", "etf": "VEA", "alt": "SCHF", "weight": 15,
             "purpose": "International diversification"},
            {"category": "Emerging Markets", "etf": "VWO", "alt": "IEMG", "weight": 5,
             "purpose": "Higher growth potential"},
            {"category": "US Total Bond Market", "etf": "BND", "alt": "AGG", "weight": 15,
             "purpose": "Volatility dampener"},
        ],
    },
    "Aggressive": {
        "description": "Maximum long-term growth. Suited for younger investors or those with high risk tolerance and 20+ year horizon.",
        "risk_score": 9,
        "expected_annual_return": "9-12%",
        "max_drawdown_estimate": "40-55%",
        "allocations": [
            {"category": "US Total Stock Market", "etf": "VTI", "alt": "ITOT", "weight": 30,
             "purpose": "Broad US equity"},
            {"category": "US Large-Cap Growth", "etf": "VUG", "alt": "QQQ", "weight": 20,
             "purpose": "Growth concentration"},
            {"category": "Technology", "etf": "QQQ", "alt": "XLK", "weight": 10,
             "purpose": "Tech tilt"},
            {"category": "US Mid-Cap Growth", "etf": "VOT", "alt": "VO", "weight": 10,
             "purpose": "Mid-cap growth"},
            {"category": "US Small-Cap", "etf": "IJR", "alt": "VB", "weight": 10,
             "purpose": "Small-cap risk premium"},
            {"category": "International Developed", "etf": "VEA", "alt": "SCHF", "weight": 10,
             "purpose": "International growth"},
            {"category": "Emerging Markets", "etf": "VWO", "alt": "IEMG", "weight": 10,
             "purpose": "EM growth potential"},
        ],
    },
    "Tech Concentrated": {
        "description": "Heavy tech and growth tilt for those bullish on innovation. High volatility expected.",
        "risk_score": 10,
        "expected_annual_return": "10-15%",
        "max_drawdown_estimate": "50-70%",
        "allocations": [
            {"category": "Nasdaq 100", "etf": "QQQ", "alt": "QQQM", "weight": 35,
             "purpose": "Big tech core"},
            {"category": "Tech Sector", "etf": "XLK", "alt": "VGT", "weight": 20,
             "purpose": "Pure tech exposure"},
            {"category": "AI / Quantum", "etf": "QTUM", "alt": "BAI", "weight": 10,
             "purpose": "Emerging tech themes"},
            {"category": "US Total Stock Market", "etf": "VTI", "alt": "ITOT", "weight": 20,
             "purpose": "Diversification anchor"},
            {"category": "International Developed", "etf": "VEA", "alt": "SCHF", "weight": 10,
             "purpose": "Geographic diversification"},
            {"category": "Bitcoin / Crypto", "etf": "IBIT", "alt": "BITQ", "weight": 5,
             "purpose": "Digital asset exposure"},
        ],
    },
    "Income Focused": {
        "description": "Maximize current income with capital preservation. Suited for retirees needing cash flow.",
        "risk_score": 4,
        "expected_annual_return": "4-6%",
        "max_drawdown_estimate": "15-25%",
        "allocations": [
            {"category": "High Dividend Yield", "etf": "VYM", "alt": "SCHD", "weight": 25,
             "purpose": "Dividend income"},
            {"category": "Dividend Appreciation", "etf": "VIG", "alt": "SCHD", "weight": 20,
             "purpose": "Growing dividends"},
            {"category": "Real Estate", "etf": "VNQ", "alt": "SCHH", "weight": 10,
             "purpose": "Real estate income"},
            {"category": "Long Treasury", "etf": "TLT", "alt": "BLV", "weight": 15,
             "purpose": "Duration income"},
            {"category": "US Total Bond Market", "etf": "BND", "alt": "AGG", "weight": 25,
             "purpose": "Diversified bonds"},
            {"category": "US Large-Cap Value", "etf": "VTV", "alt": "SCHV", "weight": 5,
             "purpose": "Value equity"},
        ],
    },
}


def get_portfolio_template(template_name):
    return PORTFOLIO_TEMPLATES.get(template_name)


def list_templates():
    return list(PORTFOLIO_TEMPLATES.keys())


def calculate_template_metrics(template_name, total_investment=100000):
    """Calculate dollar amounts and validate the template."""
    template = PORTFOLIO_TEMPLATES.get(template_name)
    if not template:
        return None

    total_weight = sum(a["weight"] for a in template["allocations"])
    rows = []
    for alloc in template["allocations"]:
        dollar_amount = total_investment * (alloc["weight"] / 100)
        rows.append({
            "Category": alloc["category"],
            "Primary ETF": alloc["etf"],
            "Alternative": alloc["alt"],
            "Weight %": alloc["weight"],
            "Amount": dollar_amount,
            "Purpose": alloc["purpose"],
        })

    return {
        "template": template,
        "rows": rows,
        "total_weight": total_weight,
        "total_investment": total_investment,
        "valid": total_weight == 100,
    }


# ══════════════════════════════════════════════════════════════════
# Section 2: ETF Comparison
# ══════════════════════════════════════════════════════════════════

def compare_etfs(tickers, raw_cache):
    """Side-by-side comparison of ETFs from cache."""
    if not tickers:
        return None

    rows = []
    for t in tickers:
        if t in raw_cache:
            data = raw_cache[t]
            rows.append({
                "Ticker": t,
                "Name": data.get("shortName", t),
                "Category": data.get("category", "N/A"),
                "Expense Ratio": data.get("expenseRatio", None),
                "AUM ($B)": data.get("totalAssets", 0) / 1e9 if data.get("totalAssets") else 0,
                "Yield %": data.get("yield", 0) * 100 if data.get("yield") else 0,
                "1M %": (data.get("momentum_1m", 0) or 0) * 100,
                "3M %": (data.get("momentum_3m", 0) or 0) * 100,
                "6M %": (data.get("momentum_6m", 0) or 0) * 100,
                "12M %": (data.get("momentum_12m", 0) or 0) * 100,
                "YTD %": (data.get("ytdReturn", 0) or 0) * 100,
                "Beta (3Y)": data.get("beta3Year", None),
                "Price": data.get("currentPrice", 0),
            })
    return pd.DataFrame(rows) if rows else None


# ══════════════════════════════════════════════════════════════════
# Section 3: Sector ETF Map
# ══════════════════════════════════════════════════════════════════

SECTOR_ETF_MAP = [
    {"sector": "Technology", "ticker": "XLK", "alternative": "VGT",
     "use_case": "Overweight tech for growth tilt. Top holdings include Apple, Microsoft, Nvidia."},
    {"sector": "Healthcare", "ticker": "XLV", "alternative": "VHT",
     "use_case": "Defensive growth. Pharma, biotech, devices, services."},
    {"sector": "Financials", "ticker": "XLF", "alternative": "VFH",
     "use_case": "Banks, insurance, asset managers. Benefits from rising rates."},
    {"sector": "Consumer Discretionary", "ticker": "XLY", "alternative": "VCR",
     "use_case": "Cyclical exposure. Amazon, Tesla, Home Depot. Bullish economy bet."},
    {"sector": "Communication Services", "ticker": "XLC", "alternative": "VOX",
     "use_case": "Meta, Google, Netflix. Media and digital advertising."},
    {"sector": "Industrials", "ticker": "XLI", "alternative": "VIS",
     "use_case": "Defense, aerospace, transportation. Infrastructure spending beneficiary."},
    {"sector": "Consumer Staples", "ticker": "XLP", "alternative": "VDC",
     "use_case": "Defensive. Food, beverages, household products. Recession-resistant."},
    {"sector": "Energy", "ticker": "XLE", "alternative": "VDE",
     "use_case": "Oil and gas. Inflation hedge. Volatile with commodity prices."},
    {"sector": "Utilities", "ticker": "XLU", "alternative": "VPU",
     "use_case": "Highly defensive. Stable dividends. Rate-sensitive."},
    {"sector": "Materials", "ticker": "XLB", "alternative": "VAW",
     "use_case": "Mining, chemicals, packaging. Commodity-driven."},
    {"sector": "Real Estate", "ticker": "XLRE", "alternative": "VNQ",
     "use_case": "REITs. Income-focused. Rate-sensitive."},
]


THEME_ETF_MAP = [
    {"theme": "Artificial Intelligence", "ticker": "BAI", "alternative": "AIQ",
     "use_case": "Concentrated AI exposure. Pure-play AI companies."},
    {"theme": "Cybersecurity", "ticker": "CIBR", "alternative": "BUG",
     "use_case": "Cybersecurity software and services."},
    {"theme": "Quantum Computing", "ticker": "QTUM", "alternative": None,
     "use_case": "Emerging quantum computing exposure. Highly speculative."},
    {"theme": "Bitcoin", "ticker": "IBIT", "alternative": "FBTC",
     "use_case": "Spot Bitcoin ETF. Direct crypto exposure without wallet."},
    {"theme": "Crypto Miners", "ticker": "BITQ", "alternative": None,
     "use_case": "Bitcoin mining and crypto-related companies."},
    {"theme": "Space", "ticker": "ARKX", "alternative": "UFO",
     "use_case": "Space exploration, satellites, aerospace."},
    {"theme": "Semiconductors", "ticker": "SOXX", "alternative": "SMH",
     "use_case": "Chip makers. AI infrastructure beneficiary."},
    {"theme": "Clean Energy", "ticker": "ICLN", "alternative": "QCLN",
     "use_case": "Solar, wind, EV. ESG / climate transition."},
    {"theme": "Nuclear", "ticker": "NLR", "alternative": "URA",
     "use_case": "Nuclear power. AI-driven energy demand thesis."},
    {"theme": "Copper", "ticker": "COPX", "alternative": None,
     "use_case": "Copper miners. Electrification metal."},
    {"theme": "Disruptive Innovation", "ticker": "ARKK", "alternative": None,
     "use_case": "Cathie Wood's flagship. Highly speculative growth."},
    {"theme": "Magnificent 7", "ticker": "MAGS", "alternative": None,
     "use_case": "Top 7 tech mega-caps in one ETF."},
]


def get_sector_etf_map():
    return SECTOR_ETF_MAP


def get_theme_etf_map():
    return THEME_ETF_MAP


def load_raw_cache():
    """Load full ETF cache including ETFs."""
    for path in ["fundamentals_cache.json", os.path.join("data_cache", "fundamentals_cache.json")]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def get_etf_universe(raw_cache):
    """Return list of all ETF tickers in the cache."""
    return sorted([t for t, d in raw_cache.items()
                   if d.get("type") == "etf" or d.get("sector") == "ETF"])
