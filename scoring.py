"""
Scoring engine with SECTOR-RELATIVE grading.
Stocks are ranked within their sector, not the entire universe.
This means a bank is compared to other banks, not to SaaS companies.

Rating system aligned to the Top25 1Q-reselect backtested strategy:
- Strong Buy + Buy ALWAYS total 25 stocks (the backtested portfolio size)
- Split between Strong Buy and Buy uses cliff-detection within the top 25:
  the largest score gap defines the conviction tier boundary
- Hold / Sell / Strong Sell use score bands for ranks 26+
- ETFs use the original score-band logic since they're not part of the portfolio strategy
"""
import numpy as np
import pandas as pd
from config import (
    PILLAR_METRICS,
    GRADE_PERCENTILE_MAP,
    GRADE_SCORES,
    OVERALL_RATING_MAP,
    DEFAULT_PILLAR_WEIGHTS,
)

# ── Top-N portfolio strategy constants ──
# The validated backtested strategy is TOP25 quarterly rebalance.
# SB + B must always equal this number.
TOP_PORTFOLIO_N = 25

# Cliff detection parameters for splitting SB vs B within the top 25
CLIFF_MIN_ABSOLUTE_GAP = 0.5       # minimum score points to qualify as a cliff
CLIFF_MIN_RELATIVE_MULTIPLE = 2.0  # cliff must be >= this x the average gap


def score_universe(
    data: dict[str, dict],
    weights: dict[str, float] | None = None,
    sector_relative: bool = True,
    preset_name: str | None = None,
) -> pd.DataFrame:
    """
    Score all tickers across the five pillars.
    If sector_relative=True, percentile ranks are computed within each sector.
    """
    if not data:
        return pd.DataFrame()

    weights = weights or DEFAULT_PILLAR_WEIGHTS
    df = pd.DataFrame.from_dict(data, orient="index")
    df.index.name = "ticker"

    # Score each pillar
    pillar_scores = {}
    pillar_grades = {}
    metric_grades = {}
    metric_percentiles = {}

    for pillar_name, metrics in PILLAR_METRICS.items():
        pillar_metric_scores = []
        for yf_key, display_name, higher_is_better in metrics:
            if yf_key not in df.columns:
                continue
            col = pd.to_numeric(df[yf_key], errors="coerce")

            if sector_relative and "sector" in df.columns:
                # Rank within each sector
                if higher_is_better:
                    pct = col.groupby(df["sector"]).rank(pct=True, na_option="bottom") * 100
                else:
                    pct = (1 - col.groupby(df["sector"]).rank(pct=True, na_option="bottom")) * 100
            else:
                # Universe-wide rank
                if higher_is_better:
                    pct = col.rank(pct=True, na_option="bottom") * 100
                else:
                    pct = (1 - col.rank(pct=True, na_option="bottom")) * 100

            grades = pct.apply(_percentile_to_grade)
            grade_nums = grades.map(GRADE_SCORES).fillna(1)

            metric_grades[f"{pillar_name}|{display_name}"] = grades
            metric_percentiles[f"{pillar_name}|{display_name}"] = pct
            pillar_metric_scores.append(grade_nums)

        if pillar_metric_scores:
            pillar_avg = pd.concat(pillar_metric_scores, axis=1).mean(axis=1)
            pillar_scores[pillar_name] = pillar_avg
            pillar_grades[pillar_name] = pillar_avg.apply(_score_to_grade)
        else:
            pillar_scores[pillar_name] = pd.Series(1, index=df.index)
            pillar_grades[pillar_name] = pd.Series("F", index=df.index)

    # Weighted composite
    composite = pd.Series(0.0, index=df.index)
    for pillar_name, w in weights.items():
        if pillar_name in pillar_scores:
            composite += pillar_scores[pillar_name] * w

    total_weight = sum(w for p, w in weights.items() if p in pillar_scores)
    if total_weight > 0:
        composite = composite / total_weight * (sum(weights.values()))

    # Build result with ALL raw metric columns
    keep_cols = ["shortName", "sector", "industry", "marketCap", "currentPrice"]
    for pillar_name, metrics in PILLAR_METRICS.items():
        for yf_key, display_name, higher_is_better in metrics:
            if yf_key in df.columns:
                keep_cols.append(yf_key)

    result = df[keep_cols].copy()
    result["marketCapB"] = (result["marketCap"] / 1e9).round(1)

    for pillar_name in PILLAR_METRICS:
        result[f"{pillar_name}_score"] = pillar_scores.get(pillar_name, 1).round(2)
        result[f"{pillar_name}_grade"] = pillar_grades.get(pillar_name, "F")

    for key, grades in metric_grades.items():
        result[f"metric|{key}"] = grades
    for key, pcts in metric_percentiles.items():
        result[f"pct|{key}"] = pcts

    result["composite_score"] = composite.round(2)

    # Rating assignment via Top25 + cliff detection
    result["overall_rating"] = _assign_ratings_top25(result)

    result = result.sort_values("composite_score", ascending=False)

    return result


