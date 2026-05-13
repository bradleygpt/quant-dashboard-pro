"""
Federal Reserve FOMC Meeting Calendar scraper.

The Fed publishes FOMC meeting dates at:
  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

This module scrapes the HTML to find the next upcoming meeting. Falls back
to a hardcoded list if scraping fails (Fed publishes the full year in advance,
so manual updates are infrequent — once per year minimum).

Zero-cost: no API key required. Cached aggressively (24-hour TTL) since
meeting dates rarely change.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

# Headers to look like a real browser (Fed sometimes blocks bare requests)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QuantDashboardPro/1.0; bmhartnett@yahoo.com)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


# Hardcoded fallback — known 2026 FOMC meeting dates.
# Source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
# UPDATE ANNUALLY when Fed publishes next year's calendar.
_FALLBACK_2026_MEETINGS = [
    "2026-01-28",  # Jan 27-28
    "2026-03-19",  # Mar 18-19 (SEP)
    "2026-04-30",  # Apr 29-30
    "2026-06-18",  # Jun 17-18 (SEP)
    "2026-07-30",  # Jul 29-30
    "2026-09-17",  # Sep 16-17 (SEP)
    "2026-11-05",  # Nov 4-5
    "2026-12-17",  # Dec 16-17 (SEP)
]

_FALLBACK_2027_MEETINGS = [
    "2027-01-27",  # tentative — verify when published
    "2027-03-18",
    "2027-04-29",
    "2027-06-17",
    "2027-07-29",
    "2027-09-16",
    "2027-11-04",
    "2027-12-16",
]


if _HAS_STREAMLIT:
    _cache_data = st.cache_data(ttl=86400, show_spinner=False)  # 24-hour cache
else:
    def _cache_data(fn):
        return fn


@_cache_data
def _scrape_fomc_meetings() -> Optional[List[str]]:
    """Scrape FOMC meeting dates from the Fed calendar page.

    Returns list of YYYY-MM-DD strings (last day of each meeting) or None on failure.
    Fed pages structure each meeting under a year heading with month/day text.
    Strategy: find date patterns near 'Meeting' or 'FOMC' anchors.
    """
    try:
        r = requests.get(FOMC_CALENDAR_URL, headers=_HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        html = r.text

        # Strategy: extract year-specific tables. Each FOMC year section has a
        # consistent structure with month abbreviations and day numbers.
        # Look for patterns like:
        #   <th>March</th>... <td>18-19</td>
        # The last day of the meeting is the "decision day".

        meetings = []

        # Get year sections — search for "2026 FOMC Meetings", "2027 FOMC Meetings", etc.
        year_sections = re.findall(
            r'(\d{4})\s+FOMC\s+Meetings(.*?)(?=\d{4}\s+FOMC\s+Meetings|</main>|\Z)',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        for year_str, section_html in year_sections:
            try:
                year = int(year_str)
            except ValueError:
                continue
            if year < datetime.now().year - 1 or year > datetime.now().year + 2:
                # Skip far-past or far-future years
                continue

            # Within the year section, find month + day-range pairs.
            # Common patterns:
            #   "March 18-19" or "January 28-29" or "January 28"
            month_day_pairs = re.findall(
                r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
                r'(\d{1,2})(?:[-–](\d{1,2}))?',
                section_html,
                re.IGNORECASE,
            )

            month_to_num = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12,
            }

            for month_name, start_day, end_day in month_day_pairs:
                month_num = month_to_num.get(month_name.lower())
                if not month_num:
                    continue
                # Use end_day if present (multi-day meeting), else start_day
                last_day = int(end_day) if end_day else int(start_day)
                try:
                    meeting_date = datetime(year, month_num, last_day)
                    meetings.append(meeting_date.strftime("%Y-%m-%d"))
                except ValueError:
                    # Invalid date (e.g., Feb 30) — skip
                    continue

        # Dedupe and sort
        meetings = sorted(set(meetings))
        # Sanity check: expect at least 4 meetings/year if scrape worked
        if len(meetings) < 4:
            return None
        return meetings
    except Exception:
        return None


def get_next_fomc_meeting() -> Dict:
    """Return info about the next upcoming FOMC meeting.

    Tries scraping first, falls back to hardcoded list. Returns:
      {
        "next_meeting": "YYYY-MM-DD",
        "days_until": int,
        "has_sep": bool,  # True if this meeting includes the Summary of Economic Projections
        "source": "scraped" | "hardcoded",
        "all_upcoming": [list of all upcoming meeting dates],
      }
    """
    today = datetime.now().date()

    # Try scraping
    scraped = _scrape_fomc_meetings()
    if scraped:
        upcoming = [d for d in scraped if datetime.strptime(d, "%Y-%m-%d").date() >= today]
        if upcoming:
            next_d = upcoming[0]
            next_date = datetime.strptime(next_d, "%Y-%m-%d").date()
            days_until = (next_date - today).days
            return {
                "next_meeting": next_d,
                "days_until": days_until,
                "has_sep": _meeting_has_sep(next_date),
                "source": "scraped",
                "all_upcoming": upcoming,
            }

    # Fall back to hardcoded
    all_dates = _FALLBACK_2026_MEETINGS + _FALLBACK_2027_MEETINGS
    upcoming = [d for d in all_dates if datetime.strptime(d, "%Y-%m-%d").date() >= today]
    if not upcoming:
        # We're past all fallback dates — return something rather than None
        return {
            "next_meeting": "Unknown — calendar fetch failed",
            "days_until": 0,
            "has_sep": False,
            "source": "fallback_exhausted",
            "all_upcoming": [],
        }
    next_d = upcoming[0]
    next_date = datetime.strptime(next_d, "%Y-%m-%d").date()
    days_until = (next_date - today).days
    return {
        "next_meeting": next_d,
        "days_until": days_until,
        "has_sep": _meeting_has_sep(next_date),
        "source": "hardcoded",
        "all_upcoming": upcoming,
    }


def _meeting_has_sep(meeting_date) -> bool:
    """SEP releases happen at March, June, September, December meetings."""
    return meeting_date.month in (3, 6, 9, 12)
