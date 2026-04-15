"""
Fair Value Estimator v3 - Quality-Adjusted Approach.

Key principle: A company's fair multiple depends on its QUALITY relative to peers.
A top-quartile growth company deserves a top-quartile multiple, not the sector median.

Methods by weight:
1. PEG-Based (30%) - primary for all sectors. PEG=1 is fair value baseline.
2. Quality-Adjusted Relative (30%) - uses the multiple the company DESERVES
   based on its growth + profitability rank within sector
3. Trailing Earnings Capitalization (20%) - quality-adjusted PE
4. Analyst Target (20%) - consensus with analyst count weighting

Sector-specific primary multiples:
- Technology/Comms: P/S relative (quality-adjusted)
- Financials: P/B relative (quality-adjusted)
- Energy/Utilities/Industrials/Materials: EV/EBITDA relative (quality-adjusted)
- Real Estate: P/B relative (proxy for P/FFO)
- Healthcare/Consumer: P/E relative (quality-adjusted)

Graham Number removed: too conservative for modern markets.
"""

import numpy as np
import pandas as pd


# ── Sector Configuration ───────────────────────────────────────────

SECTOR_RELATIVE_METRIC = {
    "Technology": {"key": "priceToSalesTrailing12Months", "name": "P/S", "label": "Price/Sales"},
    "Communication Services": {"key": "priceToSalesTrailing12Months", "name": "P/S", "label": "Price/Sales"},
    "Financial Services": {"key": "priceToBook", "name": "P/B", "label": "Price/Book"},
    "Energy": {"key": "enterpriseToEbitda", "name": "EV/EBITDA", "label": "EV/EBITDA"},
    "Utilities": {"key": "enterpriseToEbitda", "name": "EV/EBITDA", "label": "EV/EBITDA"},
    "Industrials": {"key": "enterpriseToEbitda", "name": "EV/EBITDA", "label": "EV/EBITDA"},
    "Basic Materials": {"key": "enterpriseToEbitda", "name": "EV/EBITDA", "label": "EV/EBITDA"},
    "Real Estate": {"key": "priceToBook", "name": "P/B", "label": "Price/Book"},
    "Healthcare": {"key": "trailingPE", "name": "P/E", "label": "Trailing P/E"},
    "Consumer Cyclical": {"key": "priceToSalesTrailing12Months", "name": "P/S", "label": "Price/Sales"},
    "Consumer Defensive": {"key": "trailingPE", "name": "P/E", "label": "Trailing P/E"},
}

DEFAULT_RELATIVE_METRIC = {"key": "trailingPE", "name": "P/E", "label": "Trailing P/E"}


