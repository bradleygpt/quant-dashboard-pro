"""
Prediction Market tab — Polymarket integration.

Polymarket Gamma API is fully public, no auth required. Free.
Cached at 5-minute intervals via Streamlit cache.
"""
import json
import time
from datetime import datetime, timedelta

import requests
import pandas as pd
import streamlit as st


GAMMA_BASE = "https://gamma-api.polymarket.com"


@st.cache_data(ttl=300)  # 5-minute cache
def fetch_polymarket_markets(category=None, limit=100, closed=False):
    """
    Fetch markets from Polymarket Gamma API.

    Returns list of market dicts. Cached 5 minutes.
    """
    url = f"{GAMMA_BASE}/markets"
    params = {
        "closed": str(closed).lower(),
        "limit": limit,
        "order": "volume24hr",  # sort by 24h volume desc
        "ascending": "false",
    }
    if category:
        params["category"] = category

    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        else:
            return []
    except Exception:
        return []


@st.cache_data(ttl=300)
def fetch_polymarket_events(limit=50, closed=False):
    """
    Fetch events (groupings of related markets) from Polymarket.
    Events have multiple outcomes — e.g. "Who will win the 2028 election?"
    """
    url = f"{GAMMA_BASE}/events"
    params = {
        "closed": str(closed).lower(),
        "limit": limit,
        "order": "volume24hr",
        "ascending": "false",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        else:
            return []
    except Exception:
        return []


def parse_market_for_display(m):
    """Extract display-ready fields from a raw Polymarket market object."""
    if not isinstance(m, dict):
        return None

    # Outcome prices come as JSON string of array
    try:
        prices_raw = m.get("outcomePrices", "[]")
        if isinstance(prices_raw, str):
            prices = json.loads(prices_raw)
        else:
            prices = prices_raw
    except Exception:
        prices = []

    try:
        outcomes_raw = m.get("outcomes", "[]")
        if isinstance(outcomes_raw, str):
            outcomes = json.loads(outcomes_raw)
        else:
            outcomes = outcomes_raw
    except Exception:
        outcomes = []

    # YES probability (first outcome typically)
    yes_prob = None
    if prices and len(prices) > 0:
        try:
            yes_prob = float(prices[0])
        except (ValueError, TypeError):
            pass

    # End date
    end_date_raw = m.get("endDate")
    end_date_str = ""
    if end_date_raw:
        try:
            dt = datetime.fromisoformat(end_date_raw.replace("Z", "+00:00"))
            end_date_str = dt.strftime("%b %d, %Y")
        except Exception:
            end_date_str = end_date_raw[:10] if isinstance(end_date_raw, str) else ""

    return {
        "question": m.get("question", "?"),
        "yes_probability": yes_prob,
        "yes_price": yes_prob,  # alias
        "volume_24h": float(m.get("volume24hr", 0) or 0),
        "volume_total": float(m.get("volume", 0) or 0),
        "liquidity": float(m.get("liquidity", 0) or 0),
        "end_date": end_date_str,
        "category": m.get("category", "Other"),
        "tags": m.get("tags", []) if isinstance(m.get("tags"), list) else [],
        "slug": m.get("slug", ""),
        "url": f"https://polymarket.com/event/{m.get('slug', '')}" if m.get("slug") else "",
        "outcomes": outcomes,
        "outcome_prices": prices,
        "active": m.get("active", True),
        "closed": m.get("closed", False),
        "image": m.get("image", ""),
    }


# Categories Polymarket commonly uses
KNOWN_CATEGORIES = [
    "All",
    "Politics",
    "Crypto",
    "Sports",
    "Geopolitics",
    "Economy",
    "Tech",
    "Pop Culture",
    "Mentions",
    "Climate",
]


def render_prediction_market_tab():
    """Render the Prediction Market tab content. Call inside `with tab_prediction:`"""

    st.title("🎯 Prediction Market")
    st.markdown(
        "Real-money probability estimates from Polymarket — the world's largest "
        "prediction market. These markets aggregate trader bets into probability "
        "estimates for political, economic, and geopolitical events."
    )

    # Disclaimer
    with st.expander("ℹ️ About Polymarket data"):
        st.markdown("""
        **Polymarket** is a decentralized prediction market on Polygon where users
        trade outcome tokens for real-world events. Prices reflect market consensus
        on the probability of an outcome.

        - Prices range from $0 to $1 representing 0%-100% probability
        - Volume reflects 24h trading activity (liquidity proxy)
        - Markets resolve through UMA Optimistic Oracle

        **Data source:** Polymarket Gamma API (free, public, no authentication required).
        Data refreshes every 5 minutes.

        **Note:** Polymarket trading is restricted to non-US persons. This dashboard
        only displays publicly available market data for informational purposes.
        Trading happens on Polymarket directly, not through this dashboard.
        """)

    # Filters
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        category_filter = st.selectbox(
            "Category",
            options=KNOWN_CATEGORIES,
            index=0,
            key="pm_category_filter",
        )

    with col2:
        search_query = st.text_input(
            "Search markets (keyword)",
            key="pm_search",
            placeholder="e.g. 'fed', 'election', 'recession'",
        )

    with col3:
        sort_by = st.selectbox(
            "Sort by",
            options=["24h Volume", "Total Volume", "Liquidity", "End Date"],
            key="pm_sort",
        )

    # Fetch markets
    with st.spinner("Loading prediction markets..."):
        category_param = None if category_filter == "All" else category_filter.lower()
        raw_markets = fetch_polymarket_markets(
            category=category_param,
            limit=200,
            closed=False,
        )

    if not raw_markets:
        st.warning(
            "Could not load Polymarket data. The API may be temporarily unavailable. "
            "Try again in a few minutes."
        )
        return

    # Parse markets
    parsed = [parse_market_for_display(m) for m in raw_markets]
    parsed = [m for m in parsed if m is not None and m.get("active") and not m.get("closed")]

    # Apply search filter
    if search_query:
        q = search_query.lower()
        parsed = [m for m in parsed if q in (m.get("question") or "").lower()]

    if not parsed:
        st.info("No markets match your filters. Try a different category or search term.")
        return

    # Sort
    sort_keys = {
        "24h Volume": lambda m: m.get("volume_24h", 0),
        "Total Volume": lambda m: m.get("volume_total", 0),
        "Liquidity": lambda m: m.get("liquidity", 0),
        "End Date": lambda m: m.get("end_date", ""),
    }
    parsed.sort(key=sort_keys.get(sort_by, sort_keys["24h Volume"]), reverse=(sort_by != "End Date"))

    # Top-line stats
    total_volume_24h = sum(m.get("volume_24h", 0) for m in parsed)
    total_liquidity = sum(m.get("liquidity", 0) for m in parsed)
    n_markets = len(parsed)

    s1, s2, s3 = st.columns(3)
    s1.metric("Active Markets", f"{n_markets:,}")
    s2.metric("24h Volume", f"${total_volume_24h:,.0f}")
    s3.metric("Total Liquidity", f"${total_liquidity:,.0f}")

    st.markdown("---")
    st.subheader("Markets")

    # Table view
    rows = []
    for m in parsed[:100]:  # cap displayed
        prob = m.get("yes_probability")
        prob_str = f"{prob*100:.1f}%" if prob is not None else "-"
        vol_24h = m.get("volume_24h", 0)
        vol_total = m.get("volume_total", 0)
        end = m.get("end_date", "")
        url = m.get("url", "")
        question = m.get("question", "?")
        # Truncate very long questions
        q_display = question if len(question) <= 90 else question[:87] + "..."
        rows.append({
            "Market": q_display,
            "YES Probability": prob_str,
            "24h Volume": f"${vol_24h:,.0f}",
            "Total Volume": f"${vol_total:,.0f}",
            "Resolves": end,
            "Link": url,
        })

    df = pd.DataFrame(rows)

    if not df.empty:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Market": st.column_config.TextColumn("Market", width="large"),
                "YES Probability": st.column_config.TextColumn("YES %", width="small"),
                "24h Volume": st.column_config.TextColumn("24h Vol", width="small"),
                "Total Volume": st.column_config.TextColumn("Total Vol", width="small"),
                "Resolves": st.column_config.TextColumn("Resolves", width="small"),
                "Link": st.column_config.LinkColumn("View on Polymarket", width="small"),
            },
        )

    st.markdown("---")
    st.caption(
        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. "
        f"Data cached for 5 minutes. Source: Polymarket Gamma API."
    )
