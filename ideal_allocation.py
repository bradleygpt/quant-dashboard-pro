"""
Ideal Allocation Calculator
===========================

Determines optimal cash vs equity split based on Pullback Pressure Index.

When markets are stretched (high pressure), holding more cash positions you to
buy on weakness. When markets are weak (low pressure / fear), being fully
invested captures recovery.

This is "tactical asset allocation" lite — not full market timing, but
modest defensive positioning during overheated periods.

Usage:
    from ideal_allocation import compute_ideal_allocation
    result = compute_ideal_allocation(pullback_score=72, current_total=100000)
    # Returns: target_stock_pct, target_cash_pct, current_state, suggested_actions
"""

import numpy as np


# Allocation regime thresholds
ALLOCATION_REGIMES = [
    # (pressure_max, stock_pct, cash_pct, label)
    (24,  100, 0,  "Aggressive Deploy"),       # Very Low pressure
    (44,  95,  5,  "Standard Deploy"),         # Low pressure
    (64,  85,  15, "Modest Defensive"),        # Moderate pressure
    (79,  70,  30, "Defensive"),               # Elevated pressure
    (100, 55,  45, "Highly Defensive"),        # Extreme pressure
]


def compute_ideal_allocation(pullback_score, current_total=None, current_stock_value=None, current_cash_value=None):
    """
    Compute the ideal cash/stock split based on pullback pressure.

    Args:
        pullback_score: 0-100 from compute_pullback_pressure()
        current_total: Total portfolio value (stock + cash). If provided, computes deltas.
        current_stock_value: Current value of stocks. Optional.
        current_cash_value: Current cash position. Optional.

    Returns dict with:
        target_stock_pct, target_cash_pct: Recommended allocation
        regime_label: Text description of the allocation regime
        rationale: Why this allocation is suggested
        deltas: If current state provided, what to change
    """
    # Find the matching regime
    target_stock_pct = 95
    target_cash_pct = 5
    regime_label = "Standard Deploy"
    for max_pressure, stock_pct, cash_pct, label in ALLOCATION_REGIMES:
        if pullback_score <= max_pressure:
            target_stock_pct = stock_pct
            target_cash_pct = cash_pct
            regime_label = label
            break

    rationale = _build_rationale(pullback_score, regime_label, target_stock_pct, target_cash_pct)

    result = {
        "pullback_score": pullback_score,
        "target_stock_pct": target_stock_pct,
        "target_cash_pct": target_cash_pct,
        "regime_label": regime_label,
        "rationale": rationale,
        "warnings": _build_warnings(pullback_score, target_cash_pct),
    }

    # Compute deltas if current state provided
    if current_total is not None and current_total > 0:
        target_stock_dollars = current_total * (target_stock_pct / 100)
        target_cash_dollars = current_total * (target_cash_pct / 100)

        result["target_stock_dollars"] = round(target_stock_dollars, 2)
        result["target_cash_dollars"] = round(target_cash_dollars, 2)

        if current_stock_value is not None and current_cash_value is not None:
            current_stock_pct = (current_stock_value / current_total) * 100 if current_total else 0
            current_cash_pct = (current_cash_value / current_total) * 100 if current_total else 0

            stock_delta = target_stock_dollars - current_stock_value
            cash_delta = target_cash_dollars - current_cash_value

            result["current_stock_pct"] = round(current_stock_pct, 1)
            result["current_cash_pct"] = round(current_cash_pct, 1)
            result["stock_delta_dollars"] = round(stock_delta, 2)
            result["cash_delta_dollars"] = round(cash_delta, 2)
            result["action"] = _build_action_text(stock_delta, cash_delta)

    return result


def _build_rationale(score, regime, stock_pct, cash_pct):
    """Plain-English explanation of why this allocation is suggested."""
    if regime == "Aggressive Deploy":
        return (
            f"Pullback pressure is very low ({score:.0f}/100), often indicating market fear or "
            f"oversold conditions. Historically, these moments offer favorable entry points. "
            f"Recommended: {stock_pct}% stocks, {cash_pct}% cash."
        )
    elif regime == "Standard Deploy":
        return (
            f"Pullback pressure is low ({score:.0f}/100). Market conditions are favorable for "
            f"deployment without significant defensive positioning. Recommended: {stock_pct}% stocks, "
            f"{cash_pct}% cash for opportunistic adds."
        )
    elif regime == "Modest Defensive":
        return (
            f"Pullback pressure is moderate ({score:.0f}/100). Some signs of stretching but no "
            f"strong sell signal. A 15% cash buffer provides flexibility for tactical adds on "
            f"weakness. Recommended: {stock_pct}% stocks, {cash_pct}% cash."
        )
    elif regime == "Defensive":
        return (
            f"Pullback pressure is elevated ({score:.0f}/100). Markets show signs of being stretched. "
            f"A 30% cash position provides meaningful capacity to deploy on a 5-10% pullback. "
            f"Recommended: {stock_pct}% stocks, {cash_pct}% cash."
        )
    else:  # Highly Defensive
        return (
            f"Pullback pressure is extreme ({score:.0f}/100). Multiple signals suggest "
            f"correction risk is meaningfully elevated. A 45% cash position prepares for "
            f"opportunistic deployment on a significant decline. Note: even at extreme pressure, "
            f"markets can keep rising. Recommended: {stock_pct}% stocks, {cash_pct}% cash."
        )


def _build_warnings(score, cash_pct):
    """Build list of important caveats based on the recommendation."""
    warnings = []

    if cash_pct > 20:
        warnings.append(
            "Selling existing positions to raise cash creates capital gains tax events. "
            "Consider whether tax cost outweighs defensive benefit."
        )
    if cash_pct >= 30:
        warnings.append(
            "Large cash positions (>30%) historically underperform fully-invested portfolios "
            "over long periods. Use this regime for short-term tactical positioning, not as a default."
        )
    if score >= 80:
        warnings.append(
            "Even at extreme pressure, markets can keep rising for weeks or months. "
            "This indicator suggests defense, not panic-selling."
        )
    if score < 25:
        warnings.append(
            "Low pullback pressure often coincides with fear or recent declines. "
            "Counter-intuitively, these are often good entry points historically."
        )

    return warnings


def _build_action_text(stock_delta, cash_delta):
    """Build human-readable action description."""
    if abs(stock_delta) < 100 and abs(cash_delta) < 100:
        return "Current allocation is approximately optimal — no major changes needed."

    if stock_delta > 0:
        return f"Deploy ~${stock_delta:,.0f} of cash into stocks to reach target."
    else:
        return f"Trim ~${-stock_delta:,.0f} of stocks to raise cash for defensive positioning."
