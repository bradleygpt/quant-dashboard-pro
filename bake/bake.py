"""Build-time bake: run the repo's real scoring pipeline and emit static JSON
for the React app. Source of truth = scoring.py / fairvalue.py / buy_point.py.

Run from anywhere: `python bake/bake.py`. Writes directly into
web/public/data/. Outputs:
  universe_floor{0,1,10}.json  lean rows for tables (pillar scores/grades, raw
                               metrics, FV/QBP composite, currentPrice, sector)
  detail_floor{0,1,10}.json    per-ticker: full FV dict, full QBP dict,
                               pillar_detail, + sector_stats for the floor
  prices.json                  per-ticker recent daily close (floor-independent)
  meta.json                    presets, thresholds, backtest stats, colors,
                               grade maps, sector list, generated stamp

Preset/custom-weight switching is done CLIENT-SIDE: composite = Σ(pillar×weight),
ratings re-derived from composite + FV/QBP (all preset-independent here).
"""
import json, math, sys, os
from datetime import datetime, timedelta

# Run the repo's real modules: make the repo root importable and the cwd, so
# `import config` resolves and the cache files (read by relative path) are found.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd

from config import (DEFAULT_PILLAR_WEIGHTS, WEIGHT_PRESETS, ABSOLUTE_THRESHOLDS,
                    ABSOLUTE_THRESHOLD_STATS, PILLAR_METRICS, GRADE_PERCENTILE_MAP,
                    GRADE_SCORES, RATING_MAPS_PER_PRESET, RATING_COLORS, GRADE_COLORS,
                    DEFAULT_PRESET)
from data_fetcher import get_broad_universe, fetch_universe_data
from scoring import (score_universe, get_sector_stats, get_pillar_detail)
from fairvalue import compute_fair_value
from buy_point import compute_buy_point
import price_cache

FLOORS = [0, 1, 10]
EQUAL = dict(DEFAULT_PILLAR_WEIGHTS)
OUT = os.path.join(ROOT, "web", "public", "data")
os.makedirs(OUT, exist_ok=True)
PILLARS = list(PILLAR_METRICS.keys())  # Valuation, Growth, Profitability, Momentum, EPS Revisions
RAW_KEYS = [k for metrics in PILLAR_METRICS.values() for (k, _, _) in metrics]


def log(*a): print(*a, file=sys.stderr)


# Windows reserved device names: CON.json etc. write to the console device, not a
# file. Map reserved tickers (e.g. CON) to CON_.json on disk; data.ts mirrors this.
import urllib.parse
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
def shard_filename(ticker) -> str:
    name = str(ticker)
    if name.upper() in RESERVED_NAMES:
        name = name + "_"
    return urllib.parse.quote(name, safe="") + ".json"


def unrounded_pillars(raw):
    """Reproduce scoring.score_universe's pillar averages WITHOUT the .round(2)
    that scoring applies when writing result columns. Uses scoring's own
    _percentile_to_grade + GRADE_SCORES so the math is identical, giving
    full-precision pillar scores for exact client-side composite recompute."""
    from scoring import _percentile_to_grade
    df = pd.DataFrame.from_dict(raw, orient="index")
    out = {}
    for pillar_name, metrics in PILLAR_METRICS.items():
        metric_scores = []
        for yf_key, _disp, higher in metrics:
            if yf_key not in df.columns:
                continue
            col = pd.to_numeric(df[yf_key], errors="coerce")
            if higher:
                pct = col.groupby(df["sector"]).rank(pct=True, na_option="bottom") * 100
            else:
                pct = (1 - col.groupby(df["sector"]).rank(pct=True, na_option="bottom")) * 100
            grades = pct.apply(_percentile_to_grade)
            metric_scores.append(grades.map(GRADE_SCORES).fillna(1))
        if metric_scores:
            out[pillar_name] = pd.concat(metric_scores, axis=1).mean(axis=1)
        else:
            out[pillar_name] = pd.Series(1.0, index=df.index)
    return pd.DataFrame(out)


def clean(v):
    """JSON-safe scalar: NaN/inf -> None, numpy -> python."""
    if v is None: return None
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, np.bool_): return bool(v)
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return None
    return v


def num(v):
    """to float or None"""
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def deep_clean(o):
    if isinstance(o, dict): return {k: deep_clean(x) for k, x in o.items()}
    if isinstance(o, (list, tuple)): return [deep_clean(x) for x in o]
    return clean(o)


