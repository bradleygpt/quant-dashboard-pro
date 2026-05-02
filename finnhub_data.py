"""
Finnhub Data Fetcher
Pulls quarterly earnings (EPS, estimated vs actual, surprise %) and basic financials.

Free tier: 60 API calls/minute. The /stock/earnings endpoint returns up to 4 years
of quarterly EPS with surprise data. The /stock/financials-reported endpoint can
extend further but uses XBRL-style concept names which require parsing.

Strategy: Use /stock/earnings as primary (clean, simple), supplement with
/stock/financials-reported for revenue and longer history.
"""

import os
import requests
import pandas as pd
import streamlit as st


def _get_finnhub_key():
    """Lazy-load Finnhub API key from env or Streamlit secrets."""
    val = os.getenv("FINNHUB_API_KEY")
    if val:
        return val
    try:
        if "FINNHUB_API_KEY" in st.secrets:
            return st.secrets["FINNHUB_API_KEY"]
    except Exception:
        pass
    return None


def is_finnhub_configured():
    return bool(_get_finnhub_key())


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_finnhub_earnings(ticker, limit=50):
    """
    Fetch quarterly earnings from Finnhub.

    Returns DataFrame indexed by date with columns:
    - actual: Reported EPS
    - estimate: Estimated EPS
    - surprise: Surprise amount in $
    - surprise_pct: Surprise as percentage
    - period: Quarter end date

    Or {"error": msg} on failure.
    """
    api_key = _get_finnhub_key()
    if not api_key:
        return {"error": "FINNHUB_API_KEY not configured"}

    url = "https://finnhub.io/api/v1/stock/earnings"
    params = {"symbol": ticker, "limit": limit, "token": api_key}

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 401:
            return {"error": "Finnhub 401: Invalid API key"}
        if resp.status_code == 403:
            return {"error": "Finnhub 403: Endpoint not available on free tier"}
        if resp.status_code == 429:
            return {"error": "Finnhub 429: Rate limit (60/min) exceeded"}
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list) or len(data) == 0:
            return {"error": f"Finnhub returned no earnings for {ticker}"}

        rows = []
        for entry in data:
            period = entry.get("period")
            if not period:
                continue
            try:
                date = pd.to_datetime(period)
            except Exception:
                continue
            actual = entry.get("actual")
            estimate = entry.get("estimate")
            surprise = entry.get("surprise")
            surprise_pct = entry.get("surprisePercent")
            rows.append({
                "date": date,
                "actual_eps": float(actual) if actual is not None else None,
                "estimate_eps": float(estimate) if estimate is not None else None,
                "surprise_dollars": float(surprise) if surprise is not None else None,
                "surprise_pct": float(surprise_pct) if surprise_pct is not None else None,
            })

        if not rows:
            return {"error": f"No usable earnings rows for {ticker}"}

        df = pd.DataFrame(rows).dropna(subset=["actual_eps"])
        if df.empty:
            return {"error": f"No quarters with reported EPS for {ticker}"}

        df = df.sort_values("date").reset_index(drop=True)
        df.set_index("date", inplace=True)
        return df
    except requests.Timeout:
        return {"error": "Finnhub timeout"}
    except Exception as e:
        return {"error": f"Finnhub fetch failed: {str(e)[:200]}"}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_finnhub_financials(ticker, freq="quarterly"):
    """
    Fetch reported financials (income statement) from Finnhub.

    Provides revenue, net income, EPS over a longer time horizon than /earnings.
    Returns DataFrame or {"error": msg}.
    """
    api_key = _get_finnhub_key()
    if not api_key:
        return {"error": "FINNHUB_API_KEY not configured"}

    url = "https://finnhub.io/api/v1/stock/financials-reported"
    params = {"symbol": ticker, "freq": freq, "token": api_key}

    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code == 401:
            return {"error": "Finnhub 401: Invalid API key"}
        if resp.status_code == 403:
            return {"error": "Finnhub 403: financials-reported not on free tier"}
        if resp.status_code == 429:
            return {"error": "Finnhub 429: rate limit"}
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, dict) or "data" not in data:
            return {"error": "Unexpected Finnhub response shape"}

        filings = data.get("data", [])
        if not filings:
            return {"error": f"No financials returned for {ticker}"}

        rows = []
        for filing in filings:
            end_date = filing.get("endDate") or filing.get("filedDate")
            if not end_date:
                continue
            try:
                date = pd.to_datetime(end_date)
            except Exception:
                continue

            # Finnhub structures: report -> ic (income statement) -> array of concepts
            report = filing.get("report", {})
            ic = report.get("ic", []) if isinstance(report, dict) else []

            revenue = None
            net_income = None
            eps_diluted = None
            eps_basic = None

            for concept in ic:
                concept_name = concept.get("concept", "")
                label = concept.get("label", "").lower()
                value = concept.get("value")
                if value is None:
                    continue
                try:
                    val = float(value)
                except Exception:
                    continue

                # Revenue concepts
                if "Revenues" in concept_name or "SalesRevenueNet" in concept_name or "revenue" in label[:30]:
                    if revenue is None or "total" in label:
                        revenue = val
                # Net income
                elif "NetIncomeLoss" in concept_name and "Attributable" not in concept_name:
                    if net_income is None:
                        net_income = val
                # Diluted EPS
                elif "EarningsPerShareDiluted" in concept_name:
                    if eps_diluted is None:
                        eps_diluted = val
                # Basic EPS
                elif "EarningsPerShareBasic" in concept_name:
                    if eps_basic is None:
                        eps_basic = val

            if any(v is not None for v in [revenue, net_income, eps_diluted, eps_basic]):
                rows.append({
                    "date": date,
                    "revenue": revenue,
                    "net_income": net_income,
                    "eps_diluted": eps_diluted,
                    "eps_basic": eps_basic,
                })

        if not rows:
            return {"error": f"No usable financial rows for {ticker}"}

        df = pd.DataFrame(rows)
        df = df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)
        df.set_index("date", inplace=True)
        return df
    except Exception as e:
        return {"error": f"Finnhub financials failed: {str(e)[:200]}"}


