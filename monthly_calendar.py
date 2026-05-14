"""
Monthly Economic & Earnings Calendar widget.

Replaces the old text-list `render_economic_calendar_panel()` with a 7-column
month-grid view that integrates:
- Major US economic releases (CPI, PCE, NFP, FOMC, GDP, ISM, etc.)
- S&P 100-equivalent bellwether earnings (top 100 by market cap from scored_df)

Lazy-loaded via expander to avoid blocking page load. Earnings dates cached
for 24 hours to avoid hammering yfinance.

Bellwether universe is derived from scored_df at runtime (top 100 by market
cap) — auto-updates whenever the universe refreshes. No hardcoded ticker list.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st


# ───────────────────────────────────────────────────────────────
# Recurring monthly economic release schedule (US)
# ───────────────────────────────────────────────────────────────
# These are heuristic typical-release-day rules. The BLS, BEA, ISM, etc.
# publish on consistent monthly cadences. We compute the next scheduled
# date deterministically from the rule rather than scraping individual
# calendar pages.
#
# Where a release sits on a "first Friday" or "third Wednesday" cadence,
# we compute that. Where it's a fixed day-of-month (e.g., "around the 10th"),
# we use that as the typical target.

# Format: (release_name, frequency, day_rule)
#   frequency: "monthly" | "quarterly" | "weekly" | "ad_hoc"
#   day_rule: dict describing when in the period the release happens
#     "fixed_day": int (1-31) — typical day of month
#     "nth_weekday": tuple (n, weekday) — e.g. (1, 4) = 1st Friday
#                                              (3, 2) = 3rd Wednesday
#                                              weekday is 0=Mon, 6=Sun
ECONOMIC_RELEASES = [
    # Labor market
    {"name": "Nonfarm Payrolls", "agency": "BLS", "freq": "monthly",
     "rule": {"nth_weekday": (1, 4)}, "tier": 1},
    {"name": "Initial Jobless Claims", "agency": "DOL", "freq": "weekly",
     "rule": {"weekday": 3}, "tier": 2},
    {"name": "JOLTS Job Openings", "agency": "BLS", "freq": "monthly",
     "rule": {"fixed_day": 7}, "tier": 2},

    # Inflation
    {"name": "CPI", "agency": "BLS", "freq": "monthly",
     "rule": {"fixed_day": 12}, "tier": 1},
    {"name": "Core PCE", "agency": "BEA", "freq": "monthly",
     "rule": {"fixed_day": 28}, "tier": 1},
    {"name": "PPI", "agency": "BLS", "freq": "monthly",
     "rule": {"fixed_day": 13}, "tier": 2},

    # Growth
    {"name": "GDP (Advance)", "agency": "BEA", "freq": "quarterly",
     "rule": {"quarterly_months": [1, 4, 7, 10], "fixed_day": 28}, "tier": 1},
    {"name": "Retail Sales", "agency": "Census", "freq": "monthly",
     "rule": {"fixed_day": 16}, "tier": 2},
    {"name": "Industrial Production", "agency": "Fed", "freq": "monthly",
     "rule": {"fixed_day": 17}, "tier": 3},

    # Housing
    {"name": "Housing Starts", "agency": "Census", "freq": "monthly",
     "rule": {"fixed_day": 18}, "tier": 3},
    {"name": "Existing Home Sales", "agency": "NAR", "freq": "monthly",
     "rule": {"fixed_day": 22}, "tier": 3},
    {"name": "New Home Sales", "agency": "Census", "freq": "monthly",
     "rule": {"fixed_day": 25}, "tier": 3},

    # Sentiment / surveys
    {"name": "ISM Manufacturing PMI", "agency": "ISM", "freq": "monthly",
     "rule": {"fixed_day": 1}, "tier": 1},
    {"name": "ISM Services PMI", "agency": "ISM", "freq": "monthly",
     "rule": {"fixed_day": 3}, "tier": 1},
    {"name": "Consumer Confidence", "agency": "Conf Board", "freq": "monthly",
     "rule": {"nth_weekday": (4, 1)}, "tier": 3},
    {"name": "U Mich Consumer Sentiment", "agency": "U Mich", "freq": "monthly",
     "rule": {"nth_weekday": (2, 4)}, "tier": 3},
]


def _compute_release_date(release: Dict, year: int, month: int) -> Optional[date]:
    """Given a release rule and a target month, return the expected release date."""
    rule = release["rule"]
    try:
        # Quarterly releases only happen in specific months
        if release["freq"] == "quarterly":
            valid_months = rule.get("quarterly_months", [])
            if month not in valid_months:
                return None

        # Weekly releases need different handling (they happen every week)
        if release["freq"] == "weekly":
            # Return None here; weekly is rendered separately if needed
            return None

        # "nth weekday of month" rule (e.g. 1st Friday for NFP)
        if "nth_weekday" in rule:
            n, weekday = rule["nth_weekday"]
            # Find the nth occurrence of `weekday` in the month
            first_of_month = date(year, month, 1)
            offset = (weekday - first_of_month.weekday()) % 7
            day = 1 + offset + (n - 1) * 7
            if day > calendar.monthrange(year, month)[1]:
                return None
            return date(year, month, day)

        # Fixed day-of-month rule
        if "fixed_day" in rule:
            day = rule["fixed_day"]
            max_day = calendar.monthrange(year, month)[1]
            day = min(day, max_day)
            d = date(year, month, day)
            # If the day falls on a weekend, push to next Monday
            # (BLS/BEA practice; close enough for display)
            if d.weekday() == 5:  # Saturday
                d = d + timedelta(days=2)
            elif d.weekday() == 6:  # Sunday
                d = d + timedelta(days=1)
            return d
    except Exception:
        return None
    return None


def get_economic_releases_for_month(year: int, month: int) -> Dict[date, List[Dict]]:
    """Return {date: [release dicts]} for all releases scheduled in a given month."""
    result: Dict[date, List[Dict]] = {}
    for release in ECONOMIC_RELEASES:
        release_date = _compute_release_date(release, year, month)
        if release_date is None:
            continue
        # Skip if the computed date drifted into a different month
        # (e.g., a "fixed_day=28" weekend-pushed Feb release lands in March)
        if release_date.month != month:
            continue
        result.setdefault(release_date, []).append(release)

    # Add weekly Initial Jobless Claims (every Thursday)
    weekly_release = next((r for r in ECONOMIC_RELEASES if r["freq"] == "weekly"), None)
    if weekly_release:
        weekday = weekly_release["rule"].get("weekday", 3)
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        # Find first Thursday
        offset = (weekday - first.weekday()) % 7
        d = first + timedelta(days=offset)
        while d <= last:
            result.setdefault(d, []).append(weekly_release)
            d += timedelta(days=7)

    return result


# ───────────────────────────────────────────────────────────────
# Bellwether earnings dates
# ───────────────────────────────────────────────────────────────

def _get_bellwether_tickers(scored_df: pd.DataFrame, n: int = 100) -> List[str]:
    """Top N tickers by market cap from the live universe.

    No hardcoded list. Auto-updates as scored_df refreshes during quarterly
    fundamentals cache rebuilds. SpaceX, Anthropic, or any future IPO will
    automatically appear here once they're trading and in the universe.
    """
    if scored_df is None or scored_df.empty:
        return []
    try:
        non_etf = scored_df[scored_df.get("sector", "") != "ETF"]
        # marketCapB column from your scoring pipeline
        top_n = non_etf.nlargest(n, "marketCapB")
        return top_n.index.tolist()
    except Exception:
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_earnings_dates_for_tickers(tickers_tuple: Tuple[str, ...]) -> Dict[date, List[str]]:
    """Fetch upcoming earnings dates for the given tickers (24-hour cache).

    Returns: {date: [list of ticker symbols]}.
    Uses yfinance's calendar attribute which gives the next scheduled earnings.
    Slow on first call (~30-50 seconds for 100 tickers) — cached aggressively
    to avoid repeat hits during the day.
    """
    import yfinance as yf
    result: Dict[date, List[str]] = {}
    for ticker in tickers_tuple:
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is None:
                continue
            # yfinance.calendar returns either a dict or a DataFrame depending on version
            earnings_date = None
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, list) and ed:
                    earnings_date = ed[0]
                elif ed:
                    earnings_date = ed
            elif hasattr(cal, "loc") and "Earnings Date" in (cal.index if hasattr(cal, "index") else []):
                # Older DataFrame format
                ed_row = cal.loc["Earnings Date"]
                if hasattr(ed_row, "iloc"):
                    earnings_date = ed_row.iloc[0]
                else:
                    earnings_date = ed_row

            if earnings_date is None:
                continue
            # Normalize to date
            if isinstance(earnings_date, (pd.Timestamp, datetime)):
                ed_date = earnings_date.date() if hasattr(earnings_date, "date") else earnings_date
            elif isinstance(earnings_date, date):
                ed_date = earnings_date
            else:
                continue

            result.setdefault(ed_date, []).append(ticker)
        except Exception:
            # Silently skip tickers that error (delisted, missing, etc.)
            continue
    return result


def get_bellwether_earnings_for_range(
    scored_df: pd.DataFrame,
    start_date: date,
    end_date: date,
    n_bellwethers: int = 100,
) -> Dict[date, List[str]]:
    """Get earnings dates for bellwethers within the given date range."""
    tickers = _get_bellwether_tickers(scored_df, n=n_bellwethers)
    if not tickers:
        return {}
    all_dates = _fetch_earnings_dates_for_tickers(tuple(tickers))
    # Filter to date range
    return {d: tk for d, tk in all_dates.items() if start_date <= d <= end_date}


# ───────────────────────────────────────────────────────────────
# Calendar rendering
# ───────────────────────────────────────────────────────────────

def _tier_color(tier: int) -> str:
    """Color code for release importance tier."""
    return {
        1: "#22C55E",  # green — top tier (CPI, NFP, FOMC)
        2: "#EAB308",  # yellow — second tier
        3: "#94A3B8",  # gray — supporting
    }.get(tier, "#94A3B8")


def _render_day_cell(
    day_date: date,
    is_in_month: bool,
    is_today: bool,
    releases: List[Dict],
    earnings: List[str],
) -> str:
    """Render a single day cell as inline HTML."""
    bg_color = "#1a1f2e" if is_in_month else "#0a0e1a"
    today_border = "border:2px solid #4ECDC4;" if is_today else "border:1px solid #2a2f3e;"
    opacity = "1.0" if is_in_month else "0.4"

    html = (
        f'<div style="background:{bg_color};{today_border}'
        f'border-radius:6px;padding:6px 8px;min-height:110px;'
        f'opacity:{opacity};font-size:0.78em;">'
    )
    html += (
        f'<div style="color:#94a3b8;font-weight:700;font-size:0.85em;margin-bottom:4px;">'
        f'{day_date.day}</div>'
    )

    # Economic releases (limit 3 visible per cell)
    visible_releases = sorted(releases, key=lambda r: r.get("tier", 99))[:3]
    for r in visible_releases:
        c = _tier_color(r.get("tier", 3))
        name = r["name"]
        # Truncate for narrow cells
        short = name if len(name) <= 14 else name[:13] + "."
        html += (
            f'<div style="color:{c};font-size:0.85em;line-height:1.2;'
            f'margin-bottom:2px;" title="{name}">▪ {short}</div>'
        )
    if len(releases) > 3:
        html += f'<div style="color:#666;font-size:0.75em;">+{len(releases)-3} more</div>'

    # Bellwether earnings (limit 3 visible)
    visible_earnings = sorted(earnings)[:3]
    for tk in visible_earnings:
        html += (
            f'<div style="color:#FCD34D;font-size:0.85em;line-height:1.2;'
            f'margin-bottom:2px;" title="{tk} earnings">📊 {tk}</div>'
        )
    if len(earnings) > 3:
        html += f'<div style="color:#666;font-size:0.75em;">+{len(earnings)-3} earnings</div>'

    html += '</div>'
    return html


def _render_calendar_grid(
    year: int,
    month: int,
    economic_by_date: Dict[date, List[Dict]],
    earnings_by_date: Dict[date, List[str]],
) -> str:
    """Build the full HTML for one month's calendar grid."""
    today = date.today()
    cal = calendar.Calendar(firstweekday=6)  # Sunday-first
    weeks = cal.monthdatescalendar(year, month)

    # Header row: day-of-week labels
    days_of_week = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    html = (
        '<div style="display:grid;grid-template-columns:repeat(7,1fr);'
        'gap:4px;margin-top:8px;">'
    )
    for dow in days_of_week:
        html += (
            f'<div style="text-align:center;color:#94a3b8;font-weight:700;'
            f'font-size:0.8em;padding:4px;">{dow}</div>'
        )
    # Day cells
    for week in weeks:
        for day_date in week:
            is_in_month = (day_date.month == month and day_date.year == year)
            is_today = (day_date == today)
            releases = economic_by_date.get(day_date, [])
            earnings = earnings_by_date.get(day_date, [])
            html += _render_day_cell(day_date, is_in_month, is_today, releases, earnings)
    html += '</div>'
    return html


