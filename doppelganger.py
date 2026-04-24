"""
Doppelganger Analysis Module
Finds historical analogues to current stocks by comparing fundamental fingerprints.

Approach:
1. Build a "fingerprint" vector for current stock (valuation, growth, margins, size, momentum)
2. Compare against curated database of historical setups at key inflection points
3. Use cosine similarity or weighted Euclidean distance to rank matches
4. Return top 5 with similarity scores and contextual narratives

The historical database is curated, not scraped. These are well-documented setups
where we have clear narratives and known outcomes.
"""

import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════════
# HISTORICAL REFERENCE DATABASE
# Curated snapshots of famous stock situations at key inflection points.
# ══════════════════════════════════════════════════════════════════

HISTORICAL_ANALOGS = {
    # ── DOT-COM ERA (1999-2001) ──
    "CSCO_1999": {
        "company": "Cisco Systems",
        "era": "1999 (pre-dot-com peak)",
        "marketCapB": 450,
        "trailingPE": 130,
        "priceToSalesTrailing12Months": 35,
        "revenueGrowth": 0.43,
        "profitMargins": 0.17,
        "grossMargins": 0.65,
        "momentum_12m": 1.30,
        "returnOnEquity": 0.25,
        "sector": "Technology",
        "narrative": "Infrastructure backbone of the internet. Trading at extreme P/E multiples on the belief that internet growth was unlimited.",
        "context": "Networking giant at peak of dot-com bubble. Classic 'picks and shovels' play on the internet.",
        "outcome": "Stock fell 85% from peak by 2002. Took 17 years to reach new all-time high (2019). Business remained dominant but valuation multiple collapsed.",
        "lesson": "Dominant business + extreme valuation = long wait for buyers even when fundamentals hold.",
        "tags": ["tech", "infrastructure", "bubble-era", "peak-valuation"],
    },
    "INTC_2000": {
        "company": "Intel",
        "era": "2000 (pre-dot-com peak)",
        "marketCapB": 500,
        "trailingPE": 55,
        "priceToSalesTrailing12Months": 14,
        "revenueGrowth": 0.15,
        "profitMargins": 0.31,
        "grossMargins": 0.63,
        "momentum_12m": 0.45,
        "returnOnEquity": 0.28,
        "sector": "Technology",
        "narrative": "Dominant chip designer riding the PC boom. Controlled the x86 architecture.",
        "context": "Semiconductor leader at peak hardware boom. Seemed unstoppable.",
        "outcome": "Stock fell 80% by 2002. Lost mobile, lost foundry lead to TSMC, only recovered briefly. Still below 2000 peak in 2026.",
        "lesson": "Being dominant today doesn't protect against technology shifts (mobile, ARM, custom silicon).",
        "tags": ["tech", "semiconductors", "peak-valuation", "disruption-risk"],
    },
    "MSFT_2000": {
        "company": "Microsoft",
        "era": "2000 (pre-dot-com peak)",
        "marketCapB": 600,
        "trailingPE": 62,
        "priceToSalesTrailing12Months": 26,
        "revenueGrowth": 0.16,
        "profitMargins": 0.41,
        "grossMargins": 0.87,
        "momentum_12m": -0.05,
        "returnOnEquity": 0.24,
        "sector": "Technology",
        "narrative": "Operating system monopoly with Office dominance. Sky-high multiples.",
        "context": "Facing DOJ antitrust case at peak. Investors priced in perpetual dominance.",
        "outcome": "Stock traded flat for 14 years (2000-2014). Required Nadella's cloud pivot to break out.",
        "lesson": "Even great businesses need catalysts to grow into premium valuations.",
        "tags": ["tech", "software", "monopoly", "valuation-compression"],
    },

    # ── 2008-2009 FINANCIAL CRISIS BOTTOM ──
    "AAPL_2008": {
        "company": "Apple",
        "era": "2008-2009 (crisis bottom)",
        "marketCapB": 75,
        "trailingPE": 15,
        "priceToSalesTrailing12Months": 2.1,
        "revenueGrowth": 0.28,
        "profitMargins": 0.15,
        "grossMargins": 0.34,
        "momentum_12m": -0.55,
        "returnOnEquity": 0.27,
        "sector": "Technology",
        "narrative": "iPhone launched in 2007, App Store in 2008. Major platform shift underway but market was panicking.",
        "context": "Financial crisis sell-off masked transformative iPhone/App Store ecosystem launch.",
        "outcome": "Stock up 100x from 2009 low to 2024. iPhone became largest profit pool in consumer tech history.",
        "lesson": "Crisis-era valuations on companies with new platform advantages create generational opportunities.",
        "tags": ["tech", "consumer", "platform-shift", "crisis-discount"],
    },
    "AMZN_2008": {
        "company": "Amazon",
        "era": "2008 (pre-AWS launch recognition)",
        "marketCapB": 40,
        "trailingPE": 45,
        "priceToSalesTrailing12Months": 2.0,
        "revenueGrowth": 0.29,
        "profitMargins": 0.04,
        "grossMargins": 0.22,
        "momentum_12m": -0.45,
        "returnOnEquity": 0.09,
        "sector": "Consumer Cyclical",
        "narrative": "E-commerce growing through crisis. AWS quietly launched in 2006 but not yet recognized by market.",
        "context": "Bezos's reinvestment strategy criticized as capital-destructive. Market focused on retail.",
        "outcome": "AWS recognized by 2013, stock up 50x through 2021. Cloud became larger profit pool than retail.",
        "lesson": "Hidden optionality (AWS) inside a 'boring' business often undervalued during crises.",
        "tags": ["tech", "ecommerce", "hidden-optionality", "reinvestment"],
    },

    # ── GROWTH STORIES (2015-2020) ──
    "NFLX_2015": {
        "company": "Netflix",
        "era": "2015 (international expansion)",
        "marketCapB": 40,
        "trailingPE": 200,
        "priceToSalesTrailing12Months": 7.0,
        "revenueGrowth": 0.26,
        "profitMargins": 0.01,
        "grossMargins": 0.32,
        "momentum_12m": 0.55,
        "returnOnEquity": 0.08,
        "sector": "Communication Services",
        "narrative": "Transitioning from DVD to streaming, massive content spend, international launch.",
        "context": "Burning cash on content but subscriber growth justified optimism.",
        "outcome": "Up 5x to 2021, then 70% drawdown in 2022 on subscriber losses, recovered by 2024.",
        "lesson": "High-growth cash-burners work until competition arrives and growth slows.",
        "tags": ["tech", "media", "hyper-growth", "cash-burn"],
    },
    "TSLA_2019": {
        "company": "Tesla",
        "era": "2019 (pre-profitability breakthrough)",
        "marketCapB": 55,
        "trailingPE": None,
        "priceToSalesTrailing12Months": 2.5,
        "revenueGrowth": 0.32,
        "profitMargins": -0.05,
        "grossMargins": 0.17,
        "momentum_12m": -0.10,
        "returnOnEquity": -0.08,
        "sector": "Consumer Cyclical",
        "narrative": "Model 3 ramp, manufacturing hell, short-seller darling. Musk's tweets causing SEC issues.",
        "context": "Just before sustained profitability. Most Wall Street rated it Sell.",
        "outcome": "Up 20x through 2021, then -75% drawdown, then recovered. Still highly volatile.",
        "lesson": "Emerging-profitability stories can 10x+ once cash flow inflects, but volatility extreme.",
        "tags": ["auto", "manufacturing", "pre-profitability", "cult-stock"],
    },
    "NVDA_2016": {
        "company": "Nvidia",
        "era": "2016 (AI/crypto emergence)",
        "marketCapB": 30,
        "trailingPE": 30,
        "priceToSalesTrailing12Months": 5.0,
        "revenueGrowth": 0.38,
        "profitMargins": 0.24,
        "grossMargins": 0.59,
        "momentum_12m": 2.20,
        "returnOnEquity": 0.33,
        "sector": "Technology",
        "narrative": "GPU demand exploding from gaming, crypto, and early AI research. Deep learning breakthrough papers using CUDA.",
        "context": "Most investors still saw NVDA as a gaming company. AI upside not fully priced.",
        "outcome": "Up 80x from 2016 through 2024 AI boom. Became 3rd largest company in world.",
        "lesson": "When a company has the best product in an emerging technology cycle, early optimism can be radically too low.",
        "tags": ["tech", "semiconductors", "AI", "platform-monopoly"],
    },

    # ── COVID BENEFICIARIES (2020-2022) ──
    "ZM_2020": {
        "company": "Zoom Video",
        "era": "2020 (COVID peak)",
        "marketCapB": 160,
        "trailingPE": 400,
        "priceToSalesTrailing12Months": 60,
        "revenueGrowth": 3.26,
        "profitMargins": 0.25,
        "grossMargins": 0.70,
        "momentum_12m": 4.20,
        "returnOnEquity": 0.25,
        "sector": "Technology",
        "narrative": "Essential COVID infrastructure. Revenue grew 300%+. Priced as if remote work was permanent structural shift.",
        "context": "Became verb during pandemic. Priced as if growth rate sustainable.",
        "outcome": "Fell 90% from peak. Competition (Teams, Meet) commoditized the product. Growth collapsed.",
        "lesson": "Pulled-forward demand reverts. Moats erode faster when product is easily copied.",
        "tags": ["tech", "covid-beneficiary", "demand-pull-forward", "commoditization"],
    },
    "PTON_2021": {
        "company": "Peloton",
        "era": "2021 (COVID peak)",
        "marketCapB": 45,
        "trailingPE": None,
        "priceToSalesTrailing12Months": 11,
        "revenueGrowth": 1.72,
        "profitMargins": -0.03,
        "grossMargins": 0.36,
        "momentum_12m": -0.40,
        "returnOnEquity": -0.10,
        "sector": "Consumer Cyclical",
        "narrative": "Home fitness boom during lockdowns. Seen as Apple of fitness.",
        "context": "Warehouse excess, recall issues, return-to-gym trend beginning.",
        "outcome": "Fell 95% from peak. Multiple CEO changes. Still struggling to find sustainable model.",
        "lesson": "Hardware + subscription model can work but requires category expansion beyond initial bubble.",
        "tags": ["hardware", "covid-beneficiary", "consumer", "demand-cliff"],
    },

    # ── 2022 TECH CORRECTION ──
    "META_2022": {
        "company": "Meta Platforms",
        "era": "2022 (post-Apple ATT + metaverse fear)",
        "marketCapB": 240,
        "trailingPE": 10,
        "priceToSalesTrailing12Months": 2.3,
        "revenueGrowth": -0.04,
        "profitMargins": 0.19,
        "grossMargins": 0.80,
        "momentum_12m": -0.64,
        "returnOnEquity": 0.19,
        "sector": "Communication Services",
        "narrative": "ATT crushed ad targeting. Reality Labs burning $10B+/yr. Investors rebelled against metaverse spend.",
        "context": "Priced as if core Facebook was dying. Worst sentiment in company history.",
        "outcome": "Up 5x by 2024 on AI-driven ads recovery and cost cuts. Year of Efficiency.",
        "lesson": "Durable businesses with fixable problems and activist pressure can recover faster than market expects.",
        "tags": ["tech", "advertising", "value-in-growth", "efficiency-turnaround"],
    },

    # ── FINANCIAL/CYCLICAL PATTERNS ──
    "C_2008": {
        "company": "Citigroup",
        "era": "2008 (pre-bailout)",
        "marketCapB": 75,
        "trailingPE": 8,
        "priceToSalesTrailing12Months": 0.7,
        "revenueGrowth": -0.25,
        "profitMargins": -0.10,
        "grossMargins": None,
        "momentum_12m": -0.65,
        "returnOnEquity": -0.12,
        "sector": "Financial Services",
        "narrative": "Subprime losses mounting, capital ratio under pressure, dividend cut.",
        "context": "Seemingly cheap but actually overleveraged. Book value suspect.",
        "outcome": "Stock fell 95% more through March 2009. Government bailout. 1:10 reverse split. Still below 2007 levels in 2026.",
        "lesson": "Cyclical financials with leverage problems can fall much further than P/E suggests. Book value isn't real until cycle bottoms.",
        "tags": ["financials", "crisis", "leverage", "value-trap"],
    },

    # ── COMMODITIES ──
    "XOM_2014": {
        "company": "Exxon Mobil",
        "era": "2014 (oil peak)",
        "marketCapB": 420,
        "trailingPE": 13,
        "priceToSalesTrailing12Months": 1.0,
        "revenueGrowth": -0.06,
        "profitMargins": 0.08,
        "grossMargins": 0.28,
        "momentum_12m": 0.05,
        "returnOnEquity": 0.18,
        "sector": "Energy",
        "narrative": "Dividend aristocrat at oil peak. $100/bbl oil seen as floor.",
        "context": "Saudi Arabia about to flood market to kill US shale. Production glut forming.",
        "outcome": "Oil fell to $26 by 2016. Stock dropped 45% through 2020. Eventually recovered on 2022 energy crisis.",
        "lesson": "Commodity producers at cycle peaks with high dividend payouts often disappoint for years.",
        "tags": ["energy", "commodities", "cycle-peak", "dividend"],
    },
}