def get_finnhub_earnings_data(ticker, period_start=None):
    """
    Combined fetch: earnings (with surprises) + financials (for revenue + longer history).

    Returns:
        {
          "earnings_df": DataFrame with reported_eps + surprise_pct,
          "revenue_df": DataFrame with revenue,
          "earnings_error" / "revenue_error": Error msgs if applicable,
          "source": "finnhub"
        }
    """
    result = {"ticker": ticker, "source": "finnhub"}

    # Primary: /stock/earnings (clean EPS + surprise data, ~12 years with limit=50)
    earnings = fetch_finnhub_earnings(ticker, limit=50)

    # Secondary: /stock/financials-reported (revenue + extended history)
    financials = fetch_finnhub_financials(ticker)

    # Build earnings_df from /earnings endpoint
    if isinstance(earnings, dict) and "error" in earnings:
        # Try to fall back to financials EPS
        if isinstance(financials, pd.DataFrame) and not financials.empty:
            eps_col = "eps_diluted" if "eps_diluted" in financials.columns else "eps_basic"
            eps_data = financials[eps_col].dropna() if eps_col in financials.columns else pd.Series()
            if not eps_data.empty:
                edf = pd.DataFrame({"reported_eps": eps_data})
                if period_start is not None:
                    edf = edf[edf.index >= period_start]
                result["earnings_df"] = edf if not edf.empty else None
                result["earnings_source_detail"] = "financials_fallback"
            else:
                result["earnings_df"] = None
                result["earnings_error"] = earnings["error"]
        else:
            result["earnings_df"] = None
            result["earnings_error"] = earnings["error"]
    else:
        # Use /earnings data
        edf = earnings.copy()
        edf = edf.rename(columns={"actual_eps": "reported_eps"})

        # Optionally extend with older data from /financials-reported if available
        if isinstance(financials, pd.DataFrame) and not financials.empty:
            eps_col = "eps_diluted" if "eps_diluted" in financials.columns else "eps_basic"
            if eps_col in financials.columns:
                older_eps = financials[eps_col].dropna()
                older_eps = older_eps[older_eps.index < edf.index.min()]
                if not older_eps.empty:
                    older_df = pd.DataFrame({
                        "reported_eps": older_eps,
                        "surprise_pct": [None] * len(older_eps),
                    })
                    edf = pd.concat([older_df, edf]).sort_index()

        if period_start is not None:
            edf = edf[edf.index >= period_start]
        result["earnings_df"] = edf if not edf.empty else None
        result["earnings_source_detail"] = "earnings_endpoint"

    # Build revenue_df from financials
    if isinstance(financials, dict) and "error" in financials:
        result["revenue_df"] = None
        result["revenue_error"] = financials["error"]
    else:
        rev_data = financials["revenue"].dropna() if "revenue" in financials.columns else pd.Series()
        if not rev_data.empty:
            rdf = pd.DataFrame({"revenue": rev_data})
            if period_start is not None:
                rdf = rdf[rdf.index >= period_start]
            result["revenue_df"] = rdf if not rdf.empty else None
        else:
            result["revenue_df"] = None
            result["revenue_error"] = "No revenue data in Finnhub financials"

    return result
