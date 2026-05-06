"""
Quant 5-Pillar Backtest Display
================================

Renders quant_backtest_results.json — the validated 21-year quant strategy
backtest with point-in-time SEC EDGAR fundamentals.
"""

import os
import json
import math
from datetime import datetime, timezone

import numpy as np
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


def _compute_risk_metrics(returns_pct):
    """
    Compute risk-adjusted metrics from a list of period returns (in percent).
    Quarterly returns assumed (4 periods/year).
    """
    if not returns_pct or len(returns_pct) < 2:
        return {}

    rets = np.array([r / 100 for r in returns_pct])
    n = len(rets)
    periods_per_year = 4

    total_compound = np.prod(1 + rets) - 1
    years = n / periods_per_year
    cagr = (1 + total_compound) ** (1 / years) - 1 if years > 0 else 0

    period_std = np.std(rets, ddof=1)
    vol_annualized = period_std * np.sqrt(periods_per_year)

    downside_rets = rets[rets < 0]
    if len(downside_rets) > 0:
        downside_std = np.std(downside_rets, ddof=1) if len(downside_rets) > 1 else abs(downside_rets[0])
        downside_vol = downside_std * np.sqrt(periods_per_year)
    else:
        downside_vol = 0

    rf_annual = 0.02
    rf_period = (1 + rf_annual) ** (1 / periods_per_year) - 1
    excess_returns = rets - rf_period

    if period_std > 0:
        sharpe = (np.mean(excess_returns) * periods_per_year) / vol_annualized
    else:
        sharpe = 0

    if downside_vol > 0:
        sortino = (np.mean(excess_returns) * periods_per_year) / downside_vol
    else:
        sortino = float('inf') if np.mean(excess_returns) > 0 else 0

    cum_curve = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(cum_curve)
    drawdowns = (cum_curve - peak) / peak
    max_dd = abs(drawdowns.min())

    calmar = cagr / max_dd if max_dd > 0 else float('inf') if cagr > 0 else 0

    return {
        "cagr_pct": cagr * 100,
        "volatility_annualized_pct": vol_annualized * 100,
        "downside_volatility_annualized_pct": downside_vol * 100,
        "sharpe_annualized": sharpe,
        "sortino_annualized": sortino if not math.isinf(sortino) else None,
        "calmar": calmar if not math.isinf(calmar) else None,
        "max_drawdown_pct": max_dd * 100,
    }


