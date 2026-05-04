"""
Quant 5-Pillar Strategy Backtest
=================================

Validates the 5-pillar quant scoring system on 20 years of monthly checkpoints.

Methodology:
- Every first-of-month from Jan 2005 to today (~240 checkpoints)
- For each checkpoint:
  - Pull historical price + fundamentals as of that date
  - Compute the 5 pillars (where data available)
  - Take top 10 by composite score
  - Simulate buying weighted by score, holding 1 month
- Two exit strategies:
  1. Realistic: hold to next month-end close
  2. Theoretical Max: best close price during the month

Data quality reality:
- Momentum: 100% historical (price-based)
- Valuation: ~95% historical (yfinance has trailing EPS for most periods)
- Growth: ~70% reliable post-2015, sparse pre-2015
- Profitability: ~70% reliable post-2015, sparse pre-2015
- Financial Health: ~60% reliable post-2018, very sparse pre-2018

Each checkpoint includes a data_quality_score (0-100) showing how complete
the fundamentals were. Periods with low data quality should be interpreted
with skepticism.

Output: quant_backtest_results.json
"""

import os
import json
import sys
import time
import math
from datetime import datetime, timedelta, timezone

import yfinance as yf
import pandas as pd
import numpy as np


START_YEAR = int(os.environ.get("START_YEAR", "2005"))
HOLD_DAYS_TRADING = 21  # ~1 month of trading days
TOP_N_PICKS = 10
MAX_UNIVERSE_SIZE = 200  # Sample to keep runtime manageable
VARIANT_NAME = os.environ.get("VARIANT_NAME", "")
RESULTS_FILE = f"quant_backtest_results{('_' + VARIANT_NAME) if VARIANT_NAME else ''}.json"


def get_universe_tickers():
    """Load universe with multiple fallback strategies."""
    if os.path.exists("fundamentals_cache.json"):
        try:
            with open("fundamentals_cache.json") as f:
                cache = json.load(f)
                # Try wrapped format: {"tickers": {...}}
                if "tickers" in cache and isinstance(cache["tickers"], dict):
                    tickers = list(cache["tickers"].keys())
                    if tickers:
                        return tickers
                # Try flat format: {"AAPL": {...}, "MSFT": {...}}
                tickers = [k for k in cache.keys()
                           if isinstance(k, str) and k.isupper() and 1 <= len(k) <= 6]
                if tickers:
                    return tickers
        except Exception as e:
            print(f"WARNING: Failed to load fundamentals_cache.json: {e}", flush=True)

    if os.path.exists("data_cache/fundamentals_cache.json"):
        try:
            with open("data_cache/fundamentals_cache.json") as f:
                cache = json.load(f)
                if "tickers" in cache and isinstance(cache["tickers"], dict):
                    tickers = list(cache["tickers"].keys())
                    if tickers:
                        return tickers
                tickers = [k for k in cache.keys()
                           if isinstance(k, str) and k.isupper() and 1 <= len(k) <= 6]
                if tickers:
                    return tickers
        except Exception:
            pass

    # Fallback: hardcoded liquid universe
    print("WARNING: No fundamentals cache found, using hardcoded liquid universe", flush=True)
    return [
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "NVDA", "BRK-B", "UNH",
        "JPM", "JNJ", "V", "PG", "XOM", "MA", "HD", "CVX", "MRK", "LLY",
        "ABBV", "PEP", "KO", "AVGO", "WMT", "BAC", "PFE", "TMO", "COST", "DIS",
        "CSCO", "ABT", "MCD", "ACN", "ADBE", "DHR", "VZ", "WFC", "CRM", "TXN",
        "NFLX", "PM", "NEE", "RTX", "BMY", "QCOM", "AMD", "T", "HON", "UPS",
        "INTC", "ORCL", "LIN", "LOW", "AMGN", "IBM", "INTU", "GE", "CAT", "BA",
        "GS", "DE", "BLK", "MMM", "SPGI", "AMT", "AXP", "MDLZ", "PLD", "ISRG",
        "GILD", "SYK", "TJX", "MO", "CVS", "ZTS", "C", "ELV", "TMUS", "BKNG",
        "SO", "DUK", "ADI", "REGN", "VRTX", "LMT", "BDX", "PYPL", "TGT", "MS",
        "EOG", "CI", "AON", "EQIX", "CME", "PGR", "FISV", "USB", "PNC", "KLAC",
        "SHW", "PSA", "ITW", "BSX", "AEP", "FCX", "CSX", "WM", "DG", "ICE",
        "NSC", "EMR", "EW", "ROP", "GIS", "FDX", "MAR", "F", "HUM", "ETN",
        "AIG", "ECL", "TRV", "TFC", "ATVI", "AFL", "APD", "DLR", "PSX", "BIIB",
        "MET", "MNST", "AZO", "WELL", "WMB", "ALL", "MSCI", "MCK", "STZ", "TT",
        "JCI", "ADP", "DOW", "ROST", "FIS", "TEL", "AJG", "ORLY", "CTSH", "PRU",
        "ANET", "VLO", "CMG", "DD", "RSG", "CARR", "CRWD", "MRNA", "PXD",
        "PANW", "PAYX", "OXY", "EXC", "AIZ", "STT", "AME", "EBAY", "OTIS", "FAST",
        "NOC", "BKR", "AVB", "ED", "ARE", "MTD", "ETR", "AMP", "GLW", "BAX",
        "ZBH", "FTV",
    ]