def _assign_ratings_top25(scored_df: pd.DataFrame) -> pd.Series:
    """
    Assign overall_rating aligned with the backtested Top25 1Q-reselect strategy.

    Strong Buy and Buy are EXCLUSIVE to the top 25 non-ETF stocks. SB + B = 25 always
    (or fewer if the eligible universe has fewer than 25 stocks).

    Algorithm:
    1. Rank all NON-ETF stocks by composite_score descending.
    2. Top 25 stocks become Strong Buy or Buy. Within the top 25, find the largest
       score gap between consecutive ranks. If that gap is >= CLIFF_MIN_ABSOLUTE_GAP
       AND >= CLIFF_MIN_RELATIVE_MULTIPLE x the average gap, it's a real cliff:
         - Stocks above the cliff = Strong Buy
         - Stocks below the cliff = Buy
       Otherwise (no clear cliff), all 25 = Buy.
    3. Ranks 26+ and all ETFs get Hold / Sell / Strong Sell based on their composite
       score, but are CAPPED at Hold maximum (cannot be SB/B regardless of score).
    """
    # Step 1: Apply score-band rating to EVERY row, but cap at Hold maximum
    # (SB/B from score bands are floored to Hold; the top-25 logic is the ONLY
    # path to SB/B)
    ratings = scored_df["composite_score"].apply(_score_to_rating_band_capped_at_hold)

    # Step 2: Identify non-ETF stocks (the eligible portfolio universe)
    if "sector" in scored_df.columns:
        is_stock = scored_df["sector"] != "ETF"
    else:
        is_stock = pd.Series(True, index=scored_df.index)

    stock_df = scored_df[is_stock].copy()

    if len(stock_df) == 0:
        return ratings

    # Step 3: Sort eligible stocks by composite descending
    stock_df_sorted = stock_df.sort_values("composite_score", ascending=False)

    # Step 4: Take the top N (or all stocks if universe is smaller)
    n_take = min(TOP_PORTFOLIO_N, len(stock_df_sorted))
    top_tickers = stock_df_sorted.index[:n_take].tolist()
    top_scores = stock_df_sorted["composite_score"].iloc[:n_take].values

    # Step 5: Default — every top-N stock is Buy
    sb_tickers = []
    b_tickers = list(top_tickers)

    # Step 6: Cliff detection — find the largest gap in the top N scores
    if n_take >= 2:
        # diff in descending-sorted array is negative; flip sign for positive gaps
        gaps = -np.diff(top_scores)
        max_gap = float(gaps.max()) if len(gaps) > 0 else 0.0
        avg_gap = float(gaps.mean()) if len(gaps) > 0 else 0.0

        cliff_qualifies = (
            max_gap >= CLIFF_MIN_ABSOLUTE_GAP
            and (avg_gap == 0 or max_gap >= CLIFF_MIN_RELATIVE_MULTIPLE * avg_gap)
        )

        if cliff_qualifies:
            cliff_position = int(np.argmax(gaps))
            # Strong Buy = ranks 0 through cliff_position (inclusive)
            # Buy = ranks cliff_position+1 through n_take-1
            sb_tickers = top_tickers[: cliff_position + 1]
            b_tickers = top_tickers[cliff_position + 1 :]

    # Step 7: Apply SB/B ratings to the top 25
    for t in sb_tickers:
        ratings.loc[t] = "Strong Buy"
    for t in b_tickers:
        ratings.loc[t] = "Buy"

    return ratings


def _score_to_rating_band_capped_at_hold(score: float) -> str:
    """
    Map a composite score to Hold / Sell / Strong Sell.
    Strong Buy and Buy are intentionally NOT returned here — those are reserved
    for the top-25 stocks identified by _assign_ratings_top25.

    Score bands (from OVERALL_RATING_MAP, but SB/B capped to Hold):
      score >= 8.0  -> Hold (would have been SB/B but capped)
      6.0-8.0       -> Hold
      5.0-6.0       -> Sell
      < 5.0         -> Strong Sell
    """
    if pd.isna(score):
        return "Hold"
    if score >= 6.0:
        return "Hold"
    if score >= 5.0:
        return "Sell"
    return "Strong Sell"


# Legacy helpers kept for backward compatibility
def _score_to_rating_band(score: float) -> str:
    """Original full score-band mapping. Not used in the active rating logic
    but kept for any external callers."""
    if pd.isna(score):
        return "Hold"
    for rating, (low, high) in OVERALL_RATING_MAP.items():
        if low <= score <= high:
            return rating
    return "Hold"


def _score_to_rating(score: float) -> str:
    """Legacy alias kept for backward compatibility with external imports."""
    return _score_to_rating_band(score)


# ── Sector Statistics ──────────────────────────────────────────────

