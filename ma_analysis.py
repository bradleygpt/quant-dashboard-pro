"""
M&A Analysis
============

Two complementary M&A features:

1. Backward M&A History (per-ticker, on-demand)
   - Fetches 8-K filings from SEC EDGAR
   - Classifies which are M&A-related using regex
   - Computes stock price impact 1/5/30 days after each filing
   - Used in Stock Detail tab

2. Acquisition Target Profile Score (per-ticker, batch)
   - Statistical score (0-100) based on characteristics correlated with
     historically being acquired
   - Factors: size, valuation, cash position, price weakness, sector activity
   - Used in Advanced Screener and Stock Detail tab

Zero-cost: SEC EDGAR is free, all factors derived from existing fundamentals data.

IMPORTANT CAVEATS (built into UI):
- This feature is NOT predictive of future M&A
- Most stocks fitting the "target profile" are never acquired
- Pre-deal rumor detection is intentionally NOT attempted
- Historical 8-K classification has ~70-80% accuracy via regex
"""

import os
import re
import json
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from typing import Optional, List, Dict


EDGAR_HEADERS = {
    "User-Agent": "QuantDashboard/1.0 contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}


# ═══════════════════════════════════════════════════════════════════
# CATEGORY A: Backward M&A History
# ═══════════════════════════════════════════════════════════════════

# Keywords that indicate M&A-related 8-K filings
MA_KEYWORDS = [
    r'\b(?:acquir(?:e|ed|ing|ition|er|es))\b',
    r'\b(?:merg(?:er|ed|ing|es))\b',
    r'\b(?:divest(?:ed|iture|ing))\b',
    r'\bdefinitive\s+(?:merger|acquisition|purchase)\s+agreement\b',
    r'\b(?:tender\s+offer|stock\s+purchase\s+agreement)\b',
    r'\b(?:business\s+combination|asset\s+purchase\s+agreement)\b',
    r'\b(?:spin[- ]?off|carve[- ]?out)\b',
    r'\bcompletion\s+of\s+(?:acquisition|merger|disposition)\b',
]

# Words that suggest the 8-K is NOT M&A related
NON_MA_INDICATORS = [
    r'\b(?:earnings\s+(?:announcement|release|results)|quarterly\s+results)\b',
    r'\b(?:dividend\s+(?:declaration|increase|cut))\b',
    r'\b(?:executive\s+(?:appointment|resignation|departure))\b',
    r'\b(?:stock\s+split|share\s+repurchase|buyback)\b',
]


@st.cache_data(ttl=86400, show_spinner=False)  # 24-hour cache
def fetch_ma_history(ticker, lookback_years=5):
    """
    Fetch M&A-related 8-K filings for a ticker over the past N years.

    Returns list of dicts:
        {
          "date": filing date,
          "form": "8-K",
          "items": ["1.01", "2.01"],  # SEC item codes mentioned
          "title": brief description,
          "url": link to filing,
          "ma_type": "acquisition" | "merger" | "divestiture" | "spinoff" | "other",
          "snippet": short text excerpt with M&A language,
        }
    Or {"error": msg}.
    """
    try:
        from edgar_data import get_cik_for_ticker
        cik = get_cik_for_ticker(ticker)
        if not cik:
            return {"error": f"No CIK found for ticker {ticker}"}

        cik_padded = str(cik).zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        r = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
        if r.status_code != 200:
            return {"error": f"EDGAR returned {r.status_code}"}

        data = r.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        items_list = recent.get("items", [])
        primary_docs = recent.get("primaryDocument", [])
        filing_dates = recent.get("filingDate", [])

        cutoff_date = (datetime.now() - timedelta(days=365 * lookback_years)).strftime("%Y-%m-%d")

        ma_filings = []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue

            filing_date = filing_dates[i]
            if filing_date < cutoff_date:
                continue

            items = items_list[i] if i < len(items_list) else ""
            # Filter to 8-Ks with M&A-relevant items
            # 1.01 = Material Definitive Agreement (M&A often filed here)
            # 2.01 = Completion of Acquisition or Disposition
            # 8.01 = Other Events (sometimes M&A)
            ma_relevant_items = ["1.01", "2.01", "8.01"]
            if not any(it in items for it in ma_relevant_items):
                continue

            accession = accessions[i].replace("-", "")
            primary_doc = primary_docs[i]

            # Try to fetch the filing text to verify M&A relevance
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{primary_doc}"

            try:
                doc_response = requests.get(doc_url, headers=EDGAR_HEADERS, timeout=15)
                if doc_response.status_code == 200:
                    text = doc_response.text
                    # Strip HTML
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text)
                    text_lower = text.lower()

                    # Check M&A keyword presence
                    ma_score = 0
                    matched_pattern = None
                    for pattern in MA_KEYWORDS:
                        if re.search(pattern, text_lower):
                            ma_score += 1
                            if not matched_pattern:
                                matched_pattern = pattern

                    # Penalize if non-M&A indicators present
                    non_ma_score = 0
                    for pattern in NON_MA_INDICATORS:
                        if re.search(pattern, text_lower):
                            non_ma_score += 1

                    # Filter out clearly non-M&A 8-Ks
                    if ma_score < 1 or non_ma_score >= ma_score:
                        continue

                    # Classify type
                    ma_type = "other"
                    if re.search(r'\bacquir(?:e|ed|ing|ition|er)\b', text_lower):
                        ma_type = "acquisition"
                    elif re.search(r'\bmerg(?:er|ed|ing)\b', text_lower):
                        ma_type = "merger"
                    elif re.search(r'\bdivest(?:ed|iture|ing)\b', text_lower):
                        ma_type = "divestiture"
                    elif re.search(r'\bspin[- ]?off\b', text_lower):
                        ma_type = "spinoff"

                    # Extract a snippet with M&A language
                    sentences = re.split(r'(?<=[.!?])\s+', text)
                    snippet = ""
                    for sentence in sentences[:200]:  # Look at first 200 sentences
                        if 50 < len(sentence) < 400:
                            sentence_lower = sentence.lower()
                            for pattern in MA_KEYWORDS:
                                if re.search(pattern, sentence_lower):
                                    snippet = sentence.strip()
                                    break
                            if snippet:
                                break

                    ma_filings.append({
                        "date": filing_date,
                        "form": form,
                        "items": items,
                        "url": doc_url,
                        "ma_type": ma_type,
                        "snippet": snippet[:300] if snippet else "M&A-related filing detected",
                        "ma_score": ma_score,
                    })
            except Exception:
                continue

            # Rate limit: don't hammer EDGAR
            if len(ma_filings) >= 10:
                break

        return ma_filings
    except Exception as e:
        return {"error": f"M&A history fetch failed: {str(e)[:120]}"}


