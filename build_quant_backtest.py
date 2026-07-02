"""
Quant 5-Pillar Strategy Backtest
=================================

Validates the 5-pillar quant scoring system on monthly/quarterly checkpoints and
emits per-preset headline metrics (equal / m_heavy / v_heavy from config.WEIGHT_PRESETS).

2026-07-02 rebuild — why the defaults changed:
- START_YEAR default is now 2011 (was 2005). The point-in-time fundamentals source
  (EDGAR XBRL cache) has effectively no coverage before ~2010 (AAPL probe: quality 0
  at 2005-06 AND 2009-06; 85 by 2012-06), and the yfinance fallback both lacks
  pre-~2020 quarterly statements and costs ~2s/ticker vs ~60ms cached. A 2005 start
  therefore burned ~45min per checkpoint on years that could never qualify, tripping
  the runtime-projection bail after ~6 checkpoints with 0 populated — which is exactly
  what the bake's sanity floor then (correctly) rejected. 2011+ is also the window the
  dashboard leads with (survivorship-clean framing).
- CHECKPOINT_FREQ default is now quarterly with HOLD_DAYS=63 and TOP_N=25 — the
  validated record's own convention ("TOP-25 quarterly rebalance").
- Pillar scoring itself is UNCHANGED (same thresholds, same point-in-time reads,
  entry at the last close <= checkpoint date). No lookahead was introduced: presets
  only re-WEIGHT the same as-of pillar scores at selection time.
- Preset composites weight the four app pillars with a point-in-time source
  (Valuation/Growth/Profitability/Momentum), renormalized: "EPS Revisions" has no
  historical point-in-time source and is dropped from every preset (m_heavy and
  v_heavy already weight it 0); the builder's fifth pillar (financial_health) is not
  an app preset pillar and is excluded from preset composites (still computed and
  reported per pick).

Output: quant_backtest_results.json
  monthly_results[]  — legacy schema (headline preset = "equal") for bake.py's
                       floor/curve logic, unchanged.
  presets{}          — per-preset headline CAGR/Sharpe/MaxDD/win-rate + per-checkpoint
                       returns (the source for meta.presets provenance="recomputed").
"""

import os
import json
import sys
import time
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import yfinance as yf
import pandas as pd
import numpy as np

# Speed only: memoize the EDGAR companyfacts JSON parse per ticker so ~60ms/call
# becomes ~0 across the (tickers x checkpoints) grid. Same bytes, same data.
try:
    import edgar_fundamentals as _edgar
    if not getattr(_edgar.fetch_companyfacts, "__wrapped__", None):
        _edgar.fetch_companyfacts = lru_cache(maxsize=4096)(_edgar.fetch_companyfacts)
except Exception:
    pass

START_YEAR = int(os.environ.get("START_YEAR", "2011"))
HOLD_DAYS_TRADING = int(os.environ.get("HOLD_DAYS", "63"))  # 63 = quarterly, 21 = monthly
TOP_N_PICKS = int(os.environ.get("TOP_N", "25"))  # 25 = the validated TOP-25 record
MAX_UNIVERSE_SIZE = int(os.environ.get("MAX_UNIVERSE_SIZE", "2000"))
VARIANT_NAME = os.environ.get("VARIANT_NAME", "")
RESULTS_FILE = f"quant_backtest_results{('_' + VARIANT_NAME) if VARIANT_NAME else ''}.json"

# Presets recomputed per run. Weights come from config.WEIGHT_PRESETS; only the four
# pillars with a point-in-time historical source participate (renormalized).
PRESET_KEYS = ["equal", "m_heavy", "v_heavy"]
APP_TO_BUILDER_PILLAR = {
    "Valuation": "valuation",
    "Growth": "growth",
    "Profitability": "profitability",
    "Momentum": "momentum",
}


