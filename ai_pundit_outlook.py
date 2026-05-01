"""
AI Market Outlook - Pundit Sentiment Aggregator
================================================

Aggregates current market views from named financial commentators, organized by
their typical bias (Permabull / Bull / Neutral / Bear / Permabear).

Uses Gemini's web search capability to find recent statements and synthesize
them into structured pundit summaries.

Tiered fallback design:
- Primary tier (3 per group): Always tried first
- Secondary tier (12 per group): Only fetched if primaries return "no recent statements"
- Maximum displayed per group: configurable (default 5)

IMPORTANT CAVEATS (built into UI):
- Pundit views are not investment advice
- "Bias labels" reflect general tendencies, not absolute positions
- Web-sourced quotes may be 1-4 weeks old, not real-time
- Output quality varies; verify before acting on any view

Usage:
    from ai_pundit_outlook import generate_pundit_outlook
    result = generate_pundit_outlook()
"""

import streamlit as st
from ai_assistant import _call_gemini, is_ai_available


# ════════════════════════════════════════════════════════════════════
# Pundit roster: 15 per group with primary/secondary tier structure
# ════════════════════════════════════════════════════════════════════
# Primary tier (first 3 per group) = always tried first
# Secondary tier (remaining 12) = fallback if primaries have no recent statements
#
# Bias labels reflect general tendencies in their public commentary.
# Real views shift; these are starting categorizations.
# ════════════════════════════════════════════════════════════════════