def get_first_of_months(start_year=2005, end_year=None):
    if end_year is None:
        end_year = datetime.now().year
    dates = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            try:
                d = datetime(y, m, 1)
                if d > datetime.now() - timedelta(days=30):
                    break
                dates.append(d)
            except Exception:
                continue
    return dates


def fetch_price_history(ticker, start_date, end_date):
    """Get historical prices using parquet cache (fast) with yfinance fallback."""
    try:
        from price_cache import get_prices
        hist = get_prices(ticker, start_date, end_date)
        if hist is not None and not hist.empty:
            return hist
    except ImportError:
        pass

    # Fallback: hit yfinance directly
    try:
        t = yf.Ticker(ticker)
        hist = t.history(start=start_date, end=end_date, auto_adjust=False)
        if hist.empty:
            return None
        return hist
    except Exception:
        return None


def get_historical_fundamentals(ticker, target_date):
    """
    Get fundamentals as of target_date.

    Uses SEC EDGAR XBRL data for true point-in-time fundamentals.
    Falls back to yfinance only if EDGAR returns nothing (e.g., non-US listed).

    Returns dict with available metrics, plus quality_score (0-100)
    indicating how much data was available.
    """
    # Primary: EDGAR XBRL (true point-in-time, free, comprehensive 2009+)
    try:
        from edgar_fundamentals import get_fundamentals_at_date
        result = get_fundamentals_at_date(ticker, target_date)
        if result and result.get("data_quality_score", 0) >= 20:
            return result
    except Exception as e:
        print(f"  EDGAR fetch failed for {ticker}: {e}", flush=True)

    # Fallback: yfinance (less reliable for historical, but better than nothing)
    result = {
        "ticker": ticker,
        "as_of_date": target_date.strftime("%Y-%m-%d"),
        "data_quality_score": 0,
        "_source": "yfinance_fallback",
    }

    try:
        t = yf.Ticker(ticker)

        # ── Income statement (quarterly) ──
        try:
            income = t.quarterly_income_stmt
            if income is not None and not income.empty:
                cols_before = [c for c in income.columns
                               if hasattr(c, 'date') and c.date() <= target_date.date()]
                if cols_before:
                    most_recent = cols_before[0]
                    ttm_cols = cols_before[:4]

                    if "Total Revenue" in income.index:
                        revenues = [income.loc["Total Revenue", c]
                                   for c in ttm_cols if pd.notna(income.loc["Total Revenue", c])]
                        if revenues:
                            ttm_revenue = sum(revenues)
                            result["ttm_revenue"] = float(ttm_revenue)
                            result["data_quality_score"] += 20

                            if len(cols_before) >= 8:
                                prior_revenues = [income.loc["Total Revenue", c]
                                                 for c in cols_before[4:8]
                                                 if pd.notna(income.loc["Total Revenue", c])]
                                if prior_revenues:
                                    prior_ttm = sum(prior_revenues)
                                    if prior_ttm > 0:
                                        result["revenue_growth_yoy"] = ((ttm_revenue / prior_ttm) - 1) * 100
                                        result["data_quality_score"] += 15

                    if "Net Income" in income.index:
                        nis = [income.loc["Net Income", c]
                              for c in ttm_cols if pd.notna(income.loc["Net Income", c])]
                        if nis:
                            ttm_ni = sum(nis)
                            result["ttm_net_income"] = float(ttm_ni)
                            result["data_quality_score"] += 10

                    if "Operating Income" in income.index and "Total Revenue" in income.index:
                        op_inc = income.loc["Operating Income", most_recent]
                        rev = income.loc["Total Revenue", most_recent]
                        if pd.notna(op_inc) and pd.notna(rev) and rev > 0:
                            result["operating_margin"] = float(op_inc / rev) * 100
                            result["data_quality_score"] += 10
        except Exception:
            pass

        # ── Balance sheet ──
        try:
            balance = t.quarterly_balance_sheet
            if balance is not None and not balance.empty:
                cols_before = [c for c in balance.columns
                               if hasattr(c, 'date') and c.date() <= target_date.date()]
                if cols_before:
                    bs = cols_before[0]
                    if "Total Debt" in balance.index:
                        td = balance.loc["Total Debt", bs]
                        if pd.notna(td):
                            result["total_debt"] = float(td)
                            result["data_quality_score"] += 5
                    if "Stockholders Equity" in balance.index:
                        se = balance.loc["Stockholders Equity", bs]
                        if pd.notna(se) and se > 0:
                            result["stockholders_equity"] = float(se)
                            if "total_debt" in result:
                                result["debt_to_equity"] = result["total_debt"] / float(se)
                                result["data_quality_score"] += 10
                    if "Cash And Cash Equivalents" in balance.index:
                        cash = balance.loc["Cash And Cash Equivalents", bs]
                        if pd.notna(cash):
                            result["cash"] = float(cash)
                            result["data_quality_score"] += 5
        except Exception:
            pass

        # ── EPS for valuation ──
        try:
            if "ttm_net_income" in result:
                shares = t.info.get("sharesOutstanding")
                if shares and shares > 0:
                    result["ttm_eps"] = result["ttm_net_income"] / shares
                    result["data_quality_score"] += 5
        except Exception:
            pass

    except Exception:
        pass

    return result


