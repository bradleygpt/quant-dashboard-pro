"""
Crypto Pundit Aggregator
========================

Reuses the Gemini-based fetch logic from ai_pundit_outlook but with a
crypto-focused roster organized by Bitcoin maximalism / multi-chain stance.

Bias categories:
- BTC Maxis: Bitcoin-first, often dismissive of altcoins
- Crypto Bulls: Multi-chain optimists, generally bullish on the space
- Pragmatists: Balanced, technical, or institutional voices
- Skeptics: Critical voices, focused on risks and overvaluation
- Crypto Bears / Anti-crypto: Strong critics, predict collapse or fraud
"""

import streamlit as st
import json
import re
from ai_assistant import _call_gemini, is_ai_available


# ════════════════════════════════════════════════════════════════════
# Crypto Pundit Roster — 12 per category
# ════════════════════════════════════════════════════════════════════

CRYPTO_PUNDIT_ROSTER = {
    "BTC Maxis": [
        # Primary tier
        {"name": "Michael Saylor", "firm": "Strategy (formerly MicroStrategy)", "specialty": "Bitcoin treasury strategy"},
        {"name": "Jack Mallers", "firm": "Strike", "specialty": "Bitcoin payments, Lightning"},
        {"name": "Cynthia Lummis", "firm": "US Senate (Wyoming)", "specialty": "Bitcoin policy"},
        # Secondary tier
        {"name": "Adam Back", "firm": "Blockstream", "specialty": "Cypherpunk, Bitcoin tech"},
        {"name": "Samson Mow", "firm": "JAN3", "specialty": "Bitcoin nation-state adoption"},
        {"name": "Preston Pysh", "firm": "Investor's Podcast Network", "specialty": "Bitcoin macro"},
        {"name": "Saifedean Ammous", "firm": "The Bitcoin Standard", "specialty": "Bitcoin economics"},
        {"name": "Lyn Alden", "firm": "Lyn Alden Investment Strategy", "specialty": "Macro, Bitcoin"},
        {"name": "Pierre Rochard", "firm": "Riot Platforms", "specialty": "Bitcoin mining, advocacy"},
        {"name": "Nic Carter", "firm": "Castle Island Ventures", "specialty": "Bitcoin VC, on-chain analysis"},
        {"name": "Anthony Pompliano", "firm": "Professional Capital Management", "specialty": "Bitcoin commentary"},
        {"name": "Robert Breedlove", "firm": "Parallax Digital", "specialty": "Bitcoin philosophy"},
    ],
    "Crypto Bulls": [
        # Primary tier
        {"name": "Vitalik Buterin", "firm": "Ethereum Foundation", "specialty": "Ethereum founder"},
        {"name": "Brian Armstrong", "firm": "Coinbase", "specialty": "CEX, regulation"},
        {"name": "Cathie Wood", "firm": "ARK Invest", "specialty": "Disruptive innovation"},
        # Secondary tier
        {"name": "Charles Hoskinson", "firm": "IOG / Cardano", "specialty": "Cardano, blockchain governance"},
        {"name": "Raoul Pal", "firm": "Real Vision", "specialty": "Macro, crypto adoption"},
        {"name": "Tom Lee", "firm": "Fundstrat", "specialty": "Equities, Bitcoin"},
        {"name": "Mike Novogratz", "firm": "Galaxy Digital", "specialty": "Crypto investing"},
        {"name": "Anatoly Yakovenko", "firm": "Solana Labs", "specialty": "Solana, high-perf chains"},
        {"name": "Arthur Hayes", "firm": "BitMEX (founder)", "specialty": "Macro, derivatives"},
        {"name": "Balaji Srinivasan", "firm": "Independent (formerly a16z)", "specialty": "Crypto, network states"},
        {"name": "Erik Voorhees", "firm": "ShapeShift", "specialty": "Crypto, libertarian advocacy"},
        {"name": "Andreas Antonopoulos", "firm": "Independent", "specialty": "Bitcoin/crypto education"},
    ],
    "Pragmatists": [
        # Primary tier
        {"name": "Larry Fink", "firm": "BlackRock", "specialty": "Institutional crypto adoption"},
        {"name": "Fidelity Digital Assets", "firm": "Fidelity", "specialty": "Institutional research"},
        {"name": "Matt Hougan", "firm": "Bitwise", "specialty": "Crypto ETF strategy"},
        # Secondary tier
        {"name": "Ari Paul", "firm": "BlockTower Capital", "specialty": "Crypto hedge fund"},
        {"name": "Tom Schmidt", "firm": "Dragonfly Capital", "specialty": "Crypto VC"},
        {"name": "Hasu", "firm": "Independent / Flashbots", "specialty": "Crypto research, MEV"},
        {"name": "Vance Spencer", "firm": "Framework Ventures", "specialty": "Crypto VC, DeFi"},
        {"name": "Joey Krug", "firm": "Founders Fund / Pantera", "specialty": "Crypto investing"},
        {"name": "Kyle Samani", "firm": "Multicoin Capital", "specialty": "Crypto thesis investing"},
        {"name": "Tushar Jain", "firm": "Multicoin Capital", "specialty": "Crypto research"},
        {"name": "Alex Pack", "firm": "Hack VC", "specialty": "Crypto VC"},
        {"name": "Linda Xie", "firm": "Scalar Capital", "specialty": "Crypto fund management"},
    ],
    "Skeptics": [
        # Primary tier
        {"name": "Nassim Nicholas Taleb", "firm": "Independent (NYU)", "specialty": "Risk, antifragility"},
        {"name": "Paul Krugman", "firm": "CUNY / NYT", "specialty": "Economics, Nobel laureate"},
        {"name": "Steve Hanke", "firm": "Johns Hopkins", "specialty": "Monetary economics"},
        # Secondary tier
        {"name": "Frances Coppola", "firm": "Independent", "specialty": "Banking, monetary system"},
        {"name": "Stephen Diehl", "firm": "Independent", "specialty": "Software engineering, crypto critique"},
        {"name": "David Gerard", "firm": "Independent", "specialty": "Crypto journalism, critique"},
        {"name": "Molly White", "firm": "Web3 Is Going Just Great", "specialty": "Crypto fraud tracking"},
        {"name": "Bruce Schneier", "firm": "Harvard / Independent", "specialty": "Cryptography, security"},
        {"name": "Jorge Stolfi", "firm": "University of Campinas", "specialty": "Computer science, crypto critique"},
        {"name": "Cas Piancey", "firm": "Independent / Crypto Critics' Corner", "specialty": "Crypto investigation"},
        {"name": "Bennett Tomlin", "firm": "Crypto Critics' Corner", "specialty": "Stablecoin scrutiny"},
        {"name": "Amy Castor", "firm": "Independent journalist", "specialty": "Crypto investigative journalism"},
    ],
    "Crypto Bears / Anti-crypto": [
        # Primary tier
        {"name": "Peter Schiff", "firm": "Euro Pacific Capital", "specialty": "Gold bug, crypto critic"},
        {"name": "Charlie Munger", "firm": "Berkshire Hathaway (deceased)", "specialty": "Berkshire, crypto critic"},
        {"name": "Warren Buffett", "firm": "Berkshire Hathaway", "specialty": "Value investing, crypto critic"},
        # Secondary tier
        {"name": "Jamie Dimon", "firm": "JPMorgan Chase", "specialty": "Banking, mixed crypto views"},
        {"name": "Christine Lagarde", "firm": "European Central Bank", "specialty": "Central banking"},
        {"name": "Nouriel Roubini", "firm": "Roubini Macro Associates", "specialty": "Crisis macro"},
        {"name": "Robert McCauley", "firm": "Boston University / formerly BIS", "specialty": "International finance"},
        {"name": "Eswar Prasad", "firm": "Cornell University", "specialty": "Future of money"},
        {"name": "Ben McKenzie", "firm": "Independent (actor/author)", "specialty": "Crypto fraud advocacy"},
        {"name": "Jackson Palmer", "firm": "Dogecoin co-creator", "specialty": "Crypto critic"},
        {"name": "Marc Hochstein", "firm": "CoinDesk (former)", "specialty": "Crypto journalism"},
        {"name": "Hilary Allen", "firm": "American University Law", "specialty": "Financial regulation"},
    ],
}