PUNDIT_ROSTER = {
    "Permabulls": [
        # Primary tier
        {"name": "Tom Lee", "firm": "Fundstrat", "specialty": "Equities, crypto"},
        {"name": "Dan Ives", "firm": "Wedbush Securities", "specialty": "Tech, AI"},
        {"name": "Cathie Wood", "firm": "ARK Invest", "specialty": "Disruptive innovation"},
        # Secondary tier
        {"name": "Brian Belski", "firm": "BMO Capital Markets", "specialty": "Equity strategy"},
        {"name": "Tony Dwyer", "firm": "Canaccord Genuity", "specialty": "Equity strategy"},
        {"name": "Jim Paulsen", "firm": "Independent (formerly Leuthold)", "specialty": "Macro"},
        {"name": "Ed Hyman", "firm": "Evercore ISI", "specialty": "Macro"},
        {"name": "Ed Yardeni", "firm": "Yardeni Research", "specialty": "Macro"},
        {"name": "Brian Wieser", "firm": "Madison and Wall", "specialty": "Media/ad markets"},
        {"name": "Adam Parker", "firm": "Trivariate Research", "specialty": "Equity strategy"},
        {"name": "Ronnie Moas", "firm": "Standpoint Research", "specialty": "Stocks, crypto"},
        {"name": "Lee Cooperman", "firm": "Omega Family Office", "specialty": "Long-term equities"},
        {"name": "Bill Miller", "firm": "Miller Value Partners", "specialty": "Value, contrarian"},
        {"name": "Anthony Scaramucci", "firm": "SkyBridge Capital", "specialty": "Macro, crypto"},
        {"name": "Stanley Druckenmiller", "firm": "Duquesne Family Office", "specialty": "Macro (note: views shift)"},
    ],
    "Bulls": [
        # Primary tier
        {"name": "Mike Wilson", "firm": "Morgan Stanley", "specialty": "Equity strategy"},
        {"name": "Savita Subramanian", "firm": "Bank of America", "specialty": "Equity strategy"},
        {"name": "Jeremy Siegel", "firm": "WisdomTree / Wharton", "specialty": "Long-term equities"},
        # Secondary tier
        {"name": "David Kostin", "firm": "Goldman Sachs", "specialty": "Equity strategy"},
        {"name": "Dubravko Lakos-Bujas", "firm": "JPMorgan", "specialty": "Equity strategy"},
        {"name": "Liz Ann Sonders", "firm": "Charles Schwab", "specialty": "Investment strategy"},
        {"name": "Sam Stovall", "firm": "CFRA Research", "specialty": "Investment strategy"},
        {"name": "Jurrien Timmer", "firm": "Fidelity", "specialty": "Macro, equities"},
        {"name": "John Stoltzfus", "firm": "Oppenheimer", "specialty": "Equity strategy"},
        {"name": "Lori Calvasina", "firm": "RBC Capital Markets", "specialty": "Equity strategy"},
        {"name": "Binky Chadha", "firm": "Deutsche Bank", "specialty": "Equity strategy"},
        {"name": "Tony Pasquariello", "firm": "Goldman Sachs", "specialty": "Trading flows"},
        {"name": "Marko Kolanovic", "firm": "(formerly JPMorgan)", "specialty": "Quant strategy"},
        {"name": "Andrew Sheets", "firm": "Morgan Stanley", "specialty": "Cross-asset strategy"},
        {"name": "Nicholas Colas", "firm": "DataTrek Research", "specialty": "Macro/markets"},
    ],
    "Neutral / Cautious": [
        # Primary tier
        {"name": "Howard Marks", "firm": "Oaktree Capital", "specialty": "Cycles, value"},
        {"name": "Ray Dalio", "firm": "Bridgewater Associates", "specialty": "Macro"},
        {"name": "Mohamed El-Erian", "firm": "Allianz / Cambridge", "specialty": "Macro, fixed income"},
        # Secondary tier
        {"name": "Jamie Dimon", "firm": "JPMorgan Chase", "specialty": "Banking, macro outlook"},
        {"name": "Larry Summers", "firm": "Harvard / Independent", "specialty": "Macro economics"},
        {"name": "Lloyd Blankfein", "firm": "Goldman Sachs (former CEO)", "specialty": "Macro commentary"},
        {"name": "Mark Mobius", "firm": "Mobius Capital Partners", "specialty": "Emerging markets"},
        {"name": "Larry Fink", "firm": "BlackRock", "specialty": "Macro, asset allocation"},
        {"name": "Mark Spitznagel", "firm": "Universa Investments", "specialty": "Tail-risk hedging"},
        {"name": "Jeffrey Gundlach", "firm": "DoubleLine Capital", "specialty": "Fixed income, macro"},
        {"name": "Paul Tudor Jones", "firm": "Tudor Investment", "specialty": "Macro trading"},
        {"name": "David Rubenstein", "firm": "Carlyle Group", "specialty": "Private markets, macro"},
        {"name": "Kyle Bass", "firm": "Hayman Capital", "specialty": "Macro, geopolitics"},
        {"name": "Jim Cramer", "firm": "CNBC Mad Money", "specialty": "Stocks, retail commentary"},
        {"name": "Barry Ritholtz", "firm": "Ritholtz Wealth Management", "specialty": "Behavioral finance, markets"},
    ],
    "Bears": [
        # Primary tier
        {"name": "David Rosenberg", "firm": "Rosenberg Research", "specialty": "Macro"},
        {"name": "Jeremy Grantham", "firm": "GMO", "specialty": "Bubbles, value"},
        {"name": "Michael Burry", "firm": "Scion Asset Mgmt", "specialty": "Contrarian"},
        # Secondary tier
        {"name": "Albert Edwards", "firm": "Société Générale", "specialty": "Macro, deflation"},
        {"name": "Nouriel Roubini", "firm": "Roubini Macro Associates", "specialty": "Crisis macro"},
        {"name": "John Hussman", "firm": "Hussman Funds", "specialty": "Valuation, market history"},
        {"name": "Lance Roberts", "firm": "RIA Advisors", "specialty": "Macro/markets"},
        {"name": "Doug Kass", "firm": "Seabreeze Partners", "specialty": "Short-selling, value"},
        {"name": "John Mauldin", "firm": "Mauldin Economics", "specialty": "Macro"},
        {"name": "Jim Rogers", "firm": "Rogers Holdings", "specialty": "Commodities, macro"},
        {"name": "Charles Gave", "firm": "Gavekal Research", "specialty": "Macro, asset allocation"},
        {"name": "James Grant", "firm": "Grant's Interest Rate Observer", "specialty": "Fixed income, valuation"},
        {"name": "Russell Napier", "firm": "Independent / ERIC", "specialty": "Financial repression"},
        {"name": "Felix Zulauf", "firm": "Zulauf Asset Mgmt", "specialty": "Macro cycles"},
        {"name": "Stephanie Pomboy", "firm": "MacroMavens", "specialty": "Macro"},
        {"name": "Vincent Deluard", "firm": "StoneX", "specialty": "Macro, demographics"},
    ],
    "Permabears": [
        # Primary tier
        {"name": "Peter Schiff", "firm": "Euro Pacific Capital", "specialty": "Gold, dollar pessimism"},
        {"name": "Harry Dent", "firm": "HS Dent", "specialty": "Demographic doom"},
        {"name": "Marc Faber", "firm": "Gloom Boom Doom Report", "specialty": "Crash predictions"},
        # Secondary tier
        {"name": "Robert Kiyosaki", "firm": "Rich Dad Co.", "specialty": "Doom, gold, crypto"},
        {"name": "Robert Wiedemer", "firm": "Aftershock Publishing", "specialty": "Bubble theory"},
        {"name": "Egon von Greyerz", "firm": "Matterhorn Asset Mgmt", "specialty": "Gold, financial collapse"},
        {"name": "Bill Bonner", "firm": "Bonner & Partners", "specialty": "Doom commentary"},
        {"name": "Charles Nenner", "firm": "Charles Nenner Research", "specialty": "Cycles, predictions"},
        {"name": "Martin Armstrong", "firm": "Armstrong Economics", "specialty": "Cycles, predictions"},
        {"name": "Jim Rickards", "firm": "Independent / Strategic Intelligence", "specialty": "Currency wars, gold"},
        {"name": "Mike Maloney", "firm": "GoldSilver.com", "specialty": "Hyperinflation, gold"},
        {"name": "Gerald Celente", "firm": "Trends Research Institute", "specialty": "Trends, crisis predictions"},
        {"name": "Karl Denninger", "firm": "Market Ticker", "specialty": "Doom commentary"},
        {"name": "John Williams", "firm": "Shadow Govt Statistics", "specialty": "Inflation alternatives"},
        {"name": "Doug Casey", "firm": "Casey Research", "specialty": "Gold, libertarian doom"},
    ],
}


