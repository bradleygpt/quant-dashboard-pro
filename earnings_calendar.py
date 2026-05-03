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


@st.cache_data(ttl=86400, show_spinner=False)  # 24 hour cache - earnings dates are stable
def fetch_yfinance_earnings_date(ticker):
    """
    Fetch the next earnings date for a ticker from yfinance.

    Used as backup for tickers missing from Finnhub's calendar response.
    Returns dict with date, eps_estimate, revenue_estimate, or None.
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        # yfinance has multiple ways to get earnings date - try each
        cal = t.calendar
        if cal is not None and not cal.empty if hasattr(cal, 'empty') else cal:
            # cal may be DataFrame or dict depending on yfinance version
            if isinstance(cal, dict):
                # Newer yfinance returns dict
                earnings_date = cal.get("Earnings Date")
                if earnings_date:
                    if isinstance(earnings_date, list) and earnings_date:
                        earnings_date = earnings_date[0]
                    return {
                        "symbol": ticker.upper(),
                        "date": pd.Timestamp(earnings_date),
                        "hour": "amc",  # yfinance doesn't reliably tell us, default to AMC
                        "epsEstimate": cal.get("Earnings Average", None),
                        "revenueEstimate": cal.get("Revenue Average", None),
                        "_source": "yfinance",
                    }
            else:
                # Older yfinance returned DataFrame
                if "Earnings Date" in cal.index:
                    earnings_date = cal.loc["Earnings Date"].iloc[0] if hasattr(cal.loc["Earnings Date"], 'iloc') else cal.loc["Earnings Date"]
                    return {
                        "symbol": ticker.upper(),
                        "date": pd.Timestamp(earnings_date),
                        "hour": "amc",
                        "epsEstimate": None,
                        "revenueEstimate": None,
                        "_source": "yfinance",
                    }

        # Try info dict as fallback
        try:
            info = t.info
            ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
            if ts:
                return {
                    "symbol": ticker.upper(),
                    "date": pd.Timestamp(ts, unit="s") if ts > 1e9 else pd.Timestamp(ts),
                    "hour": "amc",
                    "epsEstimate": info.get("epsForward"),
                    "revenueEstimate": info.get("revenueEstimate"),
                    "_source": "yfinance",
                }
        except Exception:
            pass

        return None
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_merged_earnings_calendar(universe_tickers, days_ahead=7):
    """
    Get a unified earnings calendar combining Finnhub batch + yfinance per-ticker fill-in.

    For each ticker in universe:
    - Check if Finnhub returned it (fast, single API call)
    - For tickers Finnhub missed, query yfinance individually

    Args:
        universe_tickers: iterable of tickers to check
        days_ahead: lookforward window in days

    Returns DataFrame with merged earnings.
    """
    # First get Finnhub batch results
    finnhub_df = fetch_earnings_calendar()
    if finnhub_df is None or finnhub_df.empty:
        finnhub_df = pd.DataFrame(columns=["symbol", "date", "hour", "epsEstimate", "revenueEstimate"])

    # Identify which tickers from our universe are missing from Finnhub
    universe_upper = {t.upper() for t in universe_tickers}
    finnhub_tickers = set(finnhub_df["symbol"].str.upper().tolist()) if "symbol" in finnhub_df.columns else set()
    missing_from_finnhub = universe_upper - finnhub_tickers

    # For each missing ticker, query yfinance
    today = pd.Timestamp(datetime.now().date())
    cutoff = today + timedelta(days=days_ahead)

    yf_rows = []
    for ticker in missing_from_finnhub:
        result = fetch_yfinance_earnings_date(ticker)
        if result and result.get("date"):
            edate = pd.Timestamp(result["date"])
            # Only include if within window
            if today <= edate <= cutoff:
                yf_rows.append(result)

    # Merge
    if yf_rows:
        yf_df = pd.DataFrame(yf_rows)
        merged = pd.concat([finnhub_df, yf_df], ignore_index=True)
    else:
        merged = finnhub_df

    return merged



    """
    Returns a SET of ticker symbols reporting earnings within the next N days.

    Used by screeners and stock detail to mark tickers with the 📅 emoji.
    Cached for 1 hour.

    Args:
        days: Window in days
        universe_tickers: Optional iterable - if provided, only returns
                         tickers that are also in this universe.
    """
    df = fetch_earnings_calendar()
    if df.empty or "symbol" not in df.columns or "date" not in df.columns:
        return set()

    cutoff = datetime.now() + timedelta(days=days)
    today = datetime.now()
    upcoming = df[(df["date"] >= today) & (df["date"] <= cutoff)]
    result = set(upcoming["symbol"].dropna().str.upper().tolist())

    # Filter to universe if provided
    if universe_tickers is not None:
        universe_upper = {t.upper() for t in universe_tickers}
        result = result & universe_upper

    return result


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


@st.cache_data(ttl=3600, show_spinner=False)
def get_tickers_reporting_within(days=7, universe_tickers=None):
    """
    Returns a SET of ticker symbols reporting earnings within the next N days.

    Used by screeners and stock detail to mark tickers with the 📅 emoji.
    Cached for 1 hour.

    If universe_tickers is provided, also queries yfinance for any tickers in
    the universe missing from Finnhub's response.
    """
    if universe_tickers is not None:
        # Use merged calendar (Finnhub + yfinance for missing tickers)
        df = get_merged_earnings_calendar(universe_tickers, days_ahead=days)
    else:
        df = fetch_earnings_calendar()

    if df.empty or "symbol" not in df.columns or "date" not in df.columns:
        return set()

    cutoff = datetime.now() + timedelta(days=days)
    today = datetime.now()
    upcoming = df[(df["date"] >= today) & (df["date"] <= cutoff)]
    result = set(upcoming["symbol"].dropna().str.upper().tolist())

    # Filter to universe if provided
    if universe_tickers is not None:
        universe_upper = {t.upper() for t in universe_tickers}
        result = result & universe_upper

    return result


def _format_hour(hour_code):
    """Convert Finnhub's hour codes to readable labels."""
    return {
        "bmo": "Before Market Open",
        "amc": "After Market Close",
        "dmh": "During Market Hours",
    }.get(hour_code, "")


