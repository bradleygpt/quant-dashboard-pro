"""
Portfolio Analyzer module with ETF support.
Stocks get full factor analysis. ETFs get value/weight/momentum tracking.
Both contribute to Monte Carlo simulation.

Monte Carlo v2: Realistic returns with mean reversion, return caps,
log-normal simulation, and macro scenario integration.
"""

import json
import os
import numpy as np
import pandas as pd
from config import PILLAR_METRICS, RATING_COLORS, GRADE_COLORS


# ── Load Raw Cache (for ETF lookups) ─────────────────────────────

def _load_raw_cache() -> dict:
    for path in ["fundamentals_cache.json", os.path.join("data_cache", "fundamentals_cache.json")]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


# ── Portfolio Scoring ──────────────────────────────────────────────

def analyze_portfolio(holdings, scored_df, sector_stats=None):
    if not holdings or scored_df.empty:
        return {}

    raw_cache = _load_raw_cache()
    matched_stocks = []
    matched_etfs = []
    unmatched = []

    for h in holdings:
        ticker = h["ticker"].upper()
        shares = h.get("shares", 0)
        cost_basis = h.get("cost_basis")

        if ticker in scored_df.index:
            row = scored_df.loc[ticker]
            price = row.get("currentPrice", 0)
            market_value = shares * price
            matched_stocks.append({
                "ticker": ticker, "shares": shares, "price": price,
                "market_value": market_value, "cost_basis": cost_basis,
                "gain_pct": ((price - cost_basis) / cost_basis * 100) if cost_basis and cost_basis > 0 else None,
                "sector": row.get("sector", "Unknown"), "type": "stock",
                "composite_score": row.get("composite_score", 0),
                "overall_rating": row.get("overall_rating", "Hold"),
                "valuation_score": row.get("Valuation_score", 0),
                "growth_score": row.get("Growth_score", 0),
                "profitability_score": row.get("Profitability_score", 0),
                "momentum_score": row.get("Momentum_score", 0),
                "eps_rev_score": row.get("EPS Revisions_score", 0),
                "market_cap_b": row.get("marketCapB", 0),
                "shortName": row.get("shortName", ticker),
            })
        elif ticker in raw_cache:
            cached = raw_cache[ticker]
            price = cached.get("currentPrice", 0)
            market_value = shares * price
            is_etf = cached.get("type") == "etf" or cached.get("sector") == "ETF"
            entry = {
                "ticker": ticker, "shares": shares, "price": price,
                "market_value": market_value, "cost_basis": cost_basis,
                "gain_pct": ((price - cost_basis) / cost_basis * 100) if cost_basis and cost_basis > 0 else None,
                "sector": cached.get("sector", "ETF" if is_etf else "Unknown"),
                "type": "etf" if is_etf else "stock",
                "composite_score": None,
                "overall_rating": "N/A (ETF)" if is_etf else "Not Scored",
                "valuation_score": 0, "growth_score": 0,
                "profitability_score": 0, "momentum_score": 0, "eps_rev_score": 0,
                "market_cap_b": 0,
                "shortName": cached.get("shortName", ticker),
                "expenseRatio": cached.get("expenseRatio"),
                "ytdReturn": cached.get("ytdReturn"),
                "momentum_1m": cached.get("momentum_1m"),
                "momentum_3m": cached.get("momentum_3m"),
                "momentum_6m": cached.get("momentum_6m"),
                "momentum_12m": cached.get("momentum_12m"),
            }
            matched_etfs.append(entry)
        else:
            unmatched.append(ticker)

    all_matched = matched_stocks + matched_etfs
    if not all_matched:
        return {"error": "No holdings matched the universe or ETF database."}

    port_df = pd.DataFrame(all_matched)
    total_value = port_df["market_value"].sum()
    port_df["weight"] = port_df["market_value"] / total_value if total_value > 0 else 0

    stocks_only = port_df[port_df["type"] == "stock"]
    stocks_weight = stocks_only["weight"].sum()
    weighted_composite = (stocks_only["weight"] * stocks_only["composite_score"]).sum() / stocks_weight if not stocks_only.empty and stocks_weight > 0 else 0

    etf_weight = port_df[port_df["type"] == "etf"]["weight"].sum()
    stock_weight = 1 - etf_weight

    pillar_scores = {}
    for pillar in ["valuation", "growth", "profitability", "momentum", "eps_rev"]:
        col = f"{pillar}_score"
        if col in stocks_only.columns and not stocks_only.empty and stocks_weight > 0:
            pillar_scores[pillar] = (stocks_only["weight"] * stocks_only[col]).sum() / stocks_weight
        else:
            pillar_scores[pillar] = 0

    rating_dist = stocks_only.groupby("overall_rating")["weight"].sum().to_dict() if not stocks_only.empty else {}

    sector_weights = port_df.groupby("sector").agg(
        weight=("weight", "sum"), count=("ticker", "count"),
        avg_score=("composite_score", lambda x: x.dropna().mean() if x.dropna().any() else 0),
    ).sort_values("weight", ascending=False).to_dict("index")

    hhi = (port_df.groupby("sector")["weight"].sum() ** 2).sum()

    top_rated = stocks_only.nlargest(5, "composite_score")[["ticker","shortName","composite_score","overall_rating","weight"]].to_dict("records") if not stocks_only.empty else []
    bottom_rated = stocks_only.nsmallest(5, "composite_score")[["ticker","shortName","composite_score","overall_rating","weight"]].to_dict("records") if not stocks_only.empty else []

    etfs_only = port_df[port_df["type"] == "etf"]
    top_etfs = etfs_only.nlargest(10, "weight")[["ticker","shortName","market_value","weight","momentum_3m","momentum_12m"]].to_dict("records") if not etfs_only.empty else []

    universe_avgs = {}
    for pillar in PILLAR_METRICS:
        score_col = f"{pillar}_score"
        if score_col in scored_df.columns:
            universe_avgs[pillar] = scored_df[score_col].mean()

    port_pillar_avgs = {"Valuation": pillar_scores.get("valuation", 0), "Growth": pillar_scores.get("growth", 0),
        "Profitability": pillar_scores.get("profitability", 0), "Momentum": pillar_scores.get("momentum", 0),
        "EPS Revisions": pillar_scores.get("eps_rev", 0)}

    factor_tilts = {}
    for pillar in PILLAR_METRICS:
        pv = port_pillar_avgs.get(pillar, 0); uv = universe_avgs.get(pillar, 0); diff = pv - uv
        factor_tilts[pillar] = {"portfolio": round(pv, 1), "universe": round(uv, 1), "diff": round(diff, 1),
            "tilt": "Overweight" if diff > 1.0 else "Underweight" if diff < -1.0 else "Neutral"}

    return {
        "total_value": total_value, "num_holdings": len(all_matched),
        "num_stocks": len(matched_stocks), "num_etfs": len(matched_etfs),
        "num_unmatched": len(unmatched), "unmatched_tickers": unmatched,
        "stock_weight": round(stock_weight * 100, 1), "etf_weight": round(etf_weight * 100, 1),
        "weighted_composite": round(weighted_composite, 2),
        "weighted_rating": _score_to_rating_simple(weighted_composite),
        "pillar_scores": port_pillar_avgs, "rating_distribution": rating_dist,
        "sector_weights": sector_weights, "hhi": round(hhi, 3),
        "concentration_level": "Diversified" if hhi < 0.15 else "Moderate" if hhi < 0.25 else "Concentrated",
        "top_rated": top_rated, "bottom_rated": bottom_rated, "top_etfs": top_etfs,
        "factor_tilts": factor_tilts, "holdings_df": port_df,
    }