# Configuration
PRIMARY_TIER_SIZE = 3  # First N per group are primary
MIN_SUCCESSFUL_PER_GROUP = 3  # Try secondary tier until at least this many succeed
MAX_DISPLAYED_PER_GROUP = 5  # Display up to this many per group
MAX_FETCH_ATTEMPTS_PER_GROUP = 8  # Hard cap to control API cost


def _get_current_spy_price():
    """Fetch current SPY price for context in pundit prompts."""
    try:
        import yfinance as yf
        spy = yf.Ticker("SPY")
        hist = spy.history(period="5d")
        if not hist.empty:
            spy_price = float(hist["Close"].iloc[-1])
            # SPY * 10 = approximate S&P 500 index level
            sp500_level = spy_price * 10
            return spy_price, sp500_level
    except Exception:
        pass
    return None, None


def get_pundit_prompt(pundit_name, firm):
    """Build the prompt for fetching one pundit's recent view."""
    spy_price, sp500_level = _get_current_spy_price()

    # Build context strings (avoid complex f-string conditionals)
    if sp500_level:
        sp500_str = f"{sp500_level:,.0f}"
        spy_str = f"${spy_price:,.2f}"
        market_context = (
            f"\n\nIMPORTANT MARKET CONTEXT (use this to validate your response):\n"
            f"- Current S&P 500 level: approximately {sp500_str}\n"
            f"- Current SPY price: approximately {spy_str}\n"
            f"- Today's date: {__import__('datetime').datetime.now().strftime('%B %d, %Y')}\n"
        )
        rule_3 = (
            f"   - If S&P 500 target is ABOVE current level (~{sp500_str}), stance is Bullish/Cautiously Bullish\n"
            f"   - If target is BELOW current level (~{sp500_str}), stance is Bearish/Cautious (NOT Bullish)\n"
            f"   - If no target or unclear, use language tone to determine stance"
        )
    else:
        market_context = ""
        rule_3 = (
            "   - Stance must match directional language used by the commentator\n"
            "   - Bullish requires positive forward language; bearish requires negative"
        )

    return f"""Search the web for {pundit_name} ({firm})'s most recent (within the last 4 weeks ONLY) public statements about the US stock market outlook.{market_context}

CRITICAL ACCURACY REQUIREMENTS:
1. ONLY use statements made within the last 4 weeks. Do not use older quotes even if they appear in recent articles.
2. If you cannot verify the quote was made recently, return the error response below.
3. The stance MUST match the price target directionally:
{rule_3}
4. Verify the price target makes sense given the current S&P 500 level. Targets below current price imply DOWNSIDE.
5. Do not fabricate dates, sources, or quotes. If unsure, return the error.

Return ONLY a JSON object in this exact format, no other text:
{{
  "name": "{pundit_name}",
  "current_stance": "Bullish" | "Cautiously Bullish" | "Neutral" | "Cautious" | "Bearish",
  "key_quote": "A direct quote of 15-25 words from their recent statement",
  "quote_source": "The publication or platform (e.g., CNBC, X/Twitter, Bloomberg)",
  "quote_date_approx": "Specific date or 'Last 2 weeks' — must be recent",
  "key_views": ["Bullet 1 about their view", "Bullet 2", "Bullet 3"],
  "price_target_or_view": "Specific S&P 500 target if mentioned, with implied % move from current level (e.g., 'Target 7,200 = +5% upside') or directional view"
}}

If you cannot find statements from the last 4-6 weeks, OR if the quote conflicts with the stance directionally, return:
{{
  "name": "{pundit_name}",
  "error": "No recent verifiable statements found"
}}

Accuracy is more important than coverage. Returning the error is better than fabricating or misclassifying."""


