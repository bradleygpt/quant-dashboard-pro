"""
Economic Releases Calendar
==========================

Provides upcoming US economic data release dates with countdown timers
and historical values from FRED (Federal Reserve Economic Data).

Zero-cost: FRED has no API key required for basic queries.

Release schedule logic:
- Most BLS/BEA/Fed releases follow predictable patterns (e.g., NFP = first Friday of month)
- We calculate the next release date programmatically
- Historical values pulled from FRED for context

Data sources:
- FRED API: https://api.stlouisfed.org/fred/ (no key needed for series obs)
- BLS schedule: derivable from calendar rules
- Fed schedule: derivable (FOMC meets roughly every 6 weeks)
"""

import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List
import calendar


# Release configuration
# Each release has: name, importance, frequency, FRED series ID, schedule logic
ECONOMIC_RELEASES = [
    {
        "id": "nfp",
        "name": "Nonfarm Payrolls / Unemployment",
        "importance": "Critical",
        "frequency": "Monthly (1st Friday)",
        "description": "Jobs added and unemployment rate. The single most market-moving release.",
        "fred_series": "PAYEMS",  # Total nonfarm payrolls
        "fred_unemployment": "UNRATE",
        "schedule": "first_friday",
        "release_time_et": "08:30",
    },
    {
        "id": "cpi",
        "name": "CPI Report",
        "importance": "Critical",
        "frequency": "Monthly (~10th-14th)",
        "description": "Consumer Price Index. Key inflation gauge for Fed policy decisions.",
        "fred_series": "CPIAUCSL",  # CPI All Urban Consumers
        "schedule": "mid_month_business_day",
        "schedule_day_range": (10, 14),
        "release_time_et": "08:30",
    },
    {
        "id": "ppi",
        "name": "PPI Report",
        "importance": "High",
        "frequency": "Monthly (~13th-15th)",
        "description": "Producer Price Index. Wholesale inflation, leads CPI.",
        "fred_series": "PPIACO",  # Producer Price Index All Commodities
        "schedule": "mid_month_business_day",
        "schedule_day_range": (13, 15),
        "release_time_et": "08:30",
    },
    {
        "id": "ism_mfg",
        "name": "ISM Manufacturing PMI",
        "importance": "High",
        "frequency": "Monthly (1st biz day)",
        "description": "Above 50 = expansion. Leading indicator for industrial sector.",
        "fred_series": "MANEMP",  # Manufacturing employment as proxy (real PMI not on FRED)
        "schedule": "first_business_day",
        "release_time_et": "10:00",
    },
    {
        "id": "ism_services",
        "name": "ISM Services PMI",
        "importance": "High",
        "frequency": "Monthly (3rd biz day)",
        "description": "Services sector health. 89% of GDP. More important than manufacturing.",
        "fred_series": None,
        "schedule": "third_business_day",
        "release_time_et": "10:00",
    },
    {
        "id": "retail_sales",
        "name": "Retail Sales",
        "importance": "Medium",
        "frequency": "Monthly (~14th-17th)",
        "description": "Consumer spending health. 70% of GDP is consumption.",
        "fred_series": "RSAFS",  # Advance Retail Sales
        "schedule": "mid_month_business_day",
        "schedule_day_range": (14, 17),
        "release_time_et": "08:30",
    },
    {
        "id": "pce",
        "name": "PCE Price Index",
        "importance": "High",
        "frequency": "Monthly (~25th-30th)",
        "description": "Fed's preferred inflation gauge. Released at end of month.",
        "fred_series": "PCEPI",
        "schedule": "late_month_business_day",
        "schedule_day_range": (25, 30),
        "release_time_et": "08:30",
    },
    {
        "id": "gdp",
        "name": "GDP Report",
        "importance": "High",
        "frequency": "Quarterly",
        "description": "Advance, second, and final estimates of economic growth.",
        "fred_series": "GDP",
        "schedule": "quarterly_advance",
        "release_time_et": "08:30",
    },
    {
        "id": "jobless_claims",
        "name": "Initial Jobless Claims",
        "importance": "High",
        "frequency": "Weekly (Thursday)",
        "description": "Weekly new unemployment filings. Rising = weakening labor market.",
        "fred_series": "ICSA",
        "schedule": "weekly_thursday",
        "release_time_et": "08:30",
    },
    {
        "id": "fomc",
        "name": "FOMC Rate Decision",
        "importance": "Critical",
        "frequency": "~Every 6 weeks",
        "description": "Federal Reserve interest rate decision and forward guidance.",
        "fred_series": "DFEDTARU",  # Fed Funds Target Upper bound
        "schedule": "fomc_meetings",
        "release_time_et": "14:00",
    },
    {
        "id": "consumer_sentiment",
        "name": "Consumer Sentiment (UMich)",
        "importance": "Medium",
        "frequency": "Monthly (Preliminary mid-month, Final end of month)",
        "description": "University of Michigan Consumer Sentiment Index.",
        "fred_series": "UMCSENT",
        "schedule": "mid_month_friday",
        "release_time_et": "10:00",
    },
    {
        "id": "housing_starts",
        "name": "Housing Starts",
        "importance": "Medium",
        "frequency": "Monthly (~16th-19th)",
        "description": "New residential construction. Leading indicator for housing market.",
        "fred_series": "HOUST",
        "schedule": "mid_month_business_day",
        "schedule_day_range": (16, 19),
        "release_time_et": "08:30",
    },
]

