"""
SEC EDGAR XBRL Data Fetcher
100% free, no API key required. Uses SEC's official company-facts JSON API.

Architecture:
1. Map ticker -> CIK (Central Index Key) using SEC company tickers JSON
2. Fetch company-facts JSON containing all XBRL concept tags
3. Extract EarningsPerShareDiluted and Revenues concepts
4. Match quarterly periods (10-Q filings) and parse fiscal periods

SEC requires a User-Agent header identifying the application.
Rate limit: 10 requests/second (we cache aggressively so this is plenty).
"""

import json
import os
import requests
import pandas as pd
import streamlit as st


# SEC requires a User-Agent identifying the requester
USER_AGENT = "QuantStrategyDashboard contact@example.com"


def _sec_headers():
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }


@st.cache_data(ttl=86400 * 7, show_spinner=False)
def get_ticker_to_cik_map():
    """
    Fetch SEC's master company tickers file. Maps ticker symbols to CIK numbers.
    Cached for 7 days since this rarely changes.
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        resp = requests.get(url, headers=_sec_headers(), timeout=20)
        resp.raise_for_status()
        data = resp.json()
        # Format: { "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ... }
        ticker_to_cik = {}
        for entry in data.values():
            ticker = entry.get("ticker", "").upper()
            cik = entry.get("cik_str")
            if ticker and cik:
                # CIK must be 10 digits zero-padded for company-facts URL
                ticker_to_cik[ticker] = str(cik).zfill(10)
        return ticker_to_cik
    except Exception as e:
        return {}


def get_cik_for_ticker(ticker):
    """Get CIK number for a ticker. Returns None if not found."""
    mapping = get_ticker_to_cik_map()
    return mapping.get(ticker.upper())


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_company_facts(ticker):
    """
    Fetch company facts JSON from SEC for a ticker.
    Returns the full XBRL facts dict or {"error": msg}.
    """
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return {"error": f"Ticker {ticker} not found in SEC database (may be foreign or recently listed)"}

    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        resp = requests.get(url, headers=_sec_headers(), timeout=20)
        if resp.status_code == 404:
            return {"error": f"SEC has no XBRL data for {ticker} (CIK {cik})"}
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"SEC fetch failed: {str(e)[:200]}"}


def _extract_concept_quarterly(facts, concept_name, units_preference=None):
    """
    Extract quarterly values for a specific XBRL concept.

    SEC XBRL concepts come in many "units" (USD, USD/shares, etc.).
    For EPS we want USD/shares. For revenue we want USD.

    Returns DataFrame indexed by period end date with 'value' column,
    or None if concept not found.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    concept_data = us_gaap.get(concept_name)
    if not concept_data:
        return None

    units_dict = concept_data.get("units", {})

    # Choose the right units
    if units_preference:
        unit_key = next((u for u in units_preference if u in units_dict), None)
    else:
        # Auto-pick: prefer USD/shares for EPS, USD for monetary
        unit_key = "USD/shares" if "USD/shares" in units_dict else ("USD" if "USD" in units_dict else None)

    if not unit_key:
        return None

    entries = units_dict.get(unit_key, [])
    if not entries:
        return None

    # Filter to 10-Q filings (quarterly) - these have 'fp' starting with 'Q' typically
    # Or filter to entries where the period (start to end) is ~3 months
    rows = []
    for entry in entries:
        end = entry.get("end")
        start = entry.get("start")
        val = entry.get("val")
        form = entry.get("form", "")
        fp = entry.get("fp", "")  # Q1, Q2, Q3, FY

        if not end or val is None:
            continue

        try:
            end_date = pd.to_datetime(end)
            start_date = pd.to_datetime(start) if start else None
        except Exception:
            continue

        # Quarterly filter: period length 80-100 days
        # OR fp explicitly Q1/Q2/Q3 (excludes FY which is annual)
        is_quarterly = False
        if start_date is not None:
            duration_days = (end_date - start_date).days
            if 80 <= duration_days <= 100:
                is_quarterly = True
        elif fp in ("Q1", "Q2", "Q3"):
            is_quarterly = True

        if not is_quarterly:
            continue

        rows.append({
            "date": end_date,
            "value": float(val),
            "form": form,
            "fp": fp,
        })

    if not rows:
        return None

    df = pd.DataFrame(rows)
    # Deduplicate by date - keep the latest filed value for each period (handles restatements)
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    df.set_index("date", inplace=True)
    return df[["value"]]


def get_edgar_earnings_data(ticker, period_start=None):
    """
    Get quarterly EPS and revenue data from SEC EDGAR.

    Returns:
        {
          "earnings_df": DataFrame with reported_eps,
          "revenue_df": DataFrame with revenue,
          "errors": dict of any partial failures,
          "source": "sec_edgar"
        }
    """
    result = {"ticker": ticker, "source": "sec_edgar", "errors": {}}

    facts = fetch_company_facts(ticker)
    if isinstance(facts, dict) and "error" in facts:
        result["earnings_df"] = None
        result["revenue_df"] = None
        result["earnings_error"] = facts["error"]
        result["revenue_error"] = facts["error"]
        return result

    # Try multiple EPS concepts (companies use slightly different ones)
    eps_concepts = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]
    eps_df = None
    for concept in eps_concepts:
        df = _extract_concept_quarterly(facts, concept, units_preference=["USD/shares"])
        if df is not None and not df.empty:
            eps_df = df.rename(columns={"value": "reported_eps"})
            break

    if eps_df is None:
        result["earnings_df"] = None
        result["earnings_error"] = "No EPS concept found in SEC XBRL data"
    else:
        if period_start is not None:
            eps_df = eps_df[eps_df.index >= period_start]
        result["earnings_df"] = eps_df if not eps_df.empty else None
        if eps_df.empty:
            result["earnings_error"] = "EPS data exists but none falls in the requested period"

    # Try multiple revenue concepts
    rev_concepts = [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",  # Newer ASC 606 standard
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ]
    rev_df = None
    for concept in rev_concepts:
        df = _extract_concept_quarterly(facts, concept, units_preference=["USD"])
        if df is not None and not df.empty:
            rev_df = df.rename(columns={"value": "revenue"})
            break

    if rev_df is None:
        result["revenue_df"] = None
        result["revenue_error"] = "No revenue concept found in SEC XBRL data"
    else:
        if period_start is not None:
            rev_df = rev_df[rev_df.index >= period_start]
        result["revenue_df"] = rev_df if not rev_df.empty else None
        if rev_df.empty:
            result["revenue_error"] = "Revenue data exists but none falls in requested period"

    return result


def is_edgar_available():
    """EDGAR is always 'available' since no key needed - check if tickers map loads."""
    try:
        m = get_ticker_to_cik_map()
        return len(m) > 100
    except Exception:
        return False