# Configuration (shares logic with equity pundits)
PRIMARY_TIER_SIZE = 3
MIN_SUCCESSFUL_PER_GROUP = 3
MAX_DISPLAYED_PER_GROUP = 5
MAX_FETCH_ATTEMPTS_PER_GROUP = 8


# ════════════════════════════════════════════════════════════════════
# Fetch logic
# ════════════════════════════════════════════════════════════════════

def _get_current_crypto_prices():
    """Fetch current BTC and ETH prices for context in pundit prompts."""
    try:
        import yfinance as yf
        btc = yf.Ticker("BTC-USD").history(period="5d")
        eth = yf.Ticker("ETH-USD").history(period="5d")
        btc_price = float(btc["Close"].iloc[-1]) if not btc.empty else None
        eth_price = float(eth["Close"].iloc[-1]) if not eth.empty else None
        return btc_price, eth_price
    except Exception:
        return None, None


def get_crypto_pundit_prompt(pundit_name, firm):
    """Build the prompt for fetching one crypto pundit's recent view."""
    btc_price, eth_price = _get_current_crypto_prices()

    if btc_price and eth_price:
        market_context = (
            f"\n\nIMPORTANT MARKET CONTEXT (use to validate response):\n"
            f"- Current BTC price: ~${btc_price:,.0f}\n"
            f"- Current ETH price: ~${eth_price:,.0f}\n"
            f"- Today's date: {__import__('datetime').datetime.now().strftime('%B %d, %Y')}\n"
        )
        directional_rule = (
            f"   - BTC price targets ABOVE ~${btc_price:,.0f} = bullish direction\n"
            f"   - BTC price targets BELOW ~${btc_price:,.0f} = bearish direction\n"
            f"   - Same logic for ETH (current ~${eth_price:,.0f})"
        )
    else:
        market_context = ""
        directional_rule = "   - Stance must match the directional language used"

    return f"""Search the web for {pundit_name} ({firm})'s most recent (within the last 4 weeks ONLY) public statements about Bitcoin, Ethereum, or cryptocurrency markets.{market_context}

CRITICAL ACCURACY REQUIREMENTS:
1. ONLY use statements made within the last 4 weeks.
2. If you cannot verify recent statements, return the error response.
3. Stance must match price targets directionally:
{directional_rule}
4. Do not fabricate dates, sources, or quotes.
5. Returning the error is better than misclassifying.

Return ONLY a JSON object:
{{
  "name": "{pundit_name}",
  "current_stance": "Very Bullish" | "Bullish" | "Cautiously Bullish" | "Neutral" | "Cautious" | "Bearish" | "Very Bearish",
  "key_quote": "Direct quote of 15-25 words from recent statement",
  "quote_source": "Publication or platform (e.g., X/Twitter, CNBC, podcast name)",
  "quote_date_approx": "Specific recent date",
  "key_views": ["Bullet 1", "Bullet 2", "Bullet 3"],
  "btc_stance": "Their BTC view if mentioned, or 'Not specified'",
  "eth_stance": "Their ETH view if mentioned, or 'Not specified'",
  "price_target": "Specific target with implied % move from current price, or directional view"
}}

If no verifiable recent statements OR if quote conflicts with stance, return:
{{
  "name": "{pundit_name}",
  "error": "No recent verifiable statements found"
}}

Focus on cryptocurrency views, not equities or general economics."""