# ── load all price histories once (full no-floor universe) ──
log("Loading no-floor universe for price histories...")
base_tickers = get_broad_universe(0)
base_raw = fetch_universe_data(base_tickers, 0, lambda p, m: None)

# ── Fail-loud price guard ────────────────────────────────────────────────
# The cache build (build_cache.py / prefetch) can lose currentPrice for nearly
# the whole universe in one run (the 2026-06-10 08:38 bake had 1338/1358 null
# prices, blanking every price/FV/Prem-Disc in the app). If currentPrice is
# missing for more than half the universe, REFUSE to bake so the bot keeps
# yesterday's good committed data instead of shipping a blank (or stale-masked)
# dataset. The per-ticker last-close fallback below still covers a few stragglers.
_n_total = len(base_raw)
_n_price = sum(1 for v in base_raw.values() if isinstance(v, dict) and num(v.get("currentPrice")) is not None)
_null_rate = 1.0 - (_n_price / _n_total) if _n_total else 1.0
log(f"  currentPrice present {_n_price}/{_n_total} (null rate {_null_rate:.1%})")
if _n_total == 0 or _null_rate > 0.50:
    log(f"FATAL: currentPrice null for {_null_rate:.0%} of the universe (>50%). Refusing to write — "
        f"keeping the previous bake. Re-run build_cache.py / check the prefetch, then re-bake.")
    sys.exit(2)

base_preview = score_universe(base_raw, EQUAL, sector_relative=True, preset_name="equal")
end = datetime.now().date()
start = end - timedelta(days=400)
PH = {}
for t in base_preview[base_preview["sector"] != "ETF"].index.tolist():
    try:
        pr = price_cache.get_prices(t, start, end)
        if pr is not None and len(pr) >= 50:
            PH[t] = pr
    except Exception:
        continue
log(f"  {len(PH)} price histories loaded")

# ── per-ticker price shards (floor-independent) ── perf: Stock Detail fetches one
# ~5KB file instead of a 6.6MB monolith. Recent daily closes only (not 5.8M rows).
import urllib.parse
PRICES_DIR = os.path.join(OUT, "prices")
os.makedirs(PRICES_DIR, exist_ok=True)
n_price = 0
for t, pr in PH.items():
    col = "close" if "close" in pr.columns else ("Close" if "Close" in pr.columns else None)
    if col is None:
        continue
    s = pr[col].astype(float)
    dates = [d.strftime("%Y-%m-%d") for d in pd.to_datetime(s.index)]
    closes = [round(float(x), 4) for x in s.values]
    fn = shard_filename(t)
    json.dump({"dates": dates, "close": closes}, open(os.path.join(PRICES_DIR, fn), "w"))
    n_price += 1
log(f"  wrote {n_price} per-ticker price shards")


