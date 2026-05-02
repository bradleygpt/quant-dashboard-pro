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
    Visual timeline showing BTC price history with all cycle events as markers
    plotted at their actual price levels. Plus projected next-cycle events.

    X-axis: Date (time)
    Y-axis: BTC price (USD, log scale) — events shown at their actual prices
    """
    st.markdown("### 📊 Bitcoin Cycle Timeline")
    st.caption(
        "Time on x-axis. BTC price on y-axis (log scale). Each event marked at its actual price level. "
        "Hollow markers indicate projections."
    )

    with st.expander("ℹ️ What is a Bitcoin halving? (click to expand)"):
        st.markdown("""
        A **Bitcoin halving** is a protocol event — NOT a cycle midpoint or price low — that occurs roughly every 4 years (every 210,000 blocks).
        Each halving cuts the rate of new BTC issuance to miners by 50%:

        - 2012 halving: rewards dropped from 50 → 25 BTC per block
        - 2016 halving: 25 → 12.5 BTC per block
        - 2020 halving: 12.5 → 6.25 BTC per block
        - 2024 halving: 6.25 → 3.125 BTC per block (current era)
        - 2028 halving (estimated): 3.125 → 1.5625 BTC per block

        This creates a programmed supply shock. Historically, in each of the prior 3 cycles, BTC has rallied dramatically 12-18 months after the halving.

        **On this chart, halving markers (purple triangles) are plotted at the BTC price on the day each halving occurred — NOT at cycle lows.** Halvings happen mid-cycle from the prior bottom, after BTC has already partially recovered. So the 2020 halving marker at ~$8,800 sits ABOVE the 2018 cycle bottom at $3,200, because BTC had bounced from $3,200 → $8,800 in the 17 months between those events.
        """)

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

    # Fetch BTC price history for the background line
    try:
        import yfinance as yf
        btc = yf.Ticker("BTC-USD")
        btc_hist = btc.history(period="max")
    except Exception:
        btc_hist = None

    # Build figure
    fig = go.Figure()

    # Background: actual BTC price line (subtle orange)
    if btc_hist is not None and not btc_hist.empty:
        fig.add_trace(go.Scatter(
            x=btc_hist.index,
            y=btc_hist["Close"],
            mode="lines",
            line=dict(color="rgba(247,147,26,0.45)", width=1.5),
            name="BTC price",
            hovertemplate="<b>BTC</b><br>%{x|%b %Y}<br>$%{y:,.0f}<extra></extra>",
        ))

    # Plot cycle event markers AT THEIR ACTUAL PRICE LEVELS
    event_types = {
        "halving": {"symbol": "triangle-up", "size": 14, "name": "Halvings"},
        "takeoff": {"symbol": "triangle-up-open", "size": 12, "name": "Takeoffs"},
        "peak": {"symbol": "star", "size": 17, "name": "Peaks"},
        "bottom": {"symbol": "triangle-down", "size": 14, "name": "Bottoms"},
    }
    type_colors = {"halving": "#9B59B6", "takeoff": "#3498DB", "peak": "#27AE60", "bottom": "#E74C3C"}

    by_type = {t: [] for t in event_types}
    for c in cycles_to_show:
        for event_type in event_types:
            if c.get(event_type):
                price_key = f"{event_type}_price"
                price = c.get(price_key)
                if price:
                    by_type[event_type].append({
                        "date": c[event_type],
                        "price": price,
                        "label": f"{c['label']}",
                        "color": c["color"],
                    })

    for event_type, events in by_type.items():
        if not events:
            continue
        cfg = event_types[event_type]
        fig.add_trace(go.Scatter(
            x=[e["date"] for e in events],
            y=[e["price"] for e in events],
            mode="markers",
            marker=dict(
                size=cfg["size"],
                color=type_colors[event_type],
                symbol=cfg["symbol"],
                line=dict(color="white", width=1.5),
            ),
            name=cfg["name"],
            text=[e["label"] for e in events],
            hovertemplate="<b>%{text}</b><br>" + cfg["name"][:-1] + "<br>%{x|%b %d, %Y}<br>$%{y:,.0f}<extra></extra>",
        ))

    # Project current cycle bottom — RANGE based on historical drawdown patterns
    # Cycle 1: -85%, Cycle 2: -84%, Cycle 3: -77%
    # Range: assume historical drawdowns hold (institutions trading OTC means
    # ETF flows don't materially cushion exchange-traded price action)
    current_peak_date = HISTORICAL_CYCLES[-1].get("peak")
    current_peak_price = HISTORICAL_CYCLES[-1].get("peak_price", 126198)
    if current_peak_date:
        projected_bottom_date = current_peak_date + timedelta(days=averages["avg_days_peak_to_bottom"])
        # Range: -85% (matches early cycles) to -65% (mild diminishing returns)
        projected_bottom_low = current_peak_price * 0.15   # -85%
        projected_bottom_high = current_peak_price * 0.35  # -65%
        projected_bottom_mid = current_peak_price * 0.23   # -77% (cycle 3)

        # Add range bar (low + high) connected by a vertical line
        fig.add_trace(go.Scatter(
            x=[projected_bottom_date, projected_bottom_date],
            y=[projected_bottom_low, projected_bottom_high],
            mode="lines+markers",
            line=dict(color="rgba(231,76,60,0.5)", width=2, dash="dot"),
            marker=dict(
                size=12, color="rgba(231,76,60,0.7)",
                symbol="triangle-down-open",
                line=dict(color="#E74C3C", width=2),
            ),
            name="Projected bottom range (current cycle)",
            hovertemplate=(
                f"<b>Projected current cycle bottom</b><br>"
                f"{projected_bottom_date.strftime('%b %Y')}<br>"
                f"Range: $%{{y:,.0f}}<br>"
                f"Low (~-85%): ${projected_bottom_low:,.0f}<br>"
                f"Mid (~-77%): ${projected_bottom_mid:,.0f}<br>"
                f"High (~-65%): ${projected_bottom_high:,.0f}<extra></extra>"
            ),
        ))

    # Next cycle projections — RANGES based on diminishing-returns multipliers
    # Peak multiples: 17x → 3.5x → 1.83x (decay rate ~0.5 per cycle)
    # Next cycle peak: 1.2x to 1.6x prior peak ($151k to $202k)
    next_halving = datetime(2028, 4, 1)
    next_takeoff = next_halving + timedelta(days=averages["avg_days_to_takeoff"])
    next_peak = next_halving + timedelta(days=averages["avg_days_to_peak"])

    # Conservative range based on diminishing-multiplier pattern
    next_peak_low = current_peak_price * 1.2   # ~$151k
    next_peak_high = current_peak_price * 1.6  # ~$202k
    next_peak_mid = current_peak_price * 1.4   # ~$177k

    # Next cycle bottom: 2-3x prior cycle bottom (also using diminishing returns)
    # Prior bottoms: 178 → 3,200 → 15,500 → ?
    # Multiples: 18x, 4.84x, next ~2-3x
    prior_bottom = 15500
    next_bottom_low = prior_bottom * 2   # $31k
    next_bottom_high = prior_bottom * 3  # $46.5k

    # Halving and takeoff prices: estimate from where current trend would put them
    # (BTC roughly midway between bottom and peak by these points)
    next_halving_price_low = next_peak_low * 0.4
    next_halving_price_high = next_peak_high * 0.55
    next_takeoff_price_low = next_peak_low * 0.5
    next_takeoff_price_high = next_peak_high * 0.7

    # Plot peak range
    fig.add_trace(go.Scatter(
        x=[next_peak, next_peak],
        y=[next_peak_low, next_peak_high],
        mode="lines+markers",
        line=dict(color="rgba(155,89,182,0.6)", width=2, dash="dot"),
        marker=dict(
            size=14, color="rgba(155,89,182,0.7)",
            symbol="diamond-open",
            line=dict(color="#9B59B6", width=2),
        ),
        name="Projected next peak range",
        hovertemplate=(
            f"<b>Projected next cycle peak</b><br>"
            f"{next_peak.strftime('%b %Y')}<br>"
            f"Range: $%{{y:,.0f}}<br>"
            f"Low (1.2x): ${next_peak_low:,.0f}<br>"
            f"Mid (1.4x): ${next_peak_mid:,.0f}<br>"
            f"High (1.6x): ${next_peak_high:,.0f}<extra></extra>"
        ),
    ))

    # Plot halving and takeoff ranges
    fig.add_trace(go.Scatter(
        x=[next_halving, next_halving],
        y=[next_halving_price_low, next_halving_price_high],
        mode="lines+markers",
        line=dict(color="rgba(155,89,182,0.4)", width=1.5, dash="dot"),
        marker=dict(
            size=10, color="rgba(155,89,182,0.6)",
            symbol="triangle-up-open",
            line=dict(color="#9B59B6", width=1.5),
        ),
        name="Projected next halving range",
        hovertemplate=f"<b>Next halving (est)</b><br>{next_halving.strftime('%b %Y')}<br>Range: $%{{y:,.0f}}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[next_takeoff, next_takeoff],
        y=[next_takeoff_price_low, next_takeoff_price_high],
        mode="lines+markers",
        line=dict(color="rgba(155,89,182,0.4)", width=1.5, dash="dot"),
        marker=dict(
            size=10, color="rgba(155,89,182,0.6)",
            symbol="triangle-up-open",
            line=dict(color="#9B59B6", width=1.5),
        ),
        name="Projected next takeoff range",
        hovertemplate=f"<b>Projected takeoff</b><br>{next_takeoff.strftime('%b %Y')}<br>Range: $%{{y:,.0f}}<extra></extra>",
    ))

    # Add trendlines connecting historical peaks and bottoms (extrapolated)
    # Use the current cycle peak and prior cycle peaks/bottoms as anchors
    peak_dates = [c["peak"] for c in HISTORICAL_CYCLES if c.get("peak")]
    peak_prices = [c["peak_price"] for c in HISTORICAL_CYCLES if c.get("peak_price")]
    bottom_dates = [c["bottom"] for c in HISTORICAL_CYCLES if c.get("bottom")]
    bottom_prices = [c["bottom_price"] for c in HISTORICAL_CYCLES if c.get("bottom_price")]

    # Add forward-projected next cycle peak/bottom to the trendlines
    peak_dates_extended = peak_dates + [next_peak]
    peak_prices_extended = peak_prices + [next_peak_mid]
    # Project current cycle bottom (mid estimate) for the bottom trendline
    bottom_dates_extended = bottom_dates + [projected_bottom_date]
    bottom_prices_extended = bottom_prices + [projected_bottom_mid]

    # Plot the historical peak trendline (with forward projection)
    fig.add_trace(go.Scatter(
        x=peak_dates_extended,
        y=peak_prices_extended,
        mode="lines",
        line=dict(color="rgba(39,174,96,0.4)", width=2, dash="dash"),
        name="Peak trendline (with projection)",
        hoverinfo="skip",
    ))

    # Plot the historical bottom trendline (with forward projection)
    fig.add_trace(go.Scatter(
        x=bottom_dates_extended,
        y=bottom_prices_extended,
        mode="lines",
        line=dict(color="rgba(231,76,60,0.4)", width=2, dash="dash"),
        name="Bottom trendline (with projection)",
        hoverinfo="skip",
    ))

    # ETF event vertical lines
    if show_etf:
        for etf in ETF_EVENTS:
            fig.add_vline(
                x=etf["date"].timestamp() * 1000,
                line_dash="dashdot",
                line_color=etf["color"],
                line_width=2,
                opacity=0.5,
                annotation_text=etf["short_label"],
                annotation_position="top",
                annotation_font=dict(size=10, color=etf["color"]),
            )

    # TODAY vertical line
    fig.add_vline(
        x=today.timestamp() * 1000,
        line_dash="solid", line_color="red", line_width=3,
        annotation_text="<b>TODAY</b>", annotation_position="top",
        annotation_font=dict(size=14, color="red"),
    )

    # Highlight projected next cycle window
    fig.add_vrect(
        x0=next_halving.timestamp() * 1000,
        x1=(next_peak + timedelta(days=60)).timestamp() * 1000,
        fillcolor="purple", opacity=0.08,
        annotation_text="Projected next cycle window",
        annotation_position="bottom left",
        line_width=0,
    )

    fig.update_layout(
        height=600,
        xaxis_title="Date",
        yaxis_title="BTC Price (USD, log scale)",
        yaxis_type="log",
        hovermode="closest",
        showlegend=True,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01, bgcolor="rgba(0,0,0,0.4)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ETF context section
    if show_etf:
        with st.expander("🏦 ETF Disruption Events"):
            st.caption("These dates fundamentally changed BTC market structure by introducing institutional-scale supply absorption.")
            for etf in ETF_EVENTS:
                st.markdown(f"**{etf['date'].strftime('%b %d, %Y')}** — {etf['label']}")
                st.markdown(f"  - {etf['description']}")
                st.markdown(f"  - **Why it matters:** {etf['impact']}")

    # Below-chart context
    days_to_next_takeoff = (next_takeoff - today).days
    days_to_next_peak = (next_peak - today).days

    st.markdown(f"""
    **Reading the chart:**
    - **Orange line** = actual BTC price history (yfinance)
    - **Filled triangles up** = Halvings (at actual price)
    - **Hollow triangles up** = Takeoffs (sustained breakouts)
    - **Stars** = Peaks
    - **Filled triangles down** = Bottoms
    - **Hollow markers** = projected future events (price estimates rough)
    - **Red line** = today's position
    - **Dashdot lines** = ETF disruption events

    **From today, projected next cycle key dates:**
    - Next takeoff: **~{next_takeoff.strftime('%b %Y')}** ({days_to_next_takeoff} days)
    - Next peak: **~{next_peak.strftime('%b %Y')}** ({days_to_next_peak} days)
    """)

    with st.expander("⚠️ How projected ranges are calculated"):
        st.markdown(f"""
        **Projected ranges are based on historical patterns, not single-point predictions:**

        **Current cycle bottom (vertical bar at projected date):**
        - Range: -65% to -85% drawdown from peak
        - Low: ${current_peak_price * 0.15:,.0f} (matches Cycle 1 -85%)
        - Mid: ${current_peak_price * 0.23:,.0f} (matches Cycle 3 -77%)
        - High: ${current_peak_price * 0.35:,.0f} (mild diminishing returns -65%)

        **Why no "ETF-cushion" assumption:** Institutions buying via spot ETFs typically transact OTC
        (off-exchange), which absorbs supply but doesn't significantly impact exchange-traded price action.
        Retail and derivatives flows still drive price discovery during drawdowns. Historical drawdown
        patterns are likely to hold.

        **Next cycle peak (vertical bar at next peak date):**
        - Based on diminishing-multiplier pattern: 17.0x → 3.5x → 1.83x → ?
        - Range: 1.2x to 1.6x prior cycle peak
        - Low: ${current_peak_price * 1.2:,.0f}
        - Mid: ${current_peak_price * 1.4:,.0f}
        - High: ${current_peak_price * 1.6:,.0f}

        **Trendlines (dashed lines):**
        - Green dashed = peak trendline (connects all cycle peaks + projected next peak)
        - Red dashed = bottom trendline (connects all cycle bottoms + projected current cycle bottom)
        - Where current price falls between these is the "expected band" if history rhymes

        **Date projections** use averages of {averages['n_cycles_used']} completed cycles
        ({', '.join(averages['cycles_used'])}). ±3 months error reasonable.

        **Important: this cycle's actual peak ($126k Oct 2025) was 0.60x what a naive log-linear trendline
        would have projected.** Diminishing returns ARE real and accelerating. The conservative end of
        ranges may prove more accurate than the high end.

        **Macro risks not modeled:** Recession, regulatory shifts, geopolitical shocks, miner capitulation,
        and other unmodeled factors can break any pattern. Treat ranges as "if history repeats" — not "this
        will happen."
        """)


# ════════════════════════════════════════════════════════════════════
# Combined renderer (for easy integration into crypto_tab.py)
# ════════════════════════════════════════════════════════════════════

def render_cycle_timing_section():
    """Render both Option A (countdown) and Option B (timeline) in sequence."""
    render_cycle_countdown()
    st.markdown("---")
    render_cycle_timeline()