def load_preset_weights():
    """{preset: {builder_pillar: weight}} — renormalized over the 4 available pillars."""
    try:
        from config import WEIGHT_PRESETS
    except Exception as e:
        print(f"WARNING: config.WEIGHT_PRESETS unavailable ({e}); using equal-only", flush=True)
        return {"equal": {p: 0.25 for p in APP_TO_BUILDER_PILLAR.values()}}
    out = {}
    for key in PRESET_KEYS:
        preset = WEIGHT_PRESETS.get(key)
        if not preset:
            continue
        w = {APP_TO_BUILDER_PILLAR[a]: float(preset["weights"].get(a, 0.0))
             for a in APP_TO_BUILDER_PILLAR}
        tot = sum(w.values())
        if tot <= 0:
            continue
        out[key] = {p: v / tot for p, v in w.items()}
    return out


def get_universe_tickers():
    """Load universe with multiple fallback strategies."""
    for path in ("fundamentals_cache.json", "data_cache/fundamentals_cache.json"):
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                cache = json.load(f)
            if "tickers" in cache and isinstance(cache["tickers"], dict):
                tickers = list(cache["tickers"].keys())
                if tickers:
                    return tickers
            tickers = [k for k in cache.keys()
                       if isinstance(k, str) and k.isupper() and 1 <= len(k) <= 6]
            if tickers:
                return tickers
        except Exception as e:
            print(f"WARNING: Failed to load {path}: {e}", flush=True)
    print("WARNING: No fundamentals cache found — universe unavailable", flush=True)
    return []


def get_first_of_months(start_year=2011, end_year=None):
    if end_year is None:
        end_year = datetime.now().year
    checkpoint_freq = os.environ.get("CHECKPOINT_FREQ", "quarterly").lower()
    months = [1, 4, 7, 10] if checkpoint_freq == "quarterly" else list(range(1, 13))
    dates = []
    for y in range(start_year, end_year + 1):
        for m in months:
            d = datetime(y, m, 1)
            if d > datetime.now() - timedelta(days=30):
                break
            dates.append(d)
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
    Fundamentals as of target_date. Primary: SEC EDGAR XBRL (true point-in-time).
    Fallback: yfinance quarterly statements filtered to columns <= target_date
    (only useful for recent dates; kept for the tail).
    """
    try:
        from edgar_fundamentals import get_fundamentals_at_date
        result = get_fundamentals_at_date(ticker, target_date)
        if result and result.get("data_quality_score", 0) >= 20:
            return result
    except Exception as e:
        print(f"  EDGAR fetch failed for {ticker}: {e}", flush=True)

    result = {
        "ticker": ticker,
        "as_of_date": target_date.strftime("%Y-%m-%d"),
        "data_quality_score": 0,
        "_source": "yfinance_fallback",
    }
    # yfinance quarterly statements reach back only a few years — skip the network
    # round-trips entirely for older checkpoints (they can never qualify).
    if target_date < datetime.now() - timedelta(days=5 * 365):
        return result

    try:
        t = yf.Ticker(ticker)
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
                            result["ttm_net_income"] = float(sum(nis))
                            result["data_quality_score"] += 10
                    if "Operating Income" in income.index and "Total Revenue" in income.index:
                        op_inc = income.loc["Operating Income", most_recent]
                        rev = income.loc["Total Revenue", most_recent]
                        if pd.notna(op_inc) and pd.notna(rev) and rev > 0:
                            result["operating_margin"] = float(op_inc / rev) * 100
                            result["data_quality_score"] += 10
        except Exception:
            pass
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
    Pillar scores AS OF target_date — thresholds unchanged from the original builder.
    Returns dict with pillar_scores, composite_score (legacy equal-5), price, quality.
    """
    fundamentals = get_historical_fundamentals(ticker, target_date)
    quality = fundamentals.get("data_quality_score", 0)

    start = (target_date - timedelta(days=365)).strftime("%Y-%m-%d")
    end = target_date.strftime("%Y-%m-%d")
    hist = fetch_price_history(ticker, start, end)
    if hist is None or len(hist) < 100:
        return None

    close = hist["Close"].astype(float)
    price = float(close.iloc[-1])
    pillars = {}

    momentum_score = 0
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
        ret_6m = ((price / close.iloc[max(0, len(close) - 126)]) - 1) * 100
        momentum_score = max(10, min(90, 50 + ret_6m))
    pillars["momentum"] = momentum_score

    valuation_score = 50
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

    growth_score = 50
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

    composite = sum(pillars.values()) / len(pillars)
    return {
        "ticker": ticker,
        "as_of_date": target_date.strftime("%Y-%m-%d"),
        "price": price,
        "composite_score": composite,
        "pillar_scores": pillars,
        "data_quality_score": quality,
    }


