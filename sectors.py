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

    # Pre-compute cross-sector pillar averages for ranking-based grades
    # This avoids the "everything is B- because sector-relative pulls all to ~7" issue
    sector_pillar_avgs = {}
    for sector in sorted(sectors):
        if sector == "ETF":
            continue
        sector_df = scored_df[scored_df["sector"] == sector]
        if len(sector_df) == 0:
            continue
        for pillar in PILLAR_METRICS:
            score_col = f"{pillar}_score"
            if score_col in sector_df.columns:
                avg = sector_df[score_col].mean()
                if pillar not in sector_pillar_avgs:
                    sector_pillar_avgs[pillar] = {}
                sector_pillar_avgs[pillar][sector] = avg

    # Build percentile-based grades per pillar
    # If a sector ranks in top 10% across pillars, it gets A; bottom 10% gets F
    sector_pillar_grades = {}
    for pillar, sector_avgs in sector_pillar_avgs.items():
        if not sector_avgs:
            continue
        sorted_sectors = sorted(sector_avgs.items(), key=lambda x: x[1], reverse=True)
        n_sectors = len(sorted_sectors)
        for rank, (sector, avg) in enumerate(sorted_sectors):
            percentile = (n_sectors - rank - 1) / max(1, n_sectors - 1)  # 0=worst, 1=best
            if percentile >= 0.90: grade = "A+"
            elif percentile >= 0.80: grade = "A"
            elif percentile >= 0.70: grade = "A-"
            elif percentile >= 0.60: grade = "B+"
            elif percentile >= 0.50: grade = "B"
            elif percentile >= 0.40: grade = "B-"
            elif percentile >= 0.30: grade = "C+"
            elif percentile >= 0.20: grade = "C"
            elif percentile >= 0.10: grade = "C-"
            else: grade = "D"
            if pillar not in sector_pillar_grades:
                sector_pillar_grades[pillar] = {}
            sector_pillar_grades[pillar][sector] = grade

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

        # Pillar averages with cross-sector percentile-based grades
        for pillar in PILLAR_METRICS:
            score_col = f"{pillar}_score"
            if score_col in sector_df.columns:
                avg = sector_df[score_col].mean()
                row[f"{pillar}_avg"] = round(avg, 1)
                # Use cross-sector ranking grade instead of absolute
                row[f"{pillar}_grade"] = sector_pillar_grades.get(pillar, {}).get(sector, "N/A")
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