def get_sector_stats(scored_df: pd.DataFrame) -> dict:
    """
    Compute sector averages and A-grade thresholds for every metric.
    Returns dict of {metric_key: {sector: {mean, median, a_threshold}}}.
    """
    stats = {}
    for pillar_name, metrics in PILLAR_METRICS.items():
        for yf_key, display_name, higher_is_better in metrics:
            if yf_key not in scored_df.columns:
                continue
            col = pd.to_numeric(scored_df[yf_key], errors="coerce")
            key = f"{pillar_name}|{display_name}"
            stats[key] = {}
            for sector in scored_df["sector"].dropna().unique():
                sector_vals = col[scored_df["sector"] == sector].dropna()
                if len(sector_vals) < 3:
                    continue
                mean_val = sector_vals.mean()
                median_val = sector_vals.median()
                # A-grade threshold = 85th percentile within sector
                if higher_is_better:
                    a_threshold = sector_vals.quantile(0.85)
                else:
                    a_threshold = sector_vals.quantile(0.15)
                stats[key][sector] = {
                    "mean": mean_val,
                    "median": median_val,
                    "a_threshold": a_threshold,
                    "count": len(sector_vals),
                }
    return stats


# ── Detail View ────────────────────────────────────────────────────

def get_pillar_detail(ticker: str, scored_df: pd.DataFrame, sector_stats: dict = None) -> dict:
    """
    Get detailed metric breakdown with sector averages and A-grade thresholds.
    """
    if ticker not in scored_df.index:
        return {}
    row = scored_df.loc[ticker]
    ticker_sector = row.get("sector", "Unknown")
    detail = {}
    for pillar_name, metrics in PILLAR_METRICS.items():
        pillar_detail = []
        for yf_key, display_name, higher_is_better in metrics:
            raw_val = row.get(yf_key)
            grade_key = f"metric|{pillar_name}|{display_name}"
            grade = row.get(grade_key, "N/A")
            pct_key = f"pct|{pillar_name}|{display_name}"
            percentile = row.get(pct_key)
            # Format raw value
            formatted = _format_value(raw_val, display_name)
            # Get sector stats
            sector_avg = "N/A"
            sector_median = "N/A"
            a_threshold = "N/A"
            if sector_stats:
                stat_key = f"{pillar_name}|{display_name}"
                if stat_key in sector_stats and ticker_sector in sector_stats[stat_key]:
                    s = sector_stats[stat_key][ticker_sector]
                    sector_avg = _format_value(s["mean"], display_name)
                    sector_median = _format_value(s["median"], display_name)
                    a_threshold = _format_value(s["a_threshold"], display_name)
            pillar_detail.append({
                "metric": display_name,
                "value": formatted,
                "grade": grade if grade != "N/A" else "---",
                "percentile": f"{percentile:.0f}th" if percentile is not None and not (isinstance(percentile, float) and np.isnan(percentile)) else "---",
                "sector_avg": sector_avg,
                "a_threshold": a_threshold,
                "higher_is_better": higher_is_better,
            })
        detail[pillar_name] = {
            "metrics": pillar_detail,
            "pillar_grade": row.get(f"{pillar_name}_grade", "N/A"),
            "pillar_score": row.get(f"{pillar_name}_score", 0),
        }
    return detail


def _format_value(raw_val, display_name: str) -> str:
    """Format a raw metric value for display."""
    if raw_val is None or (isinstance(raw_val, float) and np.isnan(raw_val)):
        return "N/A"
    try:
        raw_val = float(raw_val)
    except (ValueError, TypeError):
        return str(raw_val)
    if any(kw in display_name.lower() for kw in ["margin", "return", "growth", "upside", "surprise"]):
        if abs(raw_val) < 10:
            return f"{raw_val * 100:.1f}%"
        else:
            return f"{raw_val:.1f}%"
    elif any(kw in display_name.lower() for kw in ["p/e", "peg", "ev", "price"]):
        return f"{raw_val:.1f}x"
    elif display_name.startswith("#"):
        return f"{int(raw_val)}"
    elif "score" in display_name.lower():
        return f"{raw_val:.2f}"
    elif "month" in display_name.lower() or "sma" in display_name.lower():
        return f"{raw_val * 100:.1f}%"
    else:
        return f"{raw_val:.2f}"


# ── Grade Helpers ──────────────────────────────────────────────────

def _percentile_to_grade(pct: float) -> str:
    if pd.isna(pct):
        return "F"
    for grade, (low, high) in GRADE_PERCENTILE_MAP.items():
        if low <= pct < high:
            return grade
    if pct >= 100:
        return "A+"
    return "F"


def _score_to_grade(score: float) -> str:
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


def get_top_stocks(
    scored_df: pd.DataFrame,
    n: int = 25,
    sector: str | None = None,
    rating_filter: str | None = None,
) -> pd.DataFrame:
    df = scored_df.copy()
    if sector and sector != "All":
        df = df[df["sector"] == sector]
    if rating_filter and rating_filter != "All":
        df = df[df["overall_rating"] == rating_filter]
    return df.head(n)