def compute_quant_score_at_date(ticker, target_date, sector="Unknown"):
    """
    Compute composite quant score AS OF target_date.

    Returns dict with: composite_score (0-100), pillar_scores, data_quality_score
    """
    fundamentals = get_historical_fundamentals(ticker, target_date)
    quality = fundamentals.get("data_quality_score", 0)

    # ── Get price data ──
    start = (target_date - timedelta(days=365)).strftime("%Y-%m-%d")
    end = target_date.strftime("%Y-%m-%d")
    hist = fetch_price_history(ticker, start, end)

    if hist is None or len(hist) < 100:
        return None

    close = hist["Close"].astype(float)
    price = float(close.iloc[-1])

    pillars = {}

    # ── Pillar 1: Momentum (always computable from price) ──
    momentum_score = 0
    # 12-1 momentum (12 month return ex last month)
    if len(close) >= 252:
        ret_12_1 = ((close.iloc[-22] / close.iloc[-252]) - 1) * 100
        if ret_12_1 > 30:
            momentum_score = 90
        elif ret_12_1 > 15:
            momentum_score = 75
        elif ret_12_1 > 0:
            momentum_score = 50 + (ret_12_1 / 30) * 25
        elif ret_12_1 > -10:
            momentum_score = 35
        else:
            momentum_score = max(10, 35 + ret_12_1)
    elif len(close) >= 100:
        # Fallback: 6-month momentum
        ret_6m = ((price / close.iloc[max(0, len(close)-126)]) - 1) * 100
        momentum_score = max(10, min(90, 50 + ret_6m))
    pillars["momentum"] = momentum_score

    # ── Pillar 2: Valuation (P/E if available) ──
    valuation_score = 50  # Default neutral
    if "ttm_eps" in fundamentals and fundamentals["ttm_eps"] > 0:
        pe = price / fundamentals["ttm_eps"]
        if 0 < pe < 10:
            valuation_score = 90
        elif pe < 15:
            valuation_score = 80
        elif pe < 20:
            valuation_score = 60
        elif pe < 30:
            valuation_score = 40
        elif pe < 50:
            valuation_score = 20
        else:
            valuation_score = 10
        fundamentals["pe_ratio"] = pe
    pillars["valuation"] = valuation_score

    # ── Pillar 3: Growth (revenue growth) ──
    growth_score = 50  # Default
    if "revenue_growth_yoy" in fundamentals:
        g = fundamentals["revenue_growth_yoy"]
        if g > 30:
            growth_score = 95
        elif g > 20:
            growth_score = 85
        elif g > 10:
            growth_score = 70
        elif g > 5:
            growth_score = 55
        elif g > 0:
            growth_score = 45
        elif g > -10:
            growth_score = 25
        else:
            growth_score = 10
    pillars["growth"] = growth_score

    # ── Pillar 4: Profitability (operating margin) ──
    profitability_score = 50
    if "operating_margin" in fundamentals:
        m = fundamentals["operating_margin"]
        if m > 30:
            profitability_score = 95
        elif m > 20:
            profitability_score = 80
        elif m > 10:
            profitability_score = 65
        elif m > 5:
            profitability_score = 50
        elif m > 0:
            profitability_score = 35
        else:
            profitability_score = 15
    pillars["profitability"] = profitability_score

    # ── Pillar 5: Financial Health (debt-to-equity) ──
    fin_health_score = 50
    if "debt_to_equity" in fundamentals:
        de = fundamentals["debt_to_equity"]
        if de < 0.3:
            fin_health_score = 90
        elif de < 0.5:
            fin_health_score = 75
        elif de < 1.0:
            fin_health_score = 60
        elif de < 1.5:
            fin_health_score = 40
        elif de < 2.5:
            fin_health_score = 20
        else:
            fin_health_score = 10
    pillars["financial_health"] = fin_health_score

    # ── Composite (equal weighted) ──
    composite = sum(pillars.values()) / len(pillars)

    return {
        "ticker": ticker,
        "as_of_date": target_date.strftime("%Y-%m-%d"),
        "price": price,
        "composite_score": composite,
        "pillar_scores": pillars,
        "data_quality_score": quality,
        "fundamentals": fundamentals,
    }


