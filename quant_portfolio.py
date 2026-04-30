"""
Quant Perfect Portfolio
=======================

Score-tiered portfolio construction with sector caps and position floors/ceilings.

Two modes:
1. FRESH: Build a portfolio from scratch with $X cash
2. REBALANCE: Compare current holdings to optimal, show deltas

Methodology:
- Universe: Stocks rated Strong Buy or Buy (score >= 8.0)
- Within tier: weight by score² (heavy emphasis on top scorers)
- Apply sector caps (default 35% max per sector)
- Apply position floors ($200 minimum) and ceilings (12% max)
- Quality filter: market cap >= $2B (avoid microcap noise)
"""

import numpy as np
import pandas as pd


# ── Aggressiveness Presets ──────────────────────────────────────────

PRESETS = {
    "Conservative": {
        "max_positions": 30,
        "sector_cap": 0.25,
        "position_ceiling": 0.08,
        "score_floor": 7.5,
        "min_market_cap_b": 5.0,
        "weight_power": 1.5,  # weight = score^1.5 (modest tilt)
    },
    "Balanced": {
        "max_positions": 20,
        "sector_cap": 0.35,
        "position_ceiling": 0.12,
        "score_floor": 8.0,
        "min_market_cap_b": 2.0,
        "weight_power": 2.0,  # weight = score^2 (heavy tilt)
    },
    "Aggressive": {
        "max_positions": 12,
        "sector_cap": 0.50,
        "position_ceiling": 0.20,
        "score_floor": 8.5,
        "min_market_cap_b": 1.0,
        "weight_power": 2.5,  # weight = score^2.5 (very heavy tilt)
    },
}


# ── Core Construction ──────────────────────────────────────────────

def build_optimal_portfolio(scored_df, capital, preset="Balanced", min_position_dollars=200):
    """
    Build the optimal score-weighted portfolio from current scored universe.

    Returns DataFrame with: ticker, sector, score, rating, price, weight_pct, dollars, shares, market_cap_b
    """
    if scored_df.empty:
        return pd.DataFrame()

    settings = PRESETS.get(preset, PRESETS["Balanced"])

    # Step 1: Filter by quality
    # scored_df has ticker as INDEX, columns are: marketCap, currentPrice, sector, composite_score, overall_rating, etc.
    candidates = scored_df.copy()
    # Reset index so ticker becomes a column
    if candidates.index.name == "ticker":
        candidates = candidates.reset_index()

    candidates = candidates[candidates["composite_score"] >= settings["score_floor"]]
    candidates = candidates[candidates["marketCap"] >= settings["min_market_cap_b"] * 1e9]
    candidates = candidates[candidates["currentPrice"] > 0]

    if candidates.empty:
        return pd.DataFrame()

    # Step 2: Sort by score and take top N
    candidates = candidates.sort_values("composite_score", ascending=False)
    candidates = candidates.head(settings["max_positions"] * 2)  # Take 2x to allow sector culling

    # Step 3: Apply sector cap iteratively
    selected = _select_with_sector_cap(
        candidates,
        max_positions=settings["max_positions"],
        sector_cap=settings["sector_cap"],
        weight_power=settings["weight_power"],
    )

    if selected.empty:
        return pd.DataFrame()

    # Step 4: Compute weights using score^power
    selected = selected.copy()
    selected["raw_weight"] = selected["composite_score"] ** settings["weight_power"]

    # Step 5: Normalize and apply ceiling
    total_raw = selected["raw_weight"].sum()
    selected["weight_pct"] = selected["raw_weight"] / total_raw

    # Cap individual positions
    selected["weight_pct"] = selected["weight_pct"].clip(upper=settings["position_ceiling"])
    # Renormalize after capping
    selected["weight_pct"] = selected["weight_pct"] / selected["weight_pct"].sum()

    # Step 6: Compute dollar amounts
    selected["dollars"] = (selected["weight_pct"] * capital).round(2)

    # Step 7: Filter out positions below minimum
    selected = selected[selected["dollars"] >= min_position_dollars]
    if selected.empty:
        return pd.DataFrame()

    # Renormalize one more time after dropping small positions
    selected["weight_pct"] = selected["weight_pct"] / selected["weight_pct"].sum()
    selected["dollars"] = (selected["weight_pct"] * capital).round(2)

    # Step 8: Compute share counts
    selected["shares"] = (selected["dollars"] / selected["currentPrice"]).round(3)

    # Step 9: Rename columns to friendly names for display
    selected["price"] = selected["currentPrice"]
    selected["rating"] = selected["overall_rating"]
    selected["market_cap_b"] = (selected["marketCap"] / 1e9).round(2)
    selected["weight_pct"] = (selected["weight_pct"] * 100).round(2)

    cols = ["ticker", "sector", "rating", "composite_score", "price",
            "weight_pct", "dollars", "shares", "market_cap_b"]
    available_cols = [c for c in cols if c in selected.columns]
    return selected[available_cols].reset_index(drop=True).sort_values("weight_pct", ascending=False).reset_index(drop=True)