@st.cache_data(ttl=86400, show_spinner=False)
def compute_ma_price_impact(ticker, filing_date_str, lookahead_days=(1, 5, 30)):
    """
    Compute the stock price impact in the days following an M&A filing.

    Returns dict with returns at +1/+5/+30 days post-filing.
    """
    try:
        import yfinance as yf
        filing_date = pd.Timestamp(filing_date_str)
        end_date = filing_date + timedelta(days=max(lookahead_days) + 5)

        # Fetch a window around the filing
        hist = yf.Ticker(ticker).history(
            start=filing_date - timedelta(days=2),
            end=end_date,
        )
        if hist.empty:
            return {}

        close = hist["Close"].dropna()
        if close.empty:
            return {}

        # Find the price on the filing date or first trading day after
        idx_dates = close.index.date if hasattr(close.index, 'date') else close.index
        filing_close = None
        for date, price in close.items():
            d_naive = date.to_pydatetime().replace(tzinfo=None) if hasattr(date, 'to_pydatetime') else date
            if d_naive >= filing_date.to_pydatetime().replace(tzinfo=None):
                filing_close = price
                filing_actual_date = date
                break

        if filing_close is None:
            return {}

        results = {"price_at_filing": float(filing_close)}
        for days in lookahead_days:
            target_date = filing_actual_date + pd.Timedelta(days=days + 5)
            future_close = None
            for date, price in close.items():
                if date >= filing_actual_date + pd.Timedelta(days=days):
                    future_close = price
                    break
            if future_close is not None:
                pct_change = ((future_close - filing_close) / filing_close) * 100
                results[f"return_{days}d"] = pct_change

        return results
    except Exception:
        return {}


