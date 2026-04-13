"""
Sector Overview module.
Aggregates stock-level scores to sector level for comparative analysis.
Shows rating distributions, cumulative pillar grades, and sector rankings.
"""

import pandas as pd
import numpy as np
from config import PILLAR_METRICS, GRADE_SCORES, OVERALL_RATING_MAP


def get_sector_overview(scored_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a sector-level summary with:
    - Number of stocks per rating category
    - Average pillar scores and grades
    - Overall sector composite score and rank
    """
    if scored_df.empty:
        return pd.DataFrame()

    sectors = scored_df["sector"].dropna().unique()
    rows = []

    for sector in sorted(sectors):
        if sector == "ETF":
            continue

        sector_df = scored_df[scored_df["sector"] == sector]
        n = len(sector_df)
        if n == 0:
            continue

        row = {
            "Sector": sector,
            "Stocks": n,
        }

        # Rating distribution
        for rating in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]:
            count = len(sector_df[sector_df["overall_rating"] == rating])
            row[rating] = count
            row[f"{rating}_pct"] = round(count / n * 100, 1) if n > 0 else 0

        # Pillar averages
        for pillar in PILLAR_METRICS:
            score_col = f"{pillar}_score"
            if score_col in sector_df.columns:
                avg = sector_df[score_col].mean()
                row[f"{pillar}_avg"] = round(avg, 1)
                row[f"{pillar}_grade"] = _score_to_grade(avg)
            else:
                row[f"{pillar}_avg"] = 0
                row[f"{pillar}_grade"] = "N/A"

        # Overall sector composite
        if "composite_score" in sector_df.columns:
            row["composite_avg"] = round(sector_df["composite_score"].mean(), 2)
            row["composite_median"] = round(sector_df["composite_score"].median(), 2)
            row["composite_max"] = round(sector_df["composite_score"].max(), 2)
            row["composite_min"] = round(sector_df["composite_score"].min(), 2)
        else:
            row["composite_avg"] = 0
            row["composite_median"] = 0
            row["composite_max"] = 0
            row["composite_min"] = 0

        # Best and worst stock in sector
        if not sector_df.empty:
            best = sector_df.nlargest(1, "composite_score")
            worst = sector_df.nsmallest(1, "composite_score")
            row["best_stock"] = f"{best.index[0]} ({best['composite_score'].iloc[0]:.1f})"
            row["worst_stock"] = f"{worst.index[0]} ({worst['composite_score'].iloc[0]:.1f})"
        else:
            row["best_stock"] = "N/A"
            row["worst_stock"] = "N/A"

        rows.append(row)

    overview_df = pd.DataFrame(rows)

    # Rank sectors by composite average
    if not overview_df.empty:
        overview_df = overview_df.sort_values("composite_avg", ascending=False)
        overview_df["Rank"] = range(1, len(overview_df) + 1)

    return overview_df


def get_sector_detail(sector: str, scored_df: pd.DataFrame) -> dict:
    """
    Get detailed breakdown for a single sector.
    Returns all stocks in the sector sorted by composite score.
    """
    if scored_df.empty:
        return {}

    sector_df = scored_df[scored_df["sector"] == sector].sort_values(
        "composite_score", ascending=False
    )

    if sector_df.empty:
        return {}

    # Rating distribution
    rating_counts = {}
    for rating in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]:
        rating_counts[rating] = len(sector_df[sector_df["overall_rating"] == rating])

    # Pillar averages
    pillar_avgs = {}
    for pillar in PILLAR_METRICS:
        score_col = f"{pillar}_score"
        if score_col in sector_df.columns:
            pillar_avgs[pillar] = {
                "avg": round(sector_df[score_col].mean(), 1),
                "median": round(sector_df[score_col].median(), 1),
                "max": round(sector_df[score_col].max(), 1),
                "min": round(sector_df[score_col].min(), 1),
                "grade": _score_to_grade(sector_df[score_col].mean()),
            }

    # Display columns
    display_cols = ["shortName", "currentPrice", "marketCapB"]
    for pillar in PILLAR_METRICS:
        display_cols.append(f"{pillar}_grade")
    display_cols += ["composite_score", "overall_rating"]

    available_cols = [c for c in display_cols if c in sector_df.columns]
    stocks_df = sector_df[available_cols].copy()

    return {
        "sector": sector,
        "num_stocks": len(sector_df),
        "rating_counts": rating_counts,
        "pillar_avgs": pillar_avgs,
        "composite_avg": round(sector_df["composite_score"].mean(), 2),
        "composite_median": round(sector_df["composite_score"].median(), 2),
        "stocks_df": stocks_df,
    }


def _score_to_grade(score: float) -> str:
    """Convert numeric score to letter grade."""
    if pd.isna(score):
        return "F"
    best_grade = "F"
    best_diff = float("inf")
    for grade, num in GRADE_SCORES.items():
        diff = abs(score - num)
        if diff < best_diff:
            best_diff = diff
            best_grade = grade
    return best_grade
