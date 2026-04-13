"""
Portfolio Analyzer module with ETF support.
Stocks get full factor analysis. ETFs get value/weight/momentum tracking.
Both contribute to Monte Carlo simulation.
"""

import json
import os
import numpy as np
import pandas as pd
from config import PILLAR_METRICS, RATING_COLORS, GRADE_COLORS


# ── Load Raw Cache (for ETF lookups) ───────────────────────────────

def _load_raw_cache() -> dict:
    """Load the full cache including ETFs."""
    for path in ["fundamentals_cache.json", os.path.join("data_cache", "fundamentals_cache.json")]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


# ── Portfolio Scoring ──────────────────────────────────────────────


def analyze_portfolio(
    holdings: list[dict],
    scored_df: pd.DataFrame,
    sector_stats: dict = None,
) -> dict:
    """
    Analyze a portfolio including both stocks and ETFs.
    Stocks get full factor analysis. ETFs get value/weight tracking.
    """
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
            # Stock in scored universe
            row = scored_df.loc[ticker]
            price = row.get("currentPrice", 0)
            market_value = shares * price

            matched_stocks.append({
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "gain_pct": ((price - cost_basis) / cost_basis * 100) if cost_basis and cost_basis > 0 else None,
                "sector": row.get("sector", "Unknown"),
                "type": "stock",
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
            # ETF or stock below market cap floor -- in cache but not scored
            cached = raw_cache[ticker]
            price = cached.get("currentPrice", 0)
            market_value = shares * price
            is_etf = cached.get("type") == "etf" or cached.get("sector") == "ETF"

            entry = {
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "gain_pct": ((price - cost_basis) / cost_basis * 100) if cost_basis and cost_basis > 0 else None,
                "sector": cached.get("sector", "ETF" if is_etf else "Unknown"),
                "type": "etf" if is_etf else "stock",
                "composite_score": None,
                "overall_rating": "N/A (ETF)" if is_etf else "Not Scored",
                "valuation_score": 0, "growth_score": 0,
                "profitability_score": 0, "momentum_score": 0, "eps_rev_score": 0,
                "market_cap_b": 0,
                "shortName": cached.get("shortName", ticker),
                # ETF-specific fields
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

    # ── Portfolio-Level Metrics ─────────────────────────────────────

    # Weighted composite (stocks only)
    stocks_only = port_df[port_df["type"] == "stock"]
    stocks_weight = stocks_only["weight"].sum()

    if not stocks_only.empty and stocks_weight > 0:
        weighted_composite = (stocks_only["weight"] * stocks_only["composite_score"]).sum() / stocks_weight
    else:
        weighted_composite = 0

    # Stock vs ETF allocation
    etf_weight = port_df[port_df["type"] == "etf"]["weight"].sum()
    stock_weight = 1 - etf_weight

    # Weighted pillar scores (stocks only)
    pillar_scores = {}
    for pillar in ["valuation", "growth", "profitability", "momentum", "eps_rev"]:
        col = f"{pillar}_score"
        if col in stocks_only.columns and not stocks_only.empty and stocks_weight > 0:
            pillar_scores[pillar] = (stocks_only["weight"] * stocks_only[col]).sum() / stocks_weight
        else:
            pillar_scores[pillar] = 0

    # Rating distribution (stocks only)
    rating_dist = {}
    if not stocks_only.empty:
        rating_dist = stocks_only.groupby("overall_rating")["weight"].sum().to_dict()

    # ── Sector Concentration ───────────────────────────────────────

    sector_weights = port_df.groupby("sector").agg(
        weight=("weight", "sum"),
        count=("ticker", "count"),
        avg_score=("composite_score", lambda x: x.dropna().mean() if x.dropna().any() else 0),
    ).sort_values("weight", ascending=False).to_dict("index")

    sector_weight_series = port_df.groupby("sector")["weight"].sum()
    hhi = (sector_weight_series ** 2).sum()

    # ── Top/Bottom Holdings ────────────────────────────────────────

    top_rated = stocks_only.nlargest(5, "composite_score")[
        ["ticker", "shortName", "composite_score", "overall_rating", "weight"]
    ].to_dict("records") if not stocks_only.empty else []

    bottom_rated = stocks_only.nsmallest(5, "composite_score")[
        ["ticker", "shortName", "composite_score", "overall_rating", "weight"]
    ].to_dict("records") if not stocks_only.empty else []

    # Top ETFs by weight
    etfs_only = port_df[port_df["type"] == "etf"]
    top_etfs = etfs_only.nlargest(10, "weight")[
        ["ticker", "shortName", "market_value", "weight", "momentum_3m", "momentum_12m"]
    ].to_dict("records") if not etfs_only.empty else []

    # ── Factor Tilts (stocks only vs universe) ─────────────────────

    universe_avgs = {}
    for pillar in PILLAR_METRICS:
        score_col = f"{pillar}_score"
        if score_col in scored_df.columns:
            universe_avgs[pillar] = scored_df[score_col].mean()

    port_pillar_avgs = {
        "Valuation": pillar_scores.get("valuation", 0),
        "Growth": pillar_scores.get("growth", 0),
        "Profitability": pillar_scores.get("profitability", 0),
        "Momentum": pillar_scores.get("momentum", 0),
        "EPS Revisions": pillar_scores.get("eps_rev", 0),
    }

    factor_tilts = {}
    for pillar in PILLAR_METRICS:
        port_val = port_pillar_avgs.get(pillar, 0)
        univ_val = universe_avgs.get(pillar, 0)
        diff = port_val - univ_val
        tilt = "Overweight" if diff > 1.0 else "Underweight" if diff < -1.0 else "Neutral"
        factor_tilts[pillar] = {
            "portfolio": round(port_val, 1),
            "universe": round(univ_val, 1),
            "diff": round(diff, 1),
            "tilt": tilt,
        }

    return {
        "total_value": total_value,
        "num_holdings": len(all_matched),
        "num_stocks": len(matched_stocks),
        "num_etfs": len(matched_etfs),
        "num_unmatched": len(unmatched),
        "unmatched_tickers": unmatched,
        "stock_weight": round(stock_weight * 100, 1),
        "etf_weight": round(etf_weight * 100, 1),
        "weighted_composite": round(weighted_composite, 2),
        "weighted_rating": _score_to_rating_simple(weighted_composite),
        "pillar_scores": port_pillar_avgs,
        "rating_distribution": rating_dist,
        "sector_weights": sector_weights,
        "hhi": round(hhi, 3),
        "concentration_level": "Diversified" if hhi < 0.15 else "Moderate" if hhi < 0.25 else "Concentrated",
        "top_rated": top_rated,
        "bottom_rated": bottom_rated,
        "top_etfs": top_etfs,
        "factor_tilts": factor_tilts,
        "holdings_df": port_df,
    }


# ── Monte Carlo Simulation ─────────────────────────────────────────


def run_monte_carlo(
    holdings_df: pd.DataFrame,
    scored_df: pd.DataFrame,
    n_simulations: int = 5000,
    n_days: int = 252,
    confidence_levels: list = [0.05, 0.25, 0.50, 0.75, 0.95],
) -> dict:
    """
    Run Monte Carlo simulation on portfolio.
    Works for both stocks and ETFs using momentum data.
    """
    if holdings_df.empty:
        return {}

    raw_cache = _load_raw_cache()
    total_value = holdings_df["market_value"].sum()
    weights = holdings_df["weight"].values

    returns = []
    vols = []

    for _, row in holdings_df.iterrows():
        ticker = row["ticker"]

        # Try scored_df first, then raw cache
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

        # Best estimate of forward return
        if ret_12m is not None and not (isinstance(ret_12m, float) and np.isnan(ret_12m)):
            exp_ret = float(ret_12m)
        elif ret_6m is not None and not (isinstance(ret_6m, float) and np.isnan(ret_6m)):
            exp_ret = float(ret_6m) * 2
        else:
            exp_ret = 0.08

        # Estimate volatility
        period_rets = []
        for r in [ret_1m, ret_3m, ret_6m, ret_12m]:
            if r is not None and not (isinstance(r, float) and np.isnan(r)):
                period_rets.append(float(r))

        if len(period_rets) >= 2:
            vol = np.std(period_rets) * 2
            vol = max(vol, 0.15)
        else:
            vol = 0.30

        returns.append(exp_ret)
        vols.append(vol)

    returns = np.array(returns)
    vols = np.array(vols)

    port_return = np.dot(weights, returns)
    avg_corr = 0.4
    port_vol = np.sqrt(
        np.dot(weights ** 2, vols ** 2) +
        avg_corr * np.sum(
            np.outer(weights * vols, weights * vols) -
            np.diag(weights ** 2 * vols ** 2)
        )
    )
    port_vol = max(port_vol, 0.10)

    daily_ret = port_return / n_days
    daily_vol = port_vol / np.sqrt(n_days)

    np.random.seed(42)
    daily_returns = np.random.normal(daily_ret, daily_vol, (n_simulations, n_days))
    price_paths = total_value * np.cumprod(1 + daily_returns, axis=1)

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

    return {
        "total_value": total_value,
        "n_simulations": n_simulations,
        "n_days": n_days,
        "expected_annual_return": round(port_return * 100, 1),
        "estimated_annual_vol": round(port_vol * 100, 1),
        "terminal_mean": round(np.mean(terminal_values), 0),
        "terminal_median": round(np.median(terminal_values), 0),
        "percentiles": {k: round(v, 0) for k, v in percentiles.items()},
        "prob_positive": round(prob_positive * 100, 1),
        "prob_loss_10": round(prob_loss_10 * 100, 1),
        "prob_loss_20": round(prob_loss_20 * 100, 1),
        "prob_gain_20": round(prob_gain_20 * 100, 1),
        "prob_gain_50": round(prob_gain_50 * 100, 1),
        "path_percentiles": path_percentiles,
        "terminal_values": terminal_values,
    }


# ── Suggestions Engine ─────────────────────────────────────────────


def generate_suggestions(
    analysis: dict,
    scored_df: pd.DataFrame,
    max_suggestions: int = 8,
) -> list[dict]:
    """Generate actionable portfolio suggestions."""
    suggestions = []
    holdings_df = analysis.get("holdings_df", pd.DataFrame())
    if holdings_df.empty:
        return suggestions

    held_tickers = set(holdings_df["ticker"].tolist())

    # 1. Flag Sell-rated stock holdings
    stocks = holdings_df[holdings_df["type"] == "stock"]
    for _, row in stocks.iterrows():
        if row.get("overall_rating") in ["Sell", "Strong Sell"]:
            suggestions.append({
                "type": "warning",
                "title": f"Review {row['ticker']} ({row['overall_rating']})",
                "detail": f"{row['ticker']} scores {row.get('composite_score', 0):.1f}/12. "
                          f"It is {row['weight']*100:.1f}% of your portfolio.",
                "priority": 1,
            })

    # 2. High ETF allocation warning
    etf_weight = analysis.get("etf_weight", 0)
    if etf_weight > 60:
        suggestions.append({
            "type": "info",
            "title": f"ETFs are {etf_weight:.0f}% of your portfolio",
            "detail": "ETFs provide diversification but may overlap significantly. "
                      "Consider analyzing the underlying holdings for hidden concentration.",
            "priority": 2,
        })

    # 3. Concentration warnings
    for sector, data in analysis.get("sector_weights", {}).items():
        if sector == "ETF":
            continue
        if data["weight"] > 0.35:
            suggestions.append({
                "type": "warning",
                "title": f"High concentration in {sector} ({data['weight']*100:.0f}%)",
                "detail": f"{data['count']} holdings in {sector}. Consider diversifying.",
                "priority": 2,
            })

    # 4. Factor tilt warnings
    for pillar, tilt_data in analysis.get("factor_tilts", {}).items():
        if tilt_data["tilt"] == "Underweight" and tilt_data["diff"] < -2.0:
            suggestions.append({
                "type": "info",
                "title": f"Weak {pillar} tilt ({tilt_data['portfolio']:.1f} vs {tilt_data['universe']:.1f} avg)",
                "detail": f"Your stock holdings score {abs(tilt_data['diff']):.1f} points below average on {pillar}.",
                "priority": 3,
            })

    # 5. Suggest Strong Buy names not held
    strong_buys = scored_df[scored_df["overall_rating"] == "Strong Buy"].copy()
    if not strong_buys.empty:
        available = strong_buys[~strong_buys.index.isin(held_tickers)]
        for _, sb_row in available.head(5).iterrows():
            suggestions.append({
                "type": "opportunity",
                "title": f"Consider {sb_row.name}: Strong Buy in {sb_row.get('sector', 'N/A')}",
                "detail": f"{sb_row.get('shortName', sb_row.name)} scores "
                          f"{sb_row.get('composite_score', 0):.1f}/12.",
                "priority": 4,
            })

    suggestions.sort(key=lambda x: x["priority"])
    return suggestions[:max_suggestions]


# ── Helpers ────────────────────────────────────────────────────────


def _score_to_rating_simple(score: float) -> str:
    if score >= 8.5: return "Strong Buy"
    elif score >= 7.0: return "Buy"
    elif score >= 5.0: return "Hold"
    elif score >= 3.5: return "Sell"
    else: return "Strong Sell"


def parse_fidelity_csv(csv_content: str) -> list[dict]:
    """Parse a Fidelity positions CSV export."""
    try:
        import io
        lines = csv_content.strip().split("\n")
        clean_lines = []
        for line in lines:
            if line.strip() and not line.startswith("Date downloaded"):
                clean_lines.append(line)
        clean_content = "\n".join(clean_lines)

        df = pd.read_csv(io.StringIO(clean_content))

        holdings = []
        for _, row in df.iterrows():
            symbol = str(row.get("Symbol", "")).strip()
            if not symbol or symbol == "nan":
                continue
            if "**" in symbol or len(symbol) > 6:
                continue
            # Skip treasury bonds (numeric symbols)
            if symbol[0].isdigit():
                continue

            qty_raw = str(row.get("Quantity", "0"))
            qty_raw = qty_raw.replace(",", "").replace("$", "").strip()
            try:
                shares = float(qty_raw)
            except (ValueError, TypeError):
                continue
            if shares <= 0:
                continue

            cost_basis = None
            cost_raw = str(row.get("Average Cost Basis", ""))
            cost_raw = cost_raw.replace(",", "").replace("$", "").replace("--", "").strip()
            if cost_raw and cost_raw != "nan":
                try:
                    cost_basis = float(cost_raw)
                except (ValueError, TypeError):
                    pass

            holdings.append({
                "ticker": symbol.upper(),
                "shares": shares,
                "cost_basis": cost_basis,
            })

        return holdings
    except Exception:
        return []
