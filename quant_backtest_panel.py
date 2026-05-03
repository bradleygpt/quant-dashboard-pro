"""
Quant 5-Pillar Backtest Display
================================

Reads quant_backtest_results.json (built by build_quant_backtest.py via
GitHub Actions) and renders the results in the Quant Portfolio tab.
"""

import os
import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st


CACHE_PATHS = [
    "quant_backtest_results.json",
    os.path.join("data_cache", "quant_backtest_results.json"),
]


@st.cache_data(ttl=3600, show_spinner=False)
def load_quant_backtest_results():
    for path in CACHE_PATHS:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                return {"_error": f"Failed to parse {path}: {str(e)[:120]}"}
    return None


def render_quant_backtest_panel():
    """Render the quant 5-pillar backtest panel."""
    st.markdown("### 📊 Quant 5-Pillar Strategy Backtest")
    st.caption(
        "Validates the 5-pillar quant scoring on 20 years of monthly checkpoints. "
        "Each month: top 10 quant-rated stocks → simulated 1-month holds → portfolio returns vs SPY."
    )

    results = load_quant_backtest_results()

    if results is None:
        st.info(
            "🚧 Quant backtest results not yet available. "
            "Trigger manually: GitHub → Actions → Quant Backtest → Run workflow. "
            "First run takes 3-6 hours due to historical fundamentals fetching."
        )
        return

    if "_error" in results:
        st.error(f"Backtest cache error: {results['_error']}")
        return

    last_run = results.get("last_run_utc", "unknown")
    n_checkpoints = results.get("n_checkpoints", 0)
    universe_size = results.get("universe_size", 0)
    parameters = results.get("parameters", {})
    aggregate = results.get("aggregate_metrics", {})
    monthly = results.get("monthly_results", [])

    # ── Run metadata ──
    info_cols = st.columns(4)
    with info_cols[0]:
        st.metric("Checkpoints", f"{n_checkpoints}")
    with info_cols[1]:
        st.metric("Universe Size", f"{universe_size}")
    with info_cols[2]:
        st.metric("Hold Period", f"{parameters.get('hold_trading_days', 21)} trading days")
    with info_cols[3]:
        avg_quality = aggregate.get("avg_data_quality_across_run", 0)
        st.metric("Avg Data Quality", f"{avg_quality:.0f}/100")

    st.caption(f"Last run: {last_run}")
    st.markdown("---")

    # ── Side-by-side aggregate metrics ──
    realistic = aggregate.get("realistic_strategy", {})
    max_strat = aggregate.get("theoretical_max_strategy", {})
    spy = aggregate.get("spy_benchmark", {})

    st.markdown("#### 📊 Aggregate Performance")

    perf_cols = st.columns(3)

    with perf_cols[0]:
        st.markdown("##### 🎯 Realistic Strategy")
        st.caption("Buy top 10, hold to month-end")
        if realistic:
            _render_metric_block(realistic)

    with perf_cols[1]:
        st.markdown("##### 🚀 Theoretical Maximum")
        st.caption("Best close price during 1-month window")
        if max_strat:
            _render_metric_block(max_strat)

    with perf_cols[2]:
        st.markdown("##### 🐂 SPY Benchmark")
        st.caption("Buy SPY, hold 1 month, repeat")
        if spy:
            _render_metric_block(spy)

    # ── Edge analysis ──
    if realistic and max_strat and spy:
        st.markdown("---")
        st.markdown("#### 🔍 Edge Analysis")

        edge_cols = st.columns(3)
        with edge_cols[0]:
            edge_vs_spy = realistic.get("avg_return_pct", 0) - spy.get("avg_return_pct", 0)
            st.metric(
                "Realistic vs SPY (avg/period)",
                f"{edge_vs_spy:+.2f}%",
                "Per 1-month period"
            )
        with edge_cols[1]:
            exit_efficiency = (realistic.get("avg_return_pct", 0) / max_strat.get("avg_return_pct", 1)) * 100 if max_strat.get("avg_return_pct") else 0
            st.metric(
                "Exit Timing Efficiency",
                f"{exit_efficiency:.1f}%",
                "Realistic / Theoretical Max"
            )
        with edge_cols[2]:
            win_rate = realistic.get("win_rate_pct", 0)
            st.metric(
                "Win Rate (Realistic)",
                f"{win_rate:.1f}%",
                f"{int(win_rate * realistic.get('n_periods', 0) / 100)} of {realistic.get('n_periods', 0)}"
            )

    # ── Equity curve ──
    if monthly:
        st.markdown("---")
        st.markdown("#### 📈 Equity Curve")
        _render_equity_curve(monthly)

    # ── Data quality timeline ──
    if monthly:
        st.markdown("---")
        st.markdown("#### 📊 Data Quality Over Time")
        _render_data_quality_chart(monthly)
        st.caption(
            "Lower bars = sparser fundamentals data was available historically. "
            "Trust 2018+ checkpoints most. Pre-2015 fundamentals are partially reconstructed."
        )

    # ── Detail browser ──
    if monthly:
        st.markdown("---")
        st.markdown("#### 🔍 Monthly Results Detail")
        with st.expander("Browse individual monthly checkpoints"):
            _render_monthly_detail(monthly)

    # ── Caveats ──
    st.markdown("---")
    with st.expander("⚠️ Important Caveats — Read Before Drawing Conclusions"):
        st.markdown("""
        **This backtest has known methodological limitations specific to the quant strategy:**

        **1. Historical fundamentals data is sparse.** yfinance's historical
        fundamentals coverage degrades significantly before 2018, and is very
        thin before 2015. The "Data Quality" indicator shows how complete the
        fundamentals were at each checkpoint. Periods with quality < 50 should be
        interpreted as approximate.

        **2. Survivorship bias.** Universe = tickers existing TODAY. Companies
        that went bankrupt or got delisted are excluded. This inflates 20-year
        backtest returns by an estimated 2-4 percentage points annualized.

        **3. Pillar scoring limitations.** The five pillars are computed from
        whatever historical data was available:
        - Momentum: 100% reproducible historically
        - Valuation (P/E): ~95% reproducible (yfinance has trailing earnings)
        - Growth (revenue): ~70% reliable post-2015, sparse pre-2015
        - Profitability (margins): ~70% post-2015, sparse pre-2015
        - Financial Health (D/E): ~60% post-2018, very sparse pre-2018

        For periods where pillar data is missing, scores default to 50 (neutral).
        This is conservative but means the score isn't truly the "5-pillar" system
        in older periods — it's effectively a "1-3 pillar" system depending on
        what data was available.

        **4. Sector composition changed over time.** A "5-pillar quant" applied
        to 2005's market is reasoning about a different economy. Tech was a
        smaller share, financials larger, no FAANG companies existed yet. The
        backtest treats these structural shifts as part of the test, not adjusts
        for them.

        **5. The "Theoretical Maximum" requires perfect foresight.** Selling at
        the best price during the window is impossible in practice. The realistic
        strategy reflects what a real investor could plausibly capture.

        **6. No transaction costs.** $0-commission brokers reduce but don't
        eliminate trading friction (bid-ask spreads, market impact, taxes).

        **What this backtest IS valid for:**
        - Validating that the quant scoring has predictive value beyond random
        - Comparing risk/reward to buy-and-hold SPY across multiple regimes
        - Identifying periods of underperformance (concerning)
        - Showing the system was tested, not just built

        **What this backtest is NOT:**
        - A precise simulation of live trading
        - A guarantee of future returns
        - A reason to deploy capital mechanically
        - Comparable to a full point-in-time backtest using Compustat data
        """)