@st.cache_data(ttl=86400, show_spinner=False)  # 24-hour cache
def fetch_pundit_view(pundit_name, firm):
    """Fetch one pundit's current view via Gemini web search."""
    if not is_ai_available():
        return {"name": pundit_name, "error": "AI not configured"}

    prompt = get_pundit_prompt(pundit_name, firm)

    try:
        result = _call_gemini(prompt, max_tokens=600, temperature=0.3)
        if "error" in result:
            return {"name": pundit_name, "error": result["error"]}

        text = result.get("text", "").strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        import json
        try:
            parsed = json.loads(text)
            return parsed
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            return {
                "name": pundit_name,
                "error": "Could not parse AI response as JSON",
                "raw_response": text[:200],
            }
    except Exception as e:
        return {"name": pundit_name, "error": f"Fetch failed: {str(e)[:120]}"}


def generate_pundit_outlook(min_per_group=3, max_per_group=5, max_attempts=8):
    """
    Build the full outlook with tiered primary/secondary fallback.

    Tries primary tier (first 3) first. If fewer than min_per_group return real
    statements, falls back to secondary tier until reaching min or hitting max_attempts.

    Args:
        min_per_group: Minimum successful pundits per group before stopping fallback
        max_per_group: Maximum to display per group (caps API cost)
        max_attempts: Hard cap on fetch attempts per group (controls API cost)

    Returns:
        Dict mapping bias_group -> list of pundit views (with errors filtered)
    """
    outlook = {}

    for bias_group, pundits in PUNDIT_ROSTER.items():
        successful_views = []
        attempts = 0

        for pundit in pundits:
            if len(successful_views) >= max_per_group:
                break  # Got enough
            if attempts >= max_attempts:
                break  # Cost cap hit

            view = fetch_pundit_view(pundit["name"], pundit["firm"])
            attempts += 1
            view["bias_group"] = bias_group
            view["firm"] = pundit["firm"]
            view["specialty"] = pundit["specialty"]

            # Only count it as successful if no error and has actual content
            if "error" not in view and view.get("key_quote"):
                successful_views.append(view)
            elif len(successful_views) < min_per_group:
                # Keep trying — we don't have enough yet
                continue
            else:
                # We have minimum, no need to continue to secondary tier
                break

        outlook[bias_group] = successful_views

    return outlook


def synthesize_aggregate_view(outlook):
    """
    Once views are gathered, ask Gemini to produce a synthesized takeaway.

    Returns a paragraph-style summary that calls out points of consensus and disagreement.
    """
    if not is_ai_available():
        return "AI synthesis not available."

    # Build context from successful views
    summary_lines = []
    for bias, views in outlook.items():
        for v in views:
            if "error" not in v and v.get("key_quote"):
                summary_lines.append(
                    f"- {v['name']} ({bias}): \"{v.get('key_quote', '')}\" "
                    f"— Stance: {v.get('current_stance', 'Unknown')}"
                )

    if not summary_lines:
        return "No pundit views available to synthesize."

    context = "\n".join(summary_lines)

    prompt = f"""Below are recent statements from financial market commentators with different biases:

{context}

Provide a brief (3-5 sentence) synthesis that:
1. Identifies points of CONSENSUS across the bull/bear spectrum
2. Identifies key DISAGREEMENTS
3. Notes any specific catalysts or themes mentioned by multiple commentators

Be neutral and analytical. Do not advocate for any view. Do not use the words "permabull" or "permabear"."""

    result = _call_gemini(prompt, max_tokens=400, temperature=0.5)
    if "error" in result:
        return f"Synthesis failed: {result['error']}"
    return result.get("text", "").strip()


