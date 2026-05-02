"""
Crypto Tab Renderer
===================

Streamlit UI for the crypto module. Renders Bitcoin cycle analysis,
Ethereum supply dynamics, on-chain metrics, and the crypto pundit panel.

This is a separate file from crypto.py to keep the data/analysis
logic clean and reusable.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

from crypto import (
    get_current_halving_info, get_cycle_phase,
    fetch_btc_history, fetch_eth_history,
    compute_btc_valuation_indicators, interpret_valuation,
    fetch_coingecko_market_data,
    fetch_btc_block_height, fetch_btc_mempool_stats,
    estimate_next_halving_from_block,
    compute_eth_supply_metrics, compute_eth_btc_ratio,
    build_cycle_overlay_data,
    HALVINGS, ETH_SUPPLY_REFERENCES,
)


def render_crypto_tab():
    """Main entry point for the Crypto tab."""
    st.markdown("## ₿ Crypto Analysis")
    st.caption("Bitcoin cycle position, Ethereum supply dynamics, on-chain metrics, and commentator outlook.")

    # Sub-tabs for the four sections
    sub_tabs = st.tabs([
        "Bitcoin Cycle", "Ethereum", "ETH/BTC Ratio", "On-Chain", "🎤 Crypto Pundits"
    ])

    with sub_tabs[0]:
        render_bitcoin_section()

    with sub_tabs[1]:
        render_ethereum_section()

    with sub_tabs[2]:
        render_eth_btc_ratio_section()

    with sub_tabs[3]:
        render_onchain_section()

    with sub_tabs[4]:
        from pundit_views import render_crypto_pundit_panel
        render_crypto_pundit_panel()


# ════════════════════════════════════════════════════════════════════
# Bitcoin Section
# ════════════════════════════════════════════════════════════════════

def render_bitcoin_section():
    """Render the Bitcoin cycle analysis."""
    st.markdown("### 4-Year Halving Cycle Position")

    # Fetch data
    with st.spinner("Loading Bitcoin data..."):
        market = fetch_coingecko_market_data()
        btc_history = fetch_btc_history(period="max")
        block_height = fetch_btc_block_height()

    if btc_history is None:
        st.error("Could not load Bitcoin price history. Please try again later.")
        return

    # Cycle position header
    halving_info = get_current_halving_info()
    if halving_info:
        # Try to refine next halving estimate using actual block height
        if block_height:
            estimated = estimate_next_halving_from_block(block_height)
            if estimated:
                halving_info["next_halving"] = estimated["estimated_date"]
                halving_info["days_until_next"] = estimated["days_remaining"]
                halving_info["blocks_remaining"] = estimated["blocks_remaining"]

        phase = get_cycle_phase(halving_info["days_since_last"])

        # Top metrics row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Days since halving",
                f"{halving_info['days_since_last']:,}",
                f"{halving_info['last_halving'].strftime('%b %d, %Y')}"
            )
        with col2:
            if halving_info.get("days_until_next"):
                st.metric(
                    "Days until next halving",
                    f"{halving_info['days_until_next']:,}",
                    f"~{halving_info['next_halving'].strftime('%b %Y')}"
                )
        with col3:
            st.metric(
                "Cycle progress",
                f"{halving_info['cycle_progress_pct']:.1f}%" if halving_info['cycle_progress_pct'] else "N/A"
            )
        with col4:
            st.metric(
                "Block reward",
                f"{halving_info['current_reward']} BTC"
            )

        # Phase indicator
        st.markdown(f"#### Current Phase: **{phase['phase']}**")
        st.caption(phase['description'])

        # Visual cycle progress
        if halving_info.get("cycle_progress_pct"):
            st.progress(min(halving_info['cycle_progress_pct'] / 100, 1.0))

        # Honest caveat
        with st.expander("⚠️ Important caveats about cycle theory"):
            st.markdown("""
            **The 4-year halving cycle theory has only 3 prior cycles as data.**

            - 2012 halving → Nov 2013 peak (~12 months later)
            - 2016 halving → Dec 2017 peak (~17 months later)
            - 2020 halving → Nov 2021 peak (~18 months later)
            - 2024 halving → ??? (we are here)

            **Why this cycle may behave differently:**
            - Spot Bitcoin ETFs (Jan 2024) brought sustained institutional flows for the first time
            - BlackRock, Fidelity, and other large allocators now hold significant BTC positions
            - Macro environment (rates, dollar, geopolitics) differs from prior cycles
            - "Diminishing returns" pattern: each cycle's peak is a smaller multiple of the prior peak

            **Treat this indicator as ONE input, not a forecast.** Pattern-matching on 3 data points is not a robust prediction methodology.
            """)

    st.markdown("---")

    # Current price metrics
    if market and "btc" in market:
        btc = market["btc"]
        st.markdown("### Current State")
        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("Price", f"${btc['price']:,.0f}", f"{btc['change_24h_pct']:+.2f}% 24h" if btc.get('change_24h_pct') else None)
        with m2: st.metric("Market Cap", f"${btc['market_cap']/1e9:,.1f}B")
        with m3: st.metric("All-Time High", f"${btc['ath']:,.0f}", f"{btc['ath_change_pct']:+.1f}% from ATH" if btc.get('ath_change_pct') else None)
        with m4: st.metric("1-year change", f"{btc['change_1y_pct']:+.1f}%" if btc.get('change_1y_pct') else "N/A")

    st.markdown("---")

    # Valuation indicators
    st.markdown("### Valuation Indicators")
    indicators = compute_btc_valuation_indicators(btc_history)
    if indicators:
        interps = interpret_valuation(indicators)
        if interps:
            interp_df = pd.DataFrame(interps, columns=["Indicator", "Value", "Interpretation"])
            st.dataframe(interp_df, use_container_width=True, hide_index=True)

    # Cycle timing: countdown + timeline
    st.markdown("---")
    from cycle_timeline import render_cycle_timing_section
    render_cycle_timing_section()

    # Current cycle with historical projection band
    st.markdown("---")
    st.markdown("### Current Cycle vs Historical Projection")
    st.caption(
        "Solid orange line is the actual current cycle (April 2024 halving onward). "
        "The shaded gray band shows where past cycles (2016 and 2020) traded at the same days-since-halving, "
        "scaled to the current cycle's halving price ($64,000). "
        "Where the orange line is INSIDE the band, current cycle is tracking history. "
        "Where it's BELOW, current cycle is underperforming. ABOVE means outperforming."
    )

    overlay = build_cycle_overlay_data(btc_history)
    if overlay is not None and not overlay.empty:
        # Get today's days-since-halving
        from datetime import datetime as dt
        current_halving = dt(2024, 4, 19)
        today_days = (dt.now() - current_halving).days

        fig = go.Figure()

        # Add the projection band (shaded area between low and high)
        band_data = overlay[["days_since_halving", "projected_low", "projected_high", "projected_median"]].dropna()
        if not band_data.empty:
            # Upper bound (invisible, for fill anchor)
            fig.add_trace(go.Scatter(
                x=band_data["days_since_halving"],
                y=band_data["projected_high"],
                mode="lines",
                line=dict(color="rgba(150,150,150,0.0)", width=0),
                hoverinfo="skip",
                showlegend=False,
                name="High",
            ))
            # Lower bound, fill to upper
            fig.add_trace(go.Scatter(
                x=band_data["days_since_halving"],
                y=band_data["projected_low"],
                mode="lines",
                line=dict(color="rgba(150,150,150,0.0)", width=0),
                fill="tonexty",
                fillcolor="rgba(150,150,150,0.25)",
                hoverinfo="skip",
                showlegend=True,
                name="Historical range (cycles 2 & 3)",
            ))
            # Median line
            fig.add_trace(go.Scatter(
                x=band_data["days_since_halving"],
                y=band_data["projected_median"],
                mode="lines",
                line=dict(color="rgba(150,150,150,0.8)", width=1, dash="dot"),
                name="Historical median",
            ))

        # Add the current cycle line (orange, prominent)
        cycle_data = overlay[["days_since_halving", "current_price"]].dropna()
        if not cycle_data.empty:
            fig.add_trace(go.Scatter(
                x=cycle_data["days_since_halving"],
                y=cycle_data["current_price"],
                mode="lines",
                line=dict(color="#F7931A", width=3),
                name="Current cycle (2024-)",
            ))

        # Add today marker
        fig.add_vline(
            x=today_days, line_dash="solid", line_color="red", line_width=2,
            annotation_text="<b>TODAY</b>", annotation_position="top",
        )

        # Add halving marker at day 0
        fig.add_vline(x=0, line_dash="dash", line_color="gray", annotation_text="Halving")

        # Typical peak window highlight
        fig.add_vrect(
            x0=520, x1=550, fillcolor="green", opacity=0.15,
            annotation_text="Historical peak window",
            annotation_position="top left",
            line_width=0,
        )

        fig.update_layout(
            xaxis_title="Days since April 2024 halving",
            yaxis_title="BTC Price (USD)",
            yaxis_type="log",
            height=520,
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Reading guide
        with st.expander("📖 How to read this chart"):
            st.markdown("""
            **The orange line** is what BTC has actually done this cycle. It stops at today.

            **The gray band** is where prior cycles (2016 and 2020) traded at the same days-since-halving,
            with prices scaled so day 0 = $64,000 (the current cycle's halving price). Forward of today,
            the band shows the range where BTC HISTORICALLY went next from this point in the cycle.

            **The dotted gray line** is the median of historical paths.

            **Where the orange is below the band today:** current cycle is underperforming history.
            **Where the orange went above the band:** current cycle exceeded history at that point.
            **Past day 741 (today):** only the band is shown — that's the historical-range projection.

            **Important:** This is NOT a price forecast. It's saying "at this point in past cycles, prices
            were in this range." The actual future price could be anywhere — historical patterns may not
            repeat, especially given ETF-driven structural changes to the market.
            """)

    # BTC long-term price chart
    st.markdown("---")
    st.markdown("### Long-term Price Chart with Halvings")

    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(
        x=btc_history.index,
        y=btc_history["Close"],
        name="BTC Price",
        line=dict(color="#F7931A", width=2),
    ))

    # Add halving lines
    for h in HALVINGS:
        if h["date"] <= datetime.now():
            fig_price.add_vline(
                x=h["date"].timestamp() * 1000, line_dash="dash", line_color="red", opacity=0.5,
                annotation_text=f"Halving {h['date'].year}",
                annotation_position="top right",
            )

    # 200-week MA (a key cycle indicator)
    weekly = btc_history["Close"].resample("W").last()
    sma_200w = weekly.rolling(200).mean()
    fig_price.add_trace(go.Scatter(
        x=sma_200w.index,
        y=sma_200w,
        name="200-week MA",
        line=dict(color="#5DADE2", width=2, dash="dot"),
    ))

    fig_price.update_layout(
        yaxis_type="log",
        height=500,
        yaxis_title="Price (USD, log scale)",
        hovermode="x unified",
    )
    st.plotly_chart(fig_price, use_container_width=True)


# ════════════════════════════════════════════════════════════════════
# Ethereum Section
# ════════════════════════════════════════════════════════════════════

def render_ethereum_section():
    """Render the Ethereum analysis."""
    st.markdown("### Ethereum Analysis")

    with st.spinner("Loading Ethereum data..."):
        market = fetch_coingecko_market_data()
        eth_history = fetch_eth_history(period="max")

    if eth_history is None or market is None or "eth" not in market:
        st.error("Could not load Ethereum data. Please try again later.")
        return

    eth = market["eth"]

    # Current state
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("Price", f"${eth['price']:,.0f}", f"{eth['change_24h_pct']:+.2f}% 24h" if eth.get('change_24h_pct') else None)
    with m2: st.metric("Market Cap", f"${eth['market_cap']/1e9:,.1f}B")
    with m3: st.metric("All-Time High", f"${eth['ath']:,.0f}", f"{eth['ath_change_pct']:+.1f}% from ATH" if eth.get('ath_change_pct') else None)
    with m4: st.metric("1-year change", f"{eth['change_1y_pct']:+.1f}%" if eth.get('change_1y_pct') else "N/A")

    st.markdown("---")

    # ETH Supply Dynamics — the key bull case post-Merge
    st.markdown("### Supply Dynamics (Post-Merge)")
    st.caption(
        "ETH transitioned to proof-of-stake in September 2022 (\"The Merge\"). "
        "Combined with EIP-1559's burn mechanism, ETH supply has been roughly flat to slightly deflationary."
    )

    supply = compute_eth_supply_metrics(eth)
    if supply:
        sm1, sm2, sm3, sm4 = st.columns(4)
        with sm1:
            st.metric(
                "Current supply",
                f"{supply['current_supply']/1e6:.2f}M ETH",
                f"vs {supply['merge_supply']/1e6:.2f}M at Merge"
            )
        with sm2:
            change_pct = supply['net_change_pct']
            st.metric(
                "Change since Merge",
                f"{change_pct:+.3f}%",
                f"{supply['net_change_since_merge']/1e3:+,.0f}k ETH"
            )
        with sm3:
            ann = supply['annualized_change_pct']
            st.metric(
                "Annualized change",
                f"{ann:+.3f}%/yr",
                "Deflationary" if supply['is_deflationary'] else "Mildly inflationary"
            )
        with sm4:
            st.metric(
                "Approx. staked",
                f"~{supply['staking_ratio_pct']}%",
                "of supply locked"
            )

        # Honest reality check
        if supply['is_deflationary']:
            st.success(
                f"📉 ETH supply has DECLINED by {abs(supply['net_change_pct']):.3f}% since The Merge. "
                f"This is the 'ultrasound money' thesis playing out — gas burns exceed issuance during high activity periods."
            )
        elif supply['is_disinflationary']:
            st.info(
                f"📊 ETH supply is growing slowly ({ann:+.3f}%/yr), well below pre-Merge issuance "
                f"(~4-5%/yr). Net effect: closer to flat than meaningfully inflationary."
            )
        else:
            st.warning(
                f"📈 ETH supply is growing at {ann:+.3f}%/yr — faster than recent history. "
                f"Could indicate lower network activity (less burning) or staking changes."
            )

    st.markdown("---")

    # ETH price chart with key milestones
    st.markdown("### Price Chart with Key Milestones")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=eth_history.index,
        y=eth_history["Close"],
        name="ETH Price",
        line=dict(color="#627EEA", width=2),
    ))

    # The Merge marker
    merge_date = ETH_SUPPLY_REFERENCES["merge_date"]
    fig.add_vline(
        x=merge_date.timestamp() * 1000, line_dash="dash", line_color="green", opacity=0.7,
        annotation_text="The Merge (PoS)", annotation_position="top right",
    )

    # 200-day MA
    sma_200 = eth_history["Close"].rolling(200).mean()
    fig.add_trace(go.Scatter(
        x=sma_200.index, y=sma_200,
        name="200-day MA",
        line=dict(color="#888", width=1, dash="dot"),
    ))

    fig.update_layout(
        yaxis_type="log",
        height=450,
        yaxis_title="Price (USD, log scale)",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("### The Honest Bull and Bear Cases")
    bull_col, bear_col = st.columns(2)
    with bull_col:
        st.markdown("#### 🟢 Bull Case")
        st.markdown("""
        - **Deflationary supply** — burn often exceeds issuance during high activity
        - **Staking yield** — ~3-5% native yield from staking
        - **L2 ecosystem growth** — Arbitrum, Base, Optimism extending Ethereum's reach
        - **Institutional adoption** — ETH ETFs approved July 2024, growing flows
        - **Programmable money** — DeFi, NFTs, tokenization all built on ETH
        - **First-mover advantage** in smart contracts
        """)
    with bear_col:
        st.markdown("#### 🔴 Bear Case")
        st.markdown("""
        - **L2s extracting value** — most activity moves to L2s, ETH itself less used
        - **Solana / alt-L1 competition** — faster, cheaper alternatives gaining share
        - **Regulatory uncertainty** — staking, DeFi face SEC scrutiny
        - **Less narrative simplicity** than Bitcoin's "digital gold" story
        - **Underperformed BTC** — ETH/BTC ratio has trended down for years
        - **Validator concentration** — Lido controls large stake share
        """)


# ════════════════════════════════════════════════════════════════════
# ETH/BTC Ratio Section
# ════════════════════════════════════════════════════════════════════

def render_eth_btc_ratio_section():
    """Render the ETH/BTC ratio chart and analysis."""
    st.markdown("### ETH/BTC Ratio")
    st.caption(
        "The ETH/BTC ratio shows whether ETH is gaining or losing strength relative to Bitcoin. "
        "When ETH outperforms BTC, the ratio rises. When BTC outperforms, the ratio falls. "
        "This is one of the cleanest ways to see relative crypto performance."
    )

    with st.spinner("Loading data..."):
        btc_hist = fetch_btc_history(period="max")
        eth_hist = fetch_eth_history(period="max")

    if btc_hist is None or eth_hist is None:
        st.error("Could not load price history.")
        return

    ratio = compute_eth_btc_ratio(eth_hist, btc_hist)
    if ratio is None or ratio.empty:
        st.error("Could not compute ETH/BTC ratio.")
        return

    current_ratio = float(ratio.iloc[-1])
    ratio_30d_ago = float(ratio.iloc[-30]) if len(ratio) >= 30 else None
    ratio_1y_ago = float(ratio.iloc[-365]) if len(ratio) >= 365 else None
    ratio_ath = float(ratio.max())
    ratio_ath_date = ratio.idxmax()

    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("Current ratio", f"{current_ratio:.5f}")
    with m2:
        if ratio_30d_ago:
            change_30d = ((current_ratio / ratio_30d_ago) - 1) * 100
            st.metric("30-day change", f"{change_30d:+.2f}%")
    with m3:
        if ratio_1y_ago:
            change_1y = ((current_ratio / ratio_1y_ago) - 1) * 100
            st.metric("1-year change", f"{change_1y:+.2f}%")
    with m4:
        from_ath = ((current_ratio / ratio_ath) - 1) * 100
        st.metric("From ATH", f"{from_ath:+.1f}%", f"ATH: {ratio_ath:.5f}")

    # Interpretation
    if ratio_1y_ago:
        change_1y = ((current_ratio / ratio_1y_ago) - 1) * 100
        if change_1y > 20:
            st.success("🟢 ETH is meaningfully outperforming BTC over the past year.")
        elif change_1y > 0:
            st.info("🟡 ETH is modestly outperforming BTC over the past year.")
        elif change_1y > -20:
            st.warning("🟠 ETH is underperforming BTC over the past year.")
        else:
            st.error("🔴 ETH is significantly underperforming BTC over the past year.")

    st.markdown("---")

    # Ratio chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ratio.index,
        y=ratio.values,
        name="ETH/BTC ratio",
        line=dict(color="#9B59B6", width=2),
    ))

    # Key horizontal lines
    fig.add_hline(y=0.05, line_dash="dot", line_color="green", annotation_text="Historical floor (~0.05)", opacity=0.5)
    fig.add_hline(y=0.08, line_dash="dot", line_color="orange", annotation_text="Resistance (~0.08)", opacity=0.5)

    fig.update_layout(
        height=450,
        yaxis_title="ETH / BTC",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📐 How to interpret this chart"):
        st.markdown("""
        **The ETH/BTC ratio has historically traded in a wide range:**
        - 2017 peak: ~0.15 (during ICO mania)
        - 2018-2019 lows: ~0.025
        - 2021 cycle peak: ~0.085
        - 2022-2024 range: 0.04-0.08

        **Key observations:**
        - ETH has NOT made a higher high vs BTC since 2017
        - The general trend post-2017 has been downward, not upward
        - BTC's "store of value" narrative has dominated institutional flows
        - This contradicts the "ETH will flippen BTC" thesis from 2017-2021

        **What would change the trend:**
        - Sustained ETH staking yield > BTC perceived returns
        - L2 economic activity translating to ETH burn
        - Regulatory clarity favoring ETH (DeFi-friendly framework)
        - ETH ETF flows scaling significantly
        """)


# ════════════════════════════════════════════════════════════════════
# On-Chain Section
# ════════════════════════════════════════════════════════════════════

def render_onchain_section():
    """Render on-chain metrics from free APIs."""
    st.markdown("### On-Chain Metrics")
    st.caption(
        "Best-effort on-chain data from free APIs (mempool.space, blockchain.info). "
        "For comprehensive on-chain analytics (MVRV, NUPL, exchange flows), professional tools "
        "like Glassnode or CryptoQuant offer paid tiers."
    )

    with st.spinner("Loading on-chain data..."):
        block_height = fetch_btc_block_height()
        mempool_stats = fetch_btc_mempool_stats()

    if not block_height and not mempool_stats:
        st.error("Could not fetch on-chain data. Free APIs may be rate-limited or temporarily unavailable.")
        return

    # Block height and halving
    if block_height:
        st.markdown("#### Bitcoin Network State")
        bm1, bm2, bm3 = st.columns(3)
        with bm1:
            st.metric("Current block height", f"{block_height:,}")

        # Estimate next halving
        estimated = estimate_next_halving_from_block(block_height)
        if estimated:
            with bm2:
                st.metric(
                    "Blocks until next halving",
                    f"{estimated['blocks_remaining']:,}",
                    f"~{estimated['days_remaining']} days"
                )
            with bm3:
                st.metric(
                    "Estimated next halving",
                    estimated['estimated_date'].strftime("%b %Y")
                )

    # Mempool stats
    if mempool_stats:
        st.markdown("#### Bitcoin Mining & Mempool")
        mm1, mm2, mm3 = st.columns(3)

        if "hashrate_ehs" in mempool_stats:
            with mm1:
                st.metric("Network hash rate", f"{mempool_stats['hashrate_ehs']:.2f} EH/s")

        if "fees" in mempool_stats:
            fees = mempool_stats["fees"]
            with mm2:
                if "fastestFee" in fees:
                    st.metric("Fast fee", f"{fees['fastestFee']} sat/vB")
            with mm3:
                if "halfHourFee" in fees:
                    st.metric("30-min fee", f"{fees['halfHourFee']} sat/vB")

    st.markdown("---")
    st.markdown("#### What These Metrics Mean")
    st.markdown("""
    **Hash rate (EH/s = exahashes per second):**
    - Higher hash rate = more security and miner commitment
    - Trending up = healthy network growth
    - Sharp drops = miner capitulation events (often bear market signals)

    **Mempool fees (sat/vB = satoshis per virtual byte):**
    - Higher fees = more demand for block space
    - Sustained high fees indicate active usage and value accrual to miners
    - Very low fees may suggest bear market low-activity periods

    **Block height:**
    - Increases by 1 every ~10 minutes
    - Used to precisely calculate next halving (block 1,050,000 = next halving)
    """)

    st.markdown("---")
    st.caption(
        "💡 For deeper on-chain analytics — wallet cohort analysis, exchange flows, "
        "long/short-term holder behavior — consider professional tools. "
        "Glassnode, CryptoQuant, and IntoTheBlock offer free tiers with limited data."
    )