def bake_floor(floor):
    log(f"=== floor {floor} ===")
    tickers = get_broad_universe(floor)
    raw = fetch_universe_data(tickers, floor, lambda p, m: None)
    ph = {t: PH[t] for t in PH if t in raw}
    # ── Price robustness ──────────────────────────────────────────────────
    # The upstream currentPrice source intermittently returns null for nearly the
    # whole universe at bake time (the 2026-06-10 08:38 bake wrote 1338/1358 null
    # prices → every baked price/FV/Prem-Disc rendered blank in the app). When
    # currentPrice is missing, fall back to the last close from the per-ticker price
    # history we already loaded, so price — and the FV/QBP that scoring derives from
    # it — stay populated. Healthy bakes keep the fresh currentPrice untouched.
    _n_fallback = 0
    for _t, _pr in ph.items():
        _cur = raw[_t].get("currentPrice") if isinstance(raw.get(_t), dict) else None
        if _cur is None or (isinstance(_cur, float) and math.isnan(_cur)):
            _col = "close" if "close" in _pr.columns else ("Close" if "Close" in _pr.columns else None)
            if _col is not None and len(_pr):
                try:
                    raw[_t]["currentPrice"] = float(_pr[_col].iloc[-1])
                    _n_fallback += 1
                except Exception:
                    pass
    if _n_fallback:
        log(f"  price fallback: filled {_n_fallback} null currentPrice from last close (floor {floor})")
    scored = score_universe(raw, EQUAL, sector_relative=True, preset_name="equal",
                            price_histories=ph)
    # Authoritative per-preset composite_score + overall_rating (exact parity).
    # FV/QBP/pillars are preset-independent; only composite & rating change.
    by_preset = {}
    for pname, pinfo in WEIGHT_PRESETS.items():
        sc = score_universe(raw, pinfo["weights"], sector_relative=True,
                            preset_name=pname, price_histories=ph)
        by_preset[pname] = {tk: (num(r.get("composite_score")), r.get("overall_rating"))
                            for tk, r in sc.iterrows()}
        log(f"  scored preset {pname}")
    # M&A scores (non-critical)
    try:
        from ma_analysis import add_ma_target_scores_to_universe
        ss_for_ma = get_sector_stats(scored)
        scored = add_ma_target_scores_to_universe(scored, ss_for_ma)
    except Exception as e:
        log(f"  ma_analysis skipped: {e}")
    sector_stats = get_sector_stats(scored)
    upil = unrounded_pillars(raw)  # full-precision pillar scores for exact custom recompute
    # sanity: rounding the reproduction must equal scoring's stored columns
    _bad = 0
    for p in PILLARS:
        diff = (upil[p].round(2) - scored[f"{p}_score"]).abs()
        _bad += int((diff > 1e-9).sum())
    log(f"  unrounded-pillar reproduction mismatches vs stored (should be 0): {_bad}")

    rows = []
    detail_dir = os.path.join(OUT, "detail", f"floor{floor}")
    os.makedirs(detail_dir, exist_ok=True)
    ma_col = next((c for c in scored.columns if "ma_" in c.lower() and "score" in c.lower()), None)
    n_detail = 0

    for tk, r in scored.iterrows():
        sector = r.get("sector")
        is_etf = sector == "ETF"
        pillars = {p: num(upil.loc[tk, p]) for p in PILLARS}
        grades = {p: r.get(f"{p}_grade") for p in PILLARS}

        # ── rich detail FIRST (non-ETF get FV/QBP; all get pillar detail) ──
        # Mirror scoring.py _classify_top25_tier: FV/QBP wrapped in try/except so
        # string-typed cache fields silently yield None (matches universe columns).
        d = {"pillar_detail": deep_clean(get_pillar_detail(tk, scored, sector_stats)),
             "fv": None, "qbp": None}
        if not is_etf:
            fv_comp = None
            try:
                fv = compute_fair_value(tk, scored)
                if "error" not in fv:
                    d["fv"] = deep_clean(fv)
                    fv_comp = fv.get("composite_fair_value")
            except Exception:
                pass
            ph_t = ph.get(tk)
            if ph_t is not None:
                try:
                    qbp = compute_buy_point(tk, scored, fair_value=fv_comp, price_history=ph_t)
                    if "error" not in qbp:
                        d["qbp"] = deep_clean(qbp)
                except Exception:
                    pass
        # per-ticker detail shard
        fn = shard_filename(tk)
        json.dump(d, open(os.path.join(detail_dir, fn), "w"))
        n_detail += 1

        row = {
            "ticker": tk,
            "name": r.get("shortName"),
            "sector": sector,
            "industry": r.get("industry"),
            "marketCapB": num(r.get("marketCapB")),
            "marketCap": num(r.get("marketCap")),
            "price": num(r.get("currentPrice")),
            "fv": num(r.get("fair_value")),
            "qbp": num(r.get("buy_point")),
            # screener display fields, pulled from the Python FV/QBP dicts (parity-safe)
            "fvVerdict": (d["fv"] or {}).get("verdict"),
            "fvPremium": (d["fv"] or {}).get("premium_discount_pct"),
            "qbpDistance": (d["qbp"] or {}).get("distance_pct"),
            "qbpSignal": (d["qbp"] or {}).get("signal"),
            "pillars": pillars,
            "grades": grades,
            "raw": {k: num(r.get(k)) for k in RAW_KEYS if k in scored.columns},
        }
        if ma_col:
            row["ma_score"] = num(r.get(ma_col))
        # authoritative per-preset composite + rating
        row["byPreset"] = {p: {"c": by_preset[p].get(tk, (None, None))[0],
                               "r": by_preset[p].get(tk, (None, None))[1]}
                           for p in WEIGHT_PRESETS}
        rows.append(row)

    meta = {
        "floor": floor,
        "n_total": len(rows),
        "n_stocks": int((scored["sector"] != "ETF").sum()),
        "n_etf": int((scored["sector"] == "ETF").sum()),
        "sectors": sorted([s for s in scored["sector"].dropna().unique().tolist()]),
    }
    json.dump({"meta": meta, "rows": rows}, open(f"{OUT}/universe_floor{floor}.json", "w"))
    log(f"  wrote universe_floor{floor}.json ({len(rows)} rows) + {n_detail} detail shards")
    return meta


