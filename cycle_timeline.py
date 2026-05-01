"""
Bitcoin Cycle Timeline & Countdown
===================================

Two visualizations of where we are in the BTC 4-year cycle relative to historical patterns:

Option A: Forward countdown
    - Days until next takeoff window (post-halving recovery)
    - Days until estimated next peak
    - Compared to historical timing

Option B: Visual timeline
    - Horizontal timeline showing past + projected future markers
    - "YOU ARE HERE" indicator
    - Historical analog markers (when did 2012/2016/2020 cycles take off and peak)
    - ETF approval/launch markers (cycle disruption events)

Reference data (verified from market sources April 2026):
    Cycle 1 (2012 halving): Halving Nov 28, 2012, Takeoff ~Mar 2013, Peak Nov 30, 2013, Bottom Jan 2015
    Cycle 2 (2016 halving): Halving Jul 9, 2016, Takeoff ~Mar 2017 (~240 days), Peak Dec 17, 2017 (~526 days), Bottom Dec 2018 (~880 days)
    Cycle 3 (2020 halving): Halving May 11, 2020, Takeoff ~Oct 2020 (~150 days), Peak Nov 9, 2021 (~547 days), Bottom Nov 2022 (~915 days)
    Cycle 4 (2024 halving): Halving Apr 19, 2024, Takeoff ~Oct 2024 (~180 days), Peak Oct 6, 2025 (~535 days), Bottom: TBD

ETF disruption events (cycle-breaking institutional inflows):
    BTC Spot ETF launch: Jan 11, 2024 (~3 months BEFORE 2024 halving — pre-halving institutional bid)
    BTC Spot ETF options approved: Sep 20, 2024 (deepened institutional access)
    ETH Spot ETF launch: Jul 23, 2024 (~3 months AFTER 2024 halving)
"""

from datetime import datetime, timedelta
import streamlit as st
import plotly.graph_objects as go


# Historical cycle reference data
# Each entry: cycle name, halving date, takeoff date (sustained breakout), peak date, peak price, bottom date
HISTORICAL_CYCLES = [
    {
        "label": "Cycle 1 (2012-2015)",
        "halving": datetime(2012, 11, 28),
        "halving_price": 12,
        # Bitcoin had two peaks in 2013: April (~$266) and Nov-Dec (~$1,150)
        # Using the November peak as the "real" cycle peak since it's the second/larger one
        "takeoff": datetime(2013, 3, 1),  # Broke through prior $30 highs early 2013
        "takeoff_price": 50,
        "peak": datetime(2013, 11, 30),
        "peak_price": 1163,
        "bottom": datetime(2015, 1, 14),
        "bottom_price": 178,
        "color": "#666666",
        "data_quality_note": "Pre-2014 BTC data is sparse and exchange-dependent. Use with caution.",
    },
    {
        "label": "Cycle 2 (2016-2018)",
        "halving": datetime(2016, 7, 9),
        "halving_price": 650,
        "takeoff": datetime(2017, 3, 1),  # Broke prior ATH around early March 2017
        "takeoff_price": 1200,
        "peak": datetime(2017, 12, 17),
        "peak_price": 19783,
        "bottom": datetime(2018, 12, 15),
        "bottom_price": 3200,
        "color": "#888888",
    },
    {
        "label": "Cycle 3 (2020-2022)",
        "halving": datetime(2020, 5, 11),
        "halving_price": 8800,
        "takeoff": datetime(2020, 10, 1),  # Broke $11k decisively
        "takeoff_price": 11000,
        "peak": datetime(2021, 11, 9),
        "peak_price": 68789,
        "bottom": datetime(2022, 11, 21),
        "bottom_price": 15500,
        "color": "#5DADE2",
    },
    {
        "label": "Cycle 4 (2024-current)",
        "halving": datetime(2024, 4, 19),
        "halving_price": 64000,
        "takeoff": datetime(2024, 10, 1),  # Resumed uptrend in October 2024
        "takeoff_price": 65000,
        "peak": datetime(2025, 10, 6),
        "peak_price": 126198,
        "bottom": None,  # TBD
        "bottom_price": None,
        "color": "#F7931A",
    },
]


