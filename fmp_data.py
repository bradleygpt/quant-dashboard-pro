"""
Financial Modeling Prep (FMP) Data Fetcher
Uses /stable endpoint for free-tier access. Falls through multiple endpoint patterns
since FMP's free tier coverage has shifted over time.

Strategy:
1. Try /stable/income-statement (current free-tier endpoint as of 2026)
2. Try /api/v3/income-statement (legacy, may be paid-only now)
3. Each call's exact URL is exposed in error messages for debugging.
"""

import os
import requests
import pandas as pd
import streamlit as st


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
    return bool(_get_fmp_key())


def _try_endpoint(url, params, timeout=15):
    """Try a single endpoint and return (data, error_msg). Data is None on error."""
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return data, None
            return None, f"Empty response from {url.split('?')[0]}"
        elif resp.status_code == 401:
            return None, f"401 Unauthorized: API key invalid"
        elif resp.status_code == 403:
            return None, f"403 Forbidden: endpoint not on free plan ({url.split('?')[0]})"
        elif resp.status_code == 429:
            return None, f"429: daily quota exceeded"
        else:
            return None, f"HTTP {resp.status_code} from {url.split('?')[0]}"
    except requests.Timeout:
        return None, "FMP request timeout"
    except Exception as e:
        return None, f"FMP error: {str(e)[:120]}"


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_fmp_quarterly_financials(ticker, limit=40):
    """
    Fetch quarterly income statement.

    Tries /stable/ endpoint first (current free tier), falls back to /api/v3/
    if needed. Returns DataFrame or {"error": msg}.
    """
    api_key = _get_fmp_key()
    if not api_key:
        return {"error": "FMP_API_KEY not configured"}

    # Try /stable endpoint first - current FMP free tier path
    endpoints_to_try = [
        ("https://financialmodelingprep.com/stable/income-statement",
         {"symbol": ticker, "period": "quarter", "limit": limit, "apikey": api_key}),
        ("https://financialmodelingprep.com/api/v3/income-statement/" + ticker,
         {"period": "quarter", "limit": limit, "apikey": api_key}),
    ]

    last_error = None
    data = None
    successful_endpoint = None

    for url, params in endpoints_to_try:
        data, err = _try_endpoint(url, params)
        if data is not None:
            successful_endpoint = url
            break
        last_error = err

    if data is None:
        return {"error": last_error or "All FMP endpoints failed"}

    # Parse the data
    rows = []
    for entry in data:
        date_str = entry.get("date") or entry.get("fillingDate") or entry.get("acceptedDate")
        if not date_str:
            continue
        try:
            date = pd.to_datetime(date_str)
        except Exception:
            continue
        rows.append({
            "date": date,
            "eps_diluted": float(entry.get("epsdiluted")) if entry.get("epsdiluted") not in (None, "") else None,
            "eps_basic": float(entry.get("eps")) if entry.get("eps") not in (None, "") else None,
            "revenue": float(entry.get("revenue")) if entry.get("revenue") not in (None, "") else None,
            "net_income": float(entry.get("netIncome")) if entry.get("netIncome") not in (None, "") else None,
            "gross_profit": float(entry.get("grossProfit")) if entry.get("grossProfit") not in (None, "") else None,
            "operating_income": float(entry.get("operatingIncome")) if entry.get("operatingIncome") not in (None, "") else None,
        })

    if not rows:
        return {"error": f"No usable rows in FMP response for {ticker}"}

    df = pd.DataFrame(rows)
    df = df.sort_values("date").reset_index(drop=True)
    df.set_index("date", inplace=True)
    df.attrs["fmp_endpoint"] = successful_endpoint
    return df


def get_combined_earnings_data(ticker, period_start=None):
    """
    Get earnings + revenue data via FMP. Returns dict with earnings_df, revenue_df.
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
    fmp_endpoint = df.attrs.get("fmp_endpoint", "unknown") if hasattr(df, 'attrs') else "unknown"
    if period_start is not None:
        df = df[df.index >= period_start]

    # Build earnings_df
    if "eps_diluted" in df.columns:
        eps_data = df["eps_diluted"].dropna()
        if not eps_data.empty:
            edf = pd.DataFrame({"reported_eps": eps_data})
            edf.attrs["fmp_endpoint"] = fmp_endpoint
            result["earnings_df"] = edf
        else:
            eps_basic = df["eps_basic"].dropna() if "eps_basic" in df.columns else pd.Series()
            if not eps_basic.empty:
                edf = pd.DataFrame({"reported_eps": eps_basic})
                edf.attrs["fmp_endpoint"] = fmp_endpoint
                result["earnings_df"] = edf
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
