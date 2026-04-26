"""
Financial Modeling Prep (FMP) Data Fetcher
Pulls 5+ years of quarterly EPS via the income statement endpoint.

NOTE: FMP free tier ("Basic" plan) does NOT include the historical earnings calendar
endpoint (returns 403). However, the quarterly income statement endpoint IS included
and contains diluted EPS going back ~5 years.

Trade-off: We get full EPS history but no analyst-estimate-vs-actual surprise data.
We color bars by EPS direction (growing green / declining red) instead.

Free tier: 250 requests/day. Cache aggressively.
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
def fetch_fmp_quarterly_financials(ticker, limit=40):
    """
    Fetch quarterly income statement from FMP.
    Free tier compatible. Returns ~5 years of quarterly diluted EPS + revenue.

    Args:
        ticker: Stock ticker
        limit: Max number of quarters (default 40 = ~10 years, free tier capped at ~20)

    Returns:
        DataFrame indexed by date with: eps_diluted, eps_basic, revenue,
        net_income, gross_profit, operating_income
        OR dict with "error" key if failed
    """
    api_key = _get_fmp_key()
    if not api_key:
        return {"error": "FMP_API_KEY not configured. Get a free key at https://site.financialmodelingprep.com/"}

    url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}"
    params = {"period": "quarter", "limit": limit, "apikey": api_key}

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 401:
            return {"error": "FMP API key invalid or expired"}
        if resp.status_code == 403:
            return {"error": "FMP 403: Income statement endpoint not available on your plan. Free tier should include this — check your account at financialmodelingprep.com/dashboard"}
        if resp.status_code == 429:
            return {"error": "FMP daily quota exceeded (250/day on free tier)"}
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list) or len(data) == 0:
            return {"error": f"No financial data returned for {ticker}"}

        rows = []
        for entry in data:
            date_str = entry.get("date")
            if not date_str:
                continue
            try:
                date = pd.to_datetime(date_str)
            except Exception:
                continue
            rows.append({
                "date": date,
                "eps_diluted": float(entry.get("epsdiluted")) if entry.get("epsdiluted") is not None else None,
                "eps_basic": float(entry.get("eps")) if entry.get("eps") is not None else None,
                "revenue": float(entry.get("revenue")) if entry.get("revenue") is not None else None,
                "net_income": float(entry.get("netIncome")) if entry.get("netIncome") is not None else None,
                "gross_profit": float(entry.get("grossProfit")) if entry.get("grossProfit") is not None else None,
                "operating_income": float(entry.get("operatingIncome")) if entry.get("operatingIncome") is not None else None,
            })

        if not rows:
            return {"error": f"No usable data rows for {ticker}"}

        df = pd.DataFrame(rows)
        df = df.sort_values("date").reset_index(drop=True)
        df.set_index("date", inplace=True)
        return df
    except requests.HTTPError as e:
        return {"error": f"FMP HTTP error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"FMP fetch failed: {str(e)[:200]}"}


def get_combined_earnings_data(ticker, period_start=None):
    """
    Get earnings + revenue data via the free-tier-compatible income statement endpoint.

    Args:
        ticker: Stock ticker
        period_start: Optional pd.Timestamp to filter from

    Returns:
        Dict with:
            - earnings_df: DataFrame indexed by date with reported_eps column
            - revenue_df: same DataFrame for revenue display
            - earnings_error / revenue_error: Error message if failed
    """
    fin = fetch_fmp_quarterly_financials(ticker, limit=40)

    result = {"ticker": ticker}

    if isinstance(fin, dict) and "error" in fin:
        result["earnings_error"] = fin["error"]
        result["revenue_error"] = fin["error"]
        result["earnings_df"] = None
        result["revenue_df"] = None
        return result

    df = fin
    if period_start is not None:
        df = df[df.index >= period_start]

    # Build earnings_df (with reported_eps for chart)
    if "eps_diluted" in df.columns:
        eps_data = df["eps_diluted"].dropna()
        if not eps_data.empty:
            earnings_df = pd.DataFrame({"reported_eps": eps_data})
            # No surprise data on free tier - column omitted
            result["earnings_df"] = earnings_df
        else:
            # Fall back to basic EPS if diluted unavailable
            eps_basic = df["eps_basic"].dropna() if "eps_basic" in df.columns else pd.Series()
            if not eps_basic.empty:
                result["earnings_df"] = pd.DataFrame({"reported_eps": eps_basic})
            else:
                result["earnings_df"] = None
                result["earnings_error"] = "No EPS data in returned rows"
    else:
        result["earnings_df"] = None

    # Build revenue_df
    if "revenue" in df.columns:
        rev_data = df["revenue"].dropna()
        if not rev_data.empty:
            result["revenue_df"] = pd.DataFrame({"revenue": rev_data})
        else:
            result["revenue_df"] = None
    else:
        result["revenue_df"] = None

    return result