def compute_fair_value(ticker: str, scored_df: pd.DataFrame, raw_cache: dict = None) -> dict:
    """
    Compute fair value using quality-adjusted methods.
    No Graham Number. PEG is primary. Relative valuation adjusts for company quality.
    """
    if ticker not in scored_df.index:
        if raw_cache and ticker in raw_cache:
            data = raw_cache[ticker]
        else:
            return {"error": "Ticker not found in universe."}
    else:
        data = scored_df.loc[ticker].to_dict()

    current_price = data.get("currentPrice", 0)
    if not current_price or current_price <= 0:
        return {"error": "No price data available."}

    sector = data.get("sector", "Unknown")
    methods = {}

    # Method 1: PEG-Based (30% weight) - PRIMARY
    peg_val = _peg_fair_value(data)
    if peg_val:
        methods["PEG Fair Value"] = peg_val

    # Method 2: Quality-Adjusted Relative (30% weight)
    relative = _quality_adjusted_relative(data, sector, scored_df)
    if relative:
        methods[f"Quality-Adjusted {relative.get('metric_label', 'Relative')}"] = relative

    # Method 3: Trailing Earnings Capitalization (20% weight)
    trailing = _trailing_earnings_value(data, sector, scored_df)
    if trailing:
        methods["Earnings Capitalization"] = trailing

    # Method 4: Analyst Target (20% weight)
    analyst = _analyst_target(data)
    if analyst:
        methods["Analyst Consensus"] = analyst

    if not methods:
        return {
            "ticker": ticker, "current_price": current_price,
            "error": "Insufficient data for fair value calculation.", "methods": {},
        }

    # ── Weighted Composite ─────────────────────────────────────────
    method_weights = {
        "PEG Fair Value": 0.30,
        "Earnings Capitalization": 0.20,
        "Analyst Consensus": 0.20,
    }
    # Quality-adjusted relative gets 0.30
    for mname in methods:
        if "Quality-Adjusted" in mname:
            method_weights[mname] = 0.30

    weighted_sum = 0
    total_weight = 0
    for mname, mdata in methods.items():
        fv = mdata.get("fair_value", 0)
        w = method_weights.get(mname, 0.15)
        if fv and fv > 0 and np.isfinite(fv):
            ratio = fv / current_price
            # Wider sanity bounds: 5% to 500% of current price
            if 0.05 < ratio < 5.0:
                weighted_sum += fv * w
                total_weight += w

    composite_fv = weighted_sum / total_weight if total_weight > 0 else 0

    if composite_fv > 0:
        premium_discount_pct = ((current_price - composite_fv) / composite_fv) * 100
    else:
        premium_discount_pct = 0

    # Wider bands to reduce false precision
    if premium_discount_pct < -30:
        verdict, verdict_color = "Deeply Undervalued", "#00C805"
    elif premium_discount_pct < -10:
        verdict, verdict_color = "Undervalued", "#8BC34A"
    elif premium_discount_pct < 20:
        verdict, verdict_color = "Fairly Valued", "#FFC107"
    elif premium_discount_pct < 40:
        verdict, verdict_color = "Overvalued", "#FF5722"
    else:
        verdict, verdict_color = "Significantly Overvalued", "#D32F2F"

    rel_metric = SECTOR_RELATIVE_METRIC.get(sector, DEFAULT_RELATIVE_METRIC)

    return {
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "composite_fair_value": round(composite_fv, 2),
        "premium_discount_pct": round(premium_discount_pct, 1),
        "verdict": verdict,
        "verdict_color": verdict_color,
        "margin_of_safety": round(max(0, -premium_discount_pct), 1),
        "methods": methods,
        "num_methods_used": len(methods),
        "sector": sector,
        "north_star_metric": f"Quality-Adjusted {rel_metric['label']}",
    }


# ── Method 1: PEG-Based ───────────────────────────────────────────

def _peg_fair_value(data: dict) -> dict | None:
    """
    PEG = 1.0 means fairly valued. PEG < 1 = undervalued.
    Fair Value = EPS * Growth Rate (as PE multiple).
    Uses trailing earnings growth. Falls back to revenue growth.
    Caps fair PE at 40x to avoid extreme results.
    """
    price = data.get("currentPrice", 0)
    trailing_pe = data.get("trailingPE")
    forward_pe = data.get("forwardPE")

    pe = trailing_pe or forward_pe
    if not price or price <= 0 or not pe or pe <= 0 or pe > 500:
        return None

    eps = price / pe

    # Try multiple growth sources
    growth = None
    growth_source = None

    eg = data.get("earningsGrowth")
    if eg and isinstance(eg, (int, float)) and 0 < eg < 5:
        growth = float(eg)
        growth_source = "Trailing Earnings Growth"

    if growth is None:
        rg = data.get("revenueGrowth")
        if rg and isinstance(rg, (int, float)) and 0 < rg < 5:
            growth = float(rg)
            growth_source = "Revenue Growth"

    if growth is None:
        return None

    growth_pct = growth * 100

    # Fair PE = growth rate (PEG=1 rule), with floors and caps
    # Floor: even zero-growth companies deserve at least 8x
    # Cap: even 50%+ growers shouldn't get more than 40x from this alone
    fair_pe = max(8, min(growth_pct, 40))

    # Adjust for profitability: high-margin companies deserve PE premium
    op_margin = data.get("operatingMargins")
    if op_margin and isinstance(op_margin, (int, float)):
        if op_margin > 0.30:
            fair_pe *= 1.25  # 25% premium for exceptional margins
        elif op_margin > 0.20:
            fair_pe *= 1.15  # 15% premium
        elif op_margin < 0.05:
            fair_pe *= 0.85  # 15% discount for thin margins

    fair_value = eps * fair_pe
    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    actual_peg = pe / growth_pct if growth_pct > 0 else None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "eps": round(eps, 2),
            "growth_rate": f"{growth_pct:.1f}%",
            "growth_source": growth_source,
            "fair_pe": round(fair_pe, 1),
            "actual_pe": round(pe, 1),
            "actual_peg": round(actual_peg, 2) if actual_peg else "N/A",
            "margin_adjustment": "Yes" if op_margin and op_margin > 0.20 else "No",
            "method": "EPS * Margin-Adjusted Fair PE (PEG=1 baseline)",
        },
    }


# ── Method 2: Quality-Adjusted Relative ────────────────────────────

