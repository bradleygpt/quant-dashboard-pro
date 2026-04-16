"""
Fair Value Estimator v4 - Calibrated.

Fixes from v3:
- Capped quality-adjusted PE at 35x max (prevents 100x+ PE for tech)
- Capped PEG fair PE at 30x (prevents extreme growth premium)
- Reduced margin premium from 25% to 10%
- Widened Fairly Valued band to -15% to +25%
- All methods use TRAILING data only

Methods:
1. PEG-Based (30%) - trailing growth, capped
2. Quality-Adjusted Relative (25%) - sector metric, capped
3. Trailing Earnings Capitalization (25%) - quality-adjusted PE, capped
4. Analyst Consensus (20%) - forward-looking, highest weight of any version

No Graham Number. No DCF projection.
"""

import numpy as np
import pandas as pd

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
    if ticker not in scored_df.index:
        if raw_cache and ticker in raw_cache: data = raw_cache[ticker]
        else: return {"error": "Ticker not found."}
    else: data = scored_df.loc[ticker].to_dict()

    price = data.get("currentPrice", 0)
    if not price or price <= 0: return {"error": "No price data."}

    sector = data.get("sector", "Unknown")
    methods = {}

    r1 = _peg_fair_value(data)
    if r1: methods["PEG Fair Value"] = r1

    r2 = _quality_adjusted_relative(data, sector, scored_df)
    if r2: methods[f"Quality-Adj {r2.get('_label', 'Relative')}"] = r2

    r3 = _trailing_earnings_cap(data, sector, scored_df)
    if r3: methods["Earnings Capitalization"] = r3

    r4 = _analyst_target(data)
    if r4: methods["Analyst Consensus"] = r4

    if not methods:
        return {"ticker": ticker, "current_price": price, "error": "Insufficient data.", "methods": {}}

    weights = {"PEG Fair Value": 0.30, "Earnings Capitalization": 0.25, "Analyst Consensus": 0.20}
    for mn in methods:
        if "Quality-Adj" in mn: weights[mn] = 0.25

    wsum = 0; tw = 0
    for mn, md in methods.items():
        fv = md.get("fair_value", 0)
        w = weights.get(mn, 0.15)
        if fv and fv > 0 and np.isfinite(fv):
            ratio = fv / price
            if 0.2 < ratio < 3.0:  # Tighter sanity bounds
                wsum += fv * w; tw += w

    composite = wsum / tw if tw > 0 else 0
    pd_pct = ((price - composite) / composite * 100) if composite > 0 else 0

    # Wider bands: Fairly Valued from -15% to +25%
    if pd_pct < -30: verdict, vc = "Deeply Undervalued", "#00C805"
    elif pd_pct < -15: verdict, vc = "Undervalued", "#8BC34A"
    elif pd_pct < 25: verdict, vc = "Fairly Valued", "#FFC107"
    elif pd_pct < 50: verdict, vc = "Overvalued", "#FF5722"
    else: verdict, vc = "Significantly Overvalued", "#D32F2F"

    rel = SECTOR_RELATIVE_METRIC.get(sector, DEFAULT_RELATIVE_METRIC)
    return {
        "ticker": ticker, "current_price": round(price, 2),
        "composite_fair_value": round(composite, 2),
        "premium_discount_pct": round(pd_pct, 1),
        "verdict": verdict, "verdict_color": vc,
        "margin_of_safety": round(max(0, -pd_pct), 1),
        "methods": methods, "num_methods_used": len(methods),
        "sector": sector, "north_star_metric": f"Quality-Adjusted {rel['label']}",
    }