# ══════════════════════════════════════════════════════════════════
# FINGERPRINT CALCULATION
# ══════════════════════════════════════════════════════════════════

# Fingerprint dimensions and their weights for similarity calculation
FINGERPRINT_DIMENSIONS = {
    "trailingPE": {"weight": 0.15, "log": True, "cap_low": 1, "cap_high": 500},
    "priceToSalesTrailing12Months": {"weight": 0.15, "log": True, "cap_low": 0.1, "cap_high": 100},
    "revenueGrowth": {"weight": 0.20, "log": False, "cap_low": -0.5, "cap_high": 4.0},
    "profitMargins": {"weight": 0.10, "log": False, "cap_low": -0.5, "cap_high": 0.5},
    "grossMargins": {"weight": 0.10, "log": False, "cap_low": 0, "cap_high": 1.0},
    "momentum_12m": {"weight": 0.15, "log": False, "cap_low": -1.0, "cap_high": 5.0},
    "returnOnEquity": {"weight": 0.10, "log": False, "cap_low": -0.5, "cap_high": 0.5},
    "marketCapB": {"weight": 0.05, "log": True, "cap_low": 1, "cap_high": 5000},
}


def _normalize_value(value, dim_config):
    """Normalize a single value to 0-1 range based on caps and log scaling."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None

    v = float(value)
    v = max(dim_config["cap_low"], min(dim_config["cap_high"], v))

    if dim_config["log"]:
        # Log scale for multiplicative metrics
        log_min = np.log10(max(0.01, dim_config["cap_low"]))
        log_max = np.log10(dim_config["cap_high"])
        log_v = np.log10(max(0.01, v))
        return (log_v - log_min) / (log_max - log_min)
    else:
        # Linear scale
        return (v - dim_config["cap_low"]) / (dim_config["cap_high"] - dim_config["cap_low"])


def build_fingerprint(stock_data):
    """Build a fingerprint vector from stock data dict."""
    fingerprint = {}
    for dim, config in FINGERPRINT_DIMENSIONS.items():
        val = stock_data.get(dim)
        normalized = _normalize_value(val, config)
        fingerprint[dim] = normalized
    return fingerprint


def compute_similarity(fp1, fp2):
    """Compute weighted Euclidean similarity between two fingerprints."""
    total_distance = 0
    total_weight = 0
    matched_dims = 0

    for dim, config in FINGERPRINT_DIMENSIONS.items():
        v1 = fp1.get(dim)
        v2 = fp2.get(dim)
        if v1 is None or v2 is None:
            continue
        distance = abs(v1 - v2)
        weight = config["weight"]
        total_distance += (distance ** 2) * weight
        total_weight += weight
        matched_dims += 1

    if matched_dims < 4 or total_weight == 0:
        return 0  # Not enough data

    # Convert distance to similarity (0-1, higher = more similar)
    normalized_distance = np.sqrt(total_distance / total_weight)
    similarity = max(0, 1 - normalized_distance)

    # Penalize if too few dimensions matched
    confidence_factor = matched_dims / len(FINGERPRINT_DIMENSIONS)
    return similarity * confidence_factor


def find_doppelgangers(ticker, scored_df, top_n=5, sector_filter=None, tag_filter=None):
    """
    Find historical analogues for a current stock.

    Args:
        ticker: Current ticker to find matches for
        scored_df: Scored DataFrame with current stock data
        top_n: Number of matches to return
        sector_filter: If provided, only match within same sector
        tag_filter: If provided, only match analogs with this tag

    Returns:
        List of {match_key, company, era, similarity, data, narrative} dicts
    """
    if ticker not in scored_df.index:
        return []

    stock_data = scored_df.loc[ticker].to_dict()
    current_fp = build_fingerprint(stock_data)

    matches = []
    for key, analog in HISTORICAL_ANALOGS.items():
        # Apply filters
        if sector_filter and analog.get("sector") != stock_data.get("sector"):
            continue
        if tag_filter and tag_filter not in analog.get("tags", []):
            continue

        analog_fp = build_fingerprint(analog)
        similarity = compute_similarity(current_fp, analog_fp)

        if similarity > 0.3:  # Minimum threshold
            matches.append({
                "match_key": key,
                "company": analog["company"],
                "era": analog["era"],
                "similarity": round(similarity, 3),
                "data": analog,
                "sector": analog.get("sector", "N/A"),
                "context": analog.get("context", ""),
                "outcome": analog.get("outcome", ""),
                "lesson": analog.get("lesson", ""),
                "narrative": analog.get("narrative", ""),
                "tags": analog.get("tags", []),
            })

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:top_n]


def get_tags_list():
    """Return all unique tags in the historical database."""
    tags = set()
    for analog in HISTORICAL_ANALOGS.values():
        tags.update(analog.get("tags", []))
    return sorted(tags)


def get_database_stats():
    """Summary stats about the historical database."""
    return {
        "total_analogs": len(HISTORICAL_ANALOGS),
        "sectors": sorted(set(a["sector"] for a in HISTORICAL_ANALOGS.values() if a.get("sector"))),
        "eras_covered": sorted(set(a["era"] for a in HISTORICAL_ANALOGS.values())),
        "tags": get_tags_list(),
    }
