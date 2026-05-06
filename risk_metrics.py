"""
Risk Metrics — Shared computation utilities

Provides consistent risk-adjusted return calculations across:
- Quant Portfolio tab (already integrated)
- Stock Detail tab (per-stock metrics)
- Macro Economy tab (SPY/index regime metrics)
- Market Sentiment tab (cross-sectional dispersion)

All metrics assume daily price data unless specified.
"""

import math
import numpy as np
import pandas as pd

DEFAULT_RISK_FREE_RATE = 0.04  # 4% annualized (current Treasury short-rate)
TRADING_DAYS_PER_YEAR = 252


def daily_returns_from_prices(prices):
    """Convert price series to daily returns. Drops first NaN."""
    if prices is None or len(prices) < 2:
        return None
    if isinstance(prices, pd.Series):
        return prices.pct_change().dropna()
    arr = np.asarray(prices)
    return np.diff(arr) / arr[:-1]


def compute_volatility_annualized(returns, periods_per_year=TRADING_DAYS_PER_YEAR):
    """Annualized standard deviation of returns."""
    if returns is None or len(returns) < 2:
        return None
    rets = np.asarray(returns).flatten()
    rets = rets[~np.isnan(rets)]
    if len(rets) < 2:
        return None
    return float(np.std(rets, ddof=1) * math.sqrt(periods_per_year))


def compute_sharpe_ratio(returns, risk_free_rate=DEFAULT_RISK_FREE_RATE,
                         periods_per_year=TRADING_DAYS_PER_YEAR):
    """
    Sharpe ratio = (avg excess return) / (std dev of returns), annualized.

    > 1.0 is good, > 2.0 is excellent, > 3.0 is rarely sustainable.
    """
    if returns is None or len(returns) < 2:
        return None
    rets = np.asarray(returns).flatten()
    rets = rets[~np.isnan(rets)]
    if len(rets) < 2:
        return None

    rf_per_period = (1 + risk_free_rate) ** (1.0 / periods_per_year) - 1
    excess = rets - rf_per_period
    std = np.std(rets, ddof=1)
    if std == 0:
        return None
    return float(np.mean(excess) / std * math.sqrt(periods_per_year))


def compute_sortino_ratio(returns, risk_free_rate=DEFAULT_RISK_FREE_RATE,
                          periods_per_year=TRADING_DAYS_PER_YEAR):
    """
    Sortino ratio = (avg excess return) / (downside deviation), annualized.

    Like Sharpe but only penalizes downside volatility.
    Higher than Sharpe usually means asymmetric returns (good).
    """
    if returns is None or len(returns) < 2:
        return None
    rets = np.asarray(returns).flatten()
    rets = rets[~np.isnan(rets)]
    if len(rets) < 2:
        return None

    rf_per_period = (1 + risk_free_rate) ** (1.0 / periods_per_year) - 1
    excess = rets - rf_per_period

    downside = rets[rets < 0]
    if len(downside) < 2:
        return None
    downside_std = np.std(downside, ddof=1)
    if downside_std == 0:
        return None
    return float(np.mean(excess) / downside_std * math.sqrt(periods_per_year))


def compute_max_drawdown(returns_or_prices, is_returns=True):
    """
    Max drawdown as positive percent (e.g., 25.5 means -25.5% peak-to-trough).

    Pass is_returns=False if you have a price series instead.
    """
    if returns_or_prices is None or len(returns_or_prices) < 2:
        return None
    arr = np.asarray(returns_or_prices).flatten()
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return None

    if is_returns:
        cum = np.cumprod(1 + arr)
    else:
        cum = arr / arr[0]

    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    return float(abs(dd.min()) * 100)


