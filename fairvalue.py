"""
Fair Value Estimator - Sector-Specific Approach.
Each sector uses its "north star" valuation metric as the primary method.

Sector North Stars:
- Technology/Growth:     Price-to-Sales (P/S) ratio vs sector median
- Financial Services:    Price-to-Book (P/B) ratio vs sector median
- Energy:               EV/EBITDA vs sector median
- Utilities:            EV/EBITDA vs sector median
- Industrials:          EV/EBITDA vs sector median
- Real Estate:          Price-to-Book (P/B) as proxy for P/FFO
- Healthcare:           P/E with growth adjustment
- Consumer Cyclical:    P/E vs sector median
- Consumer Defensive:   P/E vs sector median
- Communication:        P/S ratio vs sector median (many high-growth)
- Materials:            EV/EBITDA vs sector median
- Basic Materials:      EV/EBITDA vs sector median

Methods (weighted by sector):
1. Sector North Star (40-50% weight) - sector-appropriate primary metric
2. Graham Number (15%) - classic value
3. Trailing Earnings Capitalization (15-25%) - quality-adjusted
4. Analyst Target (10-15%) - forward-looking, weighted lowest
5. PEG-Based (0-15%) - only for growth sectors
"""

import numpy as np
import pandas as pd


# ── Sector Configuration ───────────────────────────────────────────

SECTOR_CONFIG = {
    "Technology": {
        "north_star": "ps_relative",
        "north_star_name": "Price/Sales vs Sector Median",
        "weights": {"north_star": 0.40, "trailing_cap": 0.15, "graham": 0.15, "peg": 0.15, "analyst": 0.15},
    },
    "Communication Services": {
        "north_star": "ps_relative",
        "north_star_name": "Price/Sales vs Sector Median",
        "weights": {"north_star": 0.40, "trailing_cap": 0.15, "graham": 0.15, "peg": 0.15, "analyst": 0.15},
    },
    "Financial Services": {
        "north_star": "pb_relative",
        "north_star_name": "Price/Book vs Sector Median",
        "weights": {"north_star": 0.45, "trailing_cap": 0.20, "graham": 0.20, "peg": 0.0, "analyst": 0.15},
    },
    "Energy": {
        "north_star": "ev_ebitda_relative",
        "north_star_name": "EV/EBITDA vs Sector Median",
        "weights": {"north_star": 0.45, "trailing_cap": 0.20, "graham": 0.15, "peg": 0.0, "analyst": 0.20},
    },
    "Utilities": {
        "north_star": "ev_ebitda_relative",
        "north_star_name": "EV/EBITDA vs Sector Median",
        "weights": {"north_star": 0.45, "trailing_cap": 0.20, "graham": 0.20, "peg": 0.0, "analyst": 0.15},
    },
    "Industrials": {
        "north_star": "ev_ebitda_relative",
        "north_star_name": "EV/EBITDA vs Sector Median",
        "weights": {"north_star": 0.40, "trailing_cap": 0.20, "graham": 0.15, "peg": 0.10, "analyst": 0.15},
    },
    "Real Estate": {
        "north_star": "pb_relative",
        "north_star_name": "Price/Book vs Sector Median (proxy for P/FFO)",
        "weights": {"north_star": 0.45, "trailing_cap": 0.15, "graham": 0.20, "peg": 0.0, "analyst": 0.20},
    },
    "Healthcare": {
        "north_star": "pe_relative",
        "north_star_name": "P/E vs Sector Median",
        "weights": {"north_star": 0.35, "trailing_cap": 0.20, "graham": 0.15, "peg": 0.15, "analyst": 0.15},
    },
    "Consumer Cyclical": {
        "north_star": "pe_relative",
        "north_star_name": "P/E vs Sector Median",
        "weights": {"north_star": 0.35, "trailing_cap": 0.20, "graham": 0.15, "peg": 0.15, "analyst": 0.15},
    },
    "Consumer Defensive": {
        "north_star": "pe_relative",
        "north_star_name": "P/E vs Sector Median",
        "weights": {"north_star": 0.40, "trailing_cap": 0.25, "graham": 0.15, "peg": 0.0, "analyst": 0.20},
    },
    "Basic Materials": {
        "north_star": "ev_ebitda_relative",
        "north_star_name": "EV/EBITDA vs Sector Median",
        "weights": {"north_star": 0.40, "trailing_cap": 0.20, "graham": 0.15, "peg": 0.10, "analyst": 0.15},
    },
}

# Default for unknown sectors
DEFAULT_CONFIG = {
    "north_star": "pe_relative",
    "north_star_name": "P/E vs Sector Median",
    "weights": {"north_star": 0.35, "trailing_cap": 0.20, "graham": 0.15, "peg": 0.15, "analyst": 0.15},
}


