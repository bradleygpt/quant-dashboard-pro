"""
Earnings & IPO Calendar
========================

Fetches upcoming earnings reports and IPOs from Finnhub free tier endpoints.

Provides:
- get_earnings_this_week(): DataFrame of all earnings in next 7 days
- get_ipos_this_week(): DataFrame of all IPOs in next 7 days
- get_tickers_reporting_within(days): Set of tickers reporting earnings within N days
- render_earnings_calendar_panel(): Streamlit panel for earnings (Home/Macro tabs)
- render_ipo_calendar_panel(): Streamlit panel for IPOs
- render_combined_calendar_panel(): Combined earnings + IPO panel
- earnings_emoji(ticker, days=7): Returns 📅 if reporting within N days, else ""

Zero-cost: uses Finnhub free tier endpoints.
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


# ═══════════════════════════════════════════════════════════════════
# IPO CALENDAR
# ═══════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ipo_calendar(start_date=None, end_date=None):
    """
    Fetch IPO calendar from Finnhub.

    Args:
        start_date: datetime or "YYYY-MM-DD" string. Defaults to today.
        end_date: datetime or "YYYY-MM-DD" string. Defaults to today + 30 days
                  (IPOs visible further out than earnings).

    Returns:
        DataFrame with columns: symbol, name, date, exchange, price (range string),
                                numberOfShares, totalSharesValue, status
        Empty DataFrame if no IPOs or fetch fails.
    """
    if not FINNHUB_API_KEY:
        return pd.DataFrame()

    if start_date is None:
        start_date = datetime.now()
    if end_date is None:
        # IPO calendar - look 30 days out (vs earnings which is 7 days)
        end_date = start_date + timedelta(days=30)

    if isinstance(start_date, datetime):
        start_str = start_date.strftime("%Y-%m-%d")
    else:
        start_str = str(start_date)
    if isinstance(end_date, datetime):
        end_str = end_date.strftime("%Y-%m-%d")
    else:
        end_str = str(end_date)

    try:
        url = "https://finnhub.io/api/v1/calendar/ipo"
        params = {
            "from": start_str,
            "to": end_str,
            "token": FINNHUB_API_KEY,
        }
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return pd.DataFrame()

        data = r.json()
        ipos = data.get("ipoCalendar", [])
        if not ipos:
            return pd.DataFrame()

        df = pd.DataFrame(ipos)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return pd.DataFrame()


def render_ipo_calendar_panel(compact=False, days_out=14):
    """
    Render the upcoming IPO calendar panel.

    Args:
        compact: If True, shows day-counts only with expandable detail.
        days_out: How many days forward to show (default 14 = 2 weeks).
    """
    st.markdown("### 🚀 IPOs Coming Up")

    df = fetch_ipo_calendar()
    if df.empty:
        st.info("No IPO calendar data available right now. Check back in an hour.")
        return

    # Filter to upcoming
    today = pd.Timestamp(datetime.now().date())
    cutoff = today + timedelta(days=days_out)
    upcoming = df[(df["date"] >= today) & (df["date"] <= cutoff)].copy() if "date" in df.columns else df.copy()

    if upcoming.empty:
        st.info(f"No IPOs scheduled in the next {days_out} days.")
        return

    upcoming = upcoming.sort_values("date") if "date" in upcoming.columns else upcoming

    n = len(upcoming)
    st.caption(
        f"{n} IPOs scheduled in the next {days_out} days. "
        f"Note: IPO dates often slip — verify directly with the issuer or SEC for confirmed timing."
    )

    if compact:
        with st.expander(f"View all {n} upcoming IPOs"):
            _render_ipo_table(upcoming)
    else:
        _render_ipo_table(upcoming)


def _render_ipo_table(upcoming):
    """Render the IPO table."""
    display_rows = []
    for _, row in upcoming.iterrows():
        symbol = row.get("symbol", "")
        name = row.get("name", "")
        date = row.get("date")
        exchange = row.get("exchange", "")
        price = row.get("price", "")
        shares = row.get("numberOfShares")
        total_value = row.get("totalSharesValue")
        status = row.get("status", "")

        date_str = date.strftime("%a %b %d") if pd.notna(date) else ""
        shares_str = f"{shares/1e6:.1f}M" if pd.notna(shares) and shares else "—"
        total_str = f"${total_value/1e6:.1f}M" if pd.notna(total_value) and total_value else "—"
        price_str = price if price else "—"

        display_rows.append({
            "Ticker": symbol if symbol else "—",
            "Company": (name[:40] + "...") if name and len(name) > 40 else (name if name else "—"),
            "Date": date_str,
            "Exchange": exchange if exchange else "—",
            "Price Range": price_str,
            "Shares": shares_str,
            "Est. Proceeds": total_str,
            "Status": status if status else "—",
        })

    if display_rows:
        df_display = pd.DataFrame(display_rows)
        st.dataframe(df_display, use_container_width=True, hide_index=True, height=min(400, 35 * len(display_rows) + 50))


# ═══════════════════════════════════════════════════════════════════
# COMBINED PANEL: Earnings + IPOs side by side
# ═══════════════════════════════════════════════════════════════════

def render_combined_calendar_panel(compact=False):
    """
    Render both Earnings and IPO calendars side-by-side or stacked.

    Used on Home tab for at-a-glance view.
    """
    st.markdown("### 📅 This Week's Calendar")
    st.caption("Companies reporting earnings + IPOs coming up. Earnings within 7 days, IPOs within 14 days.")

    # Two columns side by side
    earnings_col, ipo_col = st.columns(2)

    with earnings_col:
        st.markdown("#### 📊 Earnings This Week")
        df_e = fetch_earnings_calendar()
        if df_e.empty:
            st.info("No earnings data available.")
        else:
            today = pd.Timestamp(datetime.now().date())
            cutoff = today + timedelta(days=7)
            upcoming_e = df_e[(df_e["date"] >= today) & (df_e["date"] <= cutoff)] if "date" in df_e.columns else df_e
            if upcoming_e.empty:
                st.info("No earnings scheduled in the next 7 days.")
            else:
                # Quick day-count display
                upcoming_e = upcoming_e.copy()
                upcoming_e["day_str"] = upcoming_e["date"].dt.strftime("%a %b %d")
                day_counts = upcoming_e.groupby("day_str").size().reset_index(name="count")
                day_counts = day_counts.sort_values("day_str")

                day_metrics = st.columns(min(7, max(1, len(day_counts))))
                for i, (_, row) in enumerate(day_counts.iterrows()):
                    if i < len(day_metrics):
                        with day_metrics[i]:
                            st.metric(row["day_str"][:6], f"{row['count']}")

                with st.expander(f"View all {len(upcoming_e)} earnings"):
                    hour_priority = {"bmo": 0, "dmh": 1, "amc": 2}
                    upcoming_e["hour_sort"] = upcoming_e["hour"].map(hour_priority).fillna(3)
                    upcoming_e = upcoming_e.sort_values(["date", "hour_sort"])
                    _render_table(upcoming_e)

    with ipo_col:
        st.markdown("#### 🚀 Upcoming IPOs")
        df_i = fetch_ipo_calendar()
        if df_i.empty:
            st.info("No IPO data available.")
        else:
            today = pd.Timestamp(datetime.now().date())
            cutoff = today + timedelta(days=14)
            upcoming_i = df_i[(df_i["date"] >= today) & (df_i["date"] <= cutoff)] if "date" in df_i.columns else df_i
            if upcoming_i.empty:
                st.info("No IPOs in the next 14 days.")
            else:
                upcoming_i = upcoming_i.sort_values("date")
                # Show compact summary
                st.metric("IPOs (next 14 days)", len(upcoming_i))
                with st.expander(f"View all {len(upcoming_i)} upcoming IPOs"):
                    _render_ipo_table(upcoming_i)