# ETF disruption events — these fundamentally changed market structure
ETF_EVENTS = [
    {
        "date": datetime(2024, 1, 11),
        "label": "BTC Spot ETF launch",
        "short_label": "BTC ETF",
        "description": "First US spot Bitcoin ETFs began trading (IBIT, FBTC, etc.)",
        "impact": "Pre-halving institutional bid changed cycle dynamics fundamentally",
        "color": "#9B59B6",
    },
    {
        "date": datetime(2024, 7, 23),
        "label": "ETH Spot ETF launch",
        "short_label": "ETH ETF",
        "description": "First US spot Ethereum ETFs began trading",
        "impact": "Brought institutional access to ETH (no staking allowed in ETFs)",
        "color": "#627EEA",
    },
    {
        "date": datetime(2024, 9, 20),
        "label": "BTC ETF options approved",
        "short_label": "IBIT options",
        "description": "SEC approved options trading on BTC ETFs",
        "impact": "Deepened institutional access; enabled hedging and leverage",
        "color": "#9B59B6",
    },
]


def compute_cycle_milestones():
    """
    Compute days-since-halving for each milestone in each cycle.
    Returns enriched list with day counts.
    """
    enriched = []
    for cycle in HISTORICAL_CYCLES:
        halving = cycle["halving"]
        days_to_takeoff = (cycle["takeoff"] - halving).days if cycle.get("takeoff") else None
        days_to_peak = (cycle["peak"] - halving).days if cycle.get("peak") else None
        days_to_bottom = (cycle["bottom"] - halving).days if cycle.get("bottom") else None
        days_takeoff_to_peak = days_to_peak - days_to_takeoff if days_to_takeoff and days_to_peak else None
        days_peak_to_bottom = days_to_bottom - days_to_peak if days_to_peak and days_to_bottom else None

        enriched.append({
            **cycle,
            "days_to_takeoff": days_to_takeoff,
            "days_to_peak": days_to_peak,
            "days_to_bottom": days_to_bottom,
            "days_takeoff_to_peak": days_takeoff_to_peak,
            "days_peak_to_bottom": days_peak_to_bottom,
        })
    return enriched


def get_historical_averages(include_2012_cycle=True):
    """
    Compute averages from completed cycles.

    Args:
        include_2012_cycle: If True, includes Cycle 1 (2012). Default True because
                            the cycle timing data is well-documented even though
                            pre-2014 BTC PRICE data is limited in yfinance.
                            (The averages here are just date math, not price data.)
    """
    completed = [c for c in HISTORICAL_CYCLES if c.get("bottom")]
    if not include_2012_cycle:
        completed = [c for c in completed if c["halving"] >= datetime(2016, 1, 1)]

    if not completed:
        return None

    avg_takeoff = sum((c["takeoff"] - c["halving"]).days for c in completed) / len(completed)
    avg_peak = sum((c["peak"] - c["halving"]).days for c in completed) / len(completed)
    avg_bottom = sum((c["bottom"] - c["halving"]).days for c in completed) / len(completed)
    avg_peak_to_bottom = sum((c["bottom"] - c["peak"]).days for c in completed) / len(completed)
    avg_takeoff_to_peak = sum((c["peak"] - c["takeoff"]).days for c in completed) / len(completed)

    return {
        "avg_days_to_takeoff": int(avg_takeoff),
        "avg_days_to_peak": int(avg_peak),
        "avg_days_to_bottom": int(avg_bottom),
        "avg_days_peak_to_bottom": int(avg_peak_to_bottom),
        "avg_days_takeoff_to_peak": int(avg_takeoff_to_peak),
        "n_cycles_used": len(completed),
        "cycles_used": [c["label"] for c in completed],
    }


# ════════════════════════════════════════════════════════════════════
# OPTION A: Forward Countdown
# ════════════════════════════════════════════════════════════════════