def compute_fair_value(ticker: str, scored_df: pd.DataFrame, raw_cache: dict = None) -> dict:
    """
    Compute CURRENT fair value using sector-specific primary metrics.
    The sector's north star metric gets the highest weight.
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
    config = SECTOR_CONFIG.get(sector, DEFAULT_CONFIG)
    methods = {}

    # Method 1: Sector North Star (highest weight)
    ns_method = config["north_star"]
    ns_result = None

    if ns_method == "ps_relative":
        ns_result = _ps_relative(data, sector, scored_df)
    elif ns_method == "pb_relative":
        ns_result = _pb_relative(data, sector, scored_df)
    elif ns_method == "ev_ebitda_relative":
        ns_result = _ev_ebitda_relative(data, sector, scored_df)
    elif ns_method == "pe_relative":
        ns_result = _pe_relative(data, sector, scored_df)

    if ns_result:
        ns_result["is_north_star"] = True
        ns_result["north_star_label"] = config["north_star_name"]
        methods[f"Sector Primary: {config['north_star_name']}"] = ns_result

    # Method 2: Trailing Earnings Capitalization
    trailing = _trailing_earnings_value(data)
    if trailing:
        methods["Trailing Earnings Value"] = trailing

    # Method 3: Graham Number
    graham = _graham_number(data)
    if graham:
        methods["Graham Number"] = graham

    # Method 4: PEG-Based (only if weight > 0)
    if config["weights"]["peg"] > 0:
        peg_val = _peg_fair_value(data)
        if peg_val:
            methods["PEG Fair Value"] = peg_val

    # Method 5: Analyst Target
    analyst = _analyst_target(data)
    if analyst:
        methods["Analyst Target"] = analyst

    if not methods:
        return {
            "ticker": ticker,
            "current_price": current_price,
            "error": "Insufficient data for fair value calculation.",
            "methods": {},
        }

    # ── Weighted Composite ─────────────────────────────────────────
    # Map method names to weight keys
    method_to_weight_key = {}
    for mname in methods:
        if "Sector Primary" in mname:
            method_to_weight_key[mname] = "north_star"
        elif "Trailing" in mname:
            method_to_weight_key[mname] = "trailing_cap"
        elif "Graham" in mname:
            method_to_weight_key[mname] = "graham"
        elif "PEG" in mname:
            method_to_weight_key[mname] = "peg"
        elif "Analyst" in mname:
            method_to_weight_key[mname] = "analyst"

    weights = config["weights"]
    weighted_sum = 0
    total_weight = 0

    for mname, mdata in methods.items():
        fv = mdata.get("fair_value", 0)
        wkey = method_to_weight_key.get(mname, "trailing_cap")
        w = weights.get(wkey, 0.10)

        if fv and fv > 0 and np.isfinite(fv):
            ratio = fv / current_price
            if 0.05 < ratio < 10.0:
                weighted_sum += fv * w
                total_weight += w

    composite_fv = weighted_sum / total_weight if total_weight > 0 else 0

    if composite_fv > 0:
        premium_discount_pct = ((current_price - composite_fv) / composite_fv) * 100
    else:
        premium_discount_pct = 0

    if premium_discount_pct < -30:
        verdict = "Deeply Undervalued"
        verdict_color = "#00C805"
    elif premium_discount_pct < -10:
        verdict = "Undervalued"
        verdict_color = "#8BC34A"
    elif premium_discount_pct < 15:
        verdict = "Fairly Valued"
        verdict_color = "#FFC107"
    elif premium_discount_pct < 35:
        verdict = "Overvalued"
        verdict_color = "#FF5722"
    else:
        verdict = "Significantly Overvalued"
        verdict_color = "#D32F2F"

    margin_of_safety = max(0, -premium_discount_pct)

    return {
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "composite_fair_value": round(composite_fv, 2),
        "premium_discount_pct": round(premium_discount_pct, 1),
        "verdict": verdict,
        "verdict_color": verdict_color,
        "margin_of_safety": round(margin_of_safety, 1),
        "methods": methods,
        "num_methods_used": len(methods),
        "sector": sector,
        "north_star_metric": config["north_star_name"],
    }


# ── North Star Methods ─────────────────────────────────────────────


def _ps_relative(data: dict, sector: str, scored_df: pd.DataFrame) -> dict | None:
    """Price-to-Sales vs sector median. Best for Tech/Growth/Comms."""
    price = data.get("currentPrice", 0)
    ps = data.get("priceToSalesTrailing12Months")

    if not price or price <= 0 or not ps or ps <= 0 or ps > 200:
        return None

    sector_stocks = scored_df[scored_df["sector"] == sector]
    if "priceToSalesTrailing12Months" not in sector_stocks.columns:
        return None

    sector_ps = pd.to_numeric(sector_stocks["priceToSalesTrailing12Months"], errors="coerce").dropna()
    sector_ps = sector_ps[(sector_ps > 0) & (sector_ps < 200)]

    if len(sector_ps) < 5:
        return None

    median_ps = sector_ps.median()
    revenue_per_share = price / ps
    fair_value = revenue_per_share * median_ps

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "revenue_per_share": round(revenue_per_share, 2),
            "your_ps": round(ps, 1),
            "sector_median_ps": round(median_ps, 1),
            "peer_count": len(sector_ps),
            "method": "Revenue/Share * Sector Median P/S",
        },
    }


def _pb_relative(data: dict, sector: str, scored_df: pd.DataFrame) -> dict | None:
    """Price-to-Book vs sector median. Best for Financials/Real Estate."""
    price = data.get("currentPrice", 0)
    pb = data.get("priceToBook")

    if not price or price <= 0 or not pb or pb <= 0 or pb > 100:
        return None

    sector_stocks = scored_df[scored_df["sector"] == sector]
    if "priceToBook" not in sector_stocks.columns:
        return None

    sector_pb = pd.to_numeric(sector_stocks["priceToBook"], errors="coerce").dropna()
    sector_pb = sector_pb[(sector_pb > 0) & (sector_pb < 100)]

    if len(sector_pb) < 5:
        return None

    median_pb = sector_pb.median()
    bvps = price / pb
    fair_value = bvps * median_pb

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "book_value_per_share": round(bvps, 2),
            "your_pb": round(pb, 1),
            "sector_median_pb": round(median_pb, 1),
            "peer_count": len(sector_pb),
            "method": "BVPS * Sector Median P/B",
        },
    }


def _ev_ebitda_relative(data: dict, sector: str, scored_df: pd.DataFrame) -> dict | None:
    """EV/EBITDA vs sector median. Best for Energy/Utilities/Industrials/Materials."""
    price = data.get("currentPrice", 0)
    ev_ebitda = data.get("enterpriseToEbitda")

    if not price or price <= 0 or not ev_ebitda or ev_ebitda <= 0 or ev_ebitda > 200:
        return None

    sector_stocks = scored_df[scored_df["sector"] == sector]
    if "enterpriseToEbitda" not in sector_stocks.columns:
        return None

    sector_ev = pd.to_numeric(sector_stocks["enterpriseToEbitda"], errors="coerce").dropna()
    sector_ev = sector_ev[(sector_ev > 0) & (sector_ev < 200)]

    if len(sector_ev) < 5:
        return None

    median_ev = sector_ev.median()

    # EV/EBITDA implies: fair EV = EBITDA * median multiple
    # But we need share price, not EV. Approximate:
    # If stock's EV/EBITDA is X and sector median is Y,
    # fair price ~ price * (Y / X)
    fair_value = price * (median_ev / ev_ebitda)

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "your_ev_ebitda": round(ev_ebitda, 1),
            "sector_median_ev_ebitda": round(median_ev, 1),
            "peer_count": len(sector_ev),
            "method": "Price * (Sector Median EV/EBITDA / Your EV/EBITDA)",
        },
    }


def _pe_relative(data: dict, sector: str, scored_df: pd.DataFrame) -> dict | None:
    """P/E vs sector median. Default for Healthcare/Consumer/Unknown sectors."""
    price = data.get("currentPrice", 0)
    trailing_pe = data.get("trailingPE")

    if not price or price <= 0 or not trailing_pe or trailing_pe <= 0 or trailing_pe > 200:
        return None

    sector_stocks = scored_df[scored_df["sector"] == sector]
    if "trailingPE" not in sector_stocks.columns:
        return None

    sector_pe = pd.to_numeric(sector_stocks["trailingPE"], errors="coerce").dropna()
    sector_pe = sector_pe[(sector_pe > 0) & (sector_pe < 200)]

    if len(sector_pe) < 5:
        return None

    median_pe = sector_pe.median()
    eps = price / trailing_pe
    fair_value = eps * median_pe

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "trailing_eps": round(eps, 2),
            "your_trailing_pe": round(trailing_pe, 1),
            "sector_median_trailing_pe": round(median_pe, 1),
            "peer_count": len(sector_pe),
            "method": "Trailing EPS * Sector Median Trailing PE",
        },
    }


# ── Supporting Methods ─────────────────────────────────────────────


def _trailing_earnings_value(data: dict) -> dict | None:
    """
    Capitalize trailing earnings at quality-adjusted multiple.
    High ROE + high margins = higher deserved PE.
    """
    price = data.get("currentPrice", 0)
    trailing_pe = data.get("trailingPE")

    if not price or price <= 0 or not trailing_pe or trailing_pe <= 0 or trailing_pe > 200:
        return None

    eps = price / trailing_pe

    roe = data.get("returnOnEquity")
    op_margin = data.get("operatingMargins")

    quality_score = 0
    if roe and isinstance(roe, (int, float)):
        if roe > 0.30: quality_score += 3
        elif roe > 0.20: quality_score += 2
        elif roe > 0.12: quality_score += 1
        elif roe < 0.05: quality_score -= 1

    if op_margin and isinstance(op_margin, (int, float)):
        if op_margin > 0.25: quality_score += 3
        elif op_margin > 0.15: quality_score += 2
        elif op_margin > 0.08: quality_score += 1
        elif op_margin < 0.03: quality_score -= 1

    # Quality-adjusted PE (no growth assumption)
    if quality_score >= 5:
        fair_pe = 25  # Elite business (AAPL, MSFT quality)
    elif quality_score >= 3:
        fair_pe = 20  # High quality
    elif quality_score >= 1:
        fair_pe = 16  # Decent
    elif quality_score >= 0:
        fair_pe = 13  # Average
    else:
        fair_pe = 10  # Low quality

    fair_value = eps * fair_pe

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "trailing_eps": round(eps, 2),
            "quality_score": quality_score,
            "quality_fair_pe": round(fair_pe, 1),
            "actual_trailing_pe": round(trailing_pe, 1),
            "method": "Trailing EPS * Quality-adjusted PE",
        },
    }


def _graham_number(data: dict) -> dict | None:
    """Graham Number = sqrt(22.5 * EPS * BVPS). Trailing data only."""
    price = data.get("currentPrice", 0)
    trailing_pe = data.get("trailingPE")
    price_to_book = data.get("priceToBook")

    if not price or price <= 0 or not trailing_pe or trailing_pe <= 0:
        return None
    if not price_to_book or price_to_book <= 0:
        return None

    eps = price / trailing_pe
    bvps = price / price_to_book

    if eps <= 0 or bvps <= 0:
        return None

    graham = np.sqrt(22.5 * eps * bvps)

    if not np.isfinite(graham) or graham <= 0:
        return None

    return {
        "fair_value": round(graham, 2),
        "premium_discount_pct": round((price / graham - 1) * 100, 1),
        "assumptions": {
            "trailing_eps": round(eps, 2),
            "book_value_per_share": round(bvps, 2),
            "method": "sqrt(22.5 * EPS * BVPS)",
        },
    }


def _peg_fair_value(data: dict) -> dict | None:
    """PEG-Based using trailing growth. PEG=1 rule."""
    price = data.get("currentPrice", 0)
    trailing_pe = data.get("trailingPE")
    earnings_growth = data.get("earningsGrowth")

    if not price or price <= 0 or not trailing_pe or trailing_pe <= 0:
        return None
    if not earnings_growth or not isinstance(earnings_growth, (int, float)):
        return None
    if earnings_growth <= 0 or earnings_growth > 5:
        return None

    growth_pct = float(earnings_growth) * 100
    if growth_pct <= 0 or growth_pct > 100:
        return None

    eps = price / trailing_pe
    fair_pe = min(growth_pct, 35)
    fair_value = eps * fair_pe

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "trailing_eps": round(eps, 2),
            "trailing_growth": f"{growth_pct:.1f}%",
            "fair_pe_at_peg1": round(fair_pe, 1),
            "method": "EPS * min(Growth%, 35) -- PEG=1 rule",
        },
    }


def _analyst_target(data: dict) -> dict | None:
    """Analyst consensus 12-month target. Forward-looking, weighted lowest."""
    price = data.get("currentPrice", 0)
    upside = data.get("analyst_mean_target_upside")

    if not price or price <= 0 or upside is None:
        return None

    target = price * (1 + float(upside))

    if target <= 0 or not np.isfinite(target):
        return None

    return {
        "fair_value": round(target, 2),
        "premium_discount_pct": round((price / target - 1) * 100, 1),
        "assumptions": {
            "analyst_12mo_target": round(target, 2),
            "implied_upside": f"{float(upside)*100:+.1f}%",
            "num_analysts": data.get("analyst_count", 0),
            "method": "Analyst consensus (forward-looking, lowest weight)",
        },
    }


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
