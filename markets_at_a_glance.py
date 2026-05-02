"""
Markets at a Glance
===================

Comparison table showing every tracked index/instrument at:
- Today
- 1 week ago
- 1 month ago

Plus high-level sentiment indicators (Fear & Greed, PGI, money market $).

Reuses the existing fetch_index_data() infrastructure but adds
time-comparison views and includes ALL the major sentiment metrics.
"""

import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


# Extended index list — every major instrument tracked in the dashboard
ALL_INDEXES = {
    # US Equity Indexes
    "S&P 500": {"ticker": "^GSPC", "category": "US Equity"},
    "Nasdaq Composite": {"ticker": "^IXIC", "category": "US Equity"},
    "Nasdaq 100": {"ticker": "^NDX", "category": "US Equity"},
    "Dow Jones Industrial": {"ticker": "^DJI", "category": "US Equity"},
    "Russell 2000": {"ticker": "^RUT", "category": "US Equity"},
    "Russell 1000": {"ticker": "^RUI", "category": "US Equity"},
    "S&P 400 Mid-Cap": {"ticker": "^MID", "category": "US Equity"},
    "S&P 600 Small-Cap": {"ticker": "^SP600", "category": "US Equity"},
    "Wilshire 5000": {"ticker": "^W5000", "category": "US Equity"},

    # International Equity
    "FTSE 100 (UK)": {"ticker": "^FTSE", "category": "Intl Equity"},
    "DAX (Germany)": {"ticker": "^GDAXI", "category": "Intl Equity"},
    "Nikkei 225 (Japan)": {"ticker": "^N225", "category": "Intl Equity"},
    "Hang Seng (HK)": {"ticker": "^HSI", "category": "Intl Equity"},

    # Volatility
    "VIX": {"ticker": "^VIX", "category": "Volatility"},

    # Treasuries / Rates
    "10Y Treasury Yield": {"ticker": "^TNX", "category": "Rates"},
    "2Y Treasury Yield": {"ticker": "^IRX", "category": "Rates"},
    "30Y Treasury Yield": {"ticker": "^TYX", "category": "Rates"},

    # Commodities
    "Gold": {"ticker": "GC=F", "category": "Commodity"},
    "Silver": {"ticker": "SI=F", "category": "Commodity"},
    "Crude Oil (WTI)": {"ticker": "CL=F", "category": "Commodity"},
    "Natural Gas": {"ticker": "NG=F", "category": "Commodity"},
    "Copper": {"ticker": "HG=F", "category": "Commodity"},

    # Currencies
    "US Dollar Index (DXY)": {"ticker": "DX-Y.NYB", "category": "Currency"},
    "EUR/USD": {"ticker": "EURUSD=X", "category": "Currency"},
    "USD/JPY": {"ticker": "JPY=X", "category": "Currency"},

    # Crypto
    "Bitcoin": {"ticker": "BTC-USD", "category": "Crypto"},
    "Ethereum": {"ticker": "ETH-USD", "category": "Crypto"},
}


@st.cache_data(ttl=600, show_spinner=False)  # 10 min cache
def fetch_market_snapshot():
    """
    Fetch current, 1-week-ago, and 1-month-ago levels for every tracked instrument.

    Returns list of dicts with: name, category, current, week_ago, month_ago,
                                wk_change_pct, mo_change_pct, ath, dist_ath_pct
    """
    results = []
    for name, info in ALL_INDEXES.items():
        try:
            ticker = yf.Ticker(info["ticker"])
            hist = ticker.history(period="3mo")
            if hist.empty or len(hist) < 22:
                continue

            close = hist["Close"].dropna()
            if close.empty:
                continue

            current = float(close.iloc[-1])

            # Approximate trading-day offsets
            # 1 week = 5 trading days back; 1 month = 22 trading days back
            week_idx = max(0, len(close) - 6)
            month_idx = max(0, len(close) - 22)
            week_ago = float(close.iloc[week_idx])
            month_ago = float(close.iloc[month_idx])

            wk_change = ((current / week_ago) - 1) * 100 if week_ago else 0
            mo_change = ((current / month_ago) - 1) * 100 if month_ago else 0

            # All-time high (from longer history)
            try:
                full = ticker.history(period="max")["Close"].dropna()
                ath = float(full.max()) if not full.empty else current
                ath_date = full.idxmax() if not full.empty else None
                dist_ath = ((current - ath) / ath) * 100 if ath else 0
            except Exception:
                ath = current
                ath_date = None
                dist_ath = 0

            results.append({
                "name": name,
                "category": info["category"],
                "current": current,
                "week_ago": week_ago,
                "month_ago": month_ago,
                "wk_change_pct": wk_change,
                "mo_change_pct": mo_change,
                "ath": ath,
                "ath_date": ath_date.strftime("%Y-%m-%d") if ath_date else "—",
                "dist_ath_pct": dist_ath,
            })
        except Exception:
            continue

    return results


