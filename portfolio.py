"""
Portfolio Analyzer module.
Analyzes a user's portfolio against the quant scoring universe.
Includes: weighted scoring, sector concentration, factor tilts,
Monte Carlo simulation, and actionable suggestions.
"""

import numpy as np
import pandas as pd
from config import PILLAR_METRICS, RATING_COLORS, GRADE_COLORS


# ── Portfolio Scoring ──────────────────────────────────────────────


def analyze_portfolio(
    holdings: list[dict],
    scored_df: pd.DataFrame,
    sector_stats: dict = None,
) -> dict:
    """
    Analyze a portfolio of holdings against the scored universe.

    Args:
        holdings: list of {ticker, shares, cost_basis (optional)}
        scored_df: the scored universe DataFrame

    Returns:
        dict with all portfolio analytics
    """
    if not holdings or scored_df.empty:
        return {}

    # Match holdings to scored universe
    matched = []
    unmatched = []

    for h in holdings:
        ticker = h["ticker"].upper()
        shares = h.get("shares", 0)
        cost_basis = h.get("cost_basis")

        if ticker in scored_df.index:
            row = scored_df.loc[ticker]
            price = row.get("currentPrice", 0)
            market_value = shares * price
            matched.append({
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "gain_pct": ((price - cost_basis) / cost_basis * 100) if cost_basis and cost_basis > 0 else None,
                "sector": row.get("sector", "Unknown"),
                "composite_score": row.get("composite_score", 0),
                "overall_rating": row.get("overall_rating", "Hold"),
                "valuation_score": row.get("Valuation_score", 0),
                "growth_score": row.get("Growth_score", 0),
                "profitability_score": row.get("Profitability_score", 0),
                "momentum_score": row.get("Momentum_score", 0),
                "eps_rev_score": row.get("EPS Revisions_score", 0),
                "market_cap_b": row.get("marketCapB", 0),
            })
        else:
            unmatched.append(ticker)

    if not matched:
        return {"error": "No holdings matched the scored universe."}

    port_df = pd.DataFrame(matched)
    total_value = port_df["market_value"].sum()
    port_df["weight"] = port_df["market_value"] / total_value if total_value > 0 else 0

    # ── Portfolio-Level Metrics ─────────────────────────────────────

    # Weighted composite score
    weighted_composite = (port_df["weight"] * port_df["composite_score"]).sum()

    # Weighted pillar scores
    pillar_scores = {}
    for pillar in ["valuation", "growth", "profitability", "momentum", "eps_rev"]:
        col = f"{pillar}_score"
        if col in port_df.columns:
            pillar_scores[pillar] = (port_df["weight"] * port_df[col]).sum()

    # Rating distribution
    rating_dist = port_df.groupby("overall_rating")["weight"].sum().to_dict()

    # ── Sector Concentration ───────────────────────────────────────

    sector_weights = port_df.groupby("sector").agg(
        weight=("weight", "sum"),
        count=("ticker", "count"),
        avg_score=("composite_score", "mean"),
    ).sort_values("weight", ascending=False).to_dict("index")

    # HHI (Herfindahl-Hirschman Index) for concentration
    sector_weight_series = port_df.groupby("sector")["weight"].sum()
    hhi = (sector_weight_series ** 2).sum()
    # HHI: 0 = perfectly diversified, 1 = single sector
    # < 0.15 = diversified, 0.15-0.25 = moderate, > 0.25 = concentrated

    # ── Top/Bottom Holdings ────────────────────────────────────────

    top_rated = port_df.nlargest(5, "composite_score")[["ticker", "composite_score", "overall_rating", "weight"]].to_dict("records")
    bottom_rated = port_df.nsmallest(5, "composite_score")[["ticker", "composite_score", "overall_rating", "weight"]].to_dict("records")

    # ── Factor Tilts ───────────────────────────────────────────────
    # Compare portfolio average pillar scores to universe averages

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
        if diff > 1.0:
            tilt = "Overweight"
        elif diff < -1.0:
            tilt = "Underweight"
        else:
            tilt = "Neutral"
        factor_tilts[pillar] = {
            "portfolio": round(port_val, 1),
            "universe": round(univ_val, 1),
            "diff": round(diff, 1),
            "tilt": tilt,
        }

    return {
        "total_value": total_value,
        "num_holdings": len(matched),
        "num_unmatched": len(unmatched),
        "unmatched_tickers": unmatched,
        "weighted_composite": round(weighted_composite, 2),
        "weighted_rating": _score_to_rating_simple(weighted_composite),
        "pillar_scores": port_pillar_avgs,
        "rating_distribution": rating_dist,
        "sector_weights": sector_weights,
        "hhi": round(hhi, 3),
        "concentration_level": "Diversified" if hhi < 0.15 else "Moderate" if hhi < 0.25 else "Concentrated",
        "top_rated": top_rated,
        "bottom_rated": bottom_rated,
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
    Uses historical momentum data to estimate expected returns and volatility.
    """
    if holdings_df.empty:
        return {}

    total_value = holdings_df["market_value"].sum()
    weights = holdings_df["weight"].values

    # Estimate annualized return and volatility per holding from momentum data
    returns = []
    vols = []

    for _, row in holdings_df.iterrows():
        ticker = row["ticker"]
        if ticker in scored_df.index:
            sr = scored_df.loc[ticker]
            # Use 12-month return as expected annual return estimate
            ret_12m = sr.get("momentum_12m")
            ret_6m = sr.get("momentum_6m")
            ret_3m = sr.get("momentum_3m")
            ret_1m = sr.get("momentum_1m")

            # Best estimate of forward return (blend of lookback periods)
            if ret_12m is not None and not np.isnan(ret_12m):
                exp_ret = float(ret_12m)
            elif ret_6m is not None and not np.isnan(ret_6m):
                exp_ret = float(ret_6m) * 2
            else:
                exp_ret = 0.08  # default 8% annual

            # Estimate volatility from spread of return periods
            period_rets = []
            for r in [ret_1m, ret_3m, ret_6m, ret_12m]:
                if r is not None and not np.isnan(r):
                    period_rets.append(float(r))

            if len(period_rets) >= 2:
                vol = np.std(period_rets) * 2  # rough annualized vol estimate
                vol = max(vol, 0.15)  # floor at 15%
            else:
                vol = 0.30  # default 30%

            returns.append(exp_ret)
            vols.append(vol)
        else:
            returns.append(0.08)
            vols.append(0.30)

    returns = np.array(returns)
    vols = np.array(vols)

    # Portfolio expected return and volatility (simplified, assumes low correlation)
    port_return = np.dot(weights, returns)
    # Rough portfolio vol (assumes avg correlation of 0.4 between holdings)
    avg_corr = 0.4
    port_vol = np.sqrt(
        np.dot(weights ** 2, vols ** 2) +
        avg_corr * np.sum(
            np.outer(weights * vols, weights * vols) -
            np.diag(weights ** 2 * vols ** 2)
        )
    )
    port_vol = max(port_vol, 0.10)

    # Daily parameters
    daily_ret = port_return / n_days
    daily_vol = port_vol / np.sqrt(n_days)

    # Simulate paths
    np.random.seed(42)
    daily_returns = np.random.normal(daily_ret, daily_vol, (n_simulations, n_days))
    price_paths = total_value * np.cumprod(1 + daily_returns, axis=1)

    # Terminal values
    terminal_values = price_paths[:, -1]

    # Statistics
    percentiles = {}
    for level in confidence_levels:
        percentiles[f"p{int(level*100)}"] = np.percentile(terminal_values, level * 100)

    prob_positive = np.mean(terminal_values > total_value)
    prob_loss_10 = np.mean(terminal_values < total_value * 0.90)
    prob_loss_20 = np.mean(terminal_values < total_value * 0.80)
    prob_gain_20 = np.mean(terminal_values > total_value * 1.20)
    prob_gain_50 = np.mean(terminal_values > total_value * 1.50)

    # Generate path percentiles for chart
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
    """
    Generate actionable portfolio suggestions based on analysis.
    """
    suggestions = []
    holdings_df = analysis.get("holdings_df", pd.DataFrame())
    if holdings_df.empty:
        return suggestions

    held_tickers = set(holdings_df["ticker"].tolist())

    # 1. Flag Sell-rated holdings
    for _, row in holdings_df.iterrows():
        if row["overall_rating"] in ["Sell", "Strong Sell"]:
            suggestions.append({
                "type": "warning",
                "title": f"Review {row['ticker']} ({row['overall_rating']})",
                "detail": f"{row['ticker']} has a composite score of {row['composite_score']:.1f}/12. "
                          f"It accounts for {row['weight']*100:.1f}% of your portfolio. Consider reducing or exiting.",
                "priority": 1,
            })

    # 2. Concentration warnings
    for sector, data in analysis.get("sector_weights", {}).items():
        if data["weight"] > 0.35:
            suggestions.append({
                "type": "warning",
                "title": f"High concentration in {sector} ({data['weight']*100:.0f}%)",
                "detail": f"Your portfolio has {data['weight']*100:.0f}% in {sector} "
                          f"({data['count']} holdings). Consider diversifying into other sectors.",
                "priority": 2,
            })

    # 3. Factor tilt warnings
    for pillar, tilt_data in analysis.get("factor_tilts", {}).items():
        if tilt_data["tilt"] == "Underweight" and tilt_data["diff"] < -2.0:
            suggestions.append({
                "type": "info",
                "title": f"Weak {pillar} tilt ({tilt_data['portfolio']:.1f} vs {tilt_data['universe']:.1f} universe avg)",
                "detail": f"Your portfolio scores {abs(tilt_data['diff']):.1f} points below the universe average on {pillar}. "
                          f"This could indicate a systematic weakness.",
                "priority": 3,
            })

    # 4. Suggest Strong Buy replacements for weak holdings
    strong_buys = scored_df[scored_df["overall_rating"] == "Strong Buy"].copy()
    if not strong_buys.empty:
        # Find strong buys not already held
        available = strong_buys[~strong_buys.index.isin(held_tickers)]
        if not available.empty:
            # Get underweight sectors
            port_sectors = set(holdings_df["sector"].unique())
            for _, sb_row in available.head(5).iterrows():
                sector = sb_row.get("sector", "Unknown")
                suggestions.append({
                    "type": "opportunity",
                    "title": f"Consider {sb_row.name}: Strong Buy in {sector}",
                    "detail": f"{sb_row.get('shortName', sb_row.name)} has a composite score of "
                              f"{sb_row.get('composite_score', 0):.1f}/12. "
                              f"Strong across multiple factors.",
                    "priority": 4,
                })

    # Sort by priority and limit
    suggestions.sort(key=lambda x: x["priority"])
    return suggestions[:max_suggestions]


# ── Helpers ────────────────────────────────────────────────────────


def _score_to_rating_simple(score: float) -> str:
    if score >= 8.5:
        return "Strong Buy"
    elif score >= 7.0:
        return "Buy"
    elif score >= 5.0:
        return "Hold"
    elif score >= 3.5:
        return "Sell"
    else:
        return "Strong Sell"


def parse_fidelity_csv(csv_content: str) -> list[dict]:
    """
    Parse a Fidelity positions CSV export.
    Returns list of {ticker, shares, cost_basis}.
    """
    try:
        import io
        df = pd.read_csv(io.StringIO(csv_content))

        # Fidelity CSV has varying column names, try common ones
        ticker_cols = ["Symbol", "symbol", "Ticker", "ticker"]
        shares_cols = ["Quantity", "quantity", "Shares", "shares", "Current Value"]
        cost_cols = ["Cost Basis Per Share", "Cost Basis", "Average Cost Basis"]

        ticker_col = None
        for c in ticker_cols:
            if c in df.columns:
                ticker_col = c
                break

        shares_col = None
        for c in shares_cols:
            if c in df.columns:
                shares_col = c
                break

        cost_col = None
        for c in cost_cols:
            if c in df.columns:
                cost_col = c
                break

        if not ticker_col or not shares_col:
            return []

        holdings = []
        for _, row in df.iterrows():
            ticker = str(row[ticker_col]).strip().upper()
            if not ticker or ticker == "NAN" or len(ticker) > 6:
                continue

            try:
                shares = float(str(row[shares_col]).replace(",", "").replace("$", ""))
            except (ValueError, TypeError):
                continue

            cost_basis = None
            if cost_col:
                try:
                    cost_basis = float(str(row[cost_col]).replace(",", "").replace("$", ""))
                except (ValueError, TypeError):
                    pass

            holdings.append({
                "ticker": ticker,
                "shares": shares,
                "cost_basis": cost_basis,
            })

        return holdings
    except Exception:
        return []