def _peg_fair_value(data: dict) -> dict | None:
    """PEG=1 rule. Fair PE = growth rate. Capped at 30x. Margin bonus capped at 10%."""
    price = data.get("currentPrice", 0)
    pe = data.get("trailingPE") or data.get("forwardPE")
    if not price or price <= 0 or not pe or pe <= 0 or pe > 500: return None
    eps = price / pe

    growth = None; gsrc = None
    eg = data.get("earningsGrowth")
    if eg and isinstance(eg, (int, float)) and 0 < eg < 5:
        growth = float(eg); gsrc = "Earnings Growth"
    if growth is None:
        rg = data.get("revenueGrowth")
        if rg and isinstance(rg, (int, float)) and 0 < rg < 5:
            growth = float(rg); gsrc = "Revenue Growth"
    if growth is None: return None

    gpct = growth * 100
    # Fair PE: floor 8x, cap 30x
    fair_pe = max(8, min(gpct, 30))

    # Small margin bonus: max 10%
    om = data.get("operatingMargins")
    if om and isinstance(om, (int, float)) and om > 0.25:
        fair_pe *= 1.10

    fv = eps * fair_pe
    if fv <= 0 or not np.isfinite(fv): return None

    return {
        "fair_value": round(fv, 2),
        "premium_discount_pct": round((price / fv - 1) * 100, 1),
        "assumptions": {
            "eps": round(eps, 2), "growth": f"{gpct:.1f}%", "source": gsrc,
            "fair_pe": round(fair_pe, 1), "actual_pe": round(pe, 1),
            "method": "EPS * min(Growth%, 30) with margin adj",
        },
    }


def _quality_adjusted_relative(data: dict, sector: str, scored_df: pd.DataFrame) -> dict | None:
    """Compare to the multiple this company DESERVES, but capped at 75th percentile."""
    price = data.get("currentPrice", 0)
    if not price or price <= 0: return None

    cfg = SECTOR_RELATIVE_METRIC.get(sector, DEFAULT_RELATIVE_METRIC)
    mk = cfg["key"]; mn = cfg["name"]; ml = cfg["label"]

    stock_mult = data.get(mk)
    if not stock_mult or not isinstance(stock_mult, (int, float)) or stock_mult <= 0 or stock_mult > 500:
        return None

    sec = scored_df[scored_df["sector"] == sector]
    if mk not in sec.columns: return None
    sm = pd.to_numeric(sec[mk], errors="coerce").dropna()
    sm = sm[(sm > 0) & (sm < 500)]
    if len(sm) < 5: return None

    # Quality percentile, but CAPPED at 75th to prevent extreme multiples
    qpct = min(_quality_pct(data, sector, scored_df), 75)
    deserved = sm.quantile(qpct / 100)

    if mk in ["priceToSalesTrailing12Months"]:
        rps = price / stock_mult; fv = rps * deserved
    elif mk in ["priceToBook"]:
        bps = price / stock_mult; fv = bps * deserved
    elif mk in ["enterpriseToEbitda"]:
        fv = price * (deserved / stock_mult)
    elif mk in ["trailingPE", "forwardPE"]:
        eps = price / stock_mult; fv = eps * deserved
    else:
        fv = price * (deserved / stock_mult)

    if fv <= 0 or not np.isfinite(fv): return None

    return {
        "fair_value": round(fv, 2), "_label": ml,
        "premium_discount_pct": round((price / fv - 1) * 100, 1),
        "assumptions": {
            f"your_{mn}": round(stock_mult, 1),
            f"deserved_{mn}": round(deserved, 1),
            "sector_median": round(sm.median(), 1),
            "quality_pct": round(qpct, 0),
            "peers": len(sm),
            "method": f"Capped at 75th pctile {mn}",
        },
    }