metas = {str(f): bake_floor(f) for f in FLOORS}

meta = {
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "source_commit": os.popen("git rev-parse --short HEAD").read().strip(),
    "default_preset": DEFAULT_PRESET,
    "default_floor": 0,
    "floors": FLOORS,
    "presets": WEIGHT_PRESETS,
    "absolute_thresholds": ABSOLUTE_THRESHOLDS,
    "absolute_threshold_stats": ABSOLUTE_THRESHOLD_STATS,
    "pillars": PILLARS,
    "pillar_metrics": {p: [{"key": k, "name": n, "higher_is_better": h}
                          for (k, n, h) in m] for p, m in PILLAR_METRICS.items()},
    "grade_percentile_map": {g: list(v) for g, v in GRADE_PERCENTILE_MAP.items()},
    "grade_scores": GRADE_SCORES,
    "rating_maps_per_preset": {p: {r: list(v) for r, v in m.items()}
                               for p, m in RATING_MAPS_PER_PRESET.items()},
    "rating_colors": RATING_COLORS,
    "grade_colors": GRADE_COLORS,
    "top_portfolio_n": 25,
    "floor_meta": metas,
}
try:
    import advanced_screener as _advs
    meta["screener"] = {"filterable_metrics": _advs.FILTERABLE_METRICS,
                        "preset_screens": _advs.PRESET_SCREENS}
except Exception as e:
    log(f"screener config skipped: {e}")
json.dump(meta, open(f"{OUT}/meta.json", "w"), indent=2)
log("wrote meta.json")

# ── help content (static strings from help_content.py) ──
try:
    import help_content as hc
    help_keys = ["GETTING_STARTED", "PILLAR_METHODOLOGY", "RATING_SYSTEM", "FAIR_VALUE",
                 "BUY_POINT", "DOPPELGANGER", "MONTE_CARLO", "PGI", "PRO_CHARTS",
                 "ETF_CENTER", "BEST_PRACTICES", "DATA_SOURCES", "DISCLAIMER"]
    help_out = {k: getattr(hc, k) for k in help_keys if isinstance(getattr(hc, k, None), str)}
    # Glossary is a list of {term, definition} — bake under a reserved key for the searchable Glossary section.
    if isinstance(getattr(hc, "GLOSSARY", None), list):
        help_out["_glossary"] = hc.GLOSSARY
    json.dump(help_out, open(f"{OUT}/help.json", "w"), indent=2)
    log(f"wrote help.json ({len(help_out)} sections, {len(help_out.get('_glossary', []))} glossary terms)")
except Exception as e:
    log(f"help.json skipped: {e}")

# ── pundits cache (cache-backed; the source renders this verbatim) ──
try:
    import shutil
    for p in ("pundits_cache.json", os.path.join("data_cache", "pundits_cache.json")):
        if os.path.exists(p):
            shutil.copyfile(p, f"{OUT}/pundits.json"); log("wrote pundits.json"); break
    else:
        log("pundits.json skipped: cache not found")
except Exception as e:
    log(f"pundits.json skipped: {e}")

# ── quarterly history (for Stock Detail quarterly earnings/margins trend) ──
try:
    qmap = {}
    for tk, d in base_raw.items():
        qh = d.get("quarterly_history")
        if isinstance(qh, list) and qh:
            qmap[tk] = qh
    json.dump(qmap, open(f"{OUT}/quarterly.json", "w"))
    log(f"wrote quarterly.json ({len(qmap)} tickers)")
except Exception as e:
    log(f"quarterly.json skipped: {e}")

# ── indicator snapshots (for Home market-health 1W/1M deltas) ──
try:
    import shutil
    for p in ("indicator_snapshots.json", os.path.join("data_cache", "indicator_snapshots.json")):
        if os.path.exists(p):
            shutil.copyfile(p, f"{OUT}/snapshots.json"); log("wrote snapshots.json"); break
    else:
        log("snapshots.json skipped: not found")