def _select_with_sector_cap(candidates, max_positions, sector_cap, weight_power):
    """
    Select stocks while respecting the per-sector cap.

    Algorithm:
    1. Take top N candidates by score (greedy)
    2. Compute final weights (score^power, normalized)
    3. If any sector exceeds cap, drop the lowest-scored stock from that sector
    4. Repeat until all sectors comply
    """
    # Step 1: Take top N by score
    selected = candidates.head(max_positions).copy()

    # Step 2-4: Iteratively trim oversaturated sectors
    max_iterations = max_positions  # Safety bound
    for _ in range(max_iterations):
        if selected.empty:
            break

        # Compute current sector weights
        selected = selected.copy()
        selected["raw_w"] = selected["composite_score"] ** weight_power
        total_w = selected["raw_w"].sum()
        if total_w <= 0:
            break
        selected["pct"] = selected["raw_w"] / total_w

        sector_totals = selected.groupby("sector")["pct"].sum()
        violators = sector_totals[sector_totals > sector_cap]

        if violators.empty:
            # All sectors comply
            break

        # For the most-violating sector, drop the lowest-scored member
        worst_sector = violators.idxmax()
        sector_members = selected[selected["sector"] == worst_sector]
        if len(sector_members) <= 1:
            # Can't shrink a 1-stock sector further; cap is effectively unenforceable here.
            # This happens when one stock is so dominant that even alone it exceeds the cap.
            # We'll allow it (the position ceiling will catch extreme cases).
            break

        # Drop lowest-scored stock in violating sector
        idx_to_drop = sector_members["composite_score"].idxmin()
        selected = selected.drop(index=idx_to_drop)

    if selected.empty:
        return pd.DataFrame()

    # Clean up helper columns
    drop_cols = [c for c in ["raw_w", "pct"] if c in selected.columns]
    return selected.drop(columns=drop_cols)


# ── Rebalance Mode ──────────────────────────────────────────────────

def compute_rebalance_deltas(optimal_df, current_holdings, scored_df, total_capital):
    """
    Compare optimal portfolio to current holdings and produce action items.

    current_holdings: list of dicts with {ticker, shares, current_price}
    optimal_df: output from build_optimal_portfolio()
    total_capital: total portfolio value (current value + new cash)

    Returns list of action dicts: {ticker, action, delta_dollars, current_dollars, target_dollars, reason}
    """
    actions = []

    # Build current state
    current_map = {}
    current_total = 0
    for h in current_holdings:
        ticker = h.get("ticker", "").upper()
        shares = float(h.get("shares", 0) or 0)
        price = float(h.get("current_price", 0) or 0)
        if not ticker or shares <= 0 or price <= 0:
            continue
        value = shares * price
        current_map[ticker] = {"shares": shares, "price": price, "value": value}
        current_total += value

    # Build target state from optimal_df
    target_map = {}
    if not optimal_df.empty:
        for _, row in optimal_df.iterrows():
            ticker = row["ticker"]
            target_map[ticker] = {
                "weight_pct": row["weight_pct"],
                "dollars": row["dollars"],
                "price": row["price"],
                "score": row["composite_score"],
                "rating": row["rating"],
                "sector": row.get("sector", "Unknown"),
            }

    # Process actions: SELL/TRIM existing positions not in target, BUY/ADD positions in target
    all_tickers = set(current_map.keys()) | set(target_map.keys())

    for ticker in all_tickers:
        cur = current_map.get(ticker)
        tgt = target_map.get(ticker)

        cur_dollars = cur["value"] if cur else 0
        tgt_dollars = tgt["dollars"] if tgt else 0
        delta = tgt_dollars - cur_dollars

        if cur and not tgt:
            # Position not in optimal — recommend exit
            reason = _explain_exit(ticker, scored_df)
            actions.append({
                "ticker": ticker,
                "action": "EXIT",
                "delta_dollars": -cur_dollars,
                "current_dollars": cur_dollars,
                "target_dollars": 0,
                "current_pct": 100 * cur_dollars / current_total if current_total else 0,
                "target_pct": 0,
                "reason": reason,
                "score": _get_score(ticker, scored_df),
                "rating": _get_rating(ticker, scored_df),
            })
        elif tgt and not cur:
            # New position
            actions.append({
                "ticker": ticker,
                "action": "INITIATE",
                "delta_dollars": delta,
                "current_dollars": 0,
                "target_dollars": tgt_dollars,
                "current_pct": 0,
                "target_pct": tgt["weight_pct"],
                "reason": f"Rated {tgt['rating']} (score {tgt['score']:.1f})",
                "score": tgt["score"],
                "rating": tgt["rating"],
            })
        else:
            # Position in both - decide ADD/TRIM/HOLD based on magnitude
            cur_pct = 100 * cur_dollars / total_capital if total_capital else 0
            tgt_pct = tgt["weight_pct"]
            pct_delta = tgt_pct - cur_pct

            # Threshold: ignore changes under 1.5 percentage points or $100
            if abs(pct_delta) < 1.5 or abs(delta) < 100:
                action = "HOLD"
                reason = "Within target range"
            elif delta > 0:
                action = "ADD"
                reason = f"Underweight by {pct_delta:.1f}pp"
            else:
                action = "TRIM"
                reason = f"Overweight by {-pct_delta:.1f}pp"

            actions.append({
                "ticker": ticker,
                "action": action,
                "delta_dollars": delta,
                "current_dollars": cur_dollars,
                "target_dollars": tgt_dollars,
                "current_pct": cur_pct,
                "target_pct": tgt_pct,
                "reason": reason,
                "score": tgt["score"],
                "rating": tgt["rating"],
            })

    # Sort: Initiates and Adds first (by magnitude), then Trims, then Exits, then Holds
    action_order = {"INITIATE": 0, "ADD": 1, "TRIM": 2, "EXIT": 3, "HOLD": 4}
    actions.sort(key=lambda a: (action_order.get(a["action"], 9), -abs(a["delta_dollars"])))

    return actions


