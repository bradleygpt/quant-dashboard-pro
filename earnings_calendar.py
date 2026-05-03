"""
Earnings Calendar
=================

Fetches upcoming earnings reports from Finnhub's /calendar/earnings endpoint.

Provides:
- get_earnings_this_week(): DataFrame of all earnings in next 7 days
- get_tickers_reporting_within(days): Set of tickers reporting within N days
- render_earnings_calendar_panel(): Streamlit panel for Home/Macro tabs
- earnings_emoji(ticker, days=7): Returns 📅 if reporting within N days, else ""

Zero-cost: uses Finnhub free tier endpoint.
"""

import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta


FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY") or st.secrets.get("FINNHUB_API_KEY", "") if hasattr(st, 'secrets') else os.environ.get("FINNHUB_API_KEY", "")


@st.cache_data(ttl=3600, show_spinner=False)  # 1 hour cache
def fetch_earnings_calendar(start_date=None, end_date=None):
    """
    Fetch earnings calendar from Finnhub.

    Args:
        start_date: datetime or "YYYY-MM-DD" string. Defaults to today.
        end_date: datetime or "YYYY-MM-DD" string. Defaults to today + 7 days.

    Returns:
        DataFrame with columns: symbol, date, hour ("bmo"/"amc"/"dmh"),
                                epsActual, epsEstimate, revenueActual, revenueEstimate, year, quarter
        Empty DataFrame if no earnings or fetch fails.
    """
    if not FINNHUB_API_KEY:
        return pd.DataFrame()

    if start_date is None:
        start_date = datetime.now()
    if end_date is None:
        end_date = start_date + timedelta(days=7)

    if isinstance(start_date, datetime):
        start_str = start_date.strftime("%Y-%m-%d")
    else:
        start_str = str(start_date)
    if isinstance(end_date, datetime):
        end_str = end_date.strftime("%Y-%m-%d")
    else:
        end_str = str(end_date)

    try:
        url = "https://finnhub.io/api/v1/calendar/earnings"
        params = {
            "from": start_str,
            "to": end_str,
            "token": FINNHUB_API_KEY,
        }
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return pd.DataFrame()

        data = r.json()
        earnings = data.get("earningsCalendar", [])
        if not earnings:
            return pd.DataFrame()

        df = pd.DataFrame(earnings)
        # Standardize date column
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def get_tickers_reporting_within(days=7):
    """
    Returns a SET of ticker symbols reporting earnings within the next N days.

    Used by screeners and stock detail to mark tickers with the 📅 emoji.
    Cached for 1 hour.
    """
    df = fetch_earnings_calendar()
    if df.empty or "symbol" not in df.columns or "date" not in df.columns:
        return set()

    cutoff = datetime.now() + timedelta(days=days)
    today = datetime.now()
    upcoming = df[(df["date"] >= today) & (df["date"] <= cutoff)]
    return set(upcoming["symbol"].dropna().str.upper().tolist())


def earnings_emoji(ticker, days=7):
    """
    Returns '📅' if the ticker is reporting earnings within `days` days, else ''.

    Used inline in screener tables and stock detail headers.
    """
    if not ticker:
        return ""
    upcoming = get_tickers_reporting_within(days=days)
    if ticker.upper() in upcoming:
        return "📅"
    return ""


def _format_hour(hour_code):
    """Convert Finnhub's hour codes to readable labels."""
    return {
        "bmo": "Before Market Open",
        "amc": "After Market Close",
        "dmh": "During Market Hours",
    }.get(hour_code, "")


def render_earnings_calendar_panel(compact=False):
    """
    Render the upcoming earnings calendar panel.

    Shows the next 7 days of earnings, sortable by date and time.
    """
    st.markdown("### 📅 Earnings This Week")

    df = fetch_earnings_calendar()
    if df.empty:
        st.info("No earnings calendar data available right now. Check back in an hour.")
        return

    # Filter to upcoming only
    today = datetime.now().normalize() if hasattr(datetime.now(), 'normalize') else datetime.now()
    today = pd.Timestamp(datetime.now().date())
    cutoff = today + timedelta(days=7)
    upcoming = df[(df["date"] >= today) & (df["date"] <= cutoff)].copy()

    if upcoming.empty:
        st.info("No earnings reports scheduled in the next 7 days.")
        return

    # Sort by date, then by hour priority (bmo < dmh < amc)
    hour_priority = {"bmo": 0, "dmh": 1, "amc": 2}
    upcoming["hour_sort"] = upcoming["hour"].map(hour_priority).fillna(3)
    upcoming = upcoming.sort_values(["date", "hour_sort"])

    # Build display
    n = len(upcoming)
    st.caption(f"{n} companies reporting earnings in the next 7 days. Times: BMO = before market open, AMC = after close.")

    if compact:
        # Compact: just show count by day
        upcoming["day_str"] = upcoming["date"].dt.strftime("%a %b %d")
        day_counts = upcoming.groupby("day_str").size().reset_index(name="count")
        day_counts = day_counts.sort_values("day_str")
        cols = st.columns(min(7, len(day_counts)))
        for i, (_, row) in enumerate(day_counts.iterrows()):
            if i < len(cols):
                with cols[i]:
                    st.metric(row["day_str"], f"{row['count']}")
        with st.expander(f"View all {n} companies"):
            _render_table(upcoming)
    else:
        _render_table(upcoming)


def _render_table(upcoming):
    """Render the full earnings table."""
    display_rows = []
    for _, row in upcoming.iterrows():
        symbol = row.get("symbol", "")
        date = row.get("date")
        hour = row.get("hour", "")

        date_str = date.strftime("%a %b %d") if pd.notna(date) else ""
        hour_str = _format_hour(hour)

        eps_est = row.get("epsEstimate")
        eps_est_str = f"${eps_est:.2f}" if pd.notna(eps_est) else "—"

        rev_est = row.get("revenueEstimate")
        rev_est_str = f"${rev_est/1e9:.2f}B" if pd.notna(rev_est) and rev_est > 1e9 else (f"${rev_est/1e6:.1f}M" if pd.notna(rev_est) else "—")

        display_rows.append({
            "Ticker": symbol,
            "Date": date_str,
            "Time": hour_str,
            "EPS Est": eps_est_str,
            "Revenue Est": rev_est_str,
        })

    if display_rows:
        df_display = pd.DataFrame(display_rows)
        st.dataframe(df_display, use_container_width=True, hide_index=True, height=min(400, 35 * len(display_rows) + 50))
