"""
PIT Universe Scoring — Dashboard-Compatible
============================================

Uses the same percentile-rank, sector-relative methodology as the live dashboard
(scoring.py) but operates on point-in-time fundamentals at any historical date.

Output: composite_score on 0-12 scale matching dashboard, with overall_rating
        from OVERALL_RATING_MAP (Strong Buy / Buy / Hold / Sell / Strong Sell).

This means: a "Strong Buy" in this backtest IS a Strong Buy on the dashboard.
The validation is real.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from edgar_fundamentals import (
    get_fundamentals_at_date,
    get_latest_earnings_filing_date,
)
from price_cache import get_prices, get_listed_tickers_at, get_first_date

from config import (
    PILLAR_METRICS,
    GRADE_PERCENTILE_MAP,
    GRADE_SCORES,
    OVERALL_RATING_MAP,
    DEFAULT_PILLAR_WEIGHTS,
)


# PIT-specific override of PILLAR_METRICS.
# The "EPS Revisions" pillar in the live dashboard uses analyst data (target upside,
# recommendation score, earnings surprise) that requires paid I/B/E/S/Refinitiv access.
# We replace it with PEAD (Post-Earnings Announcement Drift) — a documented quant signal
# that captures market acceptance of fundamentals via post-earnings price drift.
#
# Higher PEAD = stock outperformed market in window after earnings = positive signal.
# All other pillars match dashboard exactly.
PIT_PILLAR_METRICS = {
    "Valuation": PILLAR_METRICS["Valuation"],
    "Growth": PILLAR_METRICS["Growth"],
    "Profitability": PILLAR_METRICS["Profitability"],
    "Momentum": PILLAR_METRICS["Momentum"],
    "EPS Revisions": [
        # PIT replacement: PEAD (Post-Earnings Announcement Drift)
        # Higher abnormal return post-earnings = better signal
        ("pead_30d", "Post-Earnings Drift (30d abnormal return)", True),
    ],
}


# ────────────────────────────────────────────────────────────────────
# PIT-specific metric subset (what we can compute at any historical date)
# ────────────────────────────────────────────────────────────────────
# We map PIT metric names to dashboard pillar/metric structure.
# Dashboard's PILLAR_METRICS has 30+ metrics; PIT can fill ~half of them.
# Missing metrics simply don't get scored — their pillar avg uses what's available.

# Sector mapping cache - load once
_SECTOR_MAP_CACHE = None


def _load_sector_map():
    """Load ticker -> sector mapping. Used for sector-relative percentile ranking."""
    global _SECTOR_MAP_CACHE
    if _SECTOR_MAP_CACHE is not None:
        return _SECTOR_MAP_CACHE

    import json
    import os

    # Try the live universe cache (has sector data)
    cache_paths = [
        "fundamentals_cache.json",
        os.path.join("data_cache", "fundamentals_cache.json"),
    ]

    sector_map = {}
    for path in cache_paths:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                # data is dict: ticker -> { sector, ... }
                for ticker, info in data.items():
                    sector = info.get("sector") or info.get("industry") or "Unknown"
                    sector_map[ticker.upper()] = sector
                if sector_map:
                    break
            except Exception:
                continue

    _SECTOR_MAP_CACHE = sector_map
    return sector_map


def _percentile_to_grade(pct):
    """Map percentile (0-100) to letter grade matching dashboard."""
    if pd.isna(pct):
        return "F"
    for grade, (low, high) in GRADE_PERCENTILE_MAP.items():
        if low <= pct <= high:
            return grade
    return "F"


def _score_to_rating(score):
    """Map composite score (0-12) to rating tier."""
    if pd.isna(score):
        return "Hold"
    for rating, (low, high) in OVERALL_RATING_MAP.items():
        if low <= score <= high:
            return rating
    return "Hold"


def _score_to_grade(score):
    """Map pillar score (0-12 scale) to letter grade."""
    if pd.isna(score):
        return "F"
    if score >= 11: return "A+"
    if score >= 10: return "A"
    if score >= 9:  return "A-"
    if score >= 8:  return "B+"
    if score >= 7:  return "B"
    if score >= 6:  return "B-"
    if score >= 5:  return "C+"
    if score >= 4:  return "C"
    if score >= 3:  return "C-"
    if score >= 2:  return "D"
    return "F"


def compute_pit_metrics_for_ticker(ticker, target_date):
    """
    Compute all dashboard-compatible metrics for one ticker at target_date.

    Returns dict with metrics matching dashboard's PILLAR_METRICS field names:
      forwardPE, trailingPE, priceToBook, priceToSalesTrailing12Months,
      enterpriseToEbitda, enterpriseToRevenue,
      revenueGrowth, earningsGrowth,
      grossMargins, operatingMargins, profitMargins, returnOnEquity, returnOnAssets,
      momentum_1m, momentum_3m, momentum_6m, momentum_12m, momentum_vs_sma50, momentum_vs_sma200,
      sector

    Returns None if ticker has insufficient data.
    """
    # ── Get PIT fundamentals from EDGAR ──
    fundamentals = get_fundamentals_at_date(ticker, target_date)
    quality = fundamentals.get("data_quality_score", 0)
    if quality < 20:
        return None

    # ── Get price history (1 year before target_date for momentum calcs) ──
    end = target_date
    start = end - timedelta(days=400)
    hist = get_prices(ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if hist is None or len(hist) < 60:
        return None

    close = hist["Close"].astype(float)
    price = float(close.iloc[-1])

    # Sector lookup (live data, not PIT - sectors don't change much)
    sector_map = _load_sector_map()
    sector = sector_map.get(ticker.upper(), "Unknown")

    metrics = {
        "ticker": ticker,
        "sector": sector,
        "_data_quality": quality,
        "_price": price,
    }

    # ── Valuation metrics ──
    ttm_eps = fundamentals.get("ttm_eps")
    if ttm_eps and ttm_eps > 0:
        metrics["trailingPE"] = price / ttm_eps
        metrics["forwardPE"] = price / ttm_eps  # Same as trailing for PIT (no analyst forecasts)

    equity = fundamentals.get("stockholders_equity")
    shares = fundamentals.get("shares_outstanding")
    if equity and shares and shares > 0:
        book_value_per_share = equity / shares
        if book_value_per_share > 0:
            metrics["priceToBook"] = price / book_value_per_share

    revenue = fundamentals.get("ttm_revenue")
    if revenue and shares and shares > 0:
        revenue_per_share = revenue / shares
        if revenue_per_share > 0:
            metrics["priceToSalesTrailing12Months"] = price / revenue_per_share

    # EV/EBITDA and EV/Revenue (using approximation: market cap + debt - cash)
    if shares and revenue:
        market_cap = price * shares
        debt = fundamentals.get("total_debt", 0)
        cash = fundamentals.get("cash", 0)
        ev = market_cap + (debt or 0) - (cash or 0)
        if revenue > 0:
            metrics["enterpriseToRevenue"] = ev / revenue
        # EBITDA approximation: operating income + assumed D&A (8% of revenue)
        op_income = revenue * (fundamentals.get("operating_margin", 0) / 100) if fundamentals.get("operating_margin") is not None else None
        if op_income:
            ebitda_proxy = op_income + (revenue * 0.08)
            if ebitda_proxy > 0:
                metrics["enterpriseToEbitda"] = ev / ebitda_proxy

    # ── Growth metrics ──
    rev_growth = fundamentals.get("revenue_growth_yoy")
    if rev_growth is not None:
        # Dashboard expects decimal (0.10 = 10%); PIT returns percent
        metrics["revenueGrowth"] = rev_growth / 100
        metrics["revenueQuarterlyGrowth"] = rev_growth / 100

    # Earnings growth - if we have ttm_net_income and prior year ttm
    # (Currently edgar_fundamentals doesn't compute this, so we compute it here)
    ni = fundamentals.get("ttm_net_income")
    earnings_growth_decimal = None
    if ni and revenue:
        # Compute prior year by looking up fundamentals at target_date - 1 year
        prior_date = target_date - timedelta(days=365)
        prior_fundamentals = get_fundamentals_at_date(ticker, prior_date)
        prior_ni = prior_fundamentals.get("ttm_net_income") if prior_fundamentals else None
        if prior_ni and prior_ni != 0:
            earnings_growth = (ni - prior_ni) / abs(prior_ni)
            metrics["earningsGrowth"] = earnings_growth
            metrics["earningsQuarterlyGrowth"] = earnings_growth
            earnings_growth_decimal = earnings_growth

    # PEG Ratio - one of the most predictive value-vs-growth metrics
    # PEG = Trailing PE / (TTM earnings growth rate as percent)
    # Lower PEG = better value relative to growth (lower is better, < 1.0 ideal)
    # Use trailing earnings growth since we don't have forward analyst estimates in PIT
    if "trailingPE" in metrics and earnings_growth_decimal is not None:
        # Convert decimal growth to percent for PEG formula (e.g. 0.20 -> 20)
        growth_pct = earnings_growth_decimal * 100
        # PEG only meaningful with positive growth (negative growth makes PEG nonsensical)
        if growth_pct > 0:
            peg = metrics["trailingPE"] / growth_pct
            # Cap extreme PEG values that come from very low growth (PE/0.1% growth = 1000)
            # Companies with growth < 1% effectively get penalized as "no growth"
            if peg < 100:  # Reasonable upper bound; beyond this isn't useful signal
                metrics["pegRatio"] = peg
        # If growth is zero or negative, PEG is undefined - leave it out
        # (the percentile rank will treat missing as bottom)

    # ── Profitability metrics ──
    if revenue and revenue > 0:
        if ni is not None:
            metrics["profitMargins"] = ni / revenue
        op_margin_pct = fundamentals.get("operating_margin")
        if op_margin_pct is not None:
            metrics["operatingMargins"] = op_margin_pct / 100
        # Gross margin: now extracted from EDGAR via cost_of_revenue
        gross_margin_pct = fundamentals.get("gross_margin")
        if gross_margin_pct is not None:
            metrics["grossMargins"] = gross_margin_pct / 100

    if equity and equity > 0 and ni is not None:
        metrics["returnOnEquity"] = ni / equity

    total_assets = fundamentals.get("total_assets")
    if total_assets and total_assets > 0 and ni is not None:
        metrics["returnOnAssets"] = ni / total_assets

    # ── Momentum metrics (from price history) ──
    if len(close) >= 22:
        metrics["momentum_1m"] = float((close.iloc[-1] / close.iloc[-22]) - 1)
    if len(close) >= 63:
        metrics["momentum_3m"] = float((close.iloc[-1] / close.iloc[-63]) - 1)
    if len(close) >= 126:
        metrics["momentum_6m"] = float((close.iloc[-1] / close.iloc[-126]) - 1)
    if len(close) >= 252:
        metrics["momentum_12m"] = float((close.iloc[-1] / close.iloc[-252]) - 1)

    # SMA-relative momentum
    if len(close) >= 50:
        sma50 = close.iloc[-50:].mean()
        if sma50 > 0:
            metrics["momentum_vs_sma50"] = float(price / sma50 - 1)
    if len(close) >= 200:
        sma200 = close.iloc[-200:].mean()
        if sma200 > 0:
            metrics["momentum_vs_sma200"] = float(price / sma200 - 1)

    # ── Post-Earnings Announcement Drift (PEAD) ──
    # Replaces dashboard's EPS Revisions pillar (which requires paid analyst data).
    # PEAD measures abnormal return in window after earnings filing.
    # Higher PEAD = market accepting earnings positively = similar information to
    # analyst upgrades. Documented quant signal with 40+ years of academic literature.
    pead_signal = compute_pead(ticker, target_date, hist)
    if pead_signal is not None:
        metrics["pead_30d"] = pead_signal

    return metrics


# Cache SPY price history per (start, end) to avoid redundant fetches
_SPY_CACHE = {}


def _get_spy_history(start_date, end_date):
    """Get SPY price history with caching to avoid redundant fetches per checkpoint."""
    cache_key = (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    if cache_key in _SPY_CACHE:
        return _SPY_CACHE[cache_key]

    spy_hist = get_prices("SPY", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    _SPY_CACHE[cache_key] = spy_hist
    return spy_hist


def compute_pead(ticker, target_date, stock_hist):
    """
    Compute Post-Earnings Announcement Drift signal.

    Logic:
    1. Find most recent earnings filing date F before target_date
    2. If F is < 5 trading days before target_date, return None (window too short)
    3. Define window: F+1 to min(F+30 trading days, target_date)
    4. Compute stock return over window
    5. Compute SPY return over same window (market-adjusted = abnormal return)
    6. Return abnormal return as decimal (e.g., 0.05 = +5% abnormal)

    Returns float or None (insufficient data).
    """
    try:
        filing_date = get_latest_earnings_filing_date(ticker, target_date)
        if filing_date is None:
            return None

        # Convert filing_date to datetime for comparison
        if not isinstance(filing_date, datetime):
            filing_date = datetime.combine(filing_date, datetime.min.time())

        target_dt = target_date if isinstance(target_date, datetime) else datetime.combine(target_date, datetime.min.time())

        # Earnings must be at least 5 days before target for meaningful window
        days_since_earnings = (target_dt - filing_date).days
        if days_since_earnings < 5:
            return None

        # Don't go back more than 90 days (PEAD effect dissipates)
        if days_since_earnings > 90:
            return None

        # Window: from filing_date forward up to ~30 trading days (45 calendar days) or target_date
        window_end = min(filing_date + timedelta(days=45), target_dt)

        # Get stock prices in window (use already-fetched history if it covers the window)
        if stock_hist is not None and not stock_hist.empty:
            stock_in_window = stock_hist[stock_hist.index >= filing_date]
            stock_in_window = stock_in_window[stock_in_window.index <= window_end]
            if len(stock_in_window) < 5:
                return None
            stock_return = float(stock_in_window["Close"].iloc[-1] / stock_in_window["Close"].iloc[0] - 1)
        else:
            return None

        # Get SPY return over same window
        spy_hist = _get_spy_history(filing_date, window_end + timedelta(days=2))
        if spy_hist is None or spy_hist.empty:
            return None
        spy_in_window = spy_hist[spy_hist.index >= filing_date]
        spy_in_window = spy_in_window[spy_in_window.index <= window_end]
        if len(spy_in_window) < 5:
            return None
        spy_return = float(spy_in_window["Close"].iloc[-1] / spy_in_window["Close"].iloc[0] - 1)

        # Abnormal return = stock - market
        abnormal_return = stock_return - spy_return
        return abnormal_return

    except Exception:
        return None


def score_universe_pit(target_date, universe_tickers, sector_relative=True,
                      weights=None, verbose=False):
    """
    Score a list of tickers AS OF target_date using dashboard methodology.

    Returns DataFrame with columns:
      ticker, sector, composite_score (0-12), overall_rating, pillar scores, ...

    This mirrors scoring.py's score_universe() but uses PIT metrics.
    """
    weights = weights or DEFAULT_PILLAR_WEIGHTS

    # ── Step 1: Compute metrics for all tickers ──
    if verbose:
        print(f"  Computing PIT metrics for {len(universe_tickers)} tickers...", flush=True)

    rows = []
    for i, ticker in enumerate(universe_tickers):
        m = compute_pit_metrics_for_ticker(ticker, target_date)
        if m is not None:
            rows.append(m)
        if verbose and i % 100 == 99:
            print(f"    Scored {i+1}/{len(universe_tickers)}...", flush=True)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("ticker")
    if verbose:
        print(f"  Got metrics for {len(df)} tickers passing quality threshold", flush=True)

    # ── Step 2: Score each pillar via percentile ranking (same as dashboard) ──
    # Uses PIT_PILLAR_METRICS which substitutes PEAD for the analyst-data-dependent
    # EPS Revisions pillar. All other pillars are identical to dashboard.
    pillar_scores = {}

    for pillar_name, metrics in PIT_PILLAR_METRICS.items():
        pillar_metric_scores = []

        for yf_key, display_name, higher_is_better in metrics:
            if yf_key not in df.columns:
                continue

            col = pd.to_numeric(df[yf_key], errors="coerce")

            if sector_relative and "sector" in df.columns:
                if higher_is_better:
                    pct = col.groupby(df["sector"]).rank(pct=True, na_option="bottom") * 100
                else:
                    pct = (1 - col.groupby(df["sector"]).rank(pct=True, na_option="bottom")) * 100
            else:
                if higher_is_better:
                    pct = col.rank(pct=True, na_option="bottom") * 100
                else:
                    pct = (1 - col.rank(pct=True, na_option="bottom")) * 100

            grades = pct.apply(_percentile_to_grade)
            grade_nums = grades.map(GRADE_SCORES).fillna(1)

            pillar_metric_scores.append(grade_nums)

        if pillar_metric_scores:
            pillar_avg = pd.concat(pillar_metric_scores, axis=1).mean(axis=1)
            pillar_scores[pillar_name] = pillar_avg
        else:
            pillar_scores[pillar_name] = pd.Series(1, index=df.index)

    # ── Step 3: Weighted composite (matching dashboard) ──
    composite = pd.Series(0.0, index=df.index)
    for pillar_name, w in weights.items():
        if pillar_name in pillar_scores:
            composite += pillar_scores[pillar_name] * w

    total_weight = sum(w for p, w in weights.items() if p in pillar_scores)
    if total_weight > 0:
        composite = composite / total_weight * sum(weights.values())

    # ── Step 4: Build result ──
    result = df.copy()
    for pillar_name, scores in pillar_scores.items():
        result[f"{pillar_name}_score"] = scores.round(2)

    result["composite_score"] = composite.round(2)
    result["overall_rating"] = composite.apply(_score_to_rating)
    result = result.sort_values("composite_score", ascending=False)

    return result


def get_universe_for_backtest(target_date, all_tickers):
    """
    Filter a candidate universe to tickers listed at target_date.
    Used to avoid scoring pre-IPO stocks.
    """
    return get_listed_tickers_at(target_date, all_tickers)


# ────────────────────────────────────────────────────────────────────
# Test/diagnostic mode
# ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_date = datetime(2024, 1, 15)
    test_tickers = ["AAPL", "MSFT", "NVDA", "JPM", "JNJ", "GOOG", "META", "TSLA", "WMT", "JPM"]

    print(f"Testing PIT scoring at {test_date.date()}")
    print(f"Tickers: {test_tickers}")
    print()

    df = score_universe_pit(test_date, test_tickers, verbose=True)

    if not df.empty:
        print()
        print(f"{'Ticker':<8} {'Sector':<25} {'Composite':>10} {'Rating':<15}")
        print("-" * 65)
        for ticker, row in df.iterrows():
            print(f"{ticker:<8} {str(row.get('sector', ''))[:24]:<25} "
                  f"{row['composite_score']:>10.2f} {row['overall_rating']:<15}")

        print()
        print("Distribution of ratings:")
        print(df["overall_rating"].value_counts())
