"""
Unified Earnings Data Fetcher (Smart Merge)
============================================

Orchestrates multiple data sources, MERGING results to fill gaps:

1. Finnhub (primary) - Best UX with surprise data (beat/miss vs estimates)
2. SEC EDGAR (gap-filler) - Free, complete history, authoritative
3. yfinance (final fallback) - Minimal data, last resort

Key change from prior version: Instead of using EDGAR ONLY when Finnhub fails,
we now MERGE EDGAR data into Finnhub data to fill any quarterly gaps.

This solves the problem where Finnhub returns 17 of 20 expected quarters —
the missing 3 get filled in from EDGAR, giving the user a complete history.

Surprise data only comes from Finnhub (EDGAR doesn't have analyst estimates),
so quarters filled from EDGAR will show as "no estimate available" (gray).
"""

import pandas as pd
from finnhub_data import is_finnhub_configured, get_finnhub_earnings_data
from edgar_data import get_edgar_earnings_data, is_edgar_available


def _expected_quarters_in_range(period_start, period_end=None):
    """Estimate expected quarter count for the date range."""
    if period_start is None:
        return None
    if period_end is None:
        period_end = pd.Timestamp.now()

    try:
        start = pd.Timestamp(period_start)
        end = pd.Timestamp(period_end)
        days = (end - start).days
        return max(1, int(days / 91))
    except Exception:
        return None


def _merge_earnings_dataframes(primary_df, secondary_df, tolerance_days=45):
    """
    Merge two earnings DataFrames, filling gaps from secondary into primary.

    Two earnings reports for the same quarter typically have dates within a
    couple weeks of each other (filing date vs quarter-end date), so we
    consider quarters "the same" if their dates are within ~45 days.

    Args:
        primary_df: Primary source (Finnhub) — has surprise data
        secondary_df: Secondary source (EDGAR) — has more complete history
        tolerance_days: How close two dates must be to be considered the same quarter

    Returns merged DataFrame with all quarters from both, preferring primary
    when dates overlap.
    """
    if primary_df is None or primary_df.empty:
        return secondary_df
    if secondary_df is None or secondary_df.empty:
        return primary_df

    primary_df = primary_df.sort_index()
    secondary_df = secondary_df.sort_index()

    # Find secondary entries that don't have a primary counterpart within tolerance
    primary_dates = primary_df.index
    gap_filling_rows = []

    for sec_date in secondary_df.index:
        date_diffs = abs((primary_dates - sec_date).total_seconds() / 86400)
        min_diff = date_diffs.min() if len(date_diffs) > 0 else float('inf')

        if min_diff > tolerance_days:
            sec_row = secondary_df.loc[sec_date].to_dict()
            if "surprise_pct" not in sec_row:
                sec_row["surprise_pct"] = None
            gap_filling_rows.append((sec_date, sec_row))

    if not gap_filling_rows:
        return primary_df

    gap_df = pd.DataFrame(
        [r[1] for r in gap_filling_rows],
        index=[r[0] for r in gap_filling_rows]
    )

    # Ensure schema match
    for col in primary_df.columns:
        if col not in gap_df.columns:
            gap_df[col] = None

    merged = pd.concat([primary_df, gap_df[primary_df.columns]]).sort_index()
    merged = merged[~merged.index.duplicated(keep='first')]
    return merged