def render_pundit_outlook_panel():
    """Render the full pundit outlook in Streamlit."""
    st.markdown("### 🎤 Market Outlook from Commentators")
    st.caption(
        "Aggregated views from 75 financial commentators across the bull/bear spectrum. "
        "Pulled from recent public statements via AI web search. Tiered fallback: tries "
        "primary commentators first, falls back to secondary tier if no recent statements found. "
        "Cached 24 hours per commentator."
    )

    if not is_ai_available():
        st.warning("⚠️ AI provider not configured. Set GEMINI_API_KEY in Streamlit secrets to enable this feature.")
        return

    # Refresh control
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption("ℹ️ Generation may take 1-3 minutes depending on cache state. Results cached 24 hours.")
    with col_b:
        if st.button("🔄 Clear cache", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Configuration sliders
    cfg_cols = st.columns(2)
    with cfg_cols[0]:
        min_per_group = st.slider(
            "Minimum views per group", 1, 5, 3, key="pundit_min",
            help="If primary commentators have no recent statements, falls back to secondary tier "
                 "until reaching this minimum."
        )
    with cfg_cols[1]:
        max_per_group = st.slider(
            "Maximum views per group", 3, 8, 5, key="pundit_max",
            help="Hard cap on commentators displayed per group. Higher = more API calls."
        )

    if st.button("Generate Outlook", type="primary", use_container_width=True):
        with st.spinner("Searching recent commentary across the spectrum..."):
            outlook = generate_pundit_outlook(
                min_per_group=min_per_group,
                max_per_group=max_per_group,
                max_attempts=8,
            )
            st.session_state["pundit_outlook"] = outlook

            with st.spinner("Synthesizing aggregate view..."):
                synthesis = synthesize_aggregate_view(outlook)
                st.session_state["pundit_synthesis"] = synthesis

    # Display if available
    if "pundit_outlook" in st.session_state:
        outlook = st.session_state["pundit_outlook"]
        synthesis = st.session_state.get("pundit_synthesis", "")

        if synthesis:
            st.markdown("#### 📋 Aggregate View")
            st.info(synthesis)

        # Quick stats
        total_views = sum(len(v) for v in outlook.values())
        groups_with_views = sum(1 for v in outlook.values() if v)
        st.caption(f"Showing {total_views} commentators across {groups_with_views} bias groups.")

        st.markdown("---")
        st.markdown("#### Individual Commentators")

        # Color coding for bias groups
        BIAS_COLORS = {
            "Permabulls": "#00C805",
            "Bulls": "#8BC34A",
            "Neutral / Cautious": "#FFC107",
            "Bears": "#FF9800",
            "Permabears": "#D32F2F",
        }

        for bias_group, views in outlook.items():
            color = BIAS_COLORS.get(bias_group, "#888")
            count = len(views)
            count_label = f" ({count})" if count else " — no recent statements found"
            st.markdown(
                f'<h5 style="color: {color}; border-left: 4px solid {color}; padding-left: 8px;">{bias_group}{count_label}</h5>',
                unsafe_allow_html=True,
            )

            if not views:
                st.caption(f"No recent public statements found from {bias_group} commentators in the last 6 weeks. This may reflect low activity or web search limitations.")
                continue

            for v in views:
                with st.expander(
                    f"**{v.get('name', 'Unknown')}** — {v.get('current_stance', 'Unknown stance')}",
                    expanded=False,
                ):
                    st.markdown(f"**Firm:** {v.get('firm', 'n/a')} | **Focus:** {v.get('specialty', 'n/a')}")

                    if v.get("key_quote"):
                        st.markdown(f'> "{v["key_quote"]}"')
                        st.caption(f"— {v.get('quote_source', 'Source unknown')}, {v.get('quote_date_approx', 'recent')}")

                    if v.get("key_views"):
                        st.markdown("**Key views:**")
                        for kv in v["key_views"]:
                            st.markdown(f"- {kv}")

                    if v.get("price_target_or_view"):
                        st.markdown(f"**Outlook:** {v['price_target_or_view']}")

        # Disclaimer
        st.markdown("---")
        st.caption(
            "⚠️ **Important:** Commentator views are not investment advice. AI-extracted quotes may be "
            "1-4 weeks old or paraphrased. Bias categorizations reflect general tendencies, not absolute "
            "positions. Always verify quotes from primary sources before acting on any view."
        )
