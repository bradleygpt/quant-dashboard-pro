"""
Fair Value Estimator module.
Computes multiple fair value estimates and a composite intrinsic value.

Methods:
1. DCF (Discounted Cash Flow) - forward earnings based
2. Graham Number - classic value formula
3. PEG-Based Fair Value - growth-adjusted P/E
4. Relative Valuation - vs sector peer median multiples
5. Analyst Target - consensus price target

Composite: weighted average of available methods.
"""

import numpy as np
import pandas as pd
from config import PILLAR_METRICS


def compute_fair_value(ticker: str, scored_df: pd.DataFrame, raw_cache: dict = None) -> dict:
    """
    Compute fair value for a single stock using multiple methods.
    Returns dict with each method's estimate, composite, and premium/discount.
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

    # ── Method 1: Earnings-Based DCF ───────────────────────────────
    dcf = _dcf_valuation(data)
    if dcf:
        methods["DCF (Earnings-Based)"] = dcf

    # ── Method 2: Graham Number ────────────────────────────────────
    graham = _graham_number(data)
    if graham:
        methods["Graham Number"] = graham

    # ── Method 3: PEG-Based Fair Value ─────────────────────────────
    peg_val = _peg_fair_value(data)
    if peg_val:
        methods["PEG Fair Value"] = peg_val

    # ── Method 4: Relative Valuation (vs Sector) ──────────────────
    relative = _relative_valuation(data, sector, scored_df)
    if relative:
        methods["Sector Relative"] = relative

    # ── Method 5: Analyst Consensus Target ─────────────────────────
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

    # ── Composite Fair Value ───────────────────────────────────────
    # Weight each method and average
    method_weights = {
        "DCF (Earnings-Based)": 0.30,
        "Graham Number": 0.15,
        "PEG Fair Value": 0.20,
        "Sector Relative": 0.20,
        "Analyst Target": 0.15,
    }

    weighted_sum = 0
    total_weight = 0
    for method_name, method_data in methods.items():
        fv = method_data.get("fair_value", 0)
        w = method_weights.get(method_name, 0.10)
        if fv and fv > 0 and np.isfinite(fv):
            # Sanity check: skip if fair value is more than 5x or less than 0.1x current price
            ratio = fv / current_price
            if 0.1 < ratio < 5.0:
                weighted_sum += fv * w
                total_weight += w

    composite_fv = weighted_sum / total_weight if total_weight > 0 else 0

    # Premium/Discount
    if composite_fv > 0:
        premium_discount_pct = ((current_price - composite_fv) / composite_fv) * 100
    else:
        premium_discount_pct = 0

    # Verdict
    if premium_discount_pct < -25:
        verdict = "Deeply Undervalued"
        verdict_color = "#00C805"
    elif premium_discount_pct < -10:
        verdict = "Undervalued"
        verdict_color = "#8BC34A"
    elif premium_discount_pct < 10:
        verdict = "Fairly Valued"
        verdict_color = "#FFC107"
    elif premium_discount_pct < 25:
        verdict = "Overvalued"
        verdict_color = "#FF5722"
    else:
        verdict = "Significantly Overvalued"
        verdict_color = "#D32F2F"

    # Margin of safety (how much discount from fair value)
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
    }


# ── Valuation Methods ──────────────────────────────────────────────


def _dcf_valuation(data: dict) -> dict | None:
    """
    Simplified DCF using forward earnings.
    Fair Value = EPS * (1 + growth_rate)^5 * terminal_PE / (1 + discount_rate)^5
    """
    forward_pe = data.get("forwardPE")
    trailing_pe = data.get("trailingPE")
    price = data.get("currentPrice", 0)
    earnings_growth = data.get("earningsGrowth") or data.get("revenueGrowth")

    if not price or price <= 0:
        return None

    # Estimate EPS
    pe = forward_pe or trailing_pe
    if not pe or pe <= 0 or pe > 200:
        return None
    eps = price / pe

    # Growth rate
    if earnings_growth and abs(earnings_growth) < 5:
        growth = float(earnings_growth)
    else:
        growth = 0.08  # default 8%

    # Clamp growth to reasonable range
    growth = max(-0.10, min(growth, 0.40))

    # Terminal PE (mean-revert toward 15-18x)
    if pe > 25:
        terminal_pe = min(pe * 0.85, 22)
    elif pe < 10:
        terminal_pe = max(pe * 1.15, 12)
    else:
        terminal_pe = pe * 0.95

    # Discount rate (10% for equities)
    discount_rate = 0.10

    # Project 5-year earnings
    future_eps = eps * (1 + growth) ** 5
    terminal_value = future_eps * terminal_pe
    fair_value = terminal_value / (1 + discount_rate) ** 5

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "current_eps": round(eps, 2),
            "growth_rate": f"{growth*100:.1f}%",
            "terminal_pe": round(terminal_pe, 1),
            "discount_rate": "10%",
            "projection_years": 5,
        },
    }


def _graham_number(data: dict) -> dict | None:
    """
    Graham Number = sqrt(22.5 * EPS * Book Value Per Share)
    Classic Benjamin Graham formula for intrinsic value.
    """
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
            "eps": round(eps, 2),
            "book_value_per_share": round(bvps, 2),
            "multiplier": 22.5,
        },
    }


def _peg_fair_value(data: dict) -> dict | None:
    """
    PEG-Based Fair Value.
    If PEG = 1.0 is fair, then Fair PE = Growth Rate * 100.
    Fair Value = EPS * Fair PE.
    """
    price = data.get("currentPrice", 0)
    forward_pe = data.get("forwardPE") or data.get("trailingPE")
    earnings_growth = data.get("earningsGrowth") or data.get("revenueGrowth")

    if not price or price <= 0 or not forward_pe or forward_pe <= 0:
        return None
    if not earnings_growth or earnings_growth <= 0:
        return None

    growth_pct = float(earnings_growth) * 100  # Convert to percentage
    if growth_pct <= 0 or growth_pct > 100:
        return None

    eps = price / forward_pe

    # Fair PE = growth rate (PEG = 1.0 rule)
    # But cap at 30x to avoid extreme valuations for high-growth stocks
    fair_pe = min(growth_pct, 30)
    fair_value = eps * fair_pe

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "eps": round(eps, 2),
            "growth_rate": f"{growth_pct:.1f}%",
            "fair_pe_at_peg1": round(fair_pe, 1),
            "current_pe": round(forward_pe, 1),
        },
    }


def _relative_valuation(data: dict, sector: str, scored_df: pd.DataFrame) -> dict | None:
    """
    Relative Valuation vs sector peers.
    Uses median Forward P/E of sector to estimate fair value.
    """
    price = data.get("currentPrice", 0)
    forward_pe = data.get("forwardPE")

    if not price or price <= 0 or not forward_pe or forward_pe <= 0:
        return None

    # Get sector median P/E
    sector_stocks = scored_df[scored_df["sector"] == sector]
    if "forwardPE" not in sector_stocks.columns:
        return None

    sector_pe = pd.to_numeric(sector_stocks["forwardPE"], errors="coerce").dropna()
    # Filter outliers
    sector_pe = sector_pe[(sector_pe > 0) & (sector_pe < 200)]

    if len(sector_pe) < 5:
        return None

    median_pe = sector_pe.median()
    eps = price / forward_pe
    fair_value = eps * median_pe

    if fair_value <= 0 or not np.isfinite(fair_value):
        return None

    return {
        "fair_value": round(fair_value, 2),
        "premium_discount_pct": round((price / fair_value - 1) * 100, 1),
        "assumptions": {
            "eps": round(eps, 2),
            "your_pe": round(forward_pe, 1),
            "sector_median_pe": round(median_pe, 1),
            "sector": sector,
            "peer_count": len(sector_pe),
        },
    }


def _analyst_target(data: dict) -> dict | None:
    """Use analyst consensus mean price target."""
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
            "analyst_target": round(target, 2),
            "upside_pct": f"{float(upside)*100:+.1f}%",
            "num_analysts": data.get("analyst_count", 0),
        },
    }


# ── Batch Fair Value for Portfolio ─────────────────────────────────


def compute_portfolio_fair_values(holdings_df: pd.DataFrame, scored_df: pd.DataFrame) -> pd.DataFrame:
    """Compute fair values for all holdings in a portfolio."""
    results = []

    for _, row in holdings_df.iterrows():
        ticker = row.get("ticker", "")
        fv = compute_fair_value(ticker, scored_df)

        if "error" not in fv:
            results.append({
                "ticker": ticker,
                "current_price": fv["current_price"],
                "fair_value": fv["composite_fair_value"],
                "premium_discount": fv["premium_discount_pct"],
                "verdict": fv["verdict"],
                "methods_used": fv["num_methods_used"],
            })
        else:
            results.append({
                "ticker": ticker,
                "current_price": row.get("price", 0),
                "fair_value": None,
                "premium_discount": None,
                "verdict": "N/A",
                "methods_used": 0,
            })

    return pd.DataFrame(results)