# ───────────────────────────────────────────────────────────────
# Public entry point
# ───────────────────────────────────────────────────────────────

def render_monthly_calendar(scored_df: pd.DataFrame, n_bellwethers: int = 100) -> None:
    """Render the monthly calendar inside an expander (lazy-load).

    The calendar is collapsed by default; expanding triggers the first-time
    earnings fetch which can take ~30-50s for 100 tickers. After that the
    results are cached for 24 hours, so subsequent expansions are instant.
    """
    st.markdown("### 🗓 Monthly Economic & Earnings Calendar")
    st.caption(
        "Major US economic releases plus bellwether (top-100 by market cap) earnings dates. "
        "Click below to expand. Earnings dates cache for 24 hours after first load."
    )

    # Session state for month navigation
    if "mcal_year" not in st.session_state:
        today = date.today()
        st.session_state.mcal_year = today.year
        st.session_state.mcal_month = today.month

    with st.expander("Open calendar", expanded=False):
        # ── Navigation row: prev / current month / next ──
        nav_cols = st.columns([1, 4, 1])
        with nav_cols[0]:
            if st.button("◀ Prev", key="mcal_prev"):
                m = st.session_state.mcal_month
                y = st.session_state.mcal_year
                if m == 1:
                    st.session_state.mcal_month = 12
                    st.session_state.mcal_year = y - 1
                else:
                    st.session_state.mcal_month = m - 1
                st.rerun()
        with nav_cols[1]:
            mname = calendar.month_name[st.session_state.mcal_month]
            st.markdown(
                f'<div style="text-align:center;font-size:1.4em;font-weight:700;'
                f'color:#e0e0e0;padding:6px 0;">{mname} {st.session_state.mcal_year}</div>',
                unsafe_allow_html=True,
            )
        with nav_cols[2]:
            if st.button("Next ▶", key="mcal_next"):
                m = st.session_state.mcal_month
                y = st.session_state.mcal_year
                if m == 12:
                    st.session_state.mcal_month = 1
                    st.session_state.mcal_year = y + 1
                else:
                    st.session_state.mcal_month = m + 1
                st.rerun()

        year = st.session_state.mcal_year
        month = st.session_state.mcal_month

        # Compute economic releases for this month (fast)
        econ_by_date = get_economic_releases_for_month(year, month)

        # Fetch earnings (slow on first call, cached for 24h)
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        with st.spinner("Loading bellwether earnings dates (cached 24h after first load)..."):
            earnings_by_date = get_bellwether_earnings_for_range(
                scored_df, month_start, month_end, n_bellwethers=n_bellwethers
            )

        # Render the grid
        html = _render_calendar_grid(year, month, econ_by_date, earnings_by_date)
        st.markdown(html, unsafe_allow_html=True)

        # Legend
        st.markdown(
            '<div style="margin-top:12px;font-size:0.85em;color:#94a3b8;">'
            '<span style="color:#22C55E;">▪</span> Tier 1 (CPI, NFP, ISM, GDP) &nbsp;·&nbsp; '
            '<span style="color:#EAB308;">▪</span> Tier 2 (Retail, PPI, JOLTS) &nbsp;·&nbsp; '
            '<span style="color:#94A3B8;">▪</span> Tier 3 (housing, sentiment) &nbsp;·&nbsp; '
            '<span style="color:#FCD34D;">📊</span> Bellwether earnings'
            '</div>',
            unsafe_allow_html=True,
        )

        st.caption(
            "Economic release dates are computed from typical release-day patterns and may "
            "drift ±1-2 days from actual published dates. For the official schedule see "
            "bls.gov/schedule, bea.gov/news, ismworld.org. Earnings dates from yfinance."
        )