@st.cache_data(ttl=86400, show_spinner=False)  # 24-hour cache
def fetch_crypto_pundit_view(pundit_name, firm):
    """Fetch one crypto pundit's current view via Gemini web search."""
    if not is_ai_available():
        return {"name": pundit_name, "error": "AI not configured"}

    prompt = get_crypto_pundit_prompt(pundit_name, firm)

    try:
        result = _call_gemini(prompt, max_tokens=600, temperature=0.3)
        if "error" in result:
            return {"name": pundit_name, "error": result["error"]}

        text = result.get("text", "").strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            parsed = json.loads(text)
            return parsed
        except json.JSONDecodeError:
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


def generate_crypto_pundit_outlook(min_per_group=3, max_per_group=5, max_attempts=8):
    """
    Build the crypto outlook with tiered primary/secondary fallback.

    Returns dict mapping bias_group -> list of pundit views.
    """
    outlook = {}

    for bias_group, pundits in CRYPTO_PUNDIT_ROSTER.items():
        successful_views = []
        attempts = 0

        for pundit in pundits:
            if len(successful_views) >= max_per_group:
                break
            if attempts >= max_attempts:
                break

            view = fetch_crypto_pundit_view(pundit["name"], pundit["firm"])
            attempts += 1
            view["bias_group"] = bias_group
            view["firm"] = pundit["firm"]
            view["specialty"] = pundit["specialty"]

            if "error" not in view and view.get("key_quote"):
                successful_views.append(view)

        outlook[bias_group] = successful_views

    return outlook


