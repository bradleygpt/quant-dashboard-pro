"""
Pundit Views - Cached Edition
=============================

Reads from pundits_cache.json (refreshed daily by GitHub Actions).
Zero live API calls during user sessions.

If cache is stale or missing, shows graceful fallback with warning banner.
"""

import os
import json
from datetime import datetime, timezone

import streamlit as st


CACHE_PATHS = [
    "pundits_cache.json",
    os.path.join("data_cache", "pundits_cache.json"),
]


@st.cache_data(ttl=600, show_spinner=False)  # 10 min cache (cache file refreshes daily anyway)
def load_pundits_cache():
    """Load the pundits cache from JSON file."""
    for path in CACHE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                return {"_load_error": str(e)[:200]}
    return None


def _format_age(timestamp_iso):
    """Convert ISO timestamp to 'X hours/days ago' string."""
    if not timestamp_iso:
        return "unknown"
    try:
        ts = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - ts
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)} min ago"
        elif hours < 24:
            return f"{hours:.1f} hours ago"
        else:
            return f"{hours / 24:.1f} days ago"
    except Exception:
        return "unknown"


def _stance_color(stance):
    """Map stance to a color for display."""
    if not stance:
        return "gray"
    s = stance.lower()
    if "very bullish" in s:
        return "#1B5E20"
    elif "bullish" in s and "cautious" not in s:
        return "#2E7D32"
    elif "cautiously bullish" in s:
        return "#558B2F"
    elif "neutral" in s:
        return "#FF8F00"
    elif "cautious" in s:
        return "#E65100"
    elif "very bearish" in s:
        return "#B71C1C"
    elif "bearish" in s:
        return "#C62828"
    return "gray"


def render_commentator_card(c, target_key="price_target_or_view"):
    """Render a single commentator's card."""
    name = c.get("name", "Unknown")
    firm = c.get("firm", "")
    stance = c.get("stance", "Unknown")
    quote = c.get("key_quote", "")
    source = c.get("quote_source", "")
    quote_date = c.get("quote_date", "")
    views = c.get("key_views", [])
    target = c.get(target_key, "")
    btc_view = c.get("btc_view", "")
    eth_view = c.get("eth_view", "")
    warning = c.get("_validation_warning")

    color = _stance_color(stance)

    with st.expander(f"**{name}** — :{color}[{stance}]"):
        st.markdown(f"**Firm:** {firm}")

        if warning:
            st.warning(f"⚠️ {warning}")

        if quote:
            st.markdown(f'> "{quote}"')
            caption_parts = []
            if source:
                caption_parts.append(source)
            if quote_date:
                caption_parts.append(quote_date)
            if caption_parts:
                st.caption(f"— {', '.join(caption_parts)}")

        if views:
            st.markdown("**Key views:**")
            for v in views:
                st.markdown(f"- {v}")

        if target:
            st.markdown(f"**Outlook:** {target}")

        if btc_view and btc_view != "Not specified":
            st.markdown(f"**BTC view:** {btc_view}")
        if eth_view and eth_view != "Not specified":
            st.markdown(f"**ETH view:** {eth_view}")


def render_pundit_panel(section_key, target_key, header_emoji="🎤"):
    """
    Render the pundit panel for either 'equity' or 'crypto' section.

    Reads from the cached JSON, displays commentators grouped by stance,
    handles stale/failed/missing states gracefully.
    """
    cache = load_pundits_cache()

    if cache is None:
        st.info(
            "📭 Pundit views have not been fetched yet. The daily refresh runs at 6 AM ET each weekday. "
            "Check back tomorrow morning, or trigger the workflow manually from GitHub Actions."
        )
        return

    if "_load_error" in cache:
        st.error(f"Could not load pundits cache: {cache['_load_error']}")
        return

    # Show cache freshness
    last_updated = cache.get("last_updated_utc")
    age_str = _format_age(last_updated)

    section_data = cache.get(section_key, {})
    section_status = cache.get(f"{section_key}_status", "unknown")
    commentators = section_data.get("commentators", [])
    synthesis = section_data.get("synthesis", "")
    themes = section_data.get("themes", [])

    # Status banner
    if section_status == "stale":
        last_fresh = cache.get(f"{section_key}_last_fresh")
        last_fresh_age = _format_age(last_fresh)
        error = cache.get(f"{section_key}_error", "")
        st.warning(
            f"⚠️ **Showing previous data.** Today's refresh failed; this is from {last_fresh_age}. "
            f"Reason: {error[:200]}. Will retry on next scheduled run."
        )
    elif section_status == "failed":
        error = cache.get(f"{section_key}_error", "Unknown error")
        st.error(
            f"❌ Latest fetch failed and no previous cache available. Reason: {error[:200]}. "
            "Will retry on next scheduled run."
        )
        return
    elif section_status == "fresh":
        st.caption(f"✓ Last refreshed: {age_str}")
    else:
        st.caption(f"Last refresh: {age_str} (status: {section_status})")

    if not commentators:
        st.info("No commentators in current cache. Waiting for next refresh.")
        return

    # Aggregate themes
    if themes:
        st.markdown("#### 🎯 This Week's Themes")
        theme_cols = st.columns(len(themes))
        for col, theme in zip(theme_cols, themes):
            with col:
                st.markdown(f"**{theme}**")
        st.markdown("---")

    # Synthesis paragraph
    if synthesis:
        st.markdown("#### 📝 Synthesis")
        st.info(synthesis)
        st.markdown("---")

    # Group commentators by stance
    st.markdown(f"#### 👥 Individual Commentators ({len(commentators)})")

    # Sort commentators by stance order: most bullish to most bearish
    stance_order = {
        "Very Bullish": 0, "Bullish": 1, "Cautiously Bullish": 2,
        "Neutral": 3, "Cautious": 4, "Bearish": 5, "Very Bearish": 6,
    }
    sorted_commentators = sorted(
        commentators,
        key=lambda c: stance_order.get(c.get("stance", ""), 99)
    )

    for c in sorted_commentators:
        render_commentator_card(c, target_key=target_key)


def render_equity_pundit_panel():
    """Render the equity pundit panel."""
    st.markdown("### 🎤 Market Commentator Views")
    st.caption(
        "Notable equity market commentators' recent statements, refreshed daily. "
        "Aggregated via AI web search. Quotes and stances are auto-validated for directional consistency."
    )
    render_pundit_panel(
        section_key="equity",
        target_key="price_target_or_view",
    )


def render_crypto_pundit_panel():
    """Render the crypto pundit panel."""
    st.markdown("### 🎤 Crypto Commentator Views")
    st.caption(
        "Notable cryptocurrency commentators' recent statements, refreshed daily. "
        "Aggregated via AI web search."
    )
    render_pundit_panel(
        section_key="crypto",
        target_key="price_target",
    )

    st.warning(
        "**Important:** Crypto commentator views are highly speculative. "
        "Even respected voices have been wildly wrong. Use as one input among many."
    )