# ══════════════════════════════════════════════════════════════════
# MONTE CARLO v2 - REALISTIC SIMULATION
# ══════════════════════════════════════════════════════════════════
#
# Fixes from v1:
# 1. RETURN CAP: Max 40% annualized per holding (was uncapped, IREN at 300%)
# 2. MEAN REVERSION: 60% long-term premium + 40% trailing (was 100% trailing)
# 3. LOG RETURNS: Geometric Brownian Motion (was arithmetic, overstated compounding)
# 4. PROPER VOL: Market-cap-tiered floors + dispersion-based estimate
# 5. SCENARIO SELECTOR: Bull/Base/Bear/Blended shifts drift term
# 6. CORRECT ANNUALIZATION: mu - sigma^2/2 adjustment for GBM

LONG_TERM_EQUITY_PREMIUM = 0.10
LONG_TERM_SMALL_CAP_PREMIUM = 0.12
LONG_TERM_SPECULATIVE_PREMIUM = 0.08
MAX_ANNUAL_RETURN = 0.40
MIN_ANNUAL_RETURN = -0.30
MEAN_REVERSION_WEIGHT = 0.60

SCENARIO_ADJUSTMENTS = {
    "Bull": +0.08,
    "Base": 0.0,
    "Bear": -0.12,
    "Blended": None,
}