def _quality_adjusted_relative(data: dict, sector: str, scored_df: pd.DataFrame) -> dict | None:
    """
    Instead of comparing to sector MEDIAN, compare to the multiple that
    this company DESERVES based on its quality rank within the sector.

    A top-decile company (by growth + margins) is compared to the
    top-decile multiple in the sector. A bottom-quartile company
    is compared to the bottom-quartile multiple.

    This prevents penalizing NVDA for trading above the median tech P/S.
    """
    price = data.get("currentPrice", 0)
    if not price or price <= 0:
        return None

    rel_config = SECTOR_RELATIVE_METRIC.get(sector, DEFAULT_RELATIVE_METRIC)
    metric_key = rel_config["key"]
    metric_name = rel_config["name"]
    metric_label = rel_config["label"]

    # Get this stock's multiple
    stock_multiple = data.get(metric_key)
    if not stock_multiple or not isinstance(stock_multiple, (int, float)) or stock_multiple <= 0 or stock_multiple > 500:
        return None

    # Get all sector peers' data
    sector_stocks = scored_df[scored_df["sector"] == sector]
    if metric_key not in sector_stocks.columns:
        return None

    sector_multiples = pd.to_numeric(sector_stocks[metric_key], errors="coerce").dropna()
    sector_multiples = sector_multiples[(sector_multiples > 0) & (sector_multiples < 500)]

    if len(sector_multiples) < 5:
        return None

    # Compute this company's QUALITY percentile within sector
    quality_score = _compute_quality_percentile(data, sector, scored_df)

    # The company "deserves" a multiple at the same percentile as its quality
    # Quality percentile 90 -> deserves the 90th percentile multiple
    # Quality percentile 30 -> deserves the 30th percentile multiple
    deserved_multiple = sector_multiples.quantile(quality_score / 100)

    # For "lower is better" metrics (PE, EV/EBITDA), lower quality = higher deserved
    # For "higher is better" metrics... actually all these are "higher = more expensive"
    # So higher quality = deserves higher multiple

    # Compute fair value
    if metric_key in ["priceToSalesTrailing12Months"]:
        # P/S: fair_value = revenue_per_share * deserved_PS
        rev_per_share = price / stock_multiple
        fair_value = rev_per_share * deserved_multiple
    elif metric_key in ["priceToBook"]:
        # P/B: fair_value = book_per_share * deserved_PB
        book_per_share = price / stock_multiple
        fair_value = book_per_share * deserved_multiple
    elif metric_key in ["enterpriseToEbitda"]:
        # EV/EBITDA: approximate fair_value = price * (deserved / actual)
        fair_value = price * (deserved_multiple / stock_multiple)
    elif metric_key in ["trailingPE", "forwardPE"]:
        # P/E: fair_value = EPS * deserved_PE
        eps = price / stock_multiple
        fair_value = eps * deserved_multiple
    else:
        fair_value = price * (deserved_multiple / stock_multiple)

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "metric_label": metric_label,
        "assumptions": {
            f"your_{metric_name}": round(stock_multiple, 1),
            f"deserved_{metric_name}": round(deserved_multiple, 1),
            "sector_median": round(sector_multiples.median(), 1),
            "quality_percentile": round(quality_score, 0),
            "peer_count": len(sector_multiples),
            "method": f"Company deserves {round(quality_score)}th percentile {metric_name} based on growth+margins rank",
        },
    }


def _compute_quality_percentile(data: dict, sector: str, scored_df: pd.DataFrame) -> float:
    """
    Compute a company's quality percentile within its sector.
    Based on: revenue growth, earnings growth, operating margin, ROE.
    Returns 0-100 percentile (100 = best quality in sector).
    """
    sector_stocks = scored_df[scored_df["sector"] == sector]
    if len(sector_stocks) < 5:
        return 50  # Default to median if too few peers

    quality_metrics = ["revenueGrowth", "earningsGrowth", "operatingMargins", "returnOnEquity"]
    percentiles = []

    for qm in quality_metrics:
        if qm not in sector_stocks.columns:
            continue

        col = pd.to_numeric(sector_stocks[qm], errors="coerce").dropna()
        if len(col) < 5:
            continue

        stock_val = data.get(qm)
        if stock_val is None or not isinstance(stock_val, (int, float)) or not np.isfinite(stock_val):
            continue

        # What percentile is this stock at for this metric?
        pct = (col < stock_val).sum() / len(col) * 100
        percentiles.append(pct)

    if not percentiles:
        return 50

    # Average quality percentile across all available metrics
    return np.mean(percentiles)