except Exception as e:
    log(f"snapshots.json skipped: {e}")

# ── doppelganger DBs (static analog + forward-return tables; algorithm ported to TS) ──
try:
    import doppelganger as _dg, doppelganger_returns as _dgr
    json.dump({
        "fingerprint_dimensions": _dg.FINGERPRINT_DIMENSIONS,
        "historical_analogs": _dg.HISTORICAL_ANALOGS,
        "forward_returns": _dgr.FORWARD_RETURNS,
        "stats": _dg.get_database_stats(),
        "tags": _dg.get_tags_list(),
    }, open(f"{OUT}/doppelganger.json", "w"), indent=2)
    log(f"wrote doppelganger.json ({len(_dg.HISTORICAL_ANALOGS)} analogs)")
except Exception as e:
    log(f"doppelganger.json skipped: {e}")

# ── ETF center: static templates/maps + per-ETF cache fields ──
try:
    import etf_center as _ec
    etf_fields = ["shortName", "industry", "expenseRatio", "totalAssets", "navPrice",
                  "ytdReturn", "threeYearReturn", "fiveYearReturn", "currentPrice", "beta3Year",
                  "yield", "momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m"]
    etfs = {}
    for t, d in base_raw.items():
        if d.get("type") == "etf" or d.get("sector") == "ETF":
            etfs[t] = {k: clean(d.get(k)) for k in etf_fields}
    json.dump({
        "templates": _ec.PORTFOLIO_TEMPLATES,
        "sector_map": _ec.SECTOR_ETF_MAP,
        "theme_map": _ec.THEME_ETF_MAP,
        "etfs": etfs,
    }, open(f"{OUT}/etf.json", "w"), indent=2)
    log(f"wrote etf.json ({len(etfs)} ETFs)")
except Exception as e:
    log(f"etf.json skipped: {e}")

# ── market regime static (network-free pieces; live market data via /api/market) ──
try:
    import macro as _mc, sentiment as _sent
    _md = _mc.MACRO_DATA
    market_static = {
        "macro_data": _md,
        "earnings_forecast": _mc.compute_earnings_forecast(
            _md.get("cpi_current"), _md.get("unemployment_current"), _md.get("ism_composite")),
        "fed_outlook": _mc.get_fed_rate_outlook(),
        "economic_calendar": _mc.fetch_economic_calendar(),
        "coming_soon_indicators": getattr(_sent, "COMING_SOON_INDICATORS", []),
        "us_gdp_trillions": _mc.MACRO_DATA.get("us_gdp_trillions", 29.7),
    }
    try:
        from fed_calendar import _FALLBACK_2026_MEETINGS, _FALLBACK_2027_MEETINGS
        market_static["fomc_meetings"] = list(_FALLBACK_2026_MEETINGS) + list(_FALLBACK_2027_MEETINGS)
    except Exception:
        market_static["fomc_meetings"] = []
    json.dump(deep_clean(market_static), open(f"{OUT}/market_static.json", "w"), indent=2)
    log("wrote market_static.json")
except Exception as e:
    log(f"market_static.json skipped: {e}")