VOL_FLOORS = {
    "large": 0.20,   # $50B+
    "mid": 0.30,     # $10B-$50B
    "small": 0.45,   # $2B-$10B
    "micro": 0.60,   # <$2B
    "etf": 0.15,
}


def _estimate_holding_params(ticker, row, scored_df, raw_cache):
    """Estimate annualized expected return and volatility for one holding."""
    if ticker in scored_df.index:
        sr = scored_df.loc[ticker]
    elif ticker in raw_cache:
        sr = pd.Series(raw_cache[ticker])
    else:
        sr = pd.Series()

    ret_12m = sr.get("momentum_12m")
    ret_6m = sr.get("momentum_6m")
    ret_3m = sr.get("momentum_3m")
    ret_1m = sr.get("momentum_1m")
    mcap_b = row.get("market_cap_b", 0)
    if isinstance(mcap_b, (int, float)) and mcap_b > 1e6:
        mcap_b = mcap_b / 1e9
    is_etf = row.get("type") == "etf"

    # ── Expected Return ──
    trailing = None
    if ret_12m is not None and not (isinstance(ret_12m, float) and np.isnan(ret_12m)):
        trailing = float(ret_12m)
    elif ret_6m is not None and not (isinstance(ret_6m, float) and np.isnan(ret_6m)):
        trailing = float(ret_6m) * 2
    elif ret_3m is not None and not (isinstance(ret_3m, float) and np.isnan(ret_3m)):
        trailing = float(ret_3m) * 4
    else:
        trailing = LONG_TERM_EQUITY_PREMIUM

    if is_etf:
        lt_premium = LONG_TERM_EQUITY_PREMIUM
    elif mcap_b and mcap_b < 5:
        lt_premium = LONG_TERM_SPECULATIVE_PREMIUM
    elif mcap_b and mcap_b < 20:
        lt_premium = LONG_TERM_SMALL_CAP_PREMIUM
    else:
        lt_premium = LONG_TERM_EQUITY_PREMIUM

    exp_ret = MEAN_REVERSION_WEIGHT * lt_premium + (1 - MEAN_REVERSION_WEIGHT) * trailing
    exp_ret = max(MIN_ANNUAL_RETURN, min(MAX_ANNUAL_RETURN, exp_ret))

    # ── Volatility ──
    period_rets = []
    if ret_1m is not None and not (isinstance(ret_1m, float) and np.isnan(ret_1m)):
        period_rets.append(float(ret_1m) * 12)
    if ret_3m is not None and not (isinstance(ret_3m, float) and np.isnan(ret_3m)):
        period_rets.append(float(ret_3m) * 4)
    if ret_6m is not None and not (isinstance(ret_6m, float) and np.isnan(ret_6m)):
        period_rets.append(float(ret_6m) * 2)
    if ret_12m is not None and not (isinstance(ret_12m, float) and np.isnan(ret_12m)):
        period_rets.append(float(ret_12m))

    if len(period_rets) >= 2:
        vol = np.std(period_rets)
        avg_abs = np.mean([abs(r) for r in period_rets])
        vol = max(vol, avg_abs * 0.5)
    else:
        vol = 0.30

    if is_etf: vol = max(vol, VOL_FLOORS["etf"])
    elif mcap_b and mcap_b >= 50: vol = max(vol, VOL_FLOORS["large"])
    elif mcap_b and mcap_b >= 10: vol = max(vol, VOL_FLOORS["mid"])
    elif mcap_b and mcap_b >= 2: vol = max(vol, VOL_FLOORS["small"])
    else: vol = max(vol, VOL_FLOORS["micro"])

    vol = min(vol, 1.0)
    return exp_ret, vol