def _trailing_earnings_cap(data: dict, sector: str, scored_df: pd.DataFrame) -> dict | None:
    """Quality-adjusted PE, capped at 35x regardless of quality."""
    price = data.get("currentPrice", 0)
    tpe = data.get("trailingPE")
    if not price or price <= 0 or not tpe or tpe <= 0 or tpe > 500: return None
    eps = price / tpe

    sec = scored_df[scored_df["sector"] == sector]
    if "trailingPE" not in sec.columns or len(sec) < 5:
        return _fallback(data, eps, tpe, price)

    spe = pd.to_numeric(sec["trailingPE"], errors="coerce").dropna()
    spe = spe[(spe > 0) & (spe < 200)]
    if len(spe) < 5: return _fallback(data, eps, tpe, price)

    qpct = min(_quality_pct(data, sector, scored_df), 75)
    deserved = spe.quantile(qpct / 100)
    # Hard cap at 35x
    deserved = min(deserved, 35)

    fv = eps * deserved
    if fv <= 0 or not np.isfinite(fv): return None

    return {
        "fair_value": round(fv, 2),
        "premium_discount_pct": round((price / fv - 1) * 100, 1),
        "assumptions": {
            "eps": round(eps, 2), "actual_pe": round(tpe, 1),
            "deserved_pe": round(deserved, 1), "quality_pct": round(qpct, 0),
            "method": "EPS * Quality-Adj PE (capped 35x)",
        },
    }


def _fallback(data, eps, tpe, price):
    roe = data.get("returnOnEquity"); om = data.get("operatingMargins")
    q = 0
    if roe and isinstance(roe, (int, float)):
        if roe > 0.25: q += 3
        elif roe > 0.15: q += 2
        elif roe > 0.08: q += 1
    if om and isinstance(om, (int, float)):
        if om > 0.25: q += 3
        elif om > 0.15: q += 2
        elif om > 0.08: q += 1

    if q >= 5: fpe = 25
    elif q >= 3: fpe = 20
    elif q >= 1: fpe = 16
    else: fpe = 12

    fv = eps * fpe
    if fv <= 0 or not np.isfinite(fv): return None
    return {
        "fair_value": round(fv, 2),
        "premium_discount_pct": round((price / fv - 1) * 100, 1),
        "assumptions": {"eps": round(eps, 2), "quality_pe": fpe, "method": "Quality PE fallback"},
    }


def _analyst_target(data: dict) -> dict | None:
    price = data.get("currentPrice", 0)
    upside = data.get("analyst_mean_target_upside")
    cnt = data.get("analyst_count", 0)
    if not price or price <= 0 or upside is None: return None
    target = price * (1 + float(upside))
    if target <= 0 or not np.isfinite(target): return None
    return {
        "fair_value": round(target, 2),
        "premium_discount_pct": round((price / target - 1) * 100, 1),
        "assumptions": {
            "target": round(target, 2), "upside": f"{float(upside)*100:+.1f}%",
            "analysts": cnt, "method": f"Consensus of {cnt} analysts",
        },
    }


def _quality_pct(data: dict, sector: str, scored_df: pd.DataFrame) -> float:
    sec = scored_df[scored_df["sector"] == sector]
    if len(sec) < 5: return 50
    pcts = []
    for qm in ["revenueGrowth", "earningsGrowth", "operatingMargins", "returnOnEquity"]:
        if qm not in sec.columns: continue
        col = pd.to_numeric(sec[qm], errors="coerce").dropna()
        if len(col) < 5: continue
        sv = data.get(qm)
        if sv is None or not isinstance(sv, (int, float)) or not np.isfinite(sv): continue
        pcts.append((col < sv).sum() / len(col) * 100)
    return np.mean(pcts) if pcts else 50


def compute_portfolio_fair_values(holdings_df: pd.DataFrame, scored_df: pd.DataFrame) -> pd.DataFrame:
    results = []
    for _, row in holdings_df.iterrows():
        t = row.get("ticker", "")
        fv = compute_fair_value(t, scored_df)
        if "error" not in fv:
            results.append({"ticker": t, "current_price": fv["current_price"], "fair_value": fv["composite_fair_value"],
                "premium_discount": fv["premium_discount_pct"], "verdict": fv["verdict"], "methods_used": fv["num_methods_used"]})
        else:
            results.append({"ticker": t, "current_price": row.get("price", 0), "fair_value": None,
                "premium_discount": None, "verdict": "N/A", "methods_used": 0})
    return pd.DataFrame(results)