# 2026 FOMC meeting dates (announced by the Fed in advance)
# These are decision-day dates; would be updated annually
FOMC_DATES_2026 = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]
FOMC_DATES_2027 = [
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16",
    "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08",
]


def _is_business_day(d):
    """Check if a date is a US business day (excludes weekends, basic check)."""
    return d.weekday() < 5


def _next_first_friday(after_date):
    """Find the next first Friday of a month occurring after `after_date`."""
    year = after_date.year
    month = after_date.month
    while True:
        # Find first Friday of this month
        for day in range(1, 8):
            try:
                d = date(year, month, day)
                if d.weekday() == 4:  # Friday
                    if d > after_date:
                        return d
                    break
            except ValueError:
                continue
        # Move to next month
        month += 1
        if month > 12:
            month = 1
            year += 1


def _next_mid_month_business_day(after_date, day_range=(10, 14)):
    """Find the next business day within day_range of a future month."""
    year = after_date.year
    month = after_date.month
    while True:
        for day in range(day_range[0], day_range[1] + 1):
            try:
                d = date(year, month, day)
                if _is_business_day(d) and d > after_date:
                    return d
            except ValueError:
                continue
        month += 1
        if month > 12:
            month = 1
            year += 1


def _next_first_business_day(after_date):
    """Find the next first business day of a month after `after_date`."""
    year = after_date.year
    month = after_date.month + 1  # Start with next month
    if month > 12:
        month = 1
        year += 1
    while True:
        for day in range(1, 6):
            try:
                d = date(year, month, day)
                if _is_business_day(d):
                    return d
            except ValueError:
                continue
        month += 1
        if month > 12:
            month = 1
            year += 1


def _next_third_business_day(after_date):
    """Find the third business day of next month."""
    year = after_date.year
    month = after_date.month + 1
    if month > 12:
        month = 1
        year += 1
    business_count = 0
    for day in range(1, 32):
        try:
            d = date(year, month, day)
            if _is_business_day(d):
                business_count += 1
                if business_count == 3:
                    return d
        except ValueError:
            continue
    return None


def _next_thursday(after_date):
    """Find next Thursday after a date."""
    days_ahead = 3 - after_date.weekday()  # Thursday is 3
    if days_ahead <= 0:
        days_ahead += 7
    return after_date + timedelta(days=days_ahead)


def _next_fomc(after_date):
    """Find next FOMC meeting date."""
    all_dates = FOMC_DATES_2026 + FOMC_DATES_2027
    for d_str in all_dates:
        d = datetime.strptime(d_str, "%Y-%m-%d").date()
        if d > after_date:
            return d
    return None