def render_quant_backtest_panel():
    """Render the validated quant 5-pillar backtest panel."""
    st.markdown("### 📊 Quant 5-Pillar Strategy — Validated Backtest")
    st.caption(
        "Real point-in-time SEC EDGAR fundamentals. 86 quarterly checkpoints, 2005-2026. "
        "1,326-ticker universe. 5-pillar composite scoring. Top 10 picks per quarter, 63-day hold."
    )

    results = load_quant_backtest_results()

    if results is None:
        st.info(
            "Quant backtest results not yet available. "
            "Run `python build_quant_backtest.py` locally with `LOCAL_RUN=1`."
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

    realistic = aggregate.get("realistic_strategy", {})
    max_strat = aggregate.get("theoretical_max_strategy", {})
    spy = aggregate.get("spy_benchmark", {})

    realistic_rets = [m.get("portfolio_return_realistic") for m in monthly if m.get("portfolio_return_realistic") is not None]
    spy_rets = [m.get("spy_return_pct") for m in monthly if m.get("spy_return_pct") is not None]

    realistic_risk = _compute_risk_metrics(realistic_rets)
    spy_risk = _compute_risk_metrics(spy_rets)

    # ── HEADLINE: total compound return comparison ──
    st.markdown("#### 🏆 Headline Result")
    headline_cols = st.columns(4)

    quant_total = realistic.get("total_compounded_pct", 0)
    spy_total = spy.get("total_compounded_pct", 0)
    outperformance = quant_total - spy_total

    with headline_cols[0]:
        st.metric("Quant Total Return", f"+{quant_total:,.0f}%", f"$100 → ${100 + quant_total:,.0f}")
    with headline_cols[1]:
        st.metric("SPY Buy-and-Hold", f"+{spy_total:,.0f}%", f"$100 → ${100 + spy_total:,.0f}")
    with headline_cols[2]:
        st.metric("Outperformance", f"+{outperformance:,.0f}%", "absolute")
    with headline_cols[3]:
        ratio = (100 + quant_total) / (100 + spy_total) if spy_total > -100 else 0
        st.metric("Multiplier vs SPY", f"{ratio:.2f}x", f"{realistic.get('n_periods', 0)} quarters")

    st.markdown("---")
    info_cols = st.columns(4)
    with info_cols[0]:
        st.metric("Quarters Tested", f"{realistic.get('n_periods', 0)}")
    with info_cols[1]:
        st.metric("Universe Size", f"{universe_size}")
    with info_cols[2]:
        st.metric("Hold Period", f"{parameters.get('hold_trading_days', 63)} trading days")
    with info_cols[3]:
        avg_quality = aggregate.get("avg_data_quality_across_run", 0)
        st.metric("Avg Data Quality", f"{avg_quality:.0f}/100")

    st.caption(f"Last run: {last_run}")

    # ── Risk-adjusted metrics ──
    st.markdown("---")
    st.markdown("#### 📐 Risk-Adjusted Performance")
    st.caption("Risk-adjusted metrics use 2% annualized risk-free rate. Quarterly returns annualized to standard form.")

    risk_cols = st.columns(3)

    with risk_cols[0]:
        st.markdown("##### Quant Strategy")
        if realistic_risk:
            st.metric("CAGR", f"{realistic_risk['cagr_pct']:.2f}%")
            st.metric("Sharpe Ratio", f"{realistic_risk['sharpe_annualized']:.2f}")
            sortino = realistic_risk.get('sortino_annualized')
            st.metric("Sortino Ratio", f"{sortino:.2f}" if sortino else "—")
            calmar = realistic_risk.get('calmar')
            st.metric("Calmar Ratio", f"{calmar:.2f}" if calmar else "—")
            st.metric("Max Drawdown", f"-{realistic_risk['max_drawdown_pct']:.2f}%")
            st.metric("Volatility (ann.)", f"{realistic_risk['volatility_annualized_pct']:.2f}%")

    with risk_cols[1]:
        st.markdown("##### SPY Benchmark")
        if spy_risk:
            st.metric("CAGR", f"{spy_risk['cagr_pct']:.2f}%")
            st.metric("Sharpe Ratio", f"{spy_risk['sharpe_annualized']:.2f}")
            sortino = spy_risk.get('sortino_annualized')
            st.metric("Sortino Ratio", f"{sortino:.2f}" if sortino else "—")
            calmar = spy_risk.get('calmar')
            st.metric("Calmar Ratio", f"{calmar:.2f}" if calmar else "—")
            st.metric("Max Drawdown", f"-{spy_risk['max_drawdown_pct']:.2f}%")
            st.metric("Volatility (ann.)", f"{spy_risk['volatility_annualized_pct']:.2f}%")

    with risk_cols[2]:
        st.markdown("##### Edge")
        if realistic_risk and spy_risk:
            cagr_edge = realistic_risk['cagr_pct'] - spy_risk['cagr_pct']
            sharpe_edge = realistic_risk['sharpe_annualized'] - spy_risk['sharpe_annualized']
            dd_edge = spy_risk['max_drawdown_pct'] - realistic_risk['max_drawdown_pct']
            st.metric("CAGR Edge", f"+{cagr_edge:.2f}%", "annualized")
            st.metric("Sharpe Edge", f"+{sharpe_edge:.2f}", "risk-adjusted return")
            st.metric("Drawdown Edge",
                     f"{'+' if dd_edge > 0 else ''}{dd_edge:.2f}%",
                     "smaller drawdown = better")
            st.caption("**Sharpe > 1.0** is good; **>2.0** is excellent. Higher = more return per unit of risk.")

    # ── Period-level performance ──
    st.markdown("---")
    st.markdown("#### 📊 Period-Level Performance")

    perf_cols = st.columns(3)
    with perf_cols[0]:
        st.markdown("##### Realistic Strategy")
        st.caption("Top 10 picks each quarter, hold 63 days")
        if realistic:
            _render_metric_block(realistic)

    with perf_cols[1]:
        st.markdown("##### Theoretical Maximum")
        st.caption("Best close price during 63-day window")
        if max_strat:
            _render_metric_block(max_strat)

    with perf_cols[2]:
        st.markdown("##### SPY Benchmark")
        st.caption("Buy SPY, hold 63 days, repeat")
        if spy:
            _render_metric_block(spy)

    # ── Equity curve ──
    if monthly:
        st.markdown("---")
        st.markdown("#### 📈 Cumulative Returns")
        _render_equity_curve(monthly)

    # ── Drawdown comparison ──
    if monthly:
        st.markdown("---")
        st.markdown("#### 📉 Drawdown Comparison")
        _render_drawdown_chart(monthly)

    # ── Data quality timeline ──
    if monthly:
        st.markdown("---")
        st.markdown("#### 🎯 Data Quality Over Time")
        _render_data_quality_chart(monthly)
        st.caption(
            "Higher bars = more complete EDGAR XBRL fundamentals. "
            "2005-2008 had limited XBRL adoption (most companies hadn't started filing). "
            "2009+ data is reliable."
        )

    # ── Detail browser ──
    if monthly:
        st.markdown("---")
        st.markdown("#### 🔍 Quarterly Results Detail")
        with st.expander("Browse individual quarterly checkpoints"):
            _render_monthly_detail(monthly)

    # ── Methodology ──
    st.markdown("---")
    with st.expander("📖 Methodology — How This Backtest Works"):
        st.markdown("""
        ### Point-in-Time Backtesting

        This is a **true point-in-time** backtest using SEC EDGAR XBRL fundamentals data. 
        At each quarterly checkpoint:

        1. **Score the universe** using only data that was available on that date
        2. **Pick top 10** by composite score
        3. **Buy at close** of checkpoint date (1/10 of capital each)
        4. **Hold 63 trading days** (~one quarter)
        5. **Mark to market** at end of hold period
        6. **Compare to SPY** held over the same period

        Every fundamental metric (revenue, earnings, debt, etc.) is filtered to only filings 
        with `filed_date <= checkpoint_date`. This means the strategy could have been 
        executed in real-time at each point — no future information leaks into the past.

        ### 5-Pillar Composite Score

        Each stock receives scores in five categories, then averaged:

        - **Momentum** — Multi-timeframe price momentum (1mo, 3mo, 6mo, 12mo)
        - **Valuation** — P/E, P/B, EV/EBITDA relative to sector
        - **Growth** — Revenue growth, earnings growth (TTM)
        - **Profitability** — Operating margin, ROE, ROA
        - **Financial Health** — Debt/Equity, current ratio, interest coverage

        Within each pillar, stocks are scored 0-10 relative to peers in their sector.

        ### Rating Map

        | Composite Score | Rating |
        |---|---|
        | 9.0 - 12.0 | Strong Buy |
        | 8.0 - 9.0 | Buy |
        | 6.0 - 8.0 | Hold |
        | 5.0 - 6.0 | Sell |
        | 0.0 - 5.0 | Strong Sell |

        ### Why "Realistic" vs "Theoretical Max"?

        - **Realistic**: Buy at close, sell at end of 63-day window. What an investor could plausibly capture.
        - **Theoretical Max**: Best closing price during the window. Requires perfect foresight, included only as upper bound.
        """)

    # ── Caveats ──
    st.markdown("---")
    with st.expander("⚠️ Caveats — Read Before Drawing Conclusions"):
        st.markdown("""
        **What this backtest IS valid for:**
        - Validating that 5-pillar scoring has predictive value beyond random
        - Comparing risk/reward to buy-and-hold SPY across multiple market regimes
        - Showing the strategy was tested with rigorous methodology

        **Limitations:**

        **1. Survivorship bias.** Universe = 1,326 tickers existing today. Companies that 
        went bankrupt, got delisted, or merged are excluded. Inflates 21-year returns 
        by an estimated 1-3 percentage points annualized.

        **2. Pre-2009 data is sparse.** XBRL filings became standard around 2009. 
        2005-2008 checkpoints had limited fundamentals coverage.

        **3. No transaction costs.** Bid-ask spreads, slippage, taxes not modeled. 
        Estimate: -0.1% to -0.3% per quarter in real conditions.

        **4. No risk overlay.** No volatility filter, no drawdown protection, no regime detection. 
        The strategy buys top 10 every quarter regardless of market conditions.

        **5. Sample size.** 68 valid quarters is statistically meaningful but not definitive.

        **What this backtest is NOT:**
        - A precise simulation of live trading
        - A guarantee of future returns  
        - A reason to deploy capital mechanically without your own analysis
        """)


def _render_metric_block(stats):
    cols = st.columns(2)
    with cols[0]:
        st.metric("Avg Return / Quarter", f"{stats.get('avg_return_pct', 0):+.2f}%")
        st.metric("Win Rate", f"{stats.get('win_rate_pct', 0):.1f}%")
        st.metric("Avg Win", f"{stats.get('avg_win_pct', 0):+.2f}%")
    with cols[1]:
        st.metric("Best Quarter", f"{stats.get('best_period_pct', 0):+.2f}%")
        st.metric("Worst Quarter", f"{stats.get('worst_period_pct', 0):+.2f}%")
        st.metric("Avg Loss", f"{stats.get('avg_loss_pct', 0):+.2f}%")
    st.metric("Total Compounded", f"{stats.get('total_compounded_pct', 0):+.2f}%")


def _render_equity_curve(monthly):
    rows = []
    cum_realistic = 100.0
    cum_max = 100.0
    cum_spy = 100.0

    if monthly:
        first_date = sorted(monthly, key=lambda x: x.get("date", ""))[0].get("date", "")
        rows.append({
            "Date": first_date,
            "Quant Strategy": cum_realistic,
            "Theoretical Max": cum_max,
            "SPY Benchmark": cum_spy,
        })

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
            "Quant Strategy": cum_realistic,
            "Theoretical Max": cum_max,
            "SPY Benchmark": cum_spy,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
        st.line_chart(df, height=400)
        st.caption(f"Cumulative return on $100 starting capital. Final values: "
                  f"Quant ${cum_realistic:,.0f} | Max ${cum_max:,.0f} | SPY ${cum_spy:,.0f}")


def _render_drawdown_chart(monthly):
    rows = []
    cum_quant = 100.0
    cum_spy = 100.0
    peak_quant = 100.0
    peak_spy = 100.0

    for m in sorted(monthly, key=lambda x: x.get("date", "")):
        date = m.get("date")
        r_real = m.get("portfolio_return_realistic")
        r_spy = m.get("spy_return_pct")

        if r_real is not None:
            cum_quant *= (1 + r_real / 100)
            peak_quant = max(peak_quant, cum_quant)
        if r_spy is not None:
            cum_spy *= (1 + r_spy / 100)
            peak_spy = max(peak_spy, cum_spy)

        dd_quant = (cum_quant - peak_quant) / peak_quant * 100 if peak_quant > 0 else 0
        dd_spy = (cum_spy - peak_spy) / peak_spy * 100 if peak_spy > 0 else 0

        rows.append({
            "Date": date,
            "Quant Drawdown %": dd_quant,
            "SPY Drawdown %": dd_spy,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
        st.area_chart(df, height=300)
        st.caption("Drawdown = % decline from previous peak. Closer to 0 is better.")


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
            "Quant %": f"{m.get('portfolio_return_realistic', 0):+.2f}" if m.get("portfolio_return_realistic") is not None else "—",
            "Max %": f"{m.get('portfolio_return_max', 0):+.2f}" if m.get("portfolio_return_max") is not None else "—",
            "SPY %": f"{m.get('spy_return_pct', 0):+.2f}" if m.get("spy_return_pct") is not None else "—",
            "Top Pick": m.get("top_picks", [{}])[0].get("ticker", "—") if m.get("top_picks") else "—",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)