def compute_calmar_ratio(returns, periods_per_year=TRADING_DAYS_PER_YEAR):
    """
    Calmar = annualized return / max drawdown (both as decimals).
    Higher = better return per unit of worst-case drawdown.
    """
    if returns is None or len(returns) < 2:
        return None
    rets = np.asarray(returns).flatten()
    rets = rets[~np.isnan(rets)]
    if len(rets) < 2:
        return None

    n_years = len(rets) / periods_per_year
    if n_years <= 0:
        return None

    cum_return = np.prod(1 + rets) - 1
    if cum_return <= -1:
        return None
    cagr = (1 + cum_return) ** (1.0 / n_years) - 1

    max_dd_pct = compute_max_drawdown(rets, is_returns=True)
    if max_dd_pct is None or max_dd_pct == 0:
        return None
    return float(cagr / (max_dd_pct / 100))


def compute_beta_vs_benchmark(stock_returns, benchmark_returns):
    """
    Beta = covariance(stock, benchmark) / variance(benchmark).
    Beta of 1.0 means moves with market. > 1 = more volatile than market.
    """
    if stock_returns is None or benchmark_returns is None:
        return None

    s = np.asarray(stock_returns).flatten()
    b = np.asarray(benchmark_returns).flatten()

    # Align lengths (use the shorter)
    n = min(len(s), len(b))
    if n < 30:  # Need meaningful sample
        return None
    s = s[-n:]
    b = b[-n:]

    # Drop joint NaNs
    mask = ~(np.isnan(s) | np.isnan(b))
    s = s[mask]
    b = b[mask]
    if len(s) < 30:
        return None

    var_b = np.var(b, ddof=1)
    if var_b == 0:
        return None
    cov = np.mean((s - np.mean(s)) * (b - np.mean(b))) * len(s) / (len(s) - 1)
    return float(cov / var_b)


def compute_alpha_vs_benchmark(stock_returns, benchmark_returns,
                                risk_free_rate=DEFAULT_RISK_FREE_RATE,
                                periods_per_year=TRADING_DAYS_PER_YEAR):
    """
    Jensen's Alpha (annualized) — excess return after adjusting for beta-implied market risk.

    Alpha > 0 means stock beat its risk-adjusted expected return.
    Alpha < 0 means stock underperformed expected.
    """
    if stock_returns is None or benchmark_returns is None:
        return None

    beta = compute_beta_vs_benchmark(stock_returns, benchmark_returns)
    if beta is None:
        return None

    s = np.asarray(stock_returns).flatten()
    b = np.asarray(benchmark_returns).flatten()
    n = min(len(s), len(b))
    s = s[-n:]
    b = b[-n:]
    mask = ~(np.isnan(s) | np.isnan(b))
    s = s[mask]
    b = b[mask]

    rf_per_period = (1 + risk_free_rate) ** (1.0 / periods_per_year) - 1

    # Jensen's alpha: actual_return - (rf + beta * (market_return - rf))
    avg_stock = np.mean(s)
    avg_market = np.mean(b)

    period_alpha = avg_stock - (rf_per_period + beta * (avg_market - rf_per_period))
    return float(period_alpha * periods_per_year)  # annualize


def compute_full_metrics(stock_returns, benchmark_returns=None, periods_per_year=TRADING_DAYS_PER_YEAR):
    """
    All-in-one: compute every metric at once for a stock.

    Returns dict with: sharpe, sortino, calmar, max_drawdown, volatility, beta, alpha, cagr.
    Missing metrics return None (insufficient data, etc.) rather than crashing.
    """
    metrics = {}

    if stock_returns is None or len(stock_returns) < 2:
        return metrics

    rets = np.asarray(stock_returns).flatten()
    rets = rets[~np.isnan(rets)]

    metrics["sharpe"] = compute_sharpe_ratio(rets, periods_per_year=periods_per_year)
    metrics["sortino"] = compute_sortino_ratio(rets, periods_per_year=periods_per_year)
    metrics["calmar"] = compute_calmar_ratio(rets, periods_per_year=periods_per_year)
    metrics["max_drawdown_pct"] = compute_max_drawdown(rets, is_returns=True)
    metrics["volatility_annualized_pct"] = (
        compute_volatility_annualized(rets, periods_per_year=periods_per_year) * 100
        if compute_volatility_annualized(rets, periods_per_year=periods_per_year) is not None else None
    )

    # CAGR
    n_years = len(rets) / periods_per_year
    if n_years > 0 and len(rets) > 0:
        cum = np.prod(1 + rets) - 1
        if cum > -1:
            metrics["cagr_pct"] = ((1 + cum) ** (1.0 / n_years) - 1) * 100

    # Beta and Alpha vs benchmark (if provided)
    if benchmark_returns is not None:
        metrics["beta"] = compute_beta_vs_benchmark(rets, benchmark_returns)
        metrics["alpha_pct"] = (
            compute_alpha_vs_benchmark(rets, benchmark_returns, periods_per_year=periods_per_year) * 100
            if compute_alpha_vs_benchmark(rets, benchmark_returns, periods_per_year=periods_per_year) is not None else None
        )

    return metrics