def render_earnings_calendar_panel(compact=False, universe_tickers=None):
    """
    Render the upcoming earnings calendar panel.

    Args:
        compact: If True, shows day-counts only with expandable detail.
        universe_tickers: Optional iterable of ticker symbols. If provided,
                         only earnings from companies in this universe are shown,
                         AND yfinance is used as backup for tickers missing from Finnhub.
    """
    st.markdown("### 📅 Earnings This Week")

    # Use merged calendar (Finnhub + yfinance backup) if universe provided
    if universe_tickers is not None:
        with st.spinner("Loading earnings calendar (querying yfinance for any missing tickers)..."):
            df = get_merged_earnings_calendar(universe_tickers, days_ahead=7)
    else:
        df = fetch_earnings_calendar()

    if df.empty:
        st.info("No earnings calendar data available right now. Check back in an hour.")
        return

    # Capture diagnostics BEFORE filtering for debug expander
    n_total_from_api = len(df)
    n_excluded_by_universe = 0
    excluded_tickers = []

    # Filter to upcoming first (date window)
    today = pd.Timestamp(datetime.now().date())
    cutoff = today + timedelta(days=7)
    in_window = df[(df["date"] >= today) & (df["date"] <= cutoff)].copy() if "date" in df.columns else df.copy()
    n_in_window = len(in_window)

    # Then filter to universe
    if universe_tickers is not None and "symbol" in in_window.columns:
        universe_upper = {t.upper() for t in universe_tickers}
        before_count = len(in_window)
        excluded = in_window[~in_window["symbol"].str.upper().isin(universe_upper)]
        excluded_tickers = sorted(excluded["symbol"].dropna().unique().tolist())
        in_window = in_window[in_window["symbol"].str.upper().isin(universe_upper)]
        n_excluded_by_universe = before_count - len(in_window)

    upcoming = in_window

    if upcoming.empty:
        st.info("No earnings reports scheduled in the next 7 days for tracked universe.")
        # Show diagnostic
        with st.expander("🔍 Why might companies be missing? (debug)"):
            _show_calendar_diagnostics(df, today, cutoff, universe_tickers, excluded_tickers, n_excluded_by_universe)
        return

    # Sort by date, then by hour priority
    hour_priority = {"bmo": 0, "dmh": 1, "amc": 2}
    upcoming["hour_sort"] = upcoming["hour"].map(hour_priority).fillna(3)
    upcoming = upcoming.sort_values(["date", "hour_sort"])

    # Build display
    n = len(upcoming)
    universe_note = " from tracked universe" if universe_tickers else ""
    st.caption(f"{n} companies{universe_note} reporting earnings in the next 7 days. Times: BMO = before market open, AMC = after close.")

    if compact:
        # Compact: show count by day - sort by actual date, not by string
        upcoming["day_str"] = upcoming["date"].dt.strftime("%a %b %d")
        upcoming["day_sort_date"] = upcoming["date"].dt.date  # For chronological sort

        day_counts = upcoming.groupby(["day_sort_date", "day_str"]).size().reset_index(name="count")
        day_counts = day_counts.sort_values("day_sort_date")  # Sort by actual date

        cols = st.columns(min(7, len(day_counts)))
        for i, (_, row) in enumerate(day_counts.iterrows()):
            if i < len(cols):
                with cols[i]:
                    st.metric(row["day_str"], f"{row['count']}")
        with st.expander(f"View all {n} companies"):
            _render_table(upcoming)
    else:
        _render_table(upcoming)

    # Always offer diagnostic expander (collapsed by default)
    if universe_tickers is not None and n_excluded_by_universe > 0:
        with st.expander(f"🔍 {n_excluded_by_universe} companies excluded (not in tracked universe). Click to investigate."):
            _show_calendar_diagnostics(df, today, cutoff, universe_tickers, excluded_tickers, n_excluded_by_universe)


