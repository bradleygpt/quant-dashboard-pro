"""
Forward Returns Lookup for Doppelganger Predictive Analysis
Maps each historical analog to its 1-year, 3-year, and 5-year forward returns
based on documented outcomes.

These are approximations from market history. Used to give predictive context
to doppelganger matches.

Note: These are descriptive of what happened to those specific stocks,
not predictive of what will happen to the current stock. Use as historical
context, not financial prophecy.
"""

# Forward returns from the era starting point
# Format: {analog_key: {"1yr": pct, "3yr": pct, "5yr": pct, "confidence": "high/med/low"}}
FORWARD_RETURNS = {
    # ── DOT-COM ERA (1999-2001) - all crashed ──
    "CSCO_1999": {"1yr": -28, "3yr": -85, "5yr": -75, "confidence": "high",
                  "narrative": "Lost 28% in 2000, then collapsed -85% by 2002 bottom. Multiple compression."},
    "INTC_2000": {"1yr": -27, "3yr": -75, "5yr": -65, "confidence": "high",
                  "narrative": "Fell 27% in 2001, bottomed -75% in 2002. Never reached 2000 peak."},
    "MSFT_2000": {"1yr": -41, "3yr": -45, "5yr": -42, "confidence": "high",
                  "narrative": "Fell 41% in 2000, traded sideways for 14 years until cloud pivot."},

    # ── 2008 CRISIS - massive recoveries ──
    "AAPL_2008": {"1yr": 145, "3yr": 250, "5yr": 480, "confidence": "high",
                  "narrative": "iPhone era. 145% in year 1, became most valuable company by 2014."},
    "AMZN_2008": {"1yr": 162, "3yr": 220, "5yr": 285, "confidence": "high",
                  "narrative": "162% rebound in 2009. AWS scaling. 5x by 2013."},

    # ── GROWTH STORIES ──
    "NFLX_2015": {"1yr": -8, "3yr": 75, "5yr": 425, "confidence": "med",
                  "narrative": "Slow first year. International scaled 2017-2018. 5x by 2020."},
    "TSLA_2019": {"1yr": 740, "3yr": 1080, "5yr": 280, "confidence": "high",
                  "narrative": "Profitability inflection. 740% in 2020. -75% drawdown 2022. Recovered partially."},
    "NVDA_2016": {"1yr": 230, "3yr": 165, "5yr": 1100, "confidence": "high",
                  "narrative": "AI emergence. 230% in 2017. Crypto crash 2018. AI boom 2020-2024."},

    # ── COVID BENEFICIARIES ──
    "ZM_2020": {"1yr": -45, "3yr": -85, "5yr": -90, "confidence": "high",
                  "narrative": "Peak COVID overdone. Fell 45% year 1, then -90% as competition arrived."},

    # ── MEGA-CAP TURNAROUNDS ──
    "META_2022": {"1yr": 195, "3yr": 280, "5yr": 320, "confidence": "high",
                  "narrative": "Year of Efficiency. 195% in 2023. AI ads recovery. New ATH 2024."},

    # ── FINANCIALS ──
    "C_2008": {"1yr": -88, "3yr": -45, "5yr": -38, "confidence": "high",
                  "narrative": "Collapsed -88% to bailout. Reverse split. Never recovered to 2007 levels."},
    "JPM_2015": {"1yr": 8, "3yr": 35, "5yr": 65, "confidence": "high",
                  "narrative": "Steady compounding. ~12% annual through 2024."},
    "BAC_2011": {"1yr": -55, "3yr": 95, "5yr": 240, "confidence": "high",
                  "narrative": "Bottomed late 2011. 5x by 2024 as legacy issues resolved."},

    # ── CONSUMER STAPLES ──
    "PG_2018": {"1yr": 28, "3yr": 50, "5yr": 80, "confidence": "med",
                  "narrative": "Activist-driven turnaround. Steady appreciation through 2024."},
    "KO_2016": {"1yr": -2, "3yr": 25, "5yr": 30, "confidence": "med",
                  "narrative": "Steady single-digit returns. Dividend continued."},
    "COST_2015": {"1yr": 7, "3yr": 75, "5yr": 130, "confidence": "high",
                  "narrative": "Quality compounder. Premium multiple held. ~15% annual."},

    # ── UTILITIES ──
    "NEE_2017": {"1yr": 28, "3yr": 110, "5yr": 145, "confidence": "med",
                  "narrative": "Renewable transition story. Doubled by 2021, then rate-driven decline."},

    # ── ENERGY ──
    "XOM_2014": {"1yr": -22, "3yr": -38, "5yr": -45, "confidence": "high",
                  "narrative": "Oil collapse. Stock fell with crude. Recovered post-2022 only."},
    "XOM_2020": {"1yr": 60, "3yr": 220, "5yr": 240, "confidence": "high",
                  "narrative": "COVID bottom. Energy crisis 2022. 3x in 18 months."},

    # ── HEALTHCARE ──
    "UNH_2012": {"1yr": 35, "3yr": 110, "5yr": 195, "confidence": "high",
                  "narrative": "Best-performing Dow stock 2012-2024. ~20% annual."},
    "JNJ_2017": {"1yr": 20, "3yr": 18, "5yr": 25, "confidence": "med",
                  "narrative": "Mid-single digit returns. Talc litigation overhang."},
    "REGN_2011": {"1yr": 280, "3yr": 850, "5yr": 1050, "confidence": "high",
                  "narrative": "Eylea launch. Best biotech of decade. 10x by 2015."},

    # ── INDUSTRIALS ──
    "CAT_2015": {"1yr": 35, "3yr": 65, "5yr": 110, "confidence": "high",
                  "narrative": "Bottomed 2016. Trump infrastructure rally. Recovered to 3x by 2024."},

    # ── CYCLICAL ──
    "HD_2011": {"1yr": 32, "3yr": 90, "5yr": 195, "confidence": "high",
                  "narrative": "Housing recovery. Best retailer of 2010s. 8x by 2021."},
    "F_2020": {"1yr": 145, "3yr": 220, "5yr": 60, "confidence": "med",
                  "narrative": "EV pivot rally. -75% drawdown 2022 on execution doubts."},

    # ── REIT ──
    "PLD_2014": {"1yr": 18, "3yr": 65, "5yr": 145, "confidence": "high",
                  "narrative": "E-commerce logistics boom. 4x by 2021 peak."},

    # ── TELECOM ──
    "T_2017": {"1yr": -20, "3yr": -32, "5yr": -45, "confidence": "high",
                  "narrative": "Dividend trap. Time Warner spinoff at loss. Dividend cut."},

    # ── MATERIALS ──
    "FCX_2020": {"1yr": 235, "3yr": 380, "5yr": 280, "confidence": "high",
                  "narrative": "Copper supercycle recognition. 5x in 18 months."},

    # ── SAAS ──
    "CRM_2014": {"1yr": 35, "3yr": 75, "5yr": 195, "confidence": "high",
                  "narrative": "SaaS adoption. Expanded platform. 10x by 2021 peak."},
    "SHOP_2017": {"1yr": 175, "3yr": 380, "5yr": 1280, "confidence": "high",
                  "narrative": "E-commerce platform. 15x by 2021. -85% in 2022 correction."},
}