def simulate_monthly_hold(ticker, entry_date, entry_price, hold_trading_days=21):
    """
    Simulate a 1-month hold of a stock.

    Returns dict with:
      - realistic_return_pct: end-of-period close
      - max_return_pct: best close during period
    """
    try:
        end_date = entry_date + timedelta(days=hold_trading_days + 10)
        hist = fetch_price_history(
            ticker,
            entry_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
        if hist is None or hist.empty:
            return None

        # Limit to hold_trading_days
        hist = hist.head(hold_trading_days)
        if hist.empty:
            return None

        close = hist["Close"].astype(float)

        # Realistic: end-of-period close
        end_price = float(close.iloc[-1])
        realistic_return = ((end_price - entry_price) / entry_price) * 100

        # Theoretical max: best close during period
        max_close = float(close.max())
        max_return = ((max_close - entry_price) / entry_price) * 100

        return {
            "realistic_return_pct": realistic_return,
            "max_return_pct": max_return,
            "entry_price": entry_price,
            "end_price": end_price,
            "max_close_during": max_close,
        }
    except Exception:
        return None


def fetch_spy_return(start_date, hold_trading_days=21):
    try:
        end_date = start_date + timedelta(days=hold_trading_days + 10)
        hist = fetch_price_history("SPY", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if hist is None or hist.empty or len(hist) < 2:
            return None
        hist = hist.head(hold_trading_days)
        entry = float(hist["Close"].iloc[0])
        exit_p = float(hist["Close"].iloc[-1])
        return ((exit_p - entry) / entry) * 100
    except Exception:
        return None


def run_monthly_quant_backtest(checkpoint_date, universe, top_n=10):
    """Run quant backtest for one checkpoint."""
    print(f"[{checkpoint_date.strftime('%Y-%m')}] Computing quant scores...", flush=True)

    sample = universe[:MAX_UNIVERSE_SIZE]

    candidates = []
    avg_quality = 0
    n_with_data = 0

    for i, ticker in enumerate(sample):
        result = compute_quant_score_at_date(ticker, checkpoint_date)
        if result and result["data_quality_score"] >= 20:  # Need at least some real data
            candidates.append(result)
            avg_quality += result["data_quality_score"]
            n_with_data += 1
        if i % 50 == 49:
            time.sleep(0.5)

    if not candidates:
        return {
            "date": checkpoint_date.strftime("%Y-%m-%d"),
            "n_candidates_screened": len(sample),
            "n_qualified": 0,
            "avg_data_quality": 0,
            "top_picks": [],
            "portfolio_return_realistic": None,
            "portfolio_return_max": None,
            "spy_return_pct": fetch_spy_return(checkpoint_date),
        }

    avg_quality = avg_quality / n_with_data if n_with_data else 0

    candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    top = candidates[:top_n]

    total_score = sum(c["composite_score"] for c in top)
    weights = [c["composite_score"] / total_score for c in top]

    realistic_returns = []
    max_returns = []
    detailed = []

    for c, w in zip(top, weights):
        sim = simulate_monthly_hold(c["ticker"], checkpoint_date, c["price"])
        if sim:
            realistic_returns.append(sim["realistic_return_pct"] * w)
            max_returns.append(sim["max_return_pct"] * w)
            detailed.append({
                "ticker": c["ticker"],
                "composite_score": c["composite_score"],
                "data_quality": c["data_quality_score"],
                "weight": w,
                "entry_price": c["price"],
                "realistic_return_pct": sim["realistic_return_pct"],
                "max_return_pct": sim["max_return_pct"],
                "pillar_scores": c["pillar_scores"],
            })

    return {
        "date": checkpoint_date.strftime("%Y-%m-%d"),
        "n_candidates_screened": len(sample),
        "n_qualified": len(candidates),
        "avg_data_quality": avg_quality,
        "top_picks": detailed,
        "portfolio_return_realistic": sum(realistic_returns) if realistic_returns else None,
        "portfolio_return_max": sum(max_returns) if max_returns else None,
        "spy_return_pct": fetch_spy_return(checkpoint_date),
    }


def aggregate_metrics(monthly_results):
    realistic_returns = [m["portfolio_return_realistic"] for m in monthly_results if m.get("portfolio_return_realistic") is not None]
    max_returns = [m["portfolio_return_max"] for m in monthly_results if m.get("portfolio_return_max") is not None]
    spy_returns = [m["spy_return_pct"] for m in monthly_results if m.get("spy_return_pct") is not None]

    def stats(returns):
        if not returns:
            return {}
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        return {
            "n_periods": len(returns),
            "win_rate_pct": (len(wins) / len(returns)) * 100 if returns else 0,
            "avg_return_pct": sum(returns) / len(returns) if returns else 0,
            "avg_win_pct": sum(wins) / len(wins) if wins else 0,
            "avg_loss_pct": sum(losses) / len(losses) if losses else 0,
            "best_period_pct": max(returns) if returns else 0,
            "worst_period_pct": min(returns) if returns else 0,
            "total_compounded_pct": (math.prod([1 + r/100 for r in returns]) - 1) * 100 if returns else 0,
        }

    # Average data quality across run
    qualities = [m.get("avg_data_quality", 0) for m in monthly_results]
    avg_data_quality = sum(qualities) / len(qualities) if qualities else 0

    return {
        "realistic_strategy": stats(realistic_returns),
        "theoretical_max_strategy": stats(max_returns),
        "spy_benchmark": stats(spy_returns),
        "avg_data_quality_across_run": avg_data_quality,
    }


def main():
    print(f"[{datetime.now().isoformat()}] Starting QUANT 5-pillar backtest", flush=True)

    universe = get_universe_tickers()
    if not universe:
        print("ERROR: No universe found", file=sys.stderr)
        sys.exit(1)
    print(f"Universe size: {len(universe)} tickers", flush=True)

    checkpoint_dates = get_first_of_months(start_year=START_YEAR)
    print(f"Backtesting {len(checkpoint_dates)} monthly checkpoints", flush=True)

    monthly_results = []
    for i, date in enumerate(checkpoint_dates):
        try:
            result = run_monthly_quant_backtest(date, universe, top_n=TOP_N_PICKS)
            monthly_results.append(result)
            real = result.get('portfolio_return_realistic')
            max_r = result.get('portfolio_return_max')
            spy = result.get('spy_return_pct')
            quality = result.get('avg_data_quality', 0)
            print(
                f"[{i+1}/{len(checkpoint_dates)}] {date.strftime('%Y-%m')}: "
                f"qualified={result['n_qualified']}, quality={quality:.0f}, "
                f"realistic={f'{real:+.2f}%' if real is not None else 'n/a'}, "
                f"max={f'{max_r:+.2f}%' if max_r is not None else 'n/a'}, "
                f"spy={f'{spy:+.2f}%' if spy is not None else 'n/a'}",
                flush=True
            )
        except Exception as e:
            print(f"[{i+1}] FAILED for {date}: {e}", file=sys.stderr, flush=True)
            continue

    aggregate = aggregate_metrics(monthly_results)

    output = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "start_year": START_YEAR,
            "hold_trading_days": HOLD_DAYS_TRADING,
            "top_n_picks": TOP_N_PICKS,
            "min_data_quality": 20,
            "max_universe_sample": MAX_UNIVERSE_SIZE,
        },
        "aggregate_metrics": aggregate,
        "monthly_results": monthly_results,
        "universe_size": len(universe),
        "n_checkpoints": len(monthly_results),
    }

    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n[{datetime.now().isoformat()}] Wrote {RESULTS_FILE}", flush=True)
    print(json.dumps(aggregate, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