@st.cache_data(ttl=600, show_spinner=False)
def fetch_sentiment_snapshot():
    """
    Fetch sentiment-related metrics that aren't simple price levels:
    Fear & Greed score, money market dollars, total market cap.

    Returns dict with current values. Historical 1W/1M comparison
    not available for these (they're snapshot indicators).
    """
    snapshot = {}

    try:
        from sentiment import (
            fetch_index_data, fetch_vix_data, compute_market_breadth,
            fetch_buffett_indicator, compute_fear_greed, compute_pgi,
            MONEY_MARKET_ASSETS_TRILLIONS,
        )

        # Fear & Greed (current only — components don't store historicals)
        index_data = fetch_index_data()
        vix_data = fetch_vix_data()
        # breadth requires scored_df, skip in this generic snapshot
        try:
            breadth_data = {"pct_above_200sma": 50}  # placeholder if not available
        except Exception:
            breadth_data = None
        buffett_data = fetch_buffett_indicator()
        fg = compute_fear_greed(vix_data, breadth_data, index_data, buffett_data)
        if fg:
            snapshot["fear_greed_score"] = fg["score"]
            snapshot["fear_greed_classification"] = fg["classification"]

        # PGI / Money Market
        pgi = compute_pgi()
        if pgi:
            snapshot["pgi"] = pgi["pgi"]
            snapshot["pgi_level"] = pgi["level"]
            snapshot["money_market_t"] = pgi["money_market_t"]
            snapshot["total_mkt_cap_t"] = pgi["total_mkt_cap_t"]

        # VIX
        if vix_data:
            snapshot["vix_current"] = vix_data.get("current")
            snapshot["vix_level"] = vix_data.get("level")

        # Buffett Indicator
        if buffett_data:
            snapshot["buffett_ratio"] = buffett_data.get("ratio")
            snapshot["buffett_level"] = buffett_data.get("level")

    except Exception as e:
        snapshot["error"] = str(e)[:100]

    return snapshot


def _format_value(name, value):
    """Format a value appropriately based on instrument type."""
    if "Yield" in name or "VIX" in name:
        return f"{value:,.2f}"
    elif "EUR" in name or "JPY" in name or "DXY" in name or "Dollar" in name:
        return f"{value:,.4f}"
    elif "Bitcoin" in name or "Ethereum" in name:
        return f"${value:,.0f}"
    elif value > 1000:
        return f"{value:,.0f}"
    else:
        return f"{value:,.2f}"


def render_markets_at_a_glance():
    """Render the Markets at a Glance panel with full instrument table."""
    st.markdown("### 📊 Markets at a Glance")
    st.caption("Every tracked index, commodity, currency, and rate — current vs 1 week ago vs 1 month ago.")

    with st.spinner("Loading market snapshot..."):
        snapshot = fetch_market_snapshot()
        sentiment = fetch_sentiment_snapshot()

    if not snapshot:
        st.error("Could not load market data. Try refreshing.")
        return

    # ── Top-level sentiment indicators ──
    st.markdown("#### Sentiment & Allocation")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    with sc1:
        if "fear_greed_score" in sentiment:
            st.metric(
                "Fear & Greed",
                f"{sentiment['fear_greed_score']:.0f}/100",
                sentiment.get("fear_greed_classification", "")
            )
    with sc2:
        if "pgi" in sentiment:
            st.metric(
                "PGI (cash %)",
                f"{sentiment['pgi']:.2f}%",
                sentiment.get("pgi_level", "")
            )
    with sc3:
        if "money_market_t" in sentiment:
            st.metric(
                "Money Market Assets",
                f"${sentiment['money_market_t']:.2f}T",
                "ICI estimate"
            )
    with sc4:
        if "total_mkt_cap_t" in sentiment:
            st.metric(
                "US Total Market Cap",
                f"${sentiment['total_mkt_cap_t']:,.1f}T",
                "Wilshire 5000"
            )
    with sc5:
        if "buffett_ratio" in sentiment:
            st.metric(
                "Buffett Indicator",
                f"{sentiment['buffett_ratio']:.0f}%",
                sentiment.get("buffett_level", "")
            )

    st.markdown("---")

    # ── Full table grouped by category ──
    st.markdown("#### All Tracked Indexes & Instruments")

    # Convert to DataFrame
    df = pd.DataFrame(snapshot)

    # Sort by category then name
    category_order = ["US Equity", "Intl Equity", "Volatility", "Rates", "Commodity", "Currency", "Crypto"]
    df["cat_order"] = df["category"].map({c: i for i, c in enumerate(category_order)})
    df = df.sort_values(["cat_order", "name"]).drop(columns="cat_order")

    # Render by category sections so users can find what they care about
    for category in category_order:
        cat_df = df[df["category"] == category]
        if cat_df.empty:
            continue

        st.markdown(f"##### {category}")

        # Build display table
        display_rows = []
        for _, row in cat_df.iterrows():
            display_rows.append({
                "Instrument": row["name"],
                "Now": _format_value(row["name"], row["current"]),
                "1 Week Ago": _format_value(row["name"], row["week_ago"]),
                "1W Change": f"{row['wk_change_pct']:+.2f}%",
                "1 Month Ago": _format_value(row["name"], row["month_ago"]),
                "1M Change": f"{row['mo_change_pct']:+.2f}%",
                "All-Time High": _format_value(row["name"], row["ath"]),
                "From ATH": f"{row['dist_ath_pct']:+.1f}%",
            })
        cat_display = pd.DataFrame(display_rows)
        st.dataframe(cat_display, use_container_width=True, hide_index=True)

    # Footnotes
    st.caption(
        "Notes: 1 week = 5 trading days, 1 month = 22 trading days. "
        "Money market assets ($6.7T) updated manually; PGI uses live Wilshire 5000 for total market cap. "
        "Yields shown as percent. Crypto trades 24/7; equity time-windows reflect trading days. "
        "Cached for 10 minutes."
    )
