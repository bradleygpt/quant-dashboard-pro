"""
Portfolio Suggestions v2 - Prescriptive Engine
Transforms descriptive warnings into specific, actionable recommendations.

Categories:
1. Position sizing alerts (too concentrated / too small)
2. Dead weight consolidation (positions < 1%)
3. Rebalancing recommendations (sector concentration)
4. Tax loss harvesting opportunities
5. Momentum-based exit signals
6. Opportunity cost alerts
7. Correlation warnings
8. Specific BUY recommendations based on strategy
"""

import pandas as pd
import numpy as np


# ── Thresholds ─────────────────────────────────────────────────────

CONCENTRATION_WARNING_PCT = 15  # Single position warning
CONCENTRATION_CRITICAL_PCT = 25  # Single position critical
DEAD_WEIGHT_PCT = 1.0  # Positions smaller than this
SECTOR_WARNING_PCT = 40  # Sector concentration warning
SECTOR_CRITICAL_PCT = 60  # Sector concentration critical
TAX_LOSS_THRESHOLD_PCT = -10  # Harvest losses beyond this
MOMENTUM_EXIT_THRESHOLD = -15  # 3-month momentum below this with bad score


def generate_suggestions_v2(analysis, scored_df, max_suggestions=12):
    """
    Generate prescriptive, actionable portfolio recommendations.
    Each suggestion has: type, priority, title, action, reasoning, specifics.
    """
    suggestions = []
    holdings_df = analysis.get("holdings_df", pd.DataFrame())
    if holdings_df.empty:
        return suggestions

    total_value = analysis.get("total_value", 0)
    held_tickers = set(holdings_df["ticker"].tolist())
    stocks = holdings_df[holdings_df["type"] == "stock"].copy()

    # ═══ 1. CONCENTRATION ALERTS (Position Sizing) ═══════════════════
    for _, row in holdings_df.iterrows():
        weight_pct = row["weight"] * 100
        ticker = row["ticker"]
        market_value = row["market_value"]

        if weight_pct >= CONCENTRATION_CRITICAL_PCT:
            # Calculate suggested trim
            target_pct = 15  # Trim to 15%
            target_value = total_value * (target_pct / 100)
            shares_to_sell = (market_value - target_value) / row["price"] if row["price"] > 0 else 0
            sell_value = market_value - target_value
            suggestions.append({
                "type": "critical",
                "priority": 1,
                "category": "concentration",
                "title": f"TRIM {ticker}: {weight_pct:.1f}% is too concentrated",
                "action": f"Sell ~{shares_to_sell:.0f} shares (~${sell_value:,.0f})",
                "reasoning": f"Single position exceeds {CONCENTRATION_CRITICAL_PCT}% threshold. A 20% drawdown in {ticker} would cost you ${market_value*0.2:,.0f}. Trim to {target_pct}% for better risk management.",
                "ticker": ticker,
                "current_weight_pct": round(weight_pct, 1),
                "target_weight_pct": target_pct,
                "dollar_amount": round(sell_value, 0),
            })
        elif weight_pct >= CONCENTRATION_WARNING_PCT:
            suggestions.append({
                "type": "warning",
                "priority": 2,
                "category": "concentration",
                "title": f"MONITOR {ticker}: {weight_pct:.1f}% concentration",
                "action": "Watch this position carefully. Consider trimming on strength.",
                "reasoning": f"Position is {weight_pct:.0f}% of portfolio. Not critical yet but warrants attention.",
                "ticker": ticker,
                "current_weight_pct": round(weight_pct, 1),
            })

    # ═══ 2. DEAD WEIGHT CONSOLIDATION ═══════════════════════════════
    dead_weight_positions = [
        (row["ticker"], row["weight"] * 100, row["market_value"], row.get("shares", 0))
        for _, row in holdings_df.iterrows()
        if row["weight"] * 100 < DEAD_WEIGHT_PCT
    ]
    if len(dead_weight_positions) >= 3:
        total_dead_value = sum(dw[2] for dw in dead_weight_positions)
        tickers_str = ", ".join(dw[0] for dw in dead_weight_positions)
        suggestions.append({
            "type": "info",
            "priority": 3,
            "category": "consolidation",
            "title": f"CONSOLIDATE: {len(dead_weight_positions)} positions under {DEAD_WEIGHT_PCT}% each",
            "action": f"Either build to meaningful positions (5%+) or sell entirely. Combined value: ${total_dead_value:,.0f}",
            "reasoning": f"These positions ({tickers_str}) add complexity without meaningful portfolio impact. At <1% each, even a 50% gain is <0.5% portfolio return.",
            "tickers": [dw[0] for dw in dead_weight_positions],
            "dollar_amount": round(total_dead_value, 0),
        })
    elif dead_weight_positions:
        for ticker, weight_pct, mv, shares in dead_weight_positions:
            suggestions.append({
                "type": "info",
                "priority": 4,
                "category": "consolidation",
                "title": f"DECIDE {ticker}: only {shares:.0f} shares ({weight_pct:.2f}%)",
                "action": f"Build to 5%+ or exit. Currently ${mv:,.0f} adds minimal portfolio impact.",
                "reasoning": f"Position too small to matter. Either commit or move on.",
                "ticker": ticker,
                "current_weight_pct": round(weight_pct, 2),
            })

    # ═══ 3. SECTOR CONCENTRATION ═══════════════════════════════════
    sector_weights = analysis.get("sector_weights", {})
    for sector, data in sector_weights.items():
        if sector == "ETF":
            continue
        sector_pct = data["weight"] * 100
        if sector_pct >= SECTOR_CRITICAL_PCT:
            # Find the largest positions in that sector to consider trimming
            sector_stocks = stocks[stocks["sector"] == sector].sort_values("weight", ascending=False)
            top_names = sector_stocks.head(3)["ticker"].tolist() if not sector_stocks.empty else []
            suggestions.append({
                "type": "critical",
                "priority": 1,
                "category": "sector_concentration",
                "title": f"REDUCE {sector} exposure: {sector_pct:.0f}% of portfolio",
                "action": f"Consider trimming largest {sector} positions: {', '.join(top_names)}",
                "reasoning": f"Sector concentration over {SECTOR_CRITICAL_PCT}% creates macro risk. One sector-wide event could wipe out substantial portfolio value. Target: 30-45%.",
                "sector": sector,
                "current_pct": round(sector_pct, 1),
                "target_pct": 40,
            })
        elif sector_pct >= SECTOR_WARNING_PCT:
            suggestions.append({
                "type": "warning",
                "priority": 3,
                "category": "sector_concentration",
                "title": f"HIGH {sector} weight: {sector_pct:.0f}%",
                "action": f"Consider diversifying away from {sector} on strength",
                "reasoning": f"Above {SECTOR_WARNING_PCT}% in one sector. Not critical but reduces diversification benefits.",
                "sector": sector,
                "current_pct": round(sector_pct, 1),
            })

    # ═══ 4. TAX LOSS HARVEST OPPORTUNITIES ══════════════════════════
    for _, row in stocks.iterrows():
        gain_pct = row.get("gain_pct")
        if gain_pct is not None and gain_pct <= TAX_LOSS_THRESHOLD_PCT:
            ticker = row["ticker"]
            market_value = row["market_value"]
            cost_basis = row.get("cost_basis", 0)
            loss_amount = (cost_basis * row["shares"]) - market_value
            rating = row.get("overall_rating", "Hold")

            if rating in ["Strong Sell", "Sell"]:
                action = f"SELL {ticker}: harvest ~${loss_amount:,.0f} loss AND exit weak position"
                reasoning = f"Down {gain_pct:.1f}% AND rated {rating}. Double reason to sell - capture tax loss and remove weak holding."
                priority = 2
            else:
                action = f"Consider harvesting ${loss_amount:,.0f} loss on {ticker}"
                reasoning = f"Down {gain_pct:.1f}% from cost. If you still like the thesis, sell now and buy back after 31 days (wash sale) to lock in tax benefit."
                priority = 3

            suggestions.append({
                "type": "opportunity",
                "priority": priority,
                "category": "tax_loss",
                "title": f"TAX LOSS: {ticker} down {gain_pct:.1f}%",
                "action": action,
                "reasoning": reasoning,
                "ticker": ticker,
                "loss_amount": round(loss_amount, 0),
                "gain_pct": round(gain_pct, 1),
            })

    # ═══ 5. MOMENTUM EXIT SIGNALS ═══════════════════════════════════
    for _, row in stocks.iterrows():
        ticker = row["ticker"]
        if ticker in scored_df.index:
            sr = scored_df.loc[ticker]
            momentum_3m = sr.get("momentum_3m")
            if momentum_3m is not None:
                momentum_3m_pct = momentum_3m * 100
                rating = row.get("overall_rating", "Hold")
                if momentum_3m_pct <= MOMENTUM_EXIT_THRESHOLD and rating in ["Sell", "Strong Sell", "Hold"]:
                    suggestions.append({
                        "type": "warning",
                        "priority": 2,
                        "category": "momentum_exit",
                        "title": f"MOMENTUM BREAKDOWN: {ticker}",
                        "action": f"Consider exiting {ticker} (down {momentum_3m_pct:.0f}% in 3M)",
                        "reasoning": f"{ticker} rated {rating} with deteriorating 3-month momentum ({momentum_3m_pct:.0f}%). Combination of weak fundamentals and weak price action often precedes further declines.",
                        "ticker": ticker,
                        "momentum_3m_pct": round(momentum_3m_pct, 1),
                    })

    # ═══ 6. SPECIFIC BUY RECOMMENDATIONS ════════════════════════════
    # Find Strong Buys not in portfolio, ideally in underweight sectors
    strong_buys = scored_df[
        (scored_df["overall_rating"] == "Strong Buy") &
        (~scored_df.index.isin(held_tickers)) &
        (scored_df["sector"] != "ETF")
    ].copy()

    if not strong_buys.empty:
        # Prioritize sectors where the portfolio is underweight
        portfolio_sectors = set(stocks["sector"].unique()) if not stocks.empty else set()

        # Find Strong Buys in underweighted or missing sectors first
        underweight_buys = strong_buys[
            ~strong_buys["sector"].isin(portfolio_sectors)
        ].head(3)
        overweight_buys = strong_buys[
            strong_buys["sector"].isin(portfolio_sectors)
        ].head(2)

        suggested_allocation = 5.0  # 5% default allocation
        target_dollar = total_value * (suggested_allocation / 100)

        for _, sb_row in pd.concat([underweight_buys, overweight_buys]).iterrows():
            ticker = sb_row.name
            price = sb_row.get("currentPrice", 0)
            shares = target_dollar / price if price > 0 else 0
            is_new_sector = sb_row["sector"] not in portfolio_sectors
            sector_note = f" (adds {sb_row['sector']} exposure)" if is_new_sector else ""

            suggestions.append({
                "type": "opportunity",
                "priority": 3 if is_new_sector else 4,
                "category": "new_position",
                "title": f"ADD {ticker}: Strong Buy{sector_note}",
                "action": f"Buy ~{shares:.0f} shares at ${price:.2f} = ${target_dollar:,.0f} ({suggested_allocation}%)",
                "reasoning": f"{sb_row.get('shortName', ticker)} scores {sb_row.get('composite_score', 0):.1f}/12. {sb_row.get('sector', 'N/A')} sector. " + ("Diversifies portfolio." if is_new_sector else "Quality addition in familiar sector."),
                "ticker": ticker,
                "shares": round(shares, 0),
                "dollar_amount": round(target_dollar, 0),
                "composite_score": round(sb_row.get("composite_score", 0), 1),
            })

    # ═══ 7. WEAK HOLDINGS NOT YET FLAGGED ═══════════════════════════
    for _, row in stocks.iterrows():
        if row.get("overall_rating") in ["Strong Sell"]:
            ticker = row["ticker"]
            weight = row["weight"] * 100
            mv = row["market_value"]
            # Skip if already in tax loss or momentum suggestions
            already_flagged = any(
                s.get("ticker") == ticker and s["category"] in ["tax_loss", "momentum_exit"]
                for s in suggestions
            )
            if not already_flagged:
                suggestions.append({
                    "type": "warning",
                    "priority": 2,
                    "category": "weak_holding",
                    "title": f"EXIT {ticker}: Strong Sell ({weight:.1f}% of portfolio)",
                    "action": f"Sell ~${mv:,.0f} position",
                    "reasoning": f"{ticker} scores in the bottom tier ({row.get('composite_score', 0):.1f}/12). Every day held is opportunity cost vs better positions.",
                    "ticker": ticker,
                    "dollar_amount": round(mv, 0),
                })

    # ═══ 8. ETF-HEAVY PORTFOLIO ALERT ═══════════════════════════════
    etf_weight = analysis.get("etf_weight", 0)
    if etf_weight > 60:
        suggestions.append({
            "type": "info",
            "priority": 5,
            "category": "etf_heavy",
            "title": f"ETF-HEAVY: {etf_weight:.0f}% of portfolio in ETFs",
            "action": "Consider more direct stock exposure for alpha generation",
            "reasoning": "ETFs provide diversification but cap upside. With quant scoring available, direct stock picks can outperform index returns.",
            "etf_pct": round(etf_weight, 1),
        })

    # Sort by priority (1 = highest)
    suggestions.sort(key=lambda x: (x["priority"], -x.get("current_weight_pct", 0)))
    return suggestions[:max_suggestions]


def format_suggestion_card(sug):
    """Format a suggestion for HTML display."""
    type_colors = {
        "critical": "#DC2626",
        "warning": "#F97316",
        "info": "#EAB308",
        "opportunity": "#22C55E",
    }
    icons = {
        "critical": "⚠",
        "warning": "!",
        "info": "i",
        "opportunity": "+",
    }
    color = type_colors.get(sug["type"], "#666")
    icon = icons.get(sug["type"], ">")
    return {
        "color": color,
        "icon": icon,
        "title": sug["title"],
        "action": sug["action"],
        "reasoning": sug["reasoning"],
        "category": sug.get("category", "general"),
    }