def _show_calendar_diagnostics(df_full, today, cutoff, universe_tickers, excluded_tickers, n_excluded):
    """
    Diagnostic panel for investigating why companies might be missing.

    Shows:
    - Total earnings returned by Finnhub API (any date)
    - Earnings within window but excluded by universe filter
    - Search for specific ticker
    - Universe stats
    """
    st.markdown("**Diagnostic Information**")

    diag_cols = st.columns(4)
    with diag_cols[0]:
        st.metric("Total from Finnhub API", len(df_full))
    with diag_cols[1]:
        st.metric("In 7-day window", len(df_full[(df_full["date"] >= today) & (df_full["date"] <= cutoff)]) if "date" in df_full.columns else 0)
    with diag_cols[2]:
        st.metric("Excluded (not in universe)", n_excluded)
    with diag_cols[3]:
        if universe_tickers:
            st.metric("Universe size", len(universe_tickers))
        else:
            st.metric("Universe filter", "None")

    # Show excluded tickers in window
    if excluded_tickers:
        st.markdown(f"**Excluded by universe filter ({len(excluded_tickers)}):**")
        # Show in a compact wrap
        cols_per_row = 8
        for i in range(0, min(len(excluded_tickers), 80), cols_per_row):
            chunk = excluded_tickers[i:i+cols_per_row]
            cols = st.columns(cols_per_row)
            for c, ticker in zip(cols, chunk):
                with c:
                    st.caption(f"`{ticker}`")
        if len(excluded_tickers) > 80:
            st.caption(f"...and {len(excluded_tickers) - 80} more")

    # Search for a specific ticker
    st.markdown("---")
    st.markdown("**🔍 Search for a specific ticker:**")
    search_ticker = st.text_input(
        "Enter ticker (e.g. PLTR):",
        key="earnings_search_ticker",
        placeholder="PLTR"
    ).strip().upper()

    if search_ticker:
        # Search in the full unfiltered API response
        match = df_full[df_full["symbol"].str.upper() == search_ticker] if "symbol" in df_full.columns else pd.DataFrame()
        if not match.empty:
            st.success(f"✓ Found {len(match)} entries for {search_ticker} in Finnhub data")
            for _, row in match.iterrows():
                date = row.get("date")
                hour = row.get("hour", "?")
                date_str = date.strftime("%Y-%m-%d (%A)") if pd.notna(date) else "unknown"

                # Check if in window
                in_window_status = "✅ within 7-day window" if (
                    pd.notna(date) and date >= today and date <= cutoff
                ) else f"❌ outside 7-day window (today: {today.date()}, cutoff: {cutoff.date()})"

                # Check if in universe
                if universe_tickers:
                    universe_upper = {t.upper() for t in universe_tickers}
                    in_universe_status = "✅ in tracked universe" if search_ticker in universe_upper else "❌ NOT in tracked universe"
                else:
                    in_universe_status = "(no universe filter active)"

                st.markdown(f"""
                - **Date:** {date_str}
                - **Time:** {_format_hour(hour) if hour else 'unknown'}
                - **EPS Estimate:** ${row.get('epsEstimate', '—'):.2f}" if pd.notna(row.get('epsEstimate')) else 'n/a'
                - **Date filter:** {in_window_status}
                - **Universe filter:** {in_universe_status}
                """)
        else:
            st.warning(f"❌ {search_ticker} NOT found in Finnhub's earnings calendar response.")
            st.markdown(f"""
            **Possible reasons:**
            - {search_ticker}'s next earnings is more than 7 days away (Finnhub returns dates within ~30 days)
            - {search_ticker} doesn't have earnings scheduled
            - The ticker symbol on Finnhub differs from yours (e.g., '{search_ticker}.US' or other variant)
            - Finnhub's free tier doesn't cover this ticker

            **Check directly on Finnhub:** https://finnhub.io/dashboard
            **Check earnings on Yahoo Finance:** https://finance.yahoo.com/calendar/earnings?symbol={search_ticker}
            """)


