"""
Unified Earnings Data Fetcher
Orchestrates multiple data sources with graceful fallback:

1. Finnhub (primary) - Best UX with surprise data, ~4 years
2. SEC EDGAR (fallback) - Free forever, 5+ years, authoritative
3. yfinance (final fallback) - Minimal data, ~5 quarters

Each source is tried in order. The first one that returns usable data wins.
"""

import pandas as pd
from finnhub_data import is_finnhub_configured, get_finnhub_earnings_data
from edgar_data import get_edgar_earnings_data, is_edgar_available


def get_earnings_data(ticker, period_start=None):
    """
    Fetch earnings + revenue data from the best available source.

    Returns:
        {
          "earnings_df": DataFrame with reported_eps (and optionally surprise_pct),
          "revenue_df": DataFrame with revenue,
          "source": "finnhub" | "sec_edgar" | "none",
          "source_label": Human-readable label,
          "errors_by_source": Dict of attempted sources -> error msgs,
          "n_quarters": Count of EPS quarters returned,
          "has_surprises": True if surprise data is included,
        }
    """
    errors = {}
    earnings_df = None
    revenue_df = None
    source = None
    source_label = None
    has_surprises = False

    # ── Try Finnhub first ──
    if is_finnhub_configured():
        try:
            finnhub_result = get_finnhub_earnings_data(ticker, period_start=period_start)
            fh_earnings = finnhub_result.get("earnings_df")
            if fh_earnings is not None and not fh_earnings.empty:
                earnings_df = fh_earnings
                source = "finnhub"
                source_label = "Finnhub"
                # Check if surprise data is present
                if "surprise_pct" in earnings_df.columns:
                    surprises_present = earnings_df["surprise_pct"].dropna()
                    has_surprises = not surprises_present.empty
            else:
                errors["finnhub_earnings"] = finnhub_result.get("earnings_error", "Finnhub returned empty earnings")

            fh_revenue = finnhub_result.get("revenue_df")
            if fh_revenue is not None and not fh_revenue.empty:
                revenue_df = fh_revenue
            else:
                errors["finnhub_revenue"] = finnhub_result.get("revenue_error", "Finnhub returned empty revenue")
        except Exception as e:
            errors["finnhub"] = f"Finnhub exception: {str(e)[:120]}"
    else:
        errors["finnhub"] = "FINNHUB_API_KEY not configured"

    # ── Fallback to SEC EDGAR if Finnhub didn't fully succeed ──
    need_edgar = (earnings_df is None or earnings_df.empty) or (revenue_df is None or revenue_df.empty)
    if need_edgar:
        try:
            edgar_result = get_edgar_earnings_data(ticker, period_start=period_start)

            # Use EDGAR for earnings if Finnhub didn't get any
            if earnings_df is None or earnings_df.empty:
                ed_earnings = edgar_result.get("earnings_df")
                if ed_earnings is not None and not ed_earnings.empty:
                    earnings_df = ed_earnings
                    source = source or "sec_edgar"
                    source_label = source_label or "SEC EDGAR"
                else:
                    errors["edgar_earnings"] = edgar_result.get("earnings_error", "EDGAR returned no earnings")

            # Use EDGAR for revenue if Finnhub didn't get any
            if revenue_df is None or revenue_df.empty:
                ed_revenue = edgar_result.get("revenue_df")
                if ed_revenue is not None and not ed_revenue.empty:
                    revenue_df = ed_revenue
                else:
                    errors["edgar_revenue"] = edgar_result.get("revenue_error", "EDGAR returned no revenue")
        except Exception as e:
            errors["edgar"] = f"EDGAR exception: {str(e)[:120]}"

    if source is None:
        source = "none"
        source_label = "Yahoo Finance fallback"

    return {
        "earnings_df": earnings_df,
        "revenue_df": revenue_df,
        "source": source,
        "source_label": source_label,
        "errors_by_source": errors,
        "n_quarters": len(earnings_df) if earnings_df is not None and not earnings_df.empty else 0,
        "n_revenue_quarters": len(revenue_df) if revenue_df is not None and not revenue_df.empty else 0,
        "has_surprises": has_surprises,
    }


def test_earnings_sources(ticker="AAPL"):
    """
    Diagnostic: test each data source with a known good ticker.
    Returns dict of source -> (success, message).
    """
    results = {}

    # Test Finnhub
    if is_finnhub_configured():
        fh = get_finnhub_earnings_data(ticker)
        eps_df = fh.get("earnings_df")
        if eps_df is not None and not eps_df.empty:
            results["finnhub"] = (True, f"Got {len(eps_df)} quarters")
        else:
            results["finnhub"] = (False, fh.get("earnings_error", "Empty response"))
    else:
        results["finnhub"] = (False, "API key not configured")

    # Test EDGAR
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
