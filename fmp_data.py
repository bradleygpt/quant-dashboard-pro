"""
Financial Modeling Prep (FMP) Data Fetcher
Pulls 5+ years of quarterly EPS data with reported vs estimated and surprise %.

Free tier: 250 requests/day. Cache aggressively to stay under limit.
"""

import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime


def _get_fmp_key():
    """Lazy-load FMP API key from env or Streamlit secrets."""
    val = os.getenv("FMP_API_KEY")
    if val:
        return val
    try:
        if "FMP_API_KEY" in st.secrets:
            return st.secrets["FMP_API_KEY"]
    except Exception:
        pass
    return None


def is_fmp_configured():
    """Check if FMP is set up."""
    return bool(_get_fmp_key())


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_fmp_earnings_history(ticker, limit=40):
    """
    Fetch quarterly earnings history from FMP.
    Returns up to ~10 years of quarterly EPS with surprise data.

    Args:
        ticker: Stock ticker
        limit: Max number of quarters (default 40 = ~10 years)

    Returns:
        DataFrame with columns: date, reported_eps, estimated_eps, surprise_pct, revenue
        OR dict with "error" key if failed
    """
    api_key = _get_fmp_key()
    if not api_key:
        return {"error": "FMP_API_KEY not configured. Get a free key at https://site.financialmodelingprep.com/"}

    # Endpoint: historical-earnings-calendar gives EPS + revenue with surprises
    url = f"https://financialmodelingprep.com/api/v3/historical/earning_calendar/{ticker}"
    params = {"limit": limit, "apikey": api_key}

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 401:
            return {"error": "FMP API key invalid or expired"}
        if resp.status_code == 429:
            return {"error": "FMP daily quota exceeded (250/day on free tier)"}
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list) or len(data) == 0:
            return {"error": f"No earnings data returned for {ticker}"}

        # Normalize into DataFrame
        rows = []
        for entry in data:
            reported = entry.get("eps")
            estimated = entry.get("epsEstimated")
            date_str = entry.get("date")
            if not date_str or reported is None:
                continue
            try:
                date = pd.to_datetime(date_str)
            except Exception:
                continue
            # Skip future-dated entries
            if date > pd.Timestamp.now():
                continue

            surprise_pct = None
            if estimated and estimated != 0:
                surprise_pct = ((reported - estimated) / abs(estimated)) * 100

            rows.append({
                "date": date,
                "reported_eps": float(reported),
                "estimated_eps": float(estimated) if estimated is not None else None,
                "surprise_pct": round(surprise_pct, 1) if surprise_pct is not None else None,
                "revenue": entry.get("revenue"),
                "revenue_estimated": entry.get("revenueEstimated"),
            })

        if not rows:
            return {"error": f"No usable earnings data for {ticker}"}

        df = pd.DataFrame(rows)
        df = df.sort_values("date").reset_index(drop=True)
        df.set_index("date", inplace=True)
        return df
    except requests.HTTPError as e:
        return {"error": f"FMP HTTP error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"FMP fetch failed: {str(e)[:200]}"}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_fmp_revenue_history(ticker, limit=40):
    """
    Fetch quarterly revenue history from FMP income statement.
    Returns up to ~10 years of quarterly revenue.
    """
    api_key = _get_fmp_key()
    if not api_key:
        return {"error": "FMP_API_KEY not configured"}

    url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}"
    params = {"period": "quarter", "limit": limit, "apikey": api_key}

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 401:
            return {"error": "FMP API key invalid"}
        if resp.status_code == 429:
            return {"error": "FMP daily quota exceeded"}
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list) or len(data) == 0:
            return {"error": f"No revenue data for {ticker}"}

        rows = []
        for entry in data:
            date_str = entry.get("date")
            revenue = entry.get("revenue")
            if not date_str or revenue is None:
                continue
            try:
                date = pd.to_datetime(date_str)
            except Exception:
                continue
            rows.append({
                "date": date,
                "revenue": float(revenue),
                "net_income": float(entry.get("netIncome", 0) or 0),
                "eps_diluted": float(entry.get("epsdiluted", 0) or 0),
                "gross_profit": float(entry.get("grossProfit", 0) or 0),
                "operating_income": float(entry.get("operatingIncome", 0) or 0),
            })

        if not rows:
            return {"error": f"No revenue rows for {ticker}"}

        df = pd.DataFrame(rows)
        df = df.sort_values("date").reset_index(drop=True)
        df.set_index("date", inplace=True)
        return df
    except Exception as e:
        return {"error": f"FMP revenue fetch failed: {str(e)[:200]}"}


def get_combined_earnings_data(ticker, period_start=None):
    """
    Get the best available earnings data, combining FMP earnings calendar (with surprises)
    and FMP income statement (with revenue/full financials).

    Args:
        ticker: Stock ticker
        period_start: Optional pd.Timestamp to filter from

    Returns:
        Dict with 'earnings_df' (EPS+surprises), 'revenue_df' (financials), 'error' if any
    """
    earnings = fetch_fmp_earnings_history(ticker, limit=40)
    revenue = fetch_fmp_revenue_history(ticker, limit=40)

    result = {"ticker": ticker}

    if isinstance(earnings, dict) and "error" in earnings:
        result["earnings_error"] = earnings["error"]
        result["earnings_df"] = None
    else:
        df = earnings
        if period_start is not None:
            df = df[df.index >= period_start]
        result["earnings_df"] = df

    if isinstance(revenue, dict) and "error" in revenue:
        result["revenue_error"] = revenue["error"]
        result["revenue_df"] = None
    else:
        df = revenue
        if period_start is not None:
            df = df[df.index >= period_start]
        result["revenue_df"] = df

    return result