def render_cycle_countdown():
    """
    Show countdown to next major cycle milestones.

    Renders:
    - Current position
    - Next halving estimated date (~April 2028)
    - Estimated takeoff window for the NEXT cycle (post-2028 halving)
    - Estimated peak window for the next cycle
    """
    st.markdown("### 📅 Cycle Countdown")
    st.caption("How many days until each major historical cycle event, projected forward from the next halving.")

    # Toggle for including 2012 cycle
    cc1, cc2 = st.columns([2, 1])
    with cc2:
        include_2012 = st.checkbox(
            "Include 2012 cycle in averages",
            value=True,
            key="include_2012_cycle",
            help="Cycle 1 (2012) had a smaller market and the peak came faster (367 days vs 526-547 days in later cycles). Including it adds a 3rd data point but pulls averages earlier.",
        )

    today = datetime.now()
    current_cycle = HISTORICAL_CYCLES[-1]
    halving_date = current_cycle["halving"]
    days_since = (today - halving_date).days

    averages = get_historical_averages(include_2012_cycle=include_2012)
    if not averages:
        st.warning("Insufficient historical data for projection.")
        return

    cycle_count_label = f"Averages computed from {averages['n_cycles_used']} completed cycle{'s' if averages['n_cycles_used'] != 1 else ''}: {', '.join(averages['cycles_used'])}"
    st.caption(cycle_count_label)

    # Current cycle status
    peak_date = current_cycle.get("peak")
    if peak_date:
        days_since_peak = (today - peak_date).days
        st.markdown(f"#### Current Cycle (post-Apr 2024 halving)")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Days since halving", f"{days_since}")
        with c2:
            st.metric("Days since peak", f"{days_since_peak}", f"Peak: {peak_date.strftime('%b %d, %Y')}")
        with c3:
            # Projected bottom based on historical peak-to-bottom average
            projected_bottom = peak_date + timedelta(days=averages["avg_days_peak_to_bottom"])
            days_to_bottom = (projected_bottom - today).days
            if days_to_bottom > 0:
                st.metric("Projected cycle bottom", projected_bottom.strftime("%b %Y"), f"~{days_to_bottom} days away")
            else:
                st.metric("Cycle bottom (estimated)", projected_bottom.strftime("%b %Y"), "Already passed if pattern held")

    st.markdown("---")
    st.markdown("#### Next Cycle (post-2028 halving)")

    # Next halving estimate (using approximate 4-year cadence)
    next_halving = datetime(2028, 4, 1)
    days_to_halving = (next_halving - today).days

    # Project takeoff and peak windows based on historical averages
    projected_next_takeoff = next_halving + timedelta(days=averages["avg_days_to_takeoff"])
    projected_next_peak = next_halving + timedelta(days=averages["avg_days_to_peak"])

    days_to_next_takeoff = (projected_next_takeoff - today).days
    days_to_next_peak = (projected_next_peak - today).days

    n1, n2, n3 = st.columns(3)
    with n1:
        st.metric(
            "Next halving (estimated)",
            next_halving.strftime("%b %Y"),
            f"~{days_to_halving} days away"
        )
    with n2:
        st.metric(
            "Estimated next takeoff",
            projected_next_takeoff.strftime("%b %Y"),
            f"~{days_to_next_takeoff} days away"
        )
    with n3:
        st.metric(
            "Estimated next peak",
            projected_next_peak.strftime("%b %Y"),
            f"~{days_to_next_peak} days away"
        )

    # Historical context table
    st.markdown("---")
    st.markdown("#### Historical Cycle Timing")
    st.caption("Days from each halving to the major cycle milestones.")

    enriched = compute_cycle_milestones()
    import pandas as pd
    rows = []
    for c in enriched:
        rows.append({
            "Cycle": c["label"],
            "Halving date": c["halving"].strftime("%b %Y"),
            "Days to takeoff": c["days_to_takeoff"] if c["days_to_takeoff"] else "—",
            "Days to peak": c["days_to_peak"] if c["days_to_peak"] else "—",
            "Days to bottom": c["days_to_bottom"] if c["days_to_bottom"] else "TBD",
            "Takeoff → peak": c["days_takeoff_to_peak"] if c["days_takeoff_to_peak"] else "—",
            "Peak → bottom": c["days_peak_to_bottom"] if c["days_peak_to_bottom"] else "TBD",
        })
    rows.append({
        "Cycle": "**Average (per current setting)**",
        "Halving date": "—",
        "Days to takeoff": averages["avg_days_to_takeoff"],
        "Days to peak": averages["avg_days_to_peak"],
        "Days to bottom": averages["avg_days_to_bottom"],
        "Takeoff → peak": averages["avg_days_takeoff_to_peak"],
        "Peak → bottom": averages["avg_days_peak_to_bottom"],
    })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Honest caveat — UPDATED to highlight ETF disruption
    with st.expander("⚠️ Why these projections may be wrong (especially this cycle)"):
        st.markdown("""
        **The 4-year cycle has been fundamentally altered by spot ETF flows.**

        **Why this cycle is different from prior cycles:**
        - **Spot Bitcoin ETFs launched Jan 11, 2024** — three months BEFORE the halving. This created an institutional bid on BTC supply that did not exist in any prior cycle.
        - **BlackRock IBIT alone** holds hundreds of thousands of BTC that effectively don't recirculate the way retail-held BTC did in 2017 or 2021.
        - **The 21-million-coin scarcity model** assumed retail/miner-driven supply dynamics. ETFs absorbed massive amounts of supply pre-halving, breaking that assumption.
        - **ETH ETFs launched July 23, 2024** — adding institutional access to ETH, though ETH ETFs currently cannot stake (a regulatory limitation that may change).
        - **BTC ETF options approved Sep 20, 2024** — added institutional hedging tools that further deepened the market structure.

        **What this means for cycle theory:**
        - Past cycles peaked 526-547 days post-halving. The 2024 cycle peaked at day 535 — almost exactly on schedule.
        - But the post-peak drawdown so far (~40%) has been milder than 2018 (~83%) or 2022 (~78%).
        - This may indicate ETFs are providing a price floor that didn't exist in prior cycles.
        - Or the cycle may simply be more drawn out — with the bottom yet to come.

        **Honest summary:** The cycle is doing roughly what cycle theorists predicted on the UPSIDE timing (peak hit on schedule), but the DOWNSIDE may be cushioned. Treat projections as one input among many, not a forecast.

        **Also:** Pre-2014 BTC data is poor. The 2012 cycle had two peaks in 2013 and a tiny market cap that doesn't translate well to today's institutional context. Default averages exclude it.
        """)