def run_monte_carlo(
    holdings_df, scored_df,
    n_simulations=5000, n_days=252,
    scenario="Blended",
    confidence_levels=[0.05, 0.25, 0.50, 0.75, 0.95],
):
    """
    Monte Carlo v2: Geometric Brownian Motion with mean reversion,
    return caps, and scenario selector.
    """
    if holdings_df.empty:
        return {}

    raw_cache = _load_raw_cache()
    total_value = holdings_df["market_value"].sum()
    weights = holdings_df["weight"].values

    returns_arr = []
    vols_arr = []
    holding_details = []

    for _, row in holdings_df.iterrows():
        ticker = row["ticker"]
        exp_ret, vol = _estimate_holding_params(ticker, row, scored_df, raw_cache)
        returns_arr.append(exp_ret)
        vols_arr.append(vol)
        holding_details.append({
            "ticker": ticker,
            "expected_return": round(exp_ret * 100, 1),
            "estimated_vol": round(vol * 100, 1),
            "weight": round(row["weight"] * 100, 1),
        })

    returns_arr = np.array(returns_arr)
    vols_arr = np.array(vols_arr)

    # Portfolio-level
    port_return = np.dot(weights, returns_arr)
    avg_corr = 0.45
    port_vol = np.sqrt(
        np.dot(weights ** 2, vols_arr ** 2) +
        avg_corr * np.sum(
            np.outer(weights * vols_arr, weights * vols_arr) -
            np.diag(weights ** 2 * vols_arr ** 2)
        )
    )
    port_vol = max(port_vol, 0.12)

    # Scenario adjustment
    if scenario == "Blended":
        scenario_adj = 0.25 * SCENARIO_ADJUSTMENTS["Bull"] + 0.50 * SCENARIO_ADJUSTMENTS["Base"] + 0.25 * SCENARIO_ADJUSTMENTS["Bear"]
    else:
        scenario_adj = SCENARIO_ADJUSTMENTS.get(scenario, 0.0)

    adjusted_return = port_return + scenario_adj

    # GBM: daily parameters with variance drag
    daily_mu = (adjusted_return - 0.5 * port_vol ** 2) / 252
    daily_sigma = port_vol / np.sqrt(252)

    np.random.seed(42)
    daily_log_returns = np.random.normal(daily_mu, daily_sigma, (n_simulations, n_days))
    cumulative_log_returns = np.cumsum(daily_log_returns, axis=1)
    price_paths = total_value * np.exp(cumulative_log_returns)

    terminal_values = price_paths[:, -1]

    percentiles = {}
    for level in confidence_levels:
        percentiles[f"p{int(level*100)}"] = np.percentile(terminal_values, level * 100)

    prob_positive = np.mean(terminal_values > total_value)
    prob_loss_10 = np.mean(terminal_values < total_value * 0.90)
    prob_loss_20 = np.mean(terminal_values < total_value * 0.80)
    prob_gain_20 = np.mean(terminal_values > total_value * 1.20)
    prob_gain_50 = np.mean(terminal_values > total_value * 1.50)

    path_percentiles = {}
    for level in [0.05, 0.25, 0.50, 0.75, 0.95]:
        path_percentiles[f"p{int(level*100)}"] = np.percentile(price_paths, level * 100, axis=0)

    horizon_fraction = n_days / 252
    median_terminal = np.median(terminal_values)
    realized_return_annualized = ((median_terminal / total_value) ** (1 / horizon_fraction) - 1) * 100 if median_terminal > 0 else 0

    return {
        "total_value": total_value,
        "n_simulations": n_simulations, "n_days": n_days, "scenario": scenario,
        "expected_annual_return": round(adjusted_return * 100, 1),
        "estimated_annual_vol": round(port_vol * 100, 1),
        "terminal_mean": round(np.mean(terminal_values), 0),
        "terminal_median": round(median_terminal, 0),
        "realized_return_annualized": round(realized_return_annualized, 1),
        "percentiles": {k: round(v, 0) for k, v in percentiles.items()},
        "prob_positive": round(prob_positive * 100, 1),
        "prob_loss_10": round(prob_loss_10 * 100, 1),
        "prob_loss_20": round(prob_loss_20 * 100, 1),
        "prob_gain_20": round(prob_gain_20 * 100, 1),
        "prob_gain_50": round(prob_gain_50 * 100, 1),
        "path_percentiles": path_percentiles,
        "terminal_values": terminal_values,
        "holding_details": holding_details,
        "model_params": {
            "mean_reversion_weight": MEAN_REVERSION_WEIGHT,
            "max_annual_return_cap": MAX_ANNUAL_RETURN,
            "long_term_premium": LONG_TERM_EQUITY_PREMIUM,
            "avg_correlation": avg_corr,
            "scenario_adjustment": round(scenario_adj * 100, 1),
        },
    }