def get_earnings_data(ticker, period_start=None):
    """
    Fetch earnings + revenue data, MERGING multiple sources to fill gaps.

    Returns:
        {
          "earnings_df": Merged DataFrame with reported_eps + (optional) surprise_pct
          "revenue_df": Merged DataFrame with revenue
          "source": "finnhub" | "sec_edgar" | "merged" | "none"
          "source_label": Human-readable label noting which sources contributed
          "errors_by_source": Dict of attempted sources -> error msgs
          "n_quarters": Count of EPS quarters returned
          "n_quarters_with_surprises": Count of quarters with analyst estimate data
          "has_surprises": True if any surprise data is included
          "n_filled_from_edgar": Count of quarters that came from EDGAR gap-fill
          "n_expected": Estimated expected quarter count for the period
        }
    """
    errors = {}
    finnhub_earnings = None
    finnhub_revenue = None
    edgar_earnings = None
    edgar_revenue = None

    # ── Try Finnhub first ──
    if is_finnhub_configured():
        try:
            finnhub_result = get_finnhub_earnings_data(ticker, period_start=period_start)
            finnhub_earnings = finnhub_result.get("earnings_df")
            finnhub_revenue = finnhub_result.get("revenue_df")
            if finnhub_earnings is None or finnhub_earnings.empty:
                errors["finnhub_earnings"] = finnhub_result.get("earnings_error", "Finnhub returned empty earnings")
            if finnhub_revenue is None or finnhub_revenue.empty:
                errors["finnhub_revenue"] = finnhub_result.get("revenue_error", "Finnhub returned empty revenue")
        except Exception as e:
            errors["finnhub"] = f"Finnhub exception: {str(e)[:120]}"
    else:
        errors["finnhub"] = "FINNHUB_API_KEY not configured"

    # ── Always try EDGAR for gap-filling, not just fallback ──
    try:
        edgar_result = get_edgar_earnings_data(ticker, period_start=period_start)
        edgar_earnings = edgar_result.get("earnings_df")
        edgar_revenue = edgar_result.get("revenue_df")
        if edgar_earnings is None or edgar_earnings.empty:
            errors["edgar_earnings"] = edgar_result.get("earnings_error", "EDGAR returned no earnings")
        if edgar_revenue is None or edgar_revenue.empty:
            errors["edgar_revenue"] = edgar_result.get("revenue_error", "EDGAR returned no revenue")
    except Exception as e:
        errors["edgar"] = f"EDGAR exception: {str(e)[:120]}"

    # ── Smart merge: prefer Finnhub (has surprises), fill gaps from EDGAR ──
    n_filled_from_edgar = 0
    earnings_df = None
    if finnhub_earnings is not None and not finnhub_earnings.empty:
        if edgar_earnings is not None and not edgar_earnings.empty:
            n_before = len(finnhub_earnings)
            earnings_df = _merge_earnings_dataframes(finnhub_earnings, edgar_earnings)
            n_filled_from_edgar = len(earnings_df) - n_before
        else:
            earnings_df = finnhub_earnings
    elif edgar_earnings is not None and not edgar_earnings.empty:
        earnings_df = edgar_earnings

    revenue_df = None
    if finnhub_revenue is not None and not finnhub_revenue.empty:
        if edgar_revenue is not None and not edgar_revenue.empty:
            revenue_df = _merge_earnings_dataframes(finnhub_revenue, edgar_revenue)
        else:
            revenue_df = finnhub_revenue
    elif edgar_revenue is not None and not edgar_revenue.empty:
        revenue_df = edgar_revenue

    # ── Determine source label ──
    source = "none"
    source_label = "No data available"
    if earnings_df is not None and not earnings_df.empty:
        if finnhub_earnings is not None and not finnhub_earnings.empty and n_filled_from_edgar > 0:
            source = "merged"
            source_label = f"Finnhub + SEC EDGAR (merged: {len(earnings_df) - n_filled_from_edgar} from Finnhub, {n_filled_from_edgar} gap-filled from EDGAR)"
        elif finnhub_earnings is not None and not finnhub_earnings.empty:
            source = "finnhub"
            source_label = "Finnhub"
        elif edgar_earnings is not None and not edgar_earnings.empty:
            source = "sec_edgar"
            source_label = "SEC EDGAR"

    # ── Compute surprise data stats ──
    has_surprises = False
    n_with_surprises = 0
    if earnings_df is not None and not earnings_df.empty and "surprise_pct" in earnings_df.columns:
        surprises_present = earnings_df["surprise_pct"].dropna()
        has_surprises = not surprises_present.empty
        n_with_surprises = len(surprises_present)

    n_expected = _expected_quarters_in_range(period_start)

    return {
        "earnings_df": earnings_df,
        "revenue_df": revenue_df,
        "source": source,
        "source_label": source_label,
        "errors_by_source": errors,
        "n_quarters": len(earnings_df) if earnings_df is not None and not earnings_df.empty else 0,
        "n_quarters_with_surprises": n_with_surprises,
        "has_surprises": has_surprises,
        "n_filled_from_edgar": n_filled_from_edgar,
        "n_expected": n_expected,
    }


def test_earnings_sources(ticker="AAPL"):
    """
    Diagnostic: test each data source with a known good ticker.
    Returns dict of source -> (success, message).
    """
    results = {}

    if is_finnhub_configured():
        fh = get_finnhub_earnings_data(ticker)
        eps_df = fh.get("earnings_df")
        if eps_df is not None and not eps_df.empty:
            results["finnhub"] = (True, f"Got {len(eps_df)} quarters")
        else:
            results["finnhub"] = (False, fh.get("earnings_error", "Empty response"))
    else:
        results["finnhub"] = (False, "API key not configured")

    try:
        edgar = get_edgar_earnings_data(ticker)
        eps_df = edgar.get("earnings_df")
        if eps_df is not None and not eps_df.empty:
            results["sec_edgar"] = (True, f"Got {len(eps_df)} quarters")
        else:
            results["sec_edgar"] = (False, edgar.get("earnings_error", "Empty response"))
    except Exception as e:
        results["sec_edgar"] = (False, f"Exception: {str(e)[:120]}")

    return results