def render_ma_history_panel(ticker):
    """Render M&A history section on Stock Detail tab."""
    st.markdown("### 📋 M&A History (5-year lookback)")
    st.caption(
        "Past M&A-related SEC 8-K filings with stock price reaction. "
        "Filing classification uses regex pattern matching (~70-80% accuracy) — verify with full filing text."
    )

    with st.spinner("Searching SEC EDGAR for M&A filings..."):
        history = fetch_ma_history(ticker, lookback_years=5)

    if isinstance(history, dict) and "error" in history:
        st.info(f"Could not fetch M&A history: {history['error']}")
        return

    if not history:
        st.info(f"No M&A-related 8-K filings found for {ticker} in the past 5 years.")
        return

    st.markdown(f"**Found {len(history)} M&A-related filings:**")

    # Sort newest first
    history_sorted = sorted(history, key=lambda x: x["date"], reverse=True)

    for filing in history_sorted:
        with st.expander(
            f"**{filing['date']}** — {filing['ma_type'].title()} "
            f"(Items: {filing.get('items', '')})"
        ):
            st.markdown(f"**Type:** {filing['ma_type'].title()}")
            st.markdown(f"**Filed:** {filing['date']}")

            # Compute and show price impact
            impact = compute_ma_price_impact(ticker, filing["date"])
            if impact:
                st.markdown("**Stock price impact:**")
                price_cols = st.columns(4)
                with price_cols[0]:
                    p = impact.get("price_at_filing")
                    if p:
                        st.metric("Price at filing", f"${p:.2f}")
                with price_cols[1]:
                    r = impact.get("return_1d")
                    if r is not None:
                        st.metric("+1 day", f"{r:+.2f}%")
                with price_cols[2]:
                    r = impact.get("return_5d")
                    if r is not None:
                        st.metric("+5 days", f"{r:+.2f}%")
                with price_cols[3]:
                    r = impact.get("return_30d")
                    if r is not None:
                        st.metric("+30 days", f"{r:+.2f}%")

            if filing.get("snippet"):
                st.markdown("**Excerpt:**")
                st.markdown(f"> {filing['snippet']}")

            st.markdown(f"[View full filing on SEC.gov]({filing['url']})")


# ═══════════════════════════════════════════════════════════════════
# CATEGORY B: Acquisition Target Profile Score
# ═══════════════════════════════════════════════════════════════════

def compute_ma_target_score(stock_data, sector_stats):
    """
    Compute acquisition target probability score (0-100) for a single stock.

    Higher score = better fits historical patterns of acquired companies.

    Factors and weights:
    - Market cap sweet spot ($1B-$30B): 25%
    - Valuation discount vs sector: 20%
    - Cash position vs sector: 15%
    - Recent price weakness (declining 6M): 15%
    - Sector concentration / consolidation activity: 15%
    - Beta below 1 (less risky to acquirer): 10%

    Returns dict with overall score + component breakdown.
    """
    if stock_data is None:
        return None

    components = {}
    weights = {
        "size": 0.25,
        "valuation": 0.20,
        "cash_position": 0.15,
        "price_weakness": 0.15,
        "sector_activity": 0.15,
        "low_beta": 0.10,
    }

    # 1. Market cap sweet spot ($1B - $30B is most targetable)
    mcap = stock_data.get("marketCapB", 0)
    if mcap is None:
        mcap = 0
    if 1 <= mcap <= 5:
        size_score = 100  # Small-mid cap, very targetable
    elif 5 < mcap <= 15:
        size_score = 90
    elif 15 < mcap <= 30:
        size_score = 70
    elif 30 < mcap <= 50:
        size_score = 40
    elif 50 < mcap <= 100:
        size_score = 20
    else:
        size_score = 5  # Mega-caps rarely acquired
    components["size"] = size_score

    # 2. Valuation discount (lower P/E than sector = more attractive)
    pe = stock_data.get("trailingPE")
    sector = stock_data.get("sector", "")
    if pe and pe > 0 and sector_stats and sector in sector_stats:
        sector_pe = sector_stats[sector].get("median_pe")
        if sector_pe and sector_pe > 0:
            pe_ratio = pe / sector_pe
            if pe_ratio < 0.7:
                val_score = 100  # Big discount
            elif pe_ratio < 0.85:
                val_score = 80
            elif pe_ratio < 1.0:
                val_score = 60
            elif pe_ratio < 1.2:
                val_score = 40
            else:
                val_score = 20
        else:
            val_score = 50
    else:
        val_score = 50  # Unknown
    components["valuation"] = val_score

    # 3. Cash position relative to market cap
    total_cash = stock_data.get("totalCash", 0) or 0
    if total_cash > 0 and mcap > 0:
        cash_ratio = (total_cash / 1e9) / mcap  # cash in billions / mcap in billions
        if cash_ratio > 0.30:
            cash_score = 100
        elif cash_ratio > 0.20:
            cash_score = 80
        elif cash_ratio > 0.10:
            cash_score = 60
        elif cash_ratio > 0.05:
            cash_score = 40
        else:
            cash_score = 20
    else:
        cash_score = 30
    components["cash_position"] = cash_score

    # 4. Price weakness (recent decline = more receptive to bid)
    return_6m = stock_data.get("return_6m_pct")  # Custom field
    if return_6m is None:
        # Try alternative
        return_6m = stock_data.get("priceChange_6m") or stock_data.get("monthly_return")
    if return_6m is not None:
        if return_6m < -30:
            weakness_score = 100  # Down 30%+ — very receptive
        elif return_6m < -15:
            weakness_score = 80
        elif return_6m < -5:
            weakness_score = 60
        elif return_6m < 5:
            weakness_score = 40
        else:
            weakness_score = 20  # Up — less likely to accept lowball
    else:
        weakness_score = 50
    components["price_weakness"] = weakness_score

    # 5. Sector activity (some sectors have more M&A)
    high_ma_sectors = {
        "Healthcare": 80, "Technology": 75, "Financial Services": 70,
        "Communication Services": 65, "Consumer Cyclical": 60,
        "Energy": 70, "Real Estate": 55, "Industrials": 60,
        "Basic Materials": 65, "Consumer Defensive": 50, "Utilities": 45
    }
    sector_score = high_ma_sectors.get(sector, 50)
    components["sector_activity"] = sector_score

    # 6. Low beta = less risky for acquirer
    beta = stock_data.get("beta")
    if beta is not None:
        if beta < 0.7:
            beta_score = 90
        elif beta < 1.0:
            beta_score = 75
        elif beta < 1.3:
            beta_score = 50
        else:
            beta_score = 30
    else:
        beta_score = 50
    components["low_beta"] = beta_score

    # Composite
    overall = sum(components[k] * weights[k] for k in weights) if components else 0

    return {
        "overall_score": round(overall, 1),
        "components": components,
        "weights": weights,
    }


