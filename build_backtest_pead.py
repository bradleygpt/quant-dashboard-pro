"""
PEAD (Post-Earnings-Announcement Drift) Backtest
==================================================

Tests the most documented anomaly in finance: stocks that beat earnings
estimates continue to drift up for weeks after the announcement.

Strategy:
  - Each month, find all stocks that reported earnings in past 7 days
  - Filter to those that BEAT estimates by >5% (positive surprise)
  - Equal-weight portfolio of top N by surprise magnitude
  - Hold 21 trading days
  - Rebalance monthly

Reference: Ball & Brown (1968), Bernard & Thomas (1989)

Note: Modern PEAD has decayed in liquid mega-caps due to arbitrage.
Edge may persist in less-liquid mid-caps.

Data source: EDGAR fundamentals to compare actual vs prior period
(we don't have analyst estimates historical, so we use YoY EPS growth
as a proxy for "earnings surprise" - if Q-on-Q is much better than the
seasonal pattern would predict, that's a positive surprise).
"""

import os
import sys
import json
import time
import warnings
from datetime import datetime, timedelta, date, timezone

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

VARIANT_NAME = os.environ.get("VARIANT_NAME", "pead")
START_YEAR = int(os.environ.get("START_YEAR", "2010"))  # PEAD strongest pre-2015
TRAIN_END_YEAR = int(os.environ.get("TRAIN_END_YEAR", "2019"))
TOP_N = int(os.environ.get("TOP_N", "20"))
HOLD_DAYS = int(os.environ.get("HOLD_DAYS", "21"))
MIN_SURPRISE_PCT = float(os.environ.get("MIN_SURPRISE_PCT", "5.0"))
MAX_UNIVERSE_SIZE = int(os.environ.get("MAX_UNIVERSE_SIZE", "500"))

OUTPUT_FILE = f"backtest_variant_{VARIANT_NAME}.json"


def get_universe_tickers():
    if os.path.exists("fundamentals_cache.json"):
        try:
            with open("fundamentals_cache.json") as f:
                cache = json.load(f)
                if "tickers" in cache and isinstance(cache["tickers"], dict):
                    return list(cache["tickers"].keys())
                tickers = [k for k in cache.keys()
                           if isinstance(k, str) and k.isupper() and 1 <= len(k) <= 6]
                if tickers:
                    return tickers
        except Exception:
            pass
    return ["AAPL", "MSFT", "GOOGL"]


def get_first_of_months(start_year=2010, end_year=None):
    if end_year is None:
        end_year = datetime.now().year
    dates = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            d = date(y, m, 1)
            if d <= datetime.now().date():
                dates.append(d)
    return dates


def fetch_historical_prices(ticker, start_date, end_date):
    try:
        from price_cache import get_prices
        hist = get_prices(ticker, start_date, end_date)
        if hist is not None and not hist.empty:
            return hist
    except ImportError:
        pass

    try:
        import yfinance as yf
        df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


def get_earnings_surprise_proxy(ticker, target_date):
    """
    Compute earnings surprise proxy from EDGAR data.

    Without historical analyst estimates, we use:
    - Most recent quarterly EPS vs same quarter prior year
    - Greater YoY growth = more positive surprise (for stocks with established
      analyst consensus that anchors near YoY)

    Returns:
      - surprise_pct: YoY EPS growth as proxy for surprise
      - filing_date: when the data was filed (for timing entry)
      - None if data not available or filing too old
    """
    try:
        from edgar_fundamentals import (
            fetch_companyfacts, get_cik_for_ticker, CONCEPT_MAPPING
        )

        cik = get_cik_for_ticker(ticker)
        if not cik:
            return None

        facts = fetch_companyfacts(ticker, cik)
        if not facts:
            return None

        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        if not us_gaap:
            return None

        target_dt = target_date if isinstance(target_date, date) else target_date.date()

        # Look at NetIncomeLoss filings - find most recent quarterly
        for tag in CONCEPT_MAPPING["net_income"]:
            if tag not in us_gaap:
                continue
            entries = us_gaap[tag].get("units", {}).get("USD", [])

            # Find quarterly filings (90-day periods) that were filed BEFORE target_dt
            valid = []
            for entry in entries:
                try:
                    end_str = entry.get("end")
                    start_str = entry.get("start")
                    filed_str = entry.get("filed")
                    val = entry.get("val")
                    if not all([end_str, start_str, filed_str]) or val is None:
                        continue

                    end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
                    start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
                    filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()

                    if filed_dt > target_dt:
                        continue
                    period_days = (end_dt - start_dt).days
                    if 80 <= period_days <= 100:
                        valid.append({
                            "end": end_dt,
                            "filed": filed_dt,
                            "val": val,
                        })
                except Exception:
                    continue

            if not valid:
                continue

            # Sort by filing date descending
            valid.sort(key=lambda x: x["filed"], reverse=True)

            # Most recent quarter
            recent = valid[0]

            # Look for same quarter prior year (~4 quarters back)
            target_prior_end = recent["end"].replace(year=recent["end"].year - 1)
            prior_year_match = None
            for v in valid:
                # Same quarter prior year (within 30 days tolerance)
                if abs((v["end"] - target_prior_end).days) < 30:
                    prior_year_match = v
                    break

            if prior_year_match is None:
                continue

            recent_ni = recent["val"]
            prior_ni = prior_year_match["val"]

            if prior_ni == 0 or prior_ni is None:
                continue

            # YoY growth as surprise proxy
            surprise = ((recent_ni - prior_ni) / abs(prior_ni)) * 100

            # Days since filing (for timing - we want recent filings)
            days_since_filing = (target_dt - recent["filed"]).days

            return {
                "surprise_pct": surprise,
                "filed_date": recent["filed"],
                "days_since_filing": days_since_filing,
                "recent_ni": recent_ni,
                "prior_ni": prior_ni,
            }

        return None
    except Exception:
        return None