# ── Quant strategy backtest: cumulative-growth curve (quant vs SPY) + headline ──
# Mirrors app.py's "Validated Backtest: Quant Strategy vs SPY" chart, which reads
# quant_backtest_results.json and compounds $100 by portfolio_return_realistic /
# spy_return_pct per checkpoint. The in-repo canonical file is sometimes a
# degenerate placeholder; fall back to the populated sibling and record which was
# used + the populated coverage so the UI can label it honestly (no fabrication).
try:
    import json as _json
    _bt_candidates = ["quant_backtest_results.json", "backtest_results.json",
                      "quant_backtest_results_quarterly_full.json"]
    best = None
    for _name in _bt_candidates:
        _p = os.path.join(ROOT, _name)
        if not os.path.exists(_p):
            continue
        try:
            _d = _json.load(open(_p))
        except Exception:
            continue
        _rows = _d.get("monthly_results") or []
        _nn = sum(1 for r in _rows if r.get("portfolio_return_realistic") is not None)
        # prefer the file with the most populated realistic checkpoints
        if best is None or _nn > best[2]:
            best = (_name, _d, _nn)
    if best:
        _name, _d, _nn = best
        _rows = sorted(_d.get("monthly_results") or [], key=lambda x: x.get("date", ""))
        curve, cum_q, cum_spy = [], 100.0, 100.0
        if _rows:
            curve.append({"date": _rows[0].get("date"), "quant": cum_q, "spy": cum_spy})
        for m in _rows:
            rq, rs = m.get("portfolio_return_realistic"), m.get("spy_return_pct")
            if rq is not None:
                cum_q *= (1 + rq / 100)
            if rs is not None:
                cum_spy *= (1 + rs / 100)
            curve.append({"date": m.get("date"), "quant": round(cum_q, 2), "spy": round(cum_spy, 2)})
        _agg = _d.get("aggregate_metrics", {}) or {}
        _real, _spy = _agg.get("realistic_strategy", {}) or {}, _agg.get("spy_benchmark", {}) or {}
        _populated_dates = [r.get("date") for r in _rows if r.get("portfolio_return_realistic") is not None]
        json.dump({
            "source_file": _name,
            "n_checkpoints": len(_rows),
            "n_populated": _nn,
            "populated_range": [_populated_dates[0], _populated_dates[-1]] if _populated_dates else None,
            "date_range": [_rows[0].get("date"), _rows[-1].get("date")] if _rows else None,
            "headline": {
                "quant_total_pct": _real.get("total_compounded_pct"),
                "spy_total_pct": _spy.get("total_compounded_pct"),
                "win_rate_pct": _real.get("win_rate_pct"),
                "n_periods": _real.get("n_periods"),
            },
            "curve": curve,
        }, open(f"{OUT}/quant_backtest.json", "w"))
        log(f"wrote quant_backtest.json (src={_name}, {len(_rows)} checkpoints, {_nn} populated)")
    else:
        log("quant_backtest.json skipped: no backtest file found")
except Exception as e:
    log(f"quant_backtest.json skipped: {e}")

# ── c78q strategy data: copy the ETL's app payload (read-only) into the app ──
# quant-historical's c78q_etl_main.py writes reports/production/c78q_app_data.json.
# That repo has no git remote, so the app can't raw-fetch it; copy the latest into
# web/public/data/c78q.json. Read-only — we never modify quant-historical.
try:
    import shutil as _sh
    _qh = os.path.join(os.path.dirname(ROOT), "quant-historical")
    _c78q_candidates = [
        os.path.join(_qh, "mlpred_v7_data", "reports", "production", "c78q_app_data.json"),
        os.path.join(_qh, "reports", "production", "c78q_app_data.json"),
    ]
    _src = next((p for p in _c78q_candidates if os.path.exists(p)), None)
    if _src:
        _sh.copyfile(_src, f"{OUT}/c78q.json")
        log(f"wrote c78q.json (from {_src})")
    else:
        log("c78q.json skipped: no c78q_app_data.json found in quant-historical")
except Exception as e:
    log(f"c78q.json skipped: {e}")