# ════════════════════════════════════════════════════════════════════
# OPTION B: Visual Timeline
# ════════════════════════════════════════════════════════════════════

def render_cycle_timeline():
    """
    Horizontal visual timeline showing past + projected future markers.

    Shows:
    - All halvings (past)
    - Takeoff dates (past + projected)
    - Peaks (past + projected)
    - Bottoms (past + projected)
    - ETF launch dates (BTC Jan 2024, ETH Jul 2024, BTC Options Sep 2024) — cycle disruption events
    - "YOU ARE HERE" marker for today
    - Next halving + projected next cycle events
    """
    st.markdown("### 📊 Bitcoin Cycle Timeline")
    st.caption("Visual map of past Bitcoin cycles with current position, ETF events, and projected next-cycle dates.")

    # Toggles for what to display
    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        show_2012 = st.checkbox("Show 2012 cycle", value=True, key="timeline_show_2012")
    with tc2:
        show_etf = st.checkbox("Show ETF events", value=True, key="timeline_show_etf")
    with tc3:
        include_2012_avg = st.checkbox("Include 2012 in averages", value=True, key="timeline_include_2012_avg")

    today = datetime.now()
    averages = get_historical_averages(include_2012_cycle=include_2012_avg)
    if not averages:
        st.warning("Insufficient historical data.")
        return

    # Filter cycles based on toggle
    cycles_to_show = HISTORICAL_CYCLES
    if not show_2012:
        cycles_to_show = [c for c in HISTORICAL_CYCLES if c["halving"] >= datetime(2016, 1, 1)]

    # Build the timeline events
    events = []

    # Past cycles
    for c in cycles_to_show:
        events.append({"date": c["halving"], "label": "Halving", "cycle": c["label"], "type": "halving", "color": c["color"]})
        if c.get("takeoff"):
            events.append({"date": c["takeoff"], "label": "Takeoff", "cycle": c["label"], "type": "takeoff", "color": c["color"]})
        if c.get("peak"):
            events.append({
                "date": c["peak"], "label": f"Peak (${c['peak_price']:,})",
                "cycle": c["label"], "type": "peak", "color": c["color"]
            })
        if c.get("bottom"):
            events.append({
                "date": c["bottom"], "label": f"Bottom (${c['bottom_price']:,})",
                "cycle": c["label"], "type": "bottom", "color": c["color"]
            })

    # Project future events for current cycle
    current_peak = HISTORICAL_CYCLES[-1].get("peak")
    if current_peak and not HISTORICAL_CYCLES[-1].get("bottom"):
        projected_bottom = current_peak + timedelta(days=averages["avg_days_peak_to_bottom"])
        events.append({
            "date": projected_bottom, "label": "Projected bottom",
            "cycle": "Cycle 4 (projected)", "type": "projected_bottom", "color": "#F7931A"
        })

    # Project next cycle
    next_halving = datetime(2028, 4, 1)
    next_takeoff = next_halving + timedelta(days=averages["avg_days_to_takeoff"])
    next_peak = next_halving + timedelta(days=averages["avg_days_to_peak"])

    events.append({"date": next_halving, "label": "Next halving (est)", "cycle": "Cycle 5 (projected)", "type": "halving_proj", "color": "#9B59B6"})
    events.append({"date": next_takeoff, "label": "Projected takeoff", "cycle": "Cycle 5 (projected)", "type": "takeoff_proj", "color": "#9B59B6"})
    events.append({"date": next_peak, "label": "Projected peak", "cycle": "Cycle 5 (projected)", "type": "peak_proj", "color": "#9B59B6"})

    # Sort events
    events.sort(key=lambda e: e["date"])

    # Build the Plotly figure
    fig = go.Figure()

    # Plot each event as a marker
    for e in events:
        # Map event types to vertical positions (so overlapping cycles stack)
        type_y_map = {
            "halving": 1, "takeoff": 0.7, "peak": 0.4, "bottom": 0.1,
            "halving_proj": 1, "takeoff_proj": 0.7, "peak_proj": 0.4, "projected_bottom": 0.1,
        }
        y = type_y_map.get(e["type"], 0.5)

        is_projected = "proj" in e["type"]
        marker_symbol = "diamond" if is_projected else "circle"
        marker_size = 14 if e["type"] in ["peak", "peak_proj"] else 11

        fig.add_trace(go.Scatter(
            x=[e["date"]], y=[y],
            mode="markers+text",
            marker=dict(size=marker_size, color=e["color"], symbol=marker_symbol,
                       line=dict(color="white", width=1.5)),
            text=[e["label"]],
            textposition="top center",
            textfont=dict(size=10, color=e["color"]),
            hovertemplate=f"<b>{e['cycle']}</b><br>{e['label']}<br>{e['date'].strftime('%b %d, %Y')}<extra></extra>",
            showlegend=False,
        ))

    # ETF event markers — these are BIG: vertical lines spanning the chart
    if show_etf:
        for etf in ETF_EVENTS:
            fig.add_vline(
                x=etf["date"].timestamp() * 1000,
                line_dash="dashdot",
                line_color=etf["color"],
                line_width=2,
                opacity=0.6,
                annotation_text=etf["short_label"],
                annotation_position="bottom",
                annotation_font=dict(size=10, color=etf["color"]),
            )

    # Add horizontal lines for each "lane"
    # X-axis range starts based on earliest cycle shown
    earliest_date = min(c["halving"] for c in cycles_to_show)
    annotation_x = (earliest_date - timedelta(days=120)).timestamp() * 1000
    for y, label in [(1, "Halvings"), (0.7, "Takeoffs"), (0.4, "Peaks"), (0.1, "Bottoms")]:
        fig.add_hline(y=y, line_dash="dot", line_color="rgba(128,128,128,0.3)", line_width=1)
        fig.add_annotation(
            x=annotation_x, y=y,
            text=label, showarrow=False,
            font=dict(size=11, color="gray"),
            xanchor="left",
        )

    # YOU ARE HERE marker
    fig.add_vline(
        x=today.timestamp() * 1000, line_dash="solid", line_color="red", line_width=3,
        annotation_text="<b>TODAY</b>", annotation_position="top",
        annotation_font=dict(size=14, color="red"),
    )

    # Highlight projected cycle window
    fig.add_vrect(
        x0=next_halving.timestamp() * 1000,
        x1=(next_peak + timedelta(days=60)).timestamp() * 1000,
        fillcolor="purple", opacity=0.1,
        annotation_text="Projected next cycle window",
        annotation_position="top left",
        line_width=0,
    )

    fig.update_layout(
        height=550,
        xaxis_title="Date",
        yaxis=dict(visible=False, range=[-0.1, 1.25]),
        hovermode="closest",
        showlegend=False,
        margin=dict(l=80, r=20, t=40, b=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ETF context section
    if show_etf:
        st.markdown("#### 🏦 ETF Disruption Events")
        st.caption("These dates fundamentally changed BTC market structure by introducing institutional-scale supply absorption.")
        for etf in ETF_EVENTS:
            with st.expander(f"**{etf['date'].strftime('%b %d, %Y')}** — {etf['label']}"):
                st.markdown(f"**What happened:** {etf['description']}")
                st.markdown(f"**Why it matters:** {etf['impact']}")

    # Below-chart context
    days_to_next_takeoff = (next_takeoff - today).days
    days_to_next_peak = (next_peak - today).days

    st.markdown("---")
    st.markdown(f"""
    **Reading the chart:**
    - **Solid circles** = actual historical events
    - **Diamonds** = projected future events
    - **Red line** = today's position
    - **Dashdot lines** = ETF disruption events (purple = BTC, blue = ETH)
    - **Purple shaded region** = projected next-cycle takeoff-to-peak window

    **From today, projected next cycle key dates:**
    - Next takeoff (sustained breakout): **~{next_takeoff.strftime('%b %Y')}** (~{days_to_next_takeoff} days from today)
    - Next peak: **~{next_peak.strftime('%b %Y')}** (~{days_to_next_peak} days from today)
    """)

    with st.expander("⚠️ Important caveats"):
        st.markdown(f"""
        - Projections use averages of **{averages['n_cycles_used']} completed cycle{'s' if averages['n_cycles_used'] != 1 else ''}** ({', '.join(averages['cycles_used'])})
        - The 2024 cycle is still in progress — its bottom is not yet known
        - **ETF flows have fundamentally altered cycle dynamics:**
          - Spot BTC ETFs (Jan 11, 2024) launched 3 months BEFORE the 2024 halving
          - This created an institutional bid that pre-absorbed supply unlike any prior cycle
          - The "21M coin scarcity" assumed retail/miner-driven flows; ETFs broke that
          - Post-peak drawdown has been milder this cycle (~40%) than 2018 (~83%) or 2022 (~78%)
        - **±3 months error on projected dates is reasonable**
        - Macro conditions in 2028-2029 are unknowable from today
        - Cycle theory has held up remarkably well so far this cycle (peak hit at day 535, very close to historical average), but past performance does not guarantee future outcomes
        """)


# ════════════════════════════════════════════════════════════════════
# Combined renderer (for easy integration into crypto_tab.py)
# ════════════════════════════════════════════════════════════════════

def render_cycle_timing_section():
    """Render both Option A (countdown) and Option B (timeline) in sequence."""
    render_cycle_countdown()
    st.markdown("---")
    render_cycle_timeline()