def synthesize_crypto_outlook(outlook):
    """Generate a synthesis paragraph from gathered views."""
    if not is_ai_available():
        return "AI synthesis not available."

    summary_lines = []
    for bias, views in outlook.items():
        for v in views:
            if "error" not in v and v.get("key_quote"):
                summary_lines.append(
                    f"- {v['name']} ({bias}): \"{v.get('key_quote', '')}\" "
                    f"— Stance: {v.get('current_stance', 'Unknown')}"
                )

    if not summary_lines:
        return "No crypto pundit views available to synthesize."

    context = "\n".join(summary_lines)

    prompt = f"""Below are recent statements from cryptocurrency commentators with different perspectives:

{context}

Provide a brief (3-5 sentence) synthesis that:
1. Identifies points of CONSENSUS across the bull/bear spectrum on crypto
2. Identifies key DISAGREEMENTS (especially BTC vs ETH vs other chains)
3. Notes any specific catalysts mentioned by multiple commentators (regulation, ETF flows, halving, macro, etc.)

Be neutral and analytical. Do not advocate for any view."""

    result = _call_gemini(prompt, max_tokens=400, temperature=0.5)
    if "error" in result:
        return f"Synthesis failed: {result['error']}"
    return result.get("text", "").strip()


# ════════════════════════════════════════════════════════════════════
# UI Renderer
# ════════════════════════════════════════════════════════════════════

def render_crypto_pundit_panel():
    """Render the crypto pundit outlook in Streamlit."""
    st.markdown("### 🎤 Crypto Outlook from Commentators")
    st.caption(
        "Aggregated views from 60 crypto commentators across the bull/bear spectrum. "
        "Includes BTC maximalists, multi-chain bulls, pragmatists, skeptics, and crypto bears. "
        "Tiered fallback: primary 3 first, then secondary tier if needed. Cached 24 hours per commentator."
    )

    if not is_ai_available():
        st.warning("⚠️ AI provider not configured. Set GEMINI_API_KEY in Streamlit secrets to enable this feature.")
        return

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption("ℹ️ First generation may take 2-4 minutes. Cached results return instantly.")
    with col_b:
        if st.button("🔄 Clear cache", use_container_width=True, key="crypto_pundit_clear"):
            st.cache_data.clear()
            st.rerun()

    cfg_cols = st.columns(2)
    with cfg_cols[0]:
        min_per_group = st.slider(
            "Min views per group", 1, 5, 3, key="crypto_pundit_min",
            help="If primary commentators have no recent statements, falls back to secondary tier."
        )
    with cfg_cols[1]:
        max_per_group = st.slider(
            "Max views per group", 3, 8, 5, key="crypto_pundit_max",
            help="Hard cap on commentators displayed per group."
        )

    if st.button("Generate Crypto Outlook", type="primary", use_container_width=True, key="crypto_pundit_gen"):
        with st.spinner("Searching recent crypto commentary..."):
            outlook = generate_crypto_pundit_outlook(
                min_per_group=min_per_group,
                max_per_group=max_per_group,
                max_attempts=8,
            )
            st.session_state["crypto_pundit_outlook"] = outlook

            with st.spinner("Synthesizing aggregate view..."):
                synthesis = synthesize_crypto_outlook(outlook)
                st.session_state["crypto_pundit_synthesis"] = synthesis

    # Display
    if "crypto_pundit_outlook" in st.session_state:
        outlook = st.session_state["crypto_pundit_outlook"]
        synthesis = st.session_state.get("crypto_pundit_synthesis", "")

        if synthesis:
            st.markdown("#### 📋 Aggregate Crypto View")
            st.info(synthesis)

        total_views = sum(len(v) for v in outlook.values())
        groups_with_views = sum(1 for v in outlook.values() if v)
        st.caption(f"Showing {total_views} commentators across {groups_with_views} groups.")

        st.markdown("---")
        st.markdown("#### Individual Crypto Commentators")

        BIAS_COLORS = {
            "BTC Maxis": "#F7931A",            # Bitcoin orange
            "Crypto Bulls": "#00C805",          # Green
            "Pragmatists": "#FFC107",           # Yellow
            "Skeptics": "#FF9800",              # Orange
            "Crypto Bears / Anti-crypto": "#D32F2F",  # Red
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
                st.caption(f"No recent public statements found from {bias_group} commentators in the last 6 weeks.")
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

                    bs1, bs2 = st.columns(2)
                    with bs1:
                        if v.get("btc_stance") and v["btc_stance"] != "Not specified":
                            st.markdown(f"**BTC:** {v['btc_stance']}")
                    with bs2:
                        if v.get("eth_stance") and v["eth_stance"] != "Not specified":
                            st.markdown(f"**ETH:** {v['eth_stance']}")

                    if v.get("price_target"):
                        st.markdown(f"**Outlook:** {v['price_target']}")

        st.markdown("---")
        st.caption(
            "⚠️ **Important:** Crypto commentator views are highly speculative and not investment advice. "
            "AI-extracted quotes may be paraphrased. Crypto markets are extremely volatile and "
            "can move rapidly — pundit views may be obsolete by the time you read them."
        )