def preset_composite(pillars, weights):
    """Preset-weighted composite over the four app pillars (weights pre-renormalized)."""
    return sum(pillars.get(p, 50) * w for p, w in weights.items())


def simulate_monthly_hold(ticker, entry_date, entry_price, hold_trading_days=63):
    try:
        end_date = entry_date + timedelta(days=int(hold_trading_days * 1.6) + 10)
        hist = fetch_price_history(ticker, entry_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if hist is None or hist.empty:
            return None
        hist = hist.head(hold_trading_days)
        if hist.empty:
            return None
        close = hist["Close"].astype(float)
        end_price = float(close.iloc[-1])
        max_close = float(close.max())
        return {
            "realistic_return_pct": ((end_price - entry_price) / entry_price) * 100,
            "max_return_pct": ((max_close - entry_price) / entry_price) * 100,
            "entry_price": entry_price,
            "end_price": end_price,
            "max_close_during": max_close,
        }
    except Exception:
        return None


def fetch_spy_return(start_date, hold_trading_days=63):
    try:
        end_date = start_date + timedelta(days=int(hold_trading_days * 1.6) + 10)
        hist = fetch_price_history("SPY", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if hist is None or hist.empty or len(hist) < 2:
            return None
        hist = hist.head(hold_trading_days)
        entry = float(hist["Close"].iloc[0])
        exit_p = float(hist["Close"].iloc[-1])
        return ((exit_p - entry) / entry) * 100
    except Exception:
        return None


def run_checkpoint(checkpoint_date, universe, preset_weights, top_n=25):
    """Score ONCE, then derive every preset's basket + returns from the same
    as-of pillar table (presets never re-read data — no lookahead surface)."""
    sample = universe[:MAX_UNIVERSE_SIZE]
    try:
        from price_cache import get_listed_tickers_at
        listed = get_listed_tickers_at(checkpoint_date, sample)
        if len(listed) < len(sample):
            print(f"  Filtered to {len(listed)} listed tickers (skipped {len(sample) - len(listed)} pre-IPO)", flush=True)
        sample = listed
    except ImportError:
        pass

    candidates = []
    for i, ticker in enumerate(sample):
        result = compute_quant_score_at_date(ticker, checkpoint_date)
        if result and result["data_quality_score"] >= 20:
            candidates.append(result)
        if i % 200 == 199:
            time.sleep(0.2)

    spy_ret = fetch_spy_return(checkpoint_date, hold_trading_days=HOLD_DAYS_TRADING)
    base = {
        "date": checkpoint_date.strftime("%Y-%m-%d"),
        "n_candidates_screened": len(sample),
        "n_qualified": len(candidates),
        "avg_data_quality": (sum(c["data_quality_score"] for c in candidates) / len(candidates)) if candidates else 0,
        "spy_return_pct": spy_ret,
    }
    if not candidates:
        base.update({"top_picks": [], "portfolio_return_realistic": None,
                     "portfolio_return_max": None, "preset_returns": {}})
        return base

    sims = {}  # per-ticker hold simulation, shared across presets

    def sim_for(c):
        if c["ticker"] not in sims:
            sims[c["ticker"]] = simulate_monthly_hold(
                c["ticker"], checkpoint_date, c["price"], hold_trading_days=HOLD_DAYS_TRADING)
        return sims[c["ticker"]]

    preset_returns = {}
    headline_detail = []
    for pname, weights in preset_weights.items():
        ranked = sorted(candidates, key=lambda c: preset_composite(c["pillar_scores"], weights), reverse=True)
        top = ranked[:top_n]
        # equal weight within the basket — the validated record's construction
        rets_real, rets_max, n_simmed = [], [], 0
        for c in top:
            sim = sim_for(c)
            if sim:
                rets_real.append(sim["realistic_return_pct"])
                rets_max.append(sim["max_return_pct"])
                n_simmed += 1
                if pname == "equal" and len(headline_detail) < top_n:
                    headline_detail.append({
                        "ticker": c["ticker"],
                        "composite_score": preset_composite(c["pillar_scores"], weights),
                        "data_quality": c["data_quality_score"],
                        "weight": 1.0 / len(top),
                        "entry_price": c["price"],
                        "realistic_return_pct": sim["realistic_return_pct"],
                        "max_return_pct": sim["max_return_pct"],
                        "pillar_scores": c["pillar_scores"],
                    })
        preset_returns[pname] = {
            "realistic": (sum(rets_real) / len(rets_real)) if rets_real else None,
            "max": (sum(rets_max) / len(rets_max)) if rets_max else None,
            "n_picks": len(top), "n_simulated": n_simmed,
        }

    eq = preset_returns.get("equal") or {}
    base.update({
        "top_picks": headline_detail,
        "portfolio_return_realistic": eq.get("realistic"),
        "portfolio_return_max": eq.get("max"),
        "preset_returns": preset_returns,
    })
    return base


def preset_headline(returns, periods_per_year):
    rets = [r for r in returns if r is not None]
    if len(rets) < 2:
        return None
    growth = [1 + r / 100 for r in rets]
    total = math.prod(growth)
    n = len(rets)
    cagr = (total ** (periods_per_year / n) - 1) * 100
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    sharpe = (mean / math.sqrt(var)) * math.sqrt(periods_per_year) if var > 0 else None
    eq, peak, max_dd = 1.0, 1.0, 0.0
    for g in growth:
        eq *= g
        peak = max(peak, eq)
        max_dd = min(max_dd, (eq / peak - 1) * 100)
    wins = sum(1 for r in rets if r > 0)
    return {
        "cagr_pct": round(cagr, 2),
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "max_dd_pct": round(max_dd, 2),
        "win_rate_pct": round(100 * wins / n, 1),
        "n_periods": n,
        "total_compounded_pct": round((total - 1) * 100, 1),
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
            "win_rate_pct": (len(wins) / len(returns)) * 100,
            "avg_return_pct": sum(returns) / len(returns),
            "avg_win_pct": sum(wins) / len(wins) if wins else 0,
            "avg_loss_pct": sum(losses) / len(losses) if losses else 0,
            "best_period_pct": max(returns),
            "worst_period_pct": min(returns),
            "total_compounded_pct": (math.prod([1 + r / 100 for r in returns]) - 1) * 100,
        }

    qualities = [m.get("avg_data_quality", 0) for m in monthly_results]
    return {
        "realistic_strategy": stats(realistic_returns),
        "theoretical_max_strategy": stats(max_returns),
        "spy_benchmark": stats(spy_returns),
        "avg_data_quality_across_run": (sum(qualities) / len(qualities)) if qualities else 0,
    }


def main():
    print(f"[{datetime.now().isoformat()}] Starting QUANT 5-pillar backtest (per-preset)", flush=True)

    universe = get_universe_tickers()
    if not universe:
        print("ERROR: No universe found", file=sys.stderr)
        sys.exit(1)
    preset_weights = load_preset_weights()
    checkpoint_freq = os.environ.get("CHECKPOINT_FREQ", "quarterly").lower()
    periods_per_year = 4 if checkpoint_freq == "quarterly" else 12
    checkpoint_dates = get_first_of_months(start_year=START_YEAR)
    print(f"Universe: {len(universe)} tickers | presets: {list(preset_weights)} | "
          f"{len(checkpoint_dates)} {checkpoint_freq} checkpoints from {START_YEAR}, "
          f"hold={HOLD_DAYS_TRADING}d, top_n={TOP_N_PICKS}", flush=True)

    start_time = time.time()
    monthly_results = []
    for i, date in enumerate(checkpoint_dates):
        try:
            result = run_checkpoint(date, universe, preset_weights, top_n=TOP_N_PICKS)
            monthly_results.append(result)
            real = result.get("portfolio_return_realistic")
            spy = result.get("spy_return_pct")
            elapsed = time.time() - start_time
            avg_per_checkpoint = elapsed / (i + 1)
            eta_remaining = avg_per_checkpoint * (len(checkpoint_dates) - i - 1)
            print(
                f"[{i + 1}/{len(checkpoint_dates)}] {date.strftime('%Y-%m')}: "
                f"qualified={result['n_qualified']}, quality={result.get('avg_data_quality', 0):.0f}, "
                f"equal={f'{real:+.2f}%' if real is not None else 'n/a'}, "
                f"spy={f'{spy:+.2f}%' if spy is not None else 'n/a'} "
                f"(elapsed: {elapsed / 60:.1f}min, eta: {eta_remaining / 60:.1f}min)",
                flush=True,
            )
            _timeout_sec = int(os.environ.get("BACKTEST_TIMEOUT_SEC", "19800"))
            if i >= 5 and avg_per_checkpoint * len(checkpoint_dates) > _timeout_sec:
                print(f"\nWARNING: projected runtime exceeds {_timeout_sec / 60:.0f}min safety margin — saving partial results", flush=True)
                break
        except Exception as e:
            print(f"[{i + 1}] FAILED for {date}: {e}", file=sys.stderr, flush=True)
            continue

    aggregate = aggregate_metrics(monthly_results)

    presets_out = {}
    try:
        from config import WEIGHT_PRESETS as _WP
    except Exception:
        _WP = {}
    for pname, weights in preset_weights.items():
        series = [(m.get("preset_returns") or {}).get(pname, {}).get("realistic") for m in monthly_results]
        head = preset_headline(series, periods_per_year)
        if head:
            presets_out[pname] = {
                "label": (_WP.get(pname) or {}).get("label", pname),
                "weights_used": weights,
                "headline": head,
                "checkpoint_returns_pct": [None if r is None else round(r, 4) for r in series],
            }

    output = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "strategy_label": f"TOP-{TOP_N_PICKS} equal-weight · {checkpoint_freq} rebalance · {START_YEAR}+ (EDGAR point-in-time era)",
        "source": "build_quant_backtest.py (per-preset rebuild 2026-07-02)",
        "parameters": {
            "start_year": START_YEAR,
            "hold_trading_days": HOLD_DAYS_TRADING,
            "top_n_picks": TOP_N_PICKS,
            "checkpoint_freq": checkpoint_freq,
            "min_data_quality": 20,
            "max_universe_sample": MAX_UNIVERSE_SIZE,
            "presets": list(preset_weights),
        },
        "aggregate_metrics": aggregate,
        "presets": presets_out,
        "monthly_results": monthly_results,
        "universe_size": len(universe),
        "n_checkpoints": len(monthly_results),
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n[{datetime.now().isoformat()}] Wrote {RESULTS_FILE}", flush=True)
    for pname, p in presets_out.items():
        h = p["headline"]
        print(f"  {pname:10s} CAGR {h['cagr_pct']:+.2f}%  Sharpe {h['sharpe']}  MaxDD {h['max_dd_pct']}%  "
              f"win {h['win_rate_pct']}%  n={h['n_periods']}", flush=True)


if __name__ == "__main__":
    main()
