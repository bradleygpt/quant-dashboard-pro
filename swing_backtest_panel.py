"""
Swing Trader Backtest Display
=============================

Reads backtest_results.json (built by build_backtest.py via GitHub Actions)
and renders the results in the Swing Trader tab.

Shows two strategies side-by-side:
1. Realistic: target/stop/timeout exits
2. Theoretical Max: best price during window

Plus equity curve comparison vs SPY benchmark.
"""

import os
import json
import math
from datetime import datetime, timezone

import pandas as pd
import streamlit as st


CACHE_PATHS = [
    "backtest_results.json",
    os.path.join("data_cache", "backtest_results.json"),
]


@st.cache_data(ttl=3600, show_spinner=False)
def load_backtest_results():
    """Load backtest results from JSON cache."""
    for path in CACHE_PATHS:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                return {"_error": f"Failed to parse {path}: {str(e)[:120]}"}
    return None


def render_backtest_panel():
    """Render the swing trader backtest results panel."""
    st.markdown("### 📈 Swing Trader Backtest")
    st.caption(
        "Validates the swing trader hypothesis on 20 years of monthly checkpoints. "
        "Each month: top 10 swing trader picks → simulated 14-day holds → portfolio returns."
    )

    results = load_backtest_results()

    if results is None:
        st.info(
            "🚧 Backtest results not yet available. The backtest workflow runs weekly via GitHub Actions. "
            "First run takes 2-3 hours due to historical data fetching. "
            "Trigger manually: GitHub → Actions → Swing Trader Backtest → Run workflow."
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
        st.metric("Hold Period", f"{parameters.get('hold_days', 14)} days")
    with info_cols[3]:
        st.metric("Top N Picks", f"{parameters.get('top_n_picks', 10)}")

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
        st.caption("Target hit, stop hit, or 14-day timeout")
        if realistic:
            _render_metric_block(realistic)
        else:
            st.info("No data")

    with perf_cols[1]:
        st.markdown("##### 🚀 Theoretical Maximum")
        st.caption("Best price hit during 14-day window (perfect exit timing)")
        if max_strat:
            _render_metric_block(max_strat)
        else:
            st.info("No data")

    with perf_cols[2]:
        st.markdown("##### 🐂 SPY Benchmark")
        st.caption("Buy SPY, hold 14 days, repeat")
        if spy:
            _render_metric_block(spy)
        else:
            st.info("No data")

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
                "Per 14-day period"
            )
        with edge_cols[1]:
            exit_efficiency = (realistic.get("avg_return_pct", 0) / max_strat.get("avg_return_pct", 1)) * 100 if max_strat.get("avg_return_pct") else 0
            st.metric(
                "Exit Timing Efficiency",
                f"{exit_efficiency:.1f}%",
                "Realistic / Theoretical Max"
            )
        with edge_cols[2]:
            win_rate_realistic = realistic.get("win_rate_pct", 0)
            st.metric(
                "Win Rate (Realistic)",
                f"{win_rate_realistic:.1f}%",
                f"{int(win_rate_realistic * realistic.get('n_periods', 0) / 100)} of {realistic.get('n_periods', 0)} periods"
            )

    # ── Equity curve ──
    if monthly:
        st.markdown("---")
        st.markdown("#### 📈 Equity Curve")
        _render_equity_curve(monthly)

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
        **This backtest has known methodological limitations:**

        **1. Survivorship bias.** The universe used is companies that EXIST TODAY.
        Companies that went bankrupt or got delisted between 2005 and now are excluded.
        Examples: Lehman Brothers, Bear Stearns, Sears, Toys R Us. A correctly-constructed
        backtest would include these and show worse aggregate returns. Survivorship bias
        typically inflates 20-year backtest returns by 2-4 percentage points annualized.

        **2. Data limitation on universe.** To keep backtest runtime reasonable,
        the screening sample at each checkpoint is limited to 200 tickers.
        A full-universe scan would be more thorough but require significantly more
        compute and yfinance API calls.

        **3. The "Theoretical Maximum" is impossible to achieve in practice.**
        It assumes selling at the best price hit during the holding window — i.e.,
        perfect foresight on exits. No live trader can do this. The realistic
        strategy column reflects what a live trader could plausibly achieve.

        **4. No transaction costs modeled.** Real trading involves bid-ask spreads,
        commissions, and market impact that would reduce returns by 1-2% annualized.
        Modern $0-commission brokers reduce but don't eliminate this.

        **5. Quant scoring overlay uses CURRENT scoring, not historical.** The swing
        trader's technical signals are computed from historical price data correctly.
        But the ranking takes into account today's quant rating system. This creates
        a small look-ahead bias on the rating component (not the technical signals).

        **6. 2008-2009 financial crisis included.** Some monthly checkpoints during
        late 2008 and early 2009 will show severe drawdowns. This is correct — the
        system was operating during real adverse conditions.

        **What this backtest IS valid for:**
        - Validating that the technical signals have predictive value beyond random chance
        - Comparing the swing trader's risk/reward profile to buy-and-hold SPY
        - Identifying periods where the system underperformed (concerning)
        - Demonstrating the system has been tested across multiple market regimes

        **What this backtest is NOT:**
        - A guarantee of future performance
        - A complete simulation of live trading
        - A reason to deploy money mechanically
        """)


def _render_metric_block(stats):
    """Render a metric block for one strategy."""
    cols = st.columns(2)
    with cols[0]:
        st.metric("Avg Return / Period", f"{stats.get('avg_return_pct', 0):+.2f}%")
        st.metric("Win Rate", f"{stats.get('win_rate_pct', 0):.1f}%")
    with cols[1]:
        st.metric("Best Period", f"{stats.get('best_period_pct', 0):+.2f}%")
        st.metric("Worst Period", f"{stats.get('worst_period_pct', 0):+.2f}%")
    st.metric("Total Compounded", f"{stats.get('total_compounded_pct', 0):+.2f}%")


def _render_equity_curve(monthly):
    """Plot cumulative equity curve."""
    rows = []
    cum_realistic = 100  # Start at $100
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


def _render_monthly_detail(monthly):
    """Render a sortable table of all monthly checkpoints."""
    rows = []
    for m in monthly:
        rows.append({
            "Date": m.get("date"),
            "Qualified Picks": m.get("n_qualified", 0),
            "Realistic Return %": f"{m.get('portfolio_return_realistic', 0):+.2f}" if m.get("portfolio_return_realistic") is not None else "—",
            "Max Return %": f"{m.get('portfolio_return_max', 0):+.2f}" if m.get("portfolio_return_max") is not None else "—",
            "SPY Return %": f"{m.get('spy_return_pct', 0):+.2f}" if m.get("spy_return_pct") is not None else "—",
            "Top Pick": m.get("top_picks", [{}])[0].get("ticker", "—") if m.get("top_picks") else "—",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)