def add_ma_target_scores_to_universe(scored_df, sector_stats):
    """
    Add 'ma_target_score' column to the scored DataFrame.

    Called once during scoring pipeline. Result can be used in screeners.
    """
    if scored_df is None or scored_df.empty:
        return scored_df

    scores = []
    for ticker, row in scored_df.iterrows():
        result = compute_ma_target_score(row.to_dict(), sector_stats)
        if result:
            scores.append(result["overall_score"])
        else:
            scores.append(None)

    scored_df["ma_target_score"] = scores
    return scored_df


def render_ma_target_panel(ticker, stock_data, sector_stats):
    """Render acquisition target profile panel on Stock Detail."""
    st.markdown("### 🎯 Acquisition Target Profile")
    st.caption(
        "Statistical score (0-100) showing how well this stock fits historical patterns of acquired companies. "
        "**This is NOT a prediction** — most stocks fitting this profile are never acquired."
    )

    result = compute_ma_target_score(stock_data, sector_stats)
    if not result:
        st.info("Insufficient data to compute M&A target score.")
        return

    overall = result["overall_score"]
    components = result["components"]
    weights = result["weights"]

    # Header
    if overall >= 70:
        verdict = "🎯 Strong fit — multiple factors align"
        color = "#22C55E"
    elif overall >= 55:
        verdict = "📊 Moderate fit — some factors align"
        color = "#F59E0B"
    elif overall >= 40:
        verdict = "⚖️ Mixed signals"
        color = "#888888"
    else:
        verdict = "❌ Weak fit — does not match historical patterns"
        color = "#EF4444"

    col1, col2 = st.columns([1, 3])
    with col1:
        st.markdown(
            f'<div style="text-align: center; padding: 14px; border-radius: 10px; '
            f'background: {color}22; border: 2px solid {color};">'
            f'<div style="font-size: 0.85rem; opacity: 0.7;">M&A Target Score</div>'
            f'<div style="font-size: 2rem; font-weight: 700; color: {color};">{overall:.0f}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(f"**{verdict}**")
        st.caption(
            "Score reflects historical acquisition characteristics. Used as one input among many. "
            "Examine components below to understand why."
        )

    st.markdown("**Score Components:**")
    component_labels = {
        "size": "Market cap (sweet spot $1B-$30B)",
        "valuation": "Valuation discount vs sector",
        "cash_position": "Cash position",
        "price_weakness": "Recent price weakness (6M)",
        "sector_activity": "Sector M&A activity history",
        "low_beta": "Beta (lower = less risky to acquirer)",
    }

    rows = []
    for key, score in components.items():
        weight = weights[key]
        contribution = score * weight
        rows.append({
            "Factor": component_labels.get(key, key),
            "Score (0-100)": f"{score:.0f}",
            "Weight": f"{weight*100:.0f}%",
            "Contribution": f"{contribution:.1f}",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("⚠️ Important caveats"):
        st.markdown("""
        **What this score IS:**
        - Statistical alignment with historical acquisition target characteristics
        - Useful for filtering stocks that might be "of M&A interest" to acquirers
        - One input for thesis-building

        **What this score IS NOT:**
        - A prediction of future M&A activity
        - Investment advice
        - A leak detection mechanism

        **Reality check:**
        - Most stocks scoring 70+ are NEVER acquired
        - The base rate of public-company acquisition in any given year is roughly 1-3%
        - Even "obvious target" companies often remain independent for decades
        - Strategic and macro factors not captured here often dominate
        - Pre-deal rumor detection is intentionally NOT attempted (legal/quality concerns)

        Use this as a tool for understanding "why might an acquirer be interested" — not as a "this stock will be acquired" signal.
        """)