# ── Suggestions Engine ─────────────────────────────────────────────

def generate_suggestions(analysis, scored_df, max_suggestions=8):
    suggestions = []
    holdings_df = analysis.get("holdings_df", pd.DataFrame())
    if holdings_df.empty: return suggestions
    held_tickers = set(holdings_df["ticker"].tolist())

    stocks = holdings_df[holdings_df["type"] == "stock"]
    for _, row in stocks.iterrows():
        if row.get("overall_rating") in ["Sell", "Strong Sell"]:
            suggestions.append({"type": "warning", "title": f"Review {row['ticker']} ({row['overall_rating']})",
                "detail": f"{row['ticker']} scores {row.get('composite_score', 0):.1f}/12. It is {row['weight']*100:.1f}% of your portfolio.", "priority": 1})

    etf_weight = analysis.get("etf_weight", 0)
    if etf_weight > 60:
        suggestions.append({"type": "info", "title": f"ETFs are {etf_weight:.0f}% of your portfolio",
            "detail": "ETFs provide diversification but may overlap significantly.", "priority": 2})

    for sector, data in analysis.get("sector_weights", {}).items():
        if sector == "ETF": continue
        if data["weight"] > 0.35:
            suggestions.append({"type": "warning", "title": f"High concentration in {sector} ({data['weight']*100:.0f}%)",
                "detail": f"{data['count']} holdings in {sector}. Consider diversifying.", "priority": 2})

    for pillar, td in analysis.get("factor_tilts", {}).items():
        if td["tilt"] == "Underweight" and td["diff"] < -2.0:
            suggestions.append({"type": "info", "title": f"Weak {pillar} tilt ({td['portfolio']:.1f} vs {td['universe']:.1f} avg)",
                "detail": f"Your stock holdings score {abs(td['diff']):.1f} points below average on {pillar}.", "priority": 3})

    strong_buys = scored_df[scored_df["overall_rating"] == "Strong Buy"].copy()
    if not strong_buys.empty:
        available = strong_buys[~strong_buys.index.isin(held_tickers)]
        for _, sb_row in available.head(5).iterrows():
            suggestions.append({"type": "opportunity", "title": f"Consider {sb_row.name}: Strong Buy in {sb_row.get('sector', 'N/A')}",
                "detail": f"{sb_row.get('shortName', sb_row.name)} scores {sb_row.get('composite_score', 0):.1f}/12.", "priority": 4})

    suggestions.sort(key=lambda x: x["priority"])
    return suggestions[:max_suggestions]


# ── Helpers ────────────────────────────────────────────────────────

def _score_to_rating_simple(score):
    if score >= 9.0: return "Strong Buy"
    elif score >= 8.0: return "Buy"
    elif score >= 6.0: return "Hold"
    elif score >= 5.0: return "Sell"
    else: return "Strong Sell"


def parse_fidelity_csv(csv_content):
    try:
        import io
        lines = csv_content.strip().split("\n")
        clean_lines = [l for l in lines if l.strip() and not l.startswith("Date downloaded")]
        df = pd.read_csv(io.StringIO("\n".join(clean_lines)))
        holdings = []
        for _, row in df.iterrows():
            symbol = str(row.get("Symbol", "")).strip()
            if not symbol or symbol == "nan" or "**" in symbol or len(symbol) > 6: continue
            if symbol[0].isdigit(): continue
            qty_raw = str(row.get("Quantity", "0")).replace(",", "").replace("$", "").strip()
            try: shares = float(qty_raw)
            except: continue
            if shares <= 0: continue
            cost_basis = None
            cost_raw = str(row.get("Average Cost Basis", "")).replace(",", "").replace("$", "").replace("--", "").strip()
            if cost_raw and cost_raw != "nan":
                try: cost_basis = float(cost_raw)
                except: pass
            holdings.append({"ticker": symbol.upper(), "shares": shares, "cost_basis": cost_basis})
        return holdings
    except: return []
