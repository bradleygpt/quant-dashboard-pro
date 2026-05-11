"""
Absolute threshold breadth indicator.

Counts how many stocks have a composite_score above the historical
median TOP25 cutoff for the active weight scheme. The count varies
quarter to quarter as a market breadth signal:

  - count > mean: market broad, many opportunities
  - count near median: normal conditions
  - count < min historical: thin market, defensive posture warranted

Designed to be displayed at the top of the Screener tab as informational
context alongside the existing TOP25 ranking.
"""

from __future__ import annotations
import pandas as pd
from config import ABSOLUTE_THRESHOLDS, ABSOLUTE_THRESHOLD_STATS, DEFAULT_PRESET


def compute_breadth_indicator(
    scored_df: pd.DataFrame,
    preset_name: str = DEFAULT_PRESET,
) -> dict:
    """
    Return a dict with the current count of stocks above the absolute
    threshold for the given preset, plus historical context.

    {
        "count": int,
        "threshold": float,
        "preset": str,
        "context": {
            "median": int,
            "mean": float,
            "min": int,
            "max": int,
        },
        "signal": str,  # "broad" | "normal" | "thin"
        "delta_vs_median_pct": float,
    }
    """
    if scored_df is None or scored_df.empty or "composite_score" not in scored_df.columns:
        return {
            "count": 0,
            "threshold": 0.0,
            "preset": preset_name,
            "context": ABSOLUTE_THRESHOLD_STATS.get(preset_name, {}),
            "signal": "unknown",
            "delta_vs_median_pct": 0.0,
        }

    threshold = ABSOLUTE_THRESHOLDS.get(preset_name, 8.5)
    count = int((scored_df["composite_score"] >= threshold).sum())
    ctx = ABSOLUTE_THRESHOLD_STATS.get(preset_name, {})
    median = ctx.get("median_count")

    signal = "unknown"
    delta_pct = 0.0
    if median is not None and median > 0:
        delta_pct = (count - median) / median * 100
        if delta_pct >= 25:
            signal = "broad"
        elif delta_pct <= -25:
            signal = "thin"
        else:
            signal = "normal"

    return {
        "count": count,
        "threshold": threshold,
        "preset": preset_name,
        "context": ctx,
        "signal": signal,
        "delta_vs_median_pct": delta_pct,
    }


def format_breadth_indicator(indicator: dict) -> str:
    """Format the breadth indicator as a human-readable string for display."""
    count = indicator["count"]
    threshold = indicator["threshold"]
    ctx = indicator["context"]
    signal = indicator["signal"]
    delta_pct = indicator["delta_vs_median_pct"]

    if not ctx or ctx.get("median_count") is None:
        return f"{count} stocks above quality threshold ({threshold:.2f})"

    median = ctx["median_count"]
    min_c = ctx["min_count"]
    max_c = ctx["max_count"]

    signal_emoji = {"broad": "🟢", "thin": "🔴", "normal": "🟡"}.get(signal, "⚪")
    delta_str = f"{delta_pct:+.0f}% vs hist median"

    return (
        f"{signal_emoji} **{count} stocks** above quality threshold "
        f"({threshold:.2f})  •  historical median {median}, range {min_c}-{max_c}  "
        f"•  {delta_str}"
    )


def get_streamlit_status_color(signal: str) -> str:
    """Map signal to a Streamlit status color name."""
    return {
        "broad": "success",
        "normal": "info",
        "thin": "warning",
        "unknown": "info",
    }.get(signal, "info")