def simulate_hold(ticker, entry_date, hold_days):
    try:
        end_date = entry_date + timedelta(days=hold_days + 7)
        hist = fetch_historical_prices(
            ticker,
            entry_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
        if hist is None or len(hist) < 2:
            return None
        hist = hist.head(hold_days)
        if len(hist) < 2:
            return None

        entry_price = float(hist["Close"].iloc[0])
        exit_price = float(hist["Close"].iloc[-1])
        if entry_price <= 0:
            return None
        return ((exit_price - entry_price) / entry_price) * 100
    except Exception:
        return None


def fetch_spy_return(start_date, hold_days):
    return simulate_hold("SPY", start_date, hold_days)


def run_monthly_backtest(checkpoint_date, universe, top_n, hold_days, min_surprise):
    """Find recent earnings beats, buy top N, hold."""

    base = {
        "date": checkpoint_date.strftime("%Y-%m-%d"),
        "n_qualified": 0,
        "top_picks": [],
        "portfolio_return": None,
        "spy_return_pct": None,
    }

    candidates = []

    for ticker in universe:
        surprise_data = get_earnings_surprise_proxy(ticker, checkpoint_date)
        if surprise_data is None:
            continue

        # Only consider recent filings (within 30 days)
        if surprise_data["days_since_filing"] > 30:
            continue

        # Positive surprise threshold
        if surprise_data["surprise_pct"] < min_surprise:
            continue

        # Liquidity filter via market cap
        try:
            from edgar_fundamentals import get_fundamentals_at_date
            fundies = get_fundamentals_at_date(ticker, checkpoint_date)
            shares = fundies.get("shares_outstanding") if fundies else None
            if shares is None or shares <= 0:
                continue

            start = (checkpoint_date - timedelta(days=10)).strftime("%Y-%m-%d")
            end = checkpoint_date.strftime("%Y-%m-%d")
            hist = fetch_historical_prices(ticker, start, end)
            if hist is None or hist.empty:
                continue
            price = float(hist["Close"].iloc[-1])
            mcap = price * shares
            if mcap < 1e9:  # > $1B market cap
                continue
        except Exception:
            continue

        candidates.append({
            "ticker": ticker,
            "surprise_pct": surprise_data["surprise_pct"],
            "days_since_filing": surprise_data["days_since_filing"],
            "market_cap": mcap,
        })

    base["n_qualified"] = len(candidates)

    if len(candidates) < 5:
        # Not enough beats this month
        base["spy_return_pct"] = fetch_spy_return(checkpoint_date, hold_days)
        return base

    # Sort by surprise magnitude descending, take top N
    candidates.sort(key=lambda x: x["surprise_pct"], reverse=True)
    top = candidates[:top_n]

    weight = 1.0 / len(top)
    rets = []
    detailed = []

    for c in top:
        r = simulate_hold(c["ticker"], checkpoint_date, hold_days)
        if r is not None:
            rets.append(r * weight)
            detailed.append({
                "ticker": c["ticker"],
                "surprise_pct": c["surprise_pct"],
                "weight": weight,
                "return_pct": r,
            })

    if rets:
        base["portfolio_return"] = sum(rets)
    base["top_picks"] = detailed
    base["spy_return_pct"] = fetch_spy_return(checkpoint_date, hold_days)

    return base


def aggregate_metrics(monthly_results):
    valid = [m for m in monthly_results if m.get("portfolio_return") is not None]
    if not valid:
        return {"n_periods": len(monthly_results), "n_valid": 0}

    returns = [m["portfolio_return"] for m in valid]

    cum = 1.0
    cum_spy = 1.0
    for m in monthly_results:
        if m.get("portfolio_return") is not None:
            cum *= (1 + m["portfolio_return"] / 100)
        if m.get("spy_return_pct") is not None:
            cum_spy *= (1 + m["spy_return_pct"] / 100)

    n_total = len(monthly_results)
    years = n_total / 12

    wins = [r for r in returns if r > 0]
    win_rate = (len(wins) / len(returns)) * 100 if returns else 0

    peak = 1.0
    max_dd = 0.0
    cur = 1.0
    for m in monthly_results:
        if m.get("portfolio_return") is not None:
            cur *= (1 + m["portfolio_return"] / 100)
        if cur > peak:
            peak = cur
        dd = (cur - peak) / peak
        if dd < max_dd:
            max_dd = dd

    annualized = (cum ** (1/years) - 1) * 100 if years > 0 else 0
    spy_annualized = (cum_spy ** (1/years) - 1) * 100 if years > 0 and cum_spy > 0 else 0

    return {
        "n_periods": n_total,
        "n_valid": len(valid),
        "win_rate_pct": round(win_rate, 2),
        "avg_return_pct": round(sum(returns)/len(returns), 3),
        "compounded_pct": round((cum - 1)*100, 2),
        "compounded_spy_pct": round((cum_spy - 1)*100, 2),
        "annualized_pct": round(annualized, 2),
        "spy_annualized_pct": round(spy_annualized, 2),
        "edge_vs_spy_annualized": round(annualized - spy_annualized, 2),
        "max_drawdown_pct": round(max_dd*100, 2),
    }


def split_train_holdout(monthly_results, train_end_year):
    train = [m for m in monthly_results if int(m["date"][:4]) <= train_end_year]
    holdout = [m for m in monthly_results if int(m["date"][:4]) > train_end_year]
    return train, holdout


def main():
    print(f"PEAD Backtest: {VARIANT_NAME}", flush=True)
    print(f"Min surprise: {MIN_SURPRISE_PCT}%, Top N: {TOP_N}, Hold: {HOLD_DAYS} days", flush=True)
    print(flush=True)

    universe = get_universe_tickers()[:MAX_UNIVERSE_SIZE]
    print(f"Universe: {len(universe)} tickers", flush=True)

    checkpoints = get_first_of_months(start_year=START_YEAR)
    print(f"Checkpoints: {len(checkpoints)}", flush=True)

    monthly_results = []
    for i, cp in enumerate(checkpoints):
        result = run_monthly_backtest(cp, universe, TOP_N, HOLD_DAYS, MIN_SURPRISE_PCT)
        monthly_results.append(result)

        nq = result.get("n_qualified", 0)
        ret = result.get("portfolio_return")
        spy = result.get("spy_return_pct")
        ret_str = f"{ret:+.2f}%" if ret is not None else "n/a"
        spy_str = f"{spy:+.2f}%" if spy is not None else "n/a"
        print(f"[{i+1}/{len(checkpoints)}] {cp}: beats={nq}, ret={ret_str}, spy={spy_str}", flush=True)

    train, holdout = split_train_holdout(monthly_results, TRAIN_END_YEAR)

    output = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "variant_name": VARIANT_NAME,
        "parameters": {
            "min_surprise_pct": MIN_SURPRISE_PCT,
            "top_n": TOP_N,
            "hold_days": HOLD_DAYS,
            "max_universe": MAX_UNIVERSE_SIZE,
            "train_end_year": TRAIN_END_YEAR,
            "start_year": START_YEAR,
        },
        "aggregate_full": aggregate_metrics(monthly_results),
        "aggregate_train": aggregate_metrics(train),
        "aggregate_holdout": aggregate_metrics(holdout),
        "monthly_results": monthly_results,
        "n_train_periods": len(train),
        "n_holdout_periods": len(holdout),
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, default=str, indent=2)

    print(flush=True)
    print(f"Wrote {OUTPUT_FILE}", flush=True)

    full = output["aggregate_full"]
    print()
    print("=" * 70)
    print("FULL PERIOD SUMMARY")
    print("=" * 70)
    print(f"Compounded: {full.get('compounded_pct')}% vs SPY {full.get('compounded_spy_pct')}%")
    print(f"Annualized: {full.get('annualized_pct')}% vs SPY {full.get('spy_annualized_pct')}%")
    print(f"Edge: {full.get('edge_vs_spy_annualized')}%")
    print(f"Win rate: {full.get('win_rate_pct')}%")
    print(f"Max drawdown: {full.get('max_drawdown_pct')}%")


if __name__ == "__main__":
    main()