def _render_metric_block(stats):
    cols = st.columns(2)
    with cols[0]:
        st.metric("Avg Return / Period", f"{stats.get('avg_return_pct', 0):+.2f}%")
        st.metric("Win Rate", f"{stats.get('win_rate_pct', 0):.1f}%")
    with cols[1]:
        st.metric("Best Period", f"{stats.get('best_period_pct', 0):+.2f}%")
        st.metric("Worst Period", f"{stats.get('worst_period_pct', 0):+.2f}%")
    st.metric("Total Compounded", f"{stats.get('total_compounded_pct', 0):+.2f}%")


def _render_equity_curve(monthly):
    rows = []
    cum_realistic = 100
    cum_max = 100
    cum_spy = 100

    for m in sorted(monthly, key=lambda x: x.get("date", "")):
        date = m.get("date")
        r_real = m.get("portfolio_return_realistic")
        r_max = m.get("portfolio_return_max")
        r_spy = m.get("spy_return_pct")

        if r_real is not None:
            cum_realistic *= (1 + r_real / 100)
        if r_max is not None:
            cum_max *= (1 + r_max / 100)
        if r_spy is not None:
            cum_spy *= (1 + r_spy / 100)

        rows.append({
            "Date": date,
            "Realistic": cum_realistic,
            "Theoretical Max": cum_max,
            "SPY Benchmark": cum_spy,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
        st.line_chart(df, height=400)
        st.caption("Cumulative return on $100 starting capital, compounded monthly.")


def _render_data_quality_chart(monthly):
    rows = []
    for m in sorted(monthly, key=lambda x: x.get("date", "")):
        rows.append({
            "Date": m.get("date"),
            "Data Quality (0-100)": m.get("avg_data_quality", 0),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
        st.bar_chart(df, height=200)


def _render_monthly_detail(monthly):
    rows = []
    for m in monthly:
        rows.append({
            "Date": m.get("date"),
            "Quality": f"{m.get('avg_data_quality', 0):.0f}",
            "Qualified": m.get("n_qualified", 0),
            "Realistic %": f"{m.get('portfolio_return_realistic', 0):+.2f}" if m.get("portfolio_return_realistic") is not None else "—",
            "Max %": f"{m.get('portfolio_return_max', 0):+.2f}" if m.get("portfolio_return_max") is not None else "—",
            "SPY %": f"{m.get('spy_return_pct', 0):+.2f}" if m.get("spy_return_pct") is not None else "—",
            "Top Pick": m.get("top_picks", [{}])[0].get("ticker", "—") if m.get("top_picks") else "—",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)
