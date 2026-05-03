"""
Forward Outlook Module
======================

Pulls forward-looking data for a ticker from free sources:
1. yfinance: analyst consensus estimates (next Q, next Y, EPS trend)
2. SEC EDGAR: most recent 8-K filing for company guidance language extraction

This is BEST-EFFORT. Companies don't file guidance in structured XBRL format,
so 8-K parsing is regex-based and will miss many cases. We show analyst
estimates as the reliable forward signal and 8-K guidance as a bonus when
we can extract it cleanly.

Zero-cost — uses only free APIs.
"""

import re
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List

import pandas as pd
import streamlit as st


# ─────────────────────────────────────────────────────────────────────
# yfinance analyst forward estimates
# ─────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_analyst_estimates(ticker: str) -> Dict:
    """
    Pull analyst forward estimates from yfinance.

    Returns dict with keys:
      - earnings_estimate: DataFrame with periods (0q, +1q, 0y, +1y)
      - revenue_estimate: DataFrame
      - eps_trend: DataFrame showing estimate revisions over time
      - earnings_history: DataFrame of last 4 quarters actual vs estimate
      - error: error message if fetch failed entirely
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)

        result = {}

        # Each of these can independently be empty/missing
        for attr_name in ("earnings_estimate", "revenue_estimate", "eps_trend",
                          "earnings_history", "eps_revisions"):
            try:
                df = getattr(t, attr_name, None)
                if df is not None and not df.empty:
                    result[attr_name] = df
            except Exception:
                pass

        if not result:
            result["error"] = "No analyst estimate data returned"

        return result

    except Exception as e:
        return {"error": f"yfinance error: {str(e)[:100]}"}


# ─────────────────────────────────────────────────────────────────────
# SEC EDGAR 8-K guidance extraction (best-effort)
# ─────────────────────────────────────────────────────────────────────

EDGAR_HEADERS = {
    "User-Agent": "QuantDashboard bradgpt@yahoo.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}

# Regex patterns for common guidance language
# These are intentionally conservative — false negatives are better than false positives
GUIDANCE_PATTERNS = [
    # "We expect [revenue/EPS] of $X to $Y"
    re.compile(
        r'(?:we|company|management)\s+(?:expect|anticipate|project|forecast|estimate|believe)s?\s+'
        r'(?:that\s+)?(?:our\s+|total\s+|net\s+)?'
        r'(revenue|sales|earnings|eps|operating income|gross margin|operating margin|net income|cash flow)'
        r'[\s\w,\-]{0,100}'
        r'(?:of|to be|in (?:a|the)? range of|between)?\s*\$?([\d,]+\.?\d*)\s*'
        r'(?:to|-|–)\s*\$?([\d,]+\.?\d*)\s*'
        r'(billion|million|thousand|B|M|K)?',
        re.IGNORECASE
    ),
    # "guidance for [period]" — capture context phrases
    re.compile(
        r'(?:guidance|outlook)\s+(?:for|of|on)\s+(?:the\s+)?'
        r'(?:full\s+year|fiscal\s+year|next\s+quarter|FY\s*\d{4}|Q\d\s*\d{4})'
        r'[\s\w]{0,200}',
        re.IGNORECASE
    ),
    # "raising/lowering/reaffirming guidance"
    re.compile(
        r'(raising|raised|lowering|lowered|reaffirming|reaffirmed|maintaining|maintained|'
        r'narrowing|narrowed|reiterating|reiterated|updating|updated)\s+'
        r'(?:our\s+|the\s+)?(?:full\s+year\s+|annual\s+|quarterly\s+|fiscal\s+)?(?:guidance|outlook|forecast|estimates)'
        r'[\s\w,\.\$\-]{0,300}',
        re.IGNORECASE
    ),
]


@st.cache_data(ttl=86400, show_spinner=False)  # 24h cache - filings don't change
def fetch_recent_8k(ticker: str) -> Optional[Dict]:
    """
    Fetch the most recent 8-K filing for a ticker from SEC EDGAR.

    Returns dict with:
      - filing_date: str
      - accession: str (e.g., "0000320193-25-000115")
      - press_release_text: str (full text of Exhibit 99.1 if found)
      - error: error message
    """
    try:
        # Step 1: Get CIK from ticker
        # SEC has a ticker-to-CIK lookup
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": EDGAR_HEADERS["User-Agent"]},
            timeout=15
        )
        if r.status_code != 200:
            return {"error": f"Could not fetch CIK lookup: HTTP {r.status_code}"}

        ticker_lookup = r.json()
        cik = None
        for entry in ticker_lookup.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                break

        if not cik:
            return {"error": f"Ticker {ticker} not found in SEC database"}

        # Step 2: Get recent filings
        r = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers={"User-Agent": EDGAR_HEADERS["User-Agent"]},
            timeout=15
        )
        if r.status_code != 200:
            return {"error": f"Could not fetch filings list: HTTP {r.status_code}"}

        data = r.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        # Find the most recent 8-K with earnings-related items
        eight_k_idx = None
        for i, form in enumerate(forms):
            if form == "8-K":
                eight_k_idx = i
                break

        if eight_k_idx is None:
            return {"error": "No recent 8-K found"}

        accession = accessions[eight_k_idx]
        filing_date = dates[eight_k_idx]
        primary_doc = primary_docs[eight_k_idx]
        accession_clean = accession.replace("-", "")

        # Step 3: Get the filing index to find Exhibit 99.1
        index_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=8-K&dateb=&owner=include&count=10"
        # Better: use the structured filing index
        filing_index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/"

        r = requests.get(
            filing_index_url,
            headers={"User-Agent": EDGAR_HEADERS["User-Agent"]},
            timeout=15
        )
        if r.status_code != 200:
            return {
                "filing_date": filing_date,
                "accession": accession,
                "filing_url": filing_index_url,
                "error": f"Could not access filing index: HTTP {r.status_code}",
            }

        # Find the press release (usually ex99-1, ex991, or similar in filename)
        # Parse the directory listing
        filing_html = r.text
        press_release_files = re.findall(
            r'href="([^"]*(?:ex99|ex_99|exhibit99|exhibit_99)[^"]*\.htm[l]?)"',
            filing_html,
            re.IGNORECASE
        )

        press_release_text = None
        if press_release_files:
            # Try the first one
            pr_url = "https://www.sec.gov" + press_release_files[0] if press_release_files[0].startswith("/") else filing_index_url + press_release_files[0]
            try:
                r = requests.get(pr_url, headers={"User-Agent": EDGAR_HEADERS["User-Agent"]}, timeout=15)
                if r.status_code == 200:
                    # Strip HTML tags crudely
                    text = re.sub(r'<[^>]+>', ' ', r.text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    press_release_text = text[:50000]  # cap at 50K chars
            except Exception:
                pass

        return {
            "filing_date": filing_date,
            "accession": accession,
            "filing_url": filing_index_url,
            "press_release_text": press_release_text,
        }

    except Exception as e:
        return {"error": f"8-K fetch error: {str(e)[:200]}"}


def extract_guidance_snippets(text: str, max_snippets: int = 5) -> List[Dict]:
    """
    Run regex patterns over press release text to find guidance-like sentences.

    Returns list of dicts:
      - pattern_type: 'specific_target' | 'period_outlook' | 'raise_lower'
      - snippet: the matched text (truncated to readable length)
    """
    if not text:
        return []

    snippets = []

    # Try each pattern
    for i, pattern in enumerate(GUIDANCE_PATTERNS):
        for match in pattern.finditer(text):
            # Get surrounding context (before + match + after)
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()

            # Clean up
            context = re.sub(r'\s+', ' ', context)
            if len(context) < 20:
                continue

            pattern_types = ["specific_target", "period_outlook", "raise_lower"]
            snippet_type = pattern_types[i] if i < len(pattern_types) else "other"

            snippets.append({
                "pattern_type": snippet_type,
                "snippet": context[:400],  # cap each snippet
            })

            if len(snippets) >= max_snippets:
                return snippets

    return snippets


# ─────────────────────────────────────────────────────────────────────
# UI rendering
# ─────────────────────────────────────────────────────────────────────

def render_forward_outlook(ticker: str):
    """
    Render the Forward Outlook section for a ticker.

    Section 1: Analyst forward consensus (yfinance)
    Section 2: Estimate trend over time (yfinance eps_trend)
    Section 3: Latest 8-K guidance extraction (best effort)
    """
    st.markdown("### 🔭 Forward Outlook")
    st.caption("Forward-looking analyst estimates and best-effort guidance extraction from latest 8-K filing.")

    # Fetch both sources in parallel
    estimates_data = fetch_analyst_estimates(ticker)

    # ── Section 1: Analyst Forward Consensus ──
    st.markdown("#### Analyst Forward Consensus")

    if "error" in estimates_data:
        st.info(f"No analyst forward estimates available. ({estimates_data['error']})")
    else:
        ee = estimates_data.get("earnings_estimate")
        re_data = estimates_data.get("revenue_estimate")

        if ee is not None and not ee.empty:
            # ee has columns like avg, low, high, numberOfAnalysts, growth
            # Index is the period (0q, +1q, 0y, +1y)
            display_rows = []
            period_labels = {
                "0q": "Current Quarter",
                "+1q": "Next Quarter",
                "0y": "Current Year",
                "+1y": "Next Year",
            }
            for period in ee.index:
                row = ee.loc[period]
                label = period_labels.get(period, period)
                avg = row.get("avg")
                low = row.get("low")
                high = row.get("high")
                num = row.get("numberOfAnalysts")
                growth = row.get("growth")

                if avg is not None and not pd.isna(avg):
                    rev_avg = None
                    if re_data is not None and period in re_data.index:
                        rev_avg = re_data.loc[period].get("avg")

                    display_rows.append({
                        "Period": label,
                        "EPS Estimate": f"${avg:.2f}",
                        "EPS Range": f"${low:.2f} – ${high:.2f}" if not pd.isna(low) and not pd.isna(high) else "—",
                        "Revenue Estimate": f"${rev_avg/1e9:.2f}B" if rev_avg and not pd.isna(rev_avg) else "—",
                        "Growth": f"{growth*100:+.1f}%" if growth is not None and not pd.isna(growth) else "—",
                        "# Analysts": int(num) if num is not None and not pd.isna(num) else "—",
                    })

            if display_rows:
                st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
            else:
                st.info("Forward consensus data is empty for this ticker.")
        else:
            st.info("No forward earnings consensus available.")

        # ── Section 2: Estimate Trend ──
        eps_trend = estimates_data.get("eps_trend")
        if eps_trend is not None and not eps_trend.empty:
            st.markdown("#### Estimate Trend (Last 90 Days)")
            st.caption("How analyst consensus has evolved over time. Up = analysts becoming more bullish; down = becoming more bearish.")

            trend_rows = []
            for period in eps_trend.index:
                row = eps_trend.loc[period]
                label = period_labels.get(period, period)
                trend_rows.append({
                    "Period": label,
                    "Current": f"${row.get('current', 0):.2f}" if not pd.isna(row.get('current', None)) else "—",
                    "7 Days Ago": f"${row.get('7daysAgo', 0):.2f}" if not pd.isna(row.get('7daysAgo', None)) else "—",
                    "30 Days Ago": f"${row.get('30daysAgo', 0):.2f}" if not pd.isna(row.get('30daysAgo', None)) else "—",
                    "60 Days Ago": f"${row.get('60daysAgo', 0):.2f}" if not pd.isna(row.get('60daysAgo', None)) else "—",
                    "90 Days Ago": f"${row.get('90daysAgo', 0):.2f}" if not pd.isna(row.get('90daysAgo', None)) else "—",
                })

            if trend_rows:
                st.dataframe(pd.DataFrame(trend_rows), use_container_width=True, hide_index=True)

    # ── Section 3: Company Guidance from 8-K ──
    st.markdown("---")
    st.markdown("#### Company Guidance (from latest 8-K filing)")
    st.caption("Best-effort extraction. Companies file guidance in unstructured language; this regex-based parser will miss some cases.")

    with st.spinner("Pulling latest 8-K filing..."):
        eight_k = fetch_recent_8k(ticker)

    if not eight_k or "error" in (eight_k or {}):
        err = (eight_k or {}).get("error", "Could not fetch recent 8-K")
        st.info(f"Could not extract guidance: {err}")
        return

    filing_date = eight_k.get("filing_date", "unknown")
    filing_url = eight_k.get("filing_url", "")
    pr_text = eight_k.get("press_release_text")

    st.caption(f"📄 Latest 8-K filed: **{filing_date}** | [View on SEC.gov]({filing_url})")

    if not pr_text:
        st.info("Could not retrieve press release text from this 8-K. The filing may not include a press release exhibit.")
        return

    snippets = extract_guidance_snippets(pr_text)

    if not snippets:
        st.info(
            "No structured guidance language found in the latest 8-K press release. "
            "This is common — companies often state guidance in earnings call discussion (transcripts not parsed here) "
            "rather than in the press release itself. Click the SEC.gov link above to read the filing directly."
        )
        return

    st.markdown(f"**Found {len(snippets)} guidance-like passage(s):**")
    for i, snip in enumerate(snippets, 1):
        ptype_label = {
            "specific_target": "🎯 Specific Target",
            "period_outlook": "📅 Period Outlook",
            "raise_lower": "📊 Guidance Change",
        }.get(snip["pattern_type"], "Other")

        with st.expander(f"{ptype_label} — Passage {i}"):
            st.markdown(f"> {snip['snippet']}")

    st.caption(
        "⚠️ This extraction is approximate. The exact guidance numbers, periods, and qualifications "
        "are best read in the full filing. Earnings call transcripts (which often contain the most detailed "
        "guidance) are not parsed here — they require separate transcript APIs."
    )