def _render_table(upcoming, universe_tickers=None):
    """Render the full earnings table.

    Args:
        upcoming: DataFrame of upcoming earnings
        universe_tickers: Optional set of ticker symbols to filter to. If provided,
                         only earnings for tickers in this set will be shown.
    """
    # Filter to universe if provided
    if universe_tickers is not None and "symbol" in upcoming.columns:
        universe_upper = {t.upper() for t in universe_tickers}
        upcoming = upcoming[upcoming["symbol"].str.upper().isin(universe_upper)]
        if upcoming.empty:
            st.info("No earnings in the next window for tickers in your universe.")
            return

    display_rows = []
    for _, row in upcoming.iterrows():
        symbol = row.get("symbol", "")
        date = row.get("date")
        hour = row.get("hour", "")

        date_str = date.strftime("%a %b %d") if pd.notna(date) else ""
        hour_str = _format_hour(hour)

        # Keep numeric values for sorting - Streamlit will format via NumberColumn
        eps_est = row.get("epsEstimate")
        eps_est_num = float(eps_est) if pd.notna(eps_est) else None

        rev_est = row.get("revenueEstimate")
        rev_est_num = float(rev_est) if pd.notna(rev_est) and rev_est else None

        display_rows.append({
            "Ticker": symbol,
            "Date": date_str,
            "Time": hour_str,
            "EPS Est ($)": eps_est_num,
            "Revenue Est ($M)": rev_est_num / 1e6 if rev_est_num is not None else None,
        })

    if display_rows:
        df_display = pd.DataFrame(display_rows)

        # Use NumberColumn config for proper numeric sorting
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 * len(display_rows) + 50),
            column_config={
                "EPS Est ($)": st.column_config.NumberColumn(
                    "EPS Est",
                    format="$%.2f",
                ),
                "Revenue Est ($M)": st.column_config.NumberColumn(
                    "Revenue Est",
                    format="$%.1fM",
                    help="In millions. Sortable numerically.",
                ),
            },
        )


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