def get_forward_returns(analog_key):
    """Get forward returns for a specific analog. Returns None if not found."""
    return FORWARD_RETURNS.get(analog_key)


def aggregate_forward_returns(matches):
    """
    Aggregate forward returns across multiple matches using similarity-weighted average.

    Args:
        matches: List of match dicts from find_doppelgangers, each with:
                 - match_key
                 - similarity (0-1)

    Returns:
        Dict with weighted 1yr/3yr/5yr aggregate returns and metadata.
    """
    if not matches:
        return None

    weighted_1yr = 0
    weighted_3yr = 0
    weighted_5yr = 0
    total_weight = 0
    contributing = []
    missing = []

    for m in matches:
        key = m.get("match_key")
        sim = m.get("similarity", 0)
        fr = FORWARD_RETURNS.get(key)
        if fr is None:
            missing.append(key)
            continue

        weighted_1yr += fr["1yr"] * sim
        weighted_3yr += fr["3yr"] * sim
        weighted_5yr += fr["5yr"] * sim
        total_weight += sim
        contributing.append({
            "key": key,
            "company": m.get("company", ""),
            "era": m.get("era", ""),
            "similarity": sim,
            "ret_1yr": fr["1yr"],
            "ret_3yr": fr["3yr"],
            "ret_5yr": fr["5yr"],
            "narrative": fr.get("narrative", ""),
        })

    if total_weight == 0:
        return None

    # Compute statistics
    returns_1yr = [c["ret_1yr"] for c in contributing]
    returns_3yr = [c["ret_3yr"] for c in contributing]
    returns_5yr = [c["ret_5yr"] for c in contributing]

    return {
        "weighted_1yr_pct": round(weighted_1yr / total_weight, 1),
        "weighted_3yr_pct": round(weighted_3yr / total_weight, 1),
        "weighted_5yr_pct": round(weighted_5yr / total_weight, 1),
        "median_1yr_pct": round(sorted(returns_1yr)[len(returns_1yr)//2], 1) if returns_1yr else 0,
        "median_3yr_pct": round(sorted(returns_3yr)[len(returns_3yr)//2], 1) if returns_3yr else 0,
        "median_5yr_pct": round(sorted(returns_5yr)[len(returns_5yr)//2], 1) if returns_5yr else 0,
        "best_1yr": max(returns_1yr) if returns_1yr else 0,
        "worst_1yr": min(returns_1yr) if returns_1yr else 0,
        "best_5yr": max(returns_5yr) if returns_5yr else 0,
        "worst_5yr": min(returns_5yr) if returns_5yr else 0,
        "contributing_count": len(contributing),
        "missing_count": len(missing),
        "contributing": contributing,
    }