def _get_score(ticker, scored_df):
    if scored_df.empty:
        return None
    if ticker in scored_df.index:
        return float(scored_df.loc[ticker, "composite_score"])
    return None


def _get_rating(ticker, scored_df):
    if scored_df.empty:
        return None
    if ticker in scored_df.index:
        val = scored_df.loc[ticker, "overall_rating"]
        return val if isinstance(val, str) else None
    return None


def _explain_exit(ticker, scored_df):
    """Explain why we're recommending an exit."""
    score = _get_score(ticker, scored_df)
    rating = _get_rating(ticker, scored_df)
    if score is None:
        return f"{ticker} not in scored universe"
    if rating in ("Sell", "Strong Sell"):
        return f"Rated {rating} (score {score:.1f})"
    return f"Below quant threshold (score {score:.1f}, rated {rating})"


# ── Diversification Analysis ────────────────────────────────────────

def compute_diversification_stats(portfolio_df):
    """Return dict of diversification stats for display."""
    if portfolio_df.empty:
        return {}

    sector_breakdown = portfolio_df.groupby("sector")["weight_pct"].sum().sort_values(ascending=False).to_dict()

    return {
        "num_positions": len(portfolio_df),
        "avg_score": portfolio_df["composite_score"].mean(),
        "min_score": portfolio_df["composite_score"].min(),
        "max_score": portfolio_df["composite_score"].max(),
        "largest_position_pct": portfolio_df["weight_pct"].max(),
        "smallest_position_pct": portfolio_df["weight_pct"].min(),
        "largest_position_ticker": portfolio_df.iloc[0]["ticker"] if len(portfolio_df) else "",
        "sector_breakdown": sector_breakdown,
        "num_sectors": len(sector_breakdown),
        "top_sector": list(sector_breakdown.keys())[0] if sector_breakdown else "",
        "top_sector_pct": list(sector_breakdown.values())[0] if sector_breakdown else 0,
    }


def compare_to_spy_overlap(portfolio_df, spy_top_holdings=None):
    """
    Estimate overlap with SPY top holdings.
    spy_top_holdings: list of top SPY tickers (mega-caps).
    """
    if spy_top_holdings is None:
        # Hardcoded approximation of SPY top 30 by weight (may drift over time)
        spy_top_holdings = [
            "NVDA", "MSFT", "AAPL", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "BRK-B", "GOOG",
            "JPM", "LLY", "V", "WMT", "MA", "XOM", "UNH", "ORCL", "COST", "HD",
            "JNJ", "PG", "NFLX", "BAC", "ABBV", "CRM", "CVX", "KO", "MRK", "AMD",
        ]

    if portfolio_df.empty:
        return {"overlap_count": 0, "overlap_pct": 0, "overlap_tickers": []}

    overlap_tickers = [t for t in portfolio_df["ticker"].tolist() if t in spy_top_holdings]
    overlap_weight = portfolio_df[portfolio_df["ticker"].isin(spy_top_holdings)]["weight_pct"].sum()

    return {
        "overlap_count": len(overlap_tickers),
        "overlap_pct": round(overlap_weight, 1),
        "overlap_tickers": overlap_tickers,
    }