def _next_mid_month_friday(after_date):
    """Find next mid-month Friday (for UMich Consumer Sentiment preliminary)."""
    year = after_date.year
    month = after_date.month
    while True:
        for day in range(11, 17):
            try:
                d = date(year, month, day)
                if d.weekday() == 4 and d > after_date:
                    return d
            except ValueError:
                continue
        month += 1
        if month > 12:
            month = 1
            year += 1


def _next_quarterly_advance(after_date):
    """Find next quarterly GDP advance estimate (~end of month following quarter end)."""
    # GDP advance: ~Jan 25-30 (Q4), ~Apr 25-30 (Q1), ~Jul 25-30 (Q2), ~Oct 25-30 (Q3)
    quarter_end_months = [1, 4, 7, 10]
    year = after_date.year
    for month in quarter_end_months:
        for day in range(25, 31):
            try:
                d = date(year, month, day)
                if _is_business_day(d) and d > after_date:
                    return d
            except ValueError:
                continue
    # Next year
    return date(year + 1, 1, 28)


def calculate_next_release(release_config, today=None):
    """Calculate the next release date for a given release type."""
    if today is None:
        today = date.today()

    schedule = release_config.get("schedule")

    if schedule == "first_friday":
        return _next_first_friday(today)
    elif schedule == "mid_month_business_day":
        day_range = release_config.get("schedule_day_range", (10, 14))
        return _next_mid_month_business_day(today, day_range)
    elif schedule == "late_month_business_day":
        day_range = release_config.get("schedule_day_range", (25, 30))
        return _next_mid_month_business_day(today, day_range)
    elif schedule == "first_business_day":
        return _next_first_business_day(today)
    elif schedule == "third_business_day":
        return _next_third_business_day(today)
    elif schedule == "weekly_thursday":
        return _next_thursday(today)
    elif schedule == "fomc_meetings":
        return _next_fomc(today)
    elif schedule == "mid_month_friday":
        return _next_mid_month_friday(today)
    elif schedule == "quarterly_advance":
        return _next_quarterly_advance(today)
    return None


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_fred_latest(series_id, n=12):
    """Fetch latest N observations from FRED for a given series.

    Prefers official API with key (more reliable) and falls back to keyless CSV.
    """
    if not series_id:
        return None

    # Try official API first if key available
    try:
        api_key = None
        try:
            api_key = st.secrets.get("FRED_API_KEY")
        except Exception:
            api_key = None
        if not api_key:
            api_key = os.environ.get("FRED_API_KEY")

        if api_key:
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": n,
            }
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                obs = data.get("observations", [])
                if obs:
                    rows = []
                    for o in obs:
                        try:
                            v = float(o.get("value", "."))
                            d = pd.Timestamp(o.get("date"))
                            rows.append({"date": d, "value": v})
                        except (ValueError, TypeError):
                            continue
                    if rows:
                        return pd.DataFrame(rows)
    except Exception:
        pass

    # Fallback: keyless CSV download
    try:
        csv_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        r = requests.get(csv_url, timeout=10, headers={
            "User-Agent": "QuantDashboard/1.0 contact@example.com"
        })
        if r.status_code == 200 and r.text:
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            if len(df) > 0:
                df.columns = [c.strip() for c in df.columns]
                date_col = df.columns[0]
                value_col = df.columns[1] if len(df.columns) > 1 else None
                if value_col:
                    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                    df = df.dropna(subset=[date_col]).sort_values(date_col, ascending=False)
                    df = df.head(n)
                    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
                    df = df.dropna(subset=[value_col])
                    return df.rename(columns={date_col: "date", value_col: "value"})
    except Exception:
        pass

    return None