# ── Method 3: Trailing Earnings Capitalization ─────────────────────

def _trailing_earnings_value(data: dict, sector: str, scored_df: pd.DataFrame) -> dict | None:
    """
    What PE does this company deserve based on its quality?
    Uses sector PE distribution + company quality rank.
    """
    price = data.get("currentPrice", 0)
    trailing_pe = data.get("trailingPE")

    if not price or price <= 0 or not trailing_pe or trailing_pe <= 0 or trailing_pe > 500:
        return None

    eps = price / trailing_pe

    # Get sector PE distribution
    sector_stocks = scored_df[scored_df["sector"] == sector]
    if "trailingPE" not in sector_stocks.columns or len(sector_stocks) < 5:
        # Fallback: quality-based fixed PE
        return _trailing_fallback(data, eps, trailing_pe, price)

    sector_pe = pd.to_numeric(sector_stocks["trailingPE"], errors="coerce").dropna()
    sector_pe = sector_pe[(sector_pe > 0) & (sector_pe < 200)]

    if len(sector_pe) < 5:
        return _trailing_fallback(data, eps, trailing_pe, price)

    # Quality-adjusted: this company deserves a PE at its quality percentile
    quality_pct = _compute_quality_percentile(data, sector, scored_df)
    deserved_pe = sector_pe.quantile(quality_pct / 100)

    fair_value = eps * deserved_pe

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "trailing_eps": round(eps, 2),
            "actual_pe": round(trailing_pe, 1),
            "deserved_pe": round(deserved_pe, 1),
            "quality_percentile": round(quality_pct, 0),
            "sector_median_pe": round(sector_pe.median(), 1),
            "method": "EPS * Quality-Adjusted Sector PE",
        },
    }


def _trailing_fallback(data, eps, trailing_pe, price):
    """Fallback when sector PE data is insufficient."""
    roe = data.get("returnOnEquity")
    op_margin = data.get("operatingMargins")

    q = 0
    if roe and isinstance(roe, (int, float)):
        if roe > 0.25: q += 3
        elif roe > 0.15: q += 2
        elif roe > 0.08: q += 1
    if op_margin and isinstance(op_margin, (int, float)):
        if op_margin > 0.25: q += 3
        elif op_margin > 0.15: q += 2
        elif op_margin > 0.08: q += 1

    if q >= 5: fair_pe = 28
    elif q >= 3: fair_pe = 22
    elif q >= 1: fair_pe = 16
    else: fair_pe = 12

    fair_value = eps * fair_pe
    if fair_value <= 0 or not np.isfinite(fair_value): return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "trailing_eps": round(eps, 2),
            "quality_score": q,
            "quality_fair_pe": round(fair_pe, 1),
            "method": "EPS * Quality-Based PE (fallback)",
        },
    }


# ── Method 4: Analyst Target ──────────────────────────────────────

def _analyst_target(data: dict) -> dict | None:
    """Analyst consensus 12-month target."""
    price = data.get("currentPrice", 0)
    upside = data.get("analyst_mean_target_upside")
    count = data.get("analyst_count", 0)

    if not price or price <= 0 or upside is None:
        return None

    target = price * (1 + float(upside))
    if target <= 0 or not np.isfinite(target):
        return None

    return {
        "fair_value": round(target, 2),
        "premium_discount_pct": round((price / target - 1) * 100, 1),
        "assumptions": {
            "analyst_target": round(target, 2),
            "implied_upside": f"{float(upside)*100:+.1f}%",
            "num_analysts": count,
            "method": f"Consensus of {count} analysts",
        },
    }


# ── Portfolio Batch ────────────────────────────────────────────────

def compute_portfolio_fair_values(holdings_df: pd.DataFrame, scored_df: pd.DataFrame) -> pd.DataFrame:
    results = []
    for _, row in holdings_df.iterrows():
        ticker = row.get("ticker", "")
        fv = compute_fair_value(ticker, scored_df)
        if "error" not in fv:
            results.append({
                "ticker": ticker, "current_price": fv["current_price"],
                "fair_value": fv["composite_fair_value"],
                "premium_discount": fv["premium_discount_pct"],
                "verdict": fv["verdict"], "methods_used": fv["num_methods_used"],
            })
        else:
            results.append({
                "ticker": ticker, "current_price": row.get("price", 0),
                "fair_value": None, "premium_discount": None,
                "verdict": "N/A", "methods_used": 0,
            })
    return pd.DataFrame(results)