def render_ipo_calendar_panel(compact=False, days_out=14, universe_tickers=None):
    """
    Render the upcoming IPO calendar panel.

    Args:
        compact: If True, shows day-counts only with expandable detail.
        days_out: How many days forward to show (default 14 = 2 weeks).
        universe_tickers: Unused for IPOs (they aren't in universe yet).
                         Parameter kept for API consistency.
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


def _render_ipo_table(upcoming, universe_tickers=None):
    """Render the IPO table.

    Args:
        upcoming: DataFrame of upcoming IPOs
        universe_tickers: Optional set to filter (IPOs typically aren't in universe yet,
                         so this is rarely used)
    """
    # IPOs typically aren't in the existing universe yet (they haven't IPO'd!)
    # so we don't filter by default - but the option exists for symmetry

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
        shares_num = float(shares) / 1e6 if pd.notna(shares) and shares else None
        total_num = float(total_value) / 1e6 if pd.notna(total_value) and total_value else None

        display_rows.append({
            "Ticker": symbol if symbol else "—",
            "Company": (name[:40] + "...") if name and len(name) > 40 else (name if name else "—"),
            "Date": date_str,
            "Exchange": exchange if exchange else "—",
            "Price Range": price if price else "—",
            "Shares (M)": shares_num,
            "Est. Proceeds ($M)": total_num,
            "Status": status if status else "—",
        })

    if display_rows:
        df_display = pd.DataFrame(display_rows)
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 * len(display_rows) + 50),
            column_config={
                "Shares (M)": st.column_config.NumberColumn(
                    "Shares Offered",
                    format="%.1fM",
                ),
                "Est. Proceeds ($M)": st.column_config.NumberColumn(
                    "Est. Proceeds",
                    format="$%.1fM",
                ),
            },
        )


# ═══════════════════════════════════════════════════════════════════
# COMBINED PANEL: Earnings + IPOs side by side
# ═══════════════════════════════════════════════════════════════════

def render_combined_calendar_panel(compact=False, universe_tickers=None):
    """
    Render both Earnings and IPO calendars side-by-side or stacked.

    Used on Home tab for at-a-glance view.

    Args:
        compact: If True, more compact display
        universe_tickers: Optional set to filter earnings to tracked universe only.
                         IPOs are not filtered (they aren't in universe yet).
    """
    st.markdown("### 📅 This Week's Calendar")
    universe_note = " · Earnings filtered to tracked universe" if universe_tickers else ""
    st.caption(f"Companies reporting earnings + IPOs coming up. Earnings within 7 days, IPOs within 14 days.{universe_note}")

    # Two columns side by side
    earnings_col, ipo_col = st.columns(2)

    with earnings_col:
        st.markdown("#### 📊 Earnings This Week")
        # Use merged calendar (Finnhub + yfinance backup) if universe provided
        if universe_tickers is not None:
            df_e = get_merged_earnings_calendar(universe_tickers, days_ahead=7)
        else:
            df_e = fetch_earnings_calendar()
        if df_e.empty:
            st.info("No earnings data available.")
        else:
            # Filter to universe
            if universe_tickers is not None and "symbol" in df_e.columns:
                universe_upper = {t.upper() for t in universe_tickers}
                df_e = df_e[df_e["symbol"].str.upper().isin(universe_upper)]

            if df_e.empty:
                st.info("No tracked universe companies reporting earnings.")
            else:
                today = pd.Timestamp(datetime.now().date())
                cutoff = today + timedelta(days=7)
                upcoming_e = df_e[(df_e["date"] >= today) & (df_e["date"] <= cutoff)] if "date" in df_e.columns else df_e
                if upcoming_e.empty:
                    st.info("No earnings scheduled in the next 7 days.")
                else:
                    # Quick day-count display - sort by actual date, not string
                    upcoming_e = upcoming_e.copy()
                    upcoming_e["day_str"] = upcoming_e["date"].dt.strftime("%a %b %d")
                    upcoming_e["day_sort_date"] = upcoming_e["date"].dt.date

                    day_counts = upcoming_e.groupby(["day_sort_date", "day_str"]).size().reset_index(name="count")
                    day_counts = day_counts.sort_values("day_sort_date")  # Chronological

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