# ── ML Predictions: convert the latest universe_predictions CSV into mlpred.json ──
# MLPred v7.2's predict_returns writes reports/predictions/universe_predictions_<date>.csv
# in quant-historical (no git remote, so the app can't raw-fetch it). We read the
# NEWEST such CSV and convert to a slim mlpred.json in web/public/data, every bake,
# so the dashboard's ML Predictions tab always reflects the latest nightly run.
# 1-month horizon is intentionally dropped (never validated as signal).
try:
    import glob as _glob, pandas as _pd, math as _math
    _qh_root = os.path.join(os.path.dirname(ROOT), "quant-historical")
    _pred_dirs = [
        os.path.join(_qh_root, "mlpred_v7_data", "reports", "predictions"),
        os.path.join(_qh_root, "reports", "predictions"),
    ]
    _pred_dir = next((d for d in _pred_dirs if os.path.isdir(d)), None)
    _csvs = sorted(_glob.glob(os.path.join(_pred_dir, "universe_predictions_*.csv"))) if _pred_dir else []
    if _csvs:
        _csv = _csvs[-1]
        _df = _pd.read_csv(_csv)
        _eff = os.path.basename(_csv).replace("universe_predictions_", "").replace(".csv", "")

        def _g(row, col):
            v = row.get(col)
            if v is None: return None
            try:
                f = float(v)
                return None if (_math.isnan(f) or _math.isinf(f)) else f
            except Exception:
                return None

        # discover active streams present as <stream>_active columns
        _stream_ids = [c[:-7] for c in _df.columns if c.endswith("_active")]
        _streams_present = [s for s in _stream_ids if s != "n_streams" and _df[f"{s}_active"].sum() > 0]

        _rows = []
        for _, r in _df.iterrows():
            streams = {}
            for sid in _stream_ids:
                if int(r.get(f"{sid}_active", 0) or 0) == 1:
                    streams[sid] = {
                        "sig": _g(r, f"{sid}_signal"),
                        "p3m": _g(r, f"{sid}_pred_3m"),
                        "p12m": _g(r, f"{sid}_pred_12m"),
                    }
            _rows.append({
                "ticker": str(r.get("ticker", "")),
                "sector": (r.get("sector") if isinstance(r.get("sector"), str) else None),
                "market_cap": _g(r, "market_cap"),
                "price": _g(r, "current_price") if "current_price" in _df.columns else _g(r, "price"),
                "pred_3m": _g(r, "pred_3m"),
                "pred_12m": _g(r, "pred_12m"),
                "target_3m": _g(r, "target_3m"),
                "target_12m": _g(r, "target_12m"),
                "c78q_post": _g(r, "c78q_posterior"),
                "c78q_rank": _g(r, "c78q_rank"),
                "c78q_top8": int(r.get("c78q_top8_flag", 0) or 0),
                "n_active": int(r.get("n_streams_active", 0) or 0),
                "n_bull": int(r.get("n_streams_bullish_3m", 0) or 0),
                "n_bear": int(r.get("n_streams_bearish_3m", 0) or 0),
                "rsi14": _g(r, "rsi14"),
                "rsi2": _g(r, "rsi2"),
                "ret_5d": _g(r, "ret_5d"),
                "ret_21d": _g(r, "ret_21d"),
                "ret_63d": _g(r, "ret_63d"),
                "ret_252d": _g(r, "ret_252d"),
                "dd_52wh": _g(r, "dd_from_52wH"),
                "streams": streams,
            })
        # Merge the binary engine's P(beat) posterior from the newest full-ranking
        # target CSV (generate_c78q_target --top-n 2000 writes every scored ticker).
        # Tickers outside the c78q calibration universe stay null.
        try:
            _tdirs = [os.path.join(_qh_root, "mlpred_v7_data", "reports", "production_targets"),
                      os.path.join(_qh_root, "reports", "production_targets")]
            _tdir = next((d for d in _tdirs if os.path.isdir(d)), None)
            _tcsvs = sorted(_glob.glob(os.path.join(_tdir, "c78q_target_*.csv"))) if _tdir else []
            if _tcsvs:
                _tdf = _pd.read_csv(_tcsvs[-1])
                _post = dict(zip(_tdf["ticker"].astype(str), _tdf["posterior_prob"]))
                _prank = dict(zip(_tdf["ticker"].astype(str), _tdf["rank"]))
                _n_merged = 0
                for _r in _rows:
                    _p = _post.get(_r["ticker"])
                    if _p is not None:
                        try:
                            _pf = float(_p)
                            if not (_math.isnan(_pf) or _math.isinf(_pf)):
                                _r["c78q_post"] = _pf
                                _r["c78q_rank"] = int(_prank.get(_r["ticker"], 0)) or None
                                _n_merged += 1
                        except Exception:
                            pass
                log(f"  merged posterior_prob for {_n_merged} tickers (from {os.path.basename(_tcsvs[-1])})")
        except Exception as _pe:
            log(f"  posterior merge skipped: {_pe}")

        _payload = {
            "generated_at": _dt_now_iso() if "_dt_now_iso" in dir() else None,
            "effective_date": _eff,
            "n": len(_rows),
            "streams_present": _streams_present,
            "rows": _rows,
        }
        json.dump(deep_clean(_payload), open(f"{OUT}/mlpred.json", "w"), separators=(",", ":"))
        log(f"wrote mlpred.json (from {os.path.basename(_csv)}, {len(_rows)} rows, streams={_streams_present})")
    else:
        log("mlpred.json skipped: no universe_predictions_*.csv found in quant-historical")
except Exception as e:
    log(f"mlpred.json skipped: {e}")

log("DONE")