def render_economic_calendar_panel():
    """Render the upcoming economic releases panel with countdown timers."""
    st.markdown("### 🏛️ Key Economic Releases Calendar")
    st.caption("Upcoming US data releases with countdown to next release. Historical values from FRED.")

    today = date.today()
    now_dt = datetime.now()

    # Compute next release dates
    releases_with_dates = []
    for release in ECONOMIC_RELEASES:
        next_date = calculate_next_release(release, today)
        if next_date:
            days_until = (next_date - today).days
            releases_with_dates.append({**release, "next_date": next_date, "days_until": days_until})

    # Sort by days until next release
    releases_with_dates.sort(key=lambda x: x["days_until"])

    # Color mapping for importance
    importance_color = {
        "Critical": "🔴",
        "High": "🟠",
        "Medium": "🟢",
    }

    # Display
    for r in releases_with_dates:
        days_until = r["days_until"]
        next_date = r["next_date"]

        # Format countdown
        if days_until == 0:
            countdown_str = f"⏰ **TODAY** at {r.get('release_time_et', 'TBD')} ET"
            countdown_color = "#FF6B6B"
        elif days_until == 1:
            countdown_str = f"📅 **Tomorrow** ({next_date.strftime('%a %b %d')}) at {r.get('release_time_et', 'TBD')} ET"
            countdown_color = "#FFA500"
        elif days_until <= 7:
            countdown_str = f"📅 **{days_until} days** ({next_date.strftime('%a %b %d')}) at {r.get('release_time_et', 'TBD')} ET"
            countdown_color = "#FFE66D"
        else:
            countdown_str = f"📅 {days_until} days ({next_date.strftime('%a %b %d')})"
            countdown_color = "#888"

        importance_emoji = importance_color.get(r["importance"], "⚪")

        # Try to fetch latest historical value
        fred_id = r.get("fred_series")
        latest_value = None
        latest_date = None
        prev_value = None
        if fred_id:
            df = fetch_fred_latest(fred_id, n=2)
            if df is not None and len(df) > 0:
                latest_value = df.iloc[0]["value"]
                latest_date = df.iloc[0]["date"]
                if len(df) > 1:
                    prev_value = df.iloc[1]["value"]

        # Render expandable card
        title = f"{importance_emoji} **{r['name']}** ({r['frequency']})"

        with st.container():
            st.markdown(f"#### {title}")
            cols = st.columns([2, 2, 2])
            with cols[0]:
                st.markdown(f"**Next Release:**")
                st.markdown(countdown_str)
            with cols[1]:
                if latest_value is not None:
                    st.markdown(f"**Last Reading:**")
                    formatted = _format_indicator_value(r["id"], latest_value)
                    delta_str = ""
                    if prev_value is not None:
                        delta = latest_value - prev_value
                        pct_change = (delta / prev_value * 100) if prev_value != 0 else 0
                        delta_str = f" ({delta:+.2f} from prior)"
                    st.markdown(f"{formatted}{delta_str}")
                    if latest_date is not None:
                        date_str = latest_date.strftime("%b %Y") if hasattr(latest_date, 'strftime') else str(latest_date)
                        st.caption(f"As of {date_str}")
                else:
                    st.markdown("**Last Reading:** Data unavailable")
            with cols[2]:
                st.markdown(f"**Importance:** {r['importance']}")
                st.caption(r["description"])

            st.markdown("---")


def _format_indicator_value(release_id, value):
    """Format a value based on what it represents."""
    if release_id in ("nfp",):
        return f"**{value:,.0f}** thousand jobs"
    elif release_id in ("cpi", "ppi", "pce"):
        return f"**{value:,.2f}** index"
    elif release_id == "fomc":
        return f"**{value:.2f}%** Fed Funds rate"
    elif release_id == "jobless_claims":
        return f"**{value:,.0f}** initial claims"
    elif release_id == "consumer_sentiment":
        return f"**{value:.1f}** index"
    elif release_id == "retail_sales":
        return f"**${value:,.0f}M** monthly sales"
    elif release_id == "housing_starts":
        return f"**{value:,.0f}** annualized starts"
    elif release_id == "gdp":
        return f"**${value:,.0f}B** annualized GDP"
    else:
        return f"**{value:,.2f}**"