def rolling_sharpe(returns, window_days=252, periods_per_year=TRADING_DAYS_PER_YEAR,
                   risk_free_rate=DEFAULT_RISK_FREE_RATE):
    """
    Rolling 1-year Sharpe ratio for visualizing risk-adjusted performance over time.
    Returns pandas Series.
    """
    if returns is None or len(returns) < window_days:
        return None
    if not isinstance(returns, pd.Series):
        returns = pd.Series(returns)

    rf_per_period = (1 + risk_free_rate) ** (1.0 / periods_per_year) - 1
    excess = returns - rf_per_period

    rolling_mean = excess.rolling(window_days).mean()
    rolling_std = returns.rolling(window_days).std()
    rolling_sharpe = (rolling_mean / rolling_std) * math.sqrt(periods_per_year)
    return rolling_sharpe


def current_drawdown_pct(prices):
    """Current % below all-time-high. Always positive (or 0 if at ATH)."""
    if prices is None or len(prices) < 2:
        return None
    arr = np.asarray(prices).flatten()
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return None

    peak = np.maximum.accumulate(arr)
    current_dd = (arr[-1] - peak[-1]) / peak[-1]
    return float(abs(current_dd) * 100)


# ────────────────────────────────────────────────────────────────────
# Streamlit display helpers (kept here so all tabs render consistently)
# ────────────────────────────────────────────────────────────────────

def format_sharpe(value):
    """Format Sharpe with quality emoji indicator."""
    if value is None:
        return "—"
    val = f"{value:.2f}"
    if value >= 2.0:
        return f"{val} 🟢"  # Excellent
    if value >= 1.0:
        return f"{val} 🟡"  # Good
    if value >= 0:
        return f"{val} ⚪"  # Mediocre
    return f"{val} 🔴"  # Negative = losing money risk-adjusted


def format_drawdown(value):
    """Format drawdown with severity indicator."""
    if value is None:
        return "—"
    val = f"-{value:.1f}%"
    if value < 10:
        return f"{val} 🟢"
    if value < 20:
        return f"{val} 🟡"
    if value < 30:
        return f"{val} 🟠"
    return f"{val} 🔴"


def render_risk_metric_block(metrics, st):
    """
    Render a 6-cell risk metrics row in a Streamlit context.

    Use case: drop into a Stock Detail / Quant Portfolio / Macro section.
    Pass the streamlit module as `st` to avoid import collision.
    """
    cols = st.columns(6)
    with cols[0]:
        st.metric("CAGR", f"{metrics.get('cagr_pct', 0):.2f}%" if metrics.get('cagr_pct') is not None else "—")
    with cols[1]:
        st.metric("Sharpe", format_sharpe(metrics.get('sharpe')))
    with cols[2]:
        st.metric("Sortino",
                 f"{metrics['sortino']:.2f}" if metrics.get('sortino') is not None else "—")
    with cols[3]:
        st.metric("Calmar",
                 f"{metrics['calmar']:.2f}" if metrics.get('calmar') is not None else "—")
    with cols[4]:
        st.metric("Max DD", format_drawdown(metrics.get('max_drawdown_pct')))
    with cols[5]:
        st.metric("Volatility",
                 f"{metrics['volatility_annualized_pct']:.1f}%" if metrics.get('volatility_annualized_pct') is not None else "—")
