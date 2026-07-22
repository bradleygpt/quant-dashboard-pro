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
import json, math, sys, os, time as _time
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
BAKE_START_TS = _time.time()   # vintage pass: stamp only what THIS run actually wrote
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


# Curated sector backfill for names whose upstream yfinance .info intermittently returns
# a missing/"Unknown" sector. Without a sector a name becomes a lone "Unknown"-sector group
# (singleton) whose grades inflate and which sorts to row 1 with a junk display (no sector,
# FV "—", mcap 0). MCW (Mister Car Wash) is the recurring offender; its authoritative sector
# is Consumer Cyclical (per the historical scores panel). Values use the yfinance sector
# taxonomy so they merge into the real peer group (>= MIN_SECTOR members → ranked normally).
SECTOR_OVERRIDES = {
    "MCW": "Consumer Cyclical",
}
_MISSING_SECTORS = {None, "", "Unknown", "unknown", "N/A", "nan"}

def apply_sector_overrides(raw):
    """Fill a missing/Unknown sector from SECTOR_OVERRIDES. Returns the list of tickers fixed.
    Only fills when the cached sector is genuinely absent — never overrides a real sector."""
    fixed = []
    for tk, ov in SECTOR_OVERRIDES.items():
        rec = raw.get(tk)
        if isinstance(rec, dict) and rec.get("sector") in _MISSING_SECTORS:
            rec["sector"] = ov
            fixed.append(tk)
    return fixed


def unrounded_pillars(raw):
    """Reproduce scoring.score_universe's pillar averages WITHOUT the .round(2)
    that scoring applies when writing result columns. Uses scoring's own
    _percentile_to_grade + GRADE_SCORES so the math is identical, giving
    full-precision pillar scores for exact client-side composite recompute."""
    from scoring import _percentile_to_grade
    df = pd.DataFrame.from_dict(raw, orient="index")
    # MIRROR scoring.score_universe's MIN_SECTOR guard EXACTLY: rank within sector, but for
    # under-populated sectors (<10 members — e.g. a lone "Unknown"-sector name like MCW, the
    # only such row) fall back to a universe-wide rank. Without this, a singleton sector makes
    # rank(pct) a constant 1.0 → deterministic A+ on every higher-is-better metric (and F on
    # inverted valuation) → an inflated junk composite that floats MCW to row 1. This block
    # previously omitted the guard, so the DISPLAYED pillars diverged from score_universe's
    # (guarded) composite — keep them identical here.
    MIN_SECTOR = 10
    sec_n = df["sector"].map(df["sector"].value_counts())
    out = {}
    for pillar_name, metrics in PILLAR_METRICS.items():
        metric_scores = []
        for yf_key, _disp, higher in metrics:
            if yf_key not in df.columns:
                continue
            col = pd.to_numeric(df[yf_key], errors="coerce")
            if higher:
                sec_pct = col.groupby(df["sector"]).rank(pct=True, na_option="bottom") * 100
                uni_pct = col.rank(pct=True, na_option="bottom") * 100
            else:
                sec_pct = (1 - col.groupby(df["sector"]).rank(pct=True, na_option="bottom")) * 100
                uni_pct = (1 - col.rank(pct=True, na_option="bottom")) * 100
            pct = sec_pct.where(sec_n >= MIN_SECTOR, uni_pct)
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
_sec_fixed = apply_sector_overrides(base_raw)
if _sec_fixed:
    log(f"  sector backfill (base): filled {len(_sec_fixed)} missing/Unknown sectors -> {_sec_fixed}")

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

# Pull build_cache.py's diagnostic sidecar so a guard trip self-diagnoses the
# upstream cause (rate-limit vs HTTP vs empty-info) instead of just "null prices".
def _build_diag():
    import json as _dj
    for _p in (os.path.join(ROOT, "fundamentals_cache_meta.json"), "fundamentals_cache_meta.json"):
        try:
            with open(_p) as _f:
                _m = _dj.load(_f)
            _fm = _m.get("failure_modes") or {}
            _modes = ", ".join(f"{k}={v}" for k, v in sorted(_fm.items(), key=lambda x: -x[1])) or "none recorded"
            return (f"build meta (built {_m.get('built_at')}): fresh={_m.get('n_fresh')} "
                    f"rescued={_m.get('n_rescued')} batch_prices={_m.get('n_batch_prices')} "
                    f"backoffs={_m.get('backoff_pauses')} · failure modes: {_modes}")
        except Exception:
            continue
    return "no build_cache meta sidecar found (fundamentals_cache_meta.json) — update build_cache.py"

if _n_total == 0 or _null_rate > 0.50:
    log(f"FATAL: currentPrice null for {_null_rate:.0%} of the universe (>50%). Refusing to write — "
        f"keeping the previous bake. Re-run build_cache.py / check the prefetch, then re-bake.")
    log(f"  ↳ {_build_diag()}")
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
    _sec_fixed = apply_sector_overrides(raw)
    if _sec_fixed:
        log(f"  sector backfill (floor {floor}): filled {len(_sec_fixed)} missing/Unknown sectors -> {_sec_fixed}")
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
                fv = compute_fair_value(tk, scored, pred_12m=PRED12.get(tk), pred_12m_median=PRED12_MED)
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
            "name": clean(r.get("shortName")) or tk,   # never NaN/None — fall back to the ticker
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
    # deep_clean the WHOLE payload (incl. row scalars like a NaN ticker name) so we
    # never emit bare NaN/Infinity — invalid JSON that the browser refuses to parse,
    # blanking the entire universe ("0 stocks scored"). allow_nan=False is a backstop.
    json.dump(deep_clean({"meta": meta, "rows": rows}),
              open(f"{OUT}/universe_floor{floor}.json", "w"), allow_nan=False)
    log(f"  wrote universe_floor{floor}.json ({len(rows)} rows) + {n_detail} detail shards")
    return meta


# ML 12-month forecast for FV: load pred_12m + cohort median so compute_fair_value folds in the
# "ML 12-Month Target" method (demeaned relative tilt). Must precede the bake_floor pass.
def _load_pred12():
    import glob as _g, pandas as _pd, math as _m, statistics as _st
    _qh = os.path.join(os.path.dirname(ROOT), "quant-historical")
    for _d in (os.path.join(_qh, "mlpred_v7_data", "reports", "predictions"), os.path.join(_qh, "reports", "predictions")):
        if not os.path.isdir(_d): continue
        _cs = sorted(_g.glob(os.path.join(_d, "universe_predictions_*.csv")))
        if not _cs: continue
        _df = _pd.read_csv(_cs[-1])
        if "pred_12m" not in _df.columns: continue
        _p = {}
        for _, _r in _df.iterrows():
            try: _f = float(_r.get("pred_12m"))
            except Exception: continue
            if not (_m.isnan(_f) or _m.isinf(_f)): _p[str(_r.get("ticker", ""))] = _f
        if _p:
            _med = _st.median(_p.values()); log(f"  FV<-ML: {len(_p)} pred_12m loaded, cohort median {_med*100:.2f}%")
            return _p, _med
    log("  FV<-ML: no universe_predictions CSV found; FV baked without the ML method")
    return {}, None
PRED12, PRED12_MED = _load_pred12()
metas = {str(f): bake_floor(f) for f in FLOORS}

# ── meta preset provenance (2026-07-02): prefer the backtest builder's RECOMPUTED
# per-preset headlines over the config.py literals. Fallback to the literal ONLY when
# the builder output is absent, and always say which source was used — every displayed
# metric must trace to data, and the JSON must show its provenance.
import copy as _copy
_presets_out = _copy.deepcopy(WEIGHT_PRESETS)
try:
    _bt_src = os.path.join(ROOT, "quant_backtest_results.json")
    _bt_presets = {}
    if os.path.exists(_bt_src):
        with open(_bt_src) as _f:
            _btd = json.load(_f)
        _bt_presets = _btd.get("presets") or {}
    for _k, _pv in _presets_out.items():
        _rp = (_bt_presets.get(_k) or {}).get("headline") or {}
        if _rp.get("cagr_pct") is not None:
            _pv["backtest_cagr"] = _rp["cagr_pct"]
            _pv["backtest_sharpe"] = _rp.get("sharpe", _pv.get("backtest_sharpe"))
            _pv["backtest_max_dd"] = _rp.get("max_dd_pct", _pv.get("backtest_max_dd"))
            _pv["backtest_provenance"] = "recomputed"
            _pv["backtest_recomputed_at"] = _btd.get("last_run_utc")
            _pv["backtest_window"] = _btd.get("strategy_label")
        else:
            _pv["backtest_provenance"] = "config-literal"
    _n_rec = sum(1 for _pv in _presets_out.values() if _pv.get("backtest_provenance") == "recomputed")
    log(f"meta presets: {_n_rec} recomputed / {len(_presets_out) - _n_rec} config-literal")
except Exception as _pe:
    for _pv in _presets_out.values():
        _pv.setdefault("backtest_provenance", "config-literal")
    log(f"meta preset provenance pass failed ({_pe}) — all config-literal")

meta = {
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "source_commit": os.popen("git rev-parse --short HEAD").read().strip(),
    "default_preset": DEFAULT_PRESET,
    "default_floor": 0,
    "floors": FLOORS,
    "presets": _presets_out,
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

# ── risk radar cache (LLM "what to watch" — narrative half of Macro Outlook) ──
# build_risk_radar_cache.py (daily, Gemini-grounded) writes risk_radar_cache.json;
# the bake copies it verbatim. Absent → skip (the tab shows a "pending" state until
# the first CI generation). Same cache-backed model as pundits.
try:
    import shutil as _shr
    for _p in ("risk_radar_cache.json", os.path.join("data_cache", "risk_radar_cache.json")):
        if os.path.exists(_p):
            _shr.copyfile(_p, f"{OUT}/risk_radar.json"); log("wrote risk_radar.json"); break
    else:
        log("risk_radar.json skipped: cache not found (run build_risk_radar_cache.py)")
except Exception as e:
    log(f"risk_radar.json skipped: {e}")

# ── house-views freshness (twice-monthly staleness watchdog status board) ──
# build_house_views_freshness.py writes house_views_freshness.json; the bake copies it
# so the consensus panel can badge a stale bank view. Absent → skip (no badge).
try:
    import shutil as _shr
    if os.path.exists("house_views_freshness.json"):
        _shr.copyfile("house_views_freshness.json", f"{OUT}/house_views_freshness.json")
        log("wrote house_views_freshness.json")
    else:
        log("house_views_freshness.json skipped: not found (run build_house_views_freshness.py)")
except Exception as e:
    log(f"house_views_freshness.json skipped: {e}")

# ── quarterly history (for Stock Detail quarterly earnings/margins trend) ──
# Depth fix 2026-07-20: yfinance statements reach back only 5-6 quarters, so the
# strict same-quarter-4-back YoY join in build_cache left exactly ONE renderable
# growth point per ticker (the chart showed a single bar plus gaps).
# quarterly_deep.json (build_quarterly_deep.py, committed; distilled from the
# local EDGAR companyfacts cache) carries ~4 years of quarterly revenue/net
# income. Growth is recomputed DATE-BASED over the EDGAR series (year-ago
# quarter-end within ±45 days — tolerant of 52/53-week fiscal calendars);
# yfinance rows contribute margins/ROE/ROA for the quarters they cover and
# remain the full fallback when a ticker has no usable EDGAR series.
try:
    from datetime import date as _qdate

    def _qd(s):
        try:
            return _qdate.fromisoformat(str(s)[:10])
        except Exception:
            return None

    _deep = {}
    _deep_vintage = None
    try:
        _deep_raw = json.load(open("quarterly_deep.json"))
        _deep_vintage = _deep_raw.get("generated_at")
        _deep = {k: v for k, v in _deep_raw.items() if isinstance(v, list)}
    except Exception as _qe:
        log(f"  quarterly_deep.json unavailable ({_qe}) — yfinance-only depth")

    MAX_Q_DISPLAY = 13

    def _near(d, pool, tol):
        best = None
        for p in pool:
            dd = abs((p - d).days)
            if dd <= tol and (best is None or dd < abs((best - d).days)):
                best = p
        return best

    def _merged_quarterly(tk, yf_rows):
        deep = _deep.get(tk)
        if not deep:
            return yf_rows if isinstance(yf_rows, list) else []
        drows = sorted(((_qd(r.get("date")), r) for r in deep if _qd(r.get("date"))),
                       key=lambda x: x[0], reverse=True)
        rev = {d: r.get("revenue") for d, r in drows}
        ni = {d: r.get("netIncome") for d, r in drows}
        deep_by_d = {d: r for d, r in drows}
        yf_by_d = {}
        for r in (yf_rows or []):
            d = _qd(r.get("date"))
            if d:
                yf_by_d[d] = r
        ends = [d for d, _ in drows]
        # a freshly-reported quarter hits yfinance days before the 10-Q lands on
        # EDGAR — union it in so the newest bar doesn't vanish during that window
        for d in yf_by_d:
            if _near(d, ends, 10) is None:
                ends.append(d)
        ends.sort(reverse=True)
        out = []
        for d in ends[:MAX_Q_DISPLAY]:
            ym = _near(d, yf_by_d.keys(), 10)
            yr = yf_by_d.get(ym, {}) if ym else {}
            r_now, n_now = rev.get(d), ni.get(d)
            base = _near(d - timedelta(days=365), [e for e in rev if e < d], 45)
            rg = ng = None
            if base is not None:
                r_pri, n_pri = rev.get(base), ni.get(base)
                if r_now is not None and r_pri and r_pri > 0:
                    rg = round((r_now - r_pri) / r_pri, 4)
                if n_now is not None and n_pri:
                    ng = round((n_now - n_pri) / abs(n_pri), 4)
            if rg is None:
                rg = yr.get("revenueGrowth")
            if ng is None:
                ng = yr.get("earningsGrowth")
            nm = yr.get("netMargins")
            if nm is None and r_now and n_now is not None and r_now > 0:
                nm = round(n_now / r_now, 4)
            # EPS/mcap/revenue passthrough (earnings-chart rework 2026-07-21): deep
            # carries split-adjusted diluted EPS + same-basis quarter-end mcap;
            # the newest pre-10-Q quarter falls back to yfinance dilutedEPS /
            # revenueRaw (build_cache) — EPS basis is current by construction there.
            dr = deep_by_d.get(d, {})
            eps = dr.get("epsDiluted")
            if eps is None:
                eps = yr.get("dilutedEPS")
            rev_raw = r_now if r_now is not None else yr.get("revenueRaw")
            out.append({
                "date": d.isoformat(),
                "grossMargins": yr.get("grossMargins"),
                "operatingMargins": yr.get("operatingMargins"),
                "netMargins": nm,
                "returnOnEquity": yr.get("returnOnEquity"),
                "returnOnAssets": yr.get("returnOnAssets"),
                "revenueGrowth": rg,
                "earningsGrowth": ng,
                "eps": eps,
                "epsDerived": dr.get("epsDerived"),
                "mcapB": dr.get("mcapB"),
                "revenue": rev_raw,
            })
        return out

    qmap = {}
    for tk, d in base_raw.items():
        merged = _merged_quarterly(tk, d.get("quarterly_history"))
        if merged:
            qmap[tk] = merged
    # B4 seasonal-rebuild guard (S6): ship the deep artifact's vintage so the UI can
    # badge staleness (quarterly_deep is rebuilt manually post-10-Q-season, NOT nightly).
    # Frontend indexes this map by ticker, so a string meta key is invisible to charts.
    if _deep_vintage:
        qmap["deep_generated_at"] = _deep_vintage
    json.dump(qmap, open(f"{OUT}/quarterly.json", "w"))
    _n_deep = sum(1 for tk in qmap if tk in _deep)
    log(f"wrote quarterly.json ({len(qmap)} tickers; {_n_deep} EDGAR-deepened; deep vintage {_deep_vintage})")
except Exception as e:
    log(f"quarterly.json skipped: {e}")

# ── baked investment theses (handoff §2, 2026-07-20) ──
# theses/baked/*.json are generated in Claude Code (see theses/PROMPT_PACK.md)
# and committed; the bake ships them to the app as public/data/theses/ plus a
# per-ticker index (latest file wins by the date+version in the filename).
# No theses yet → no index written → the Stock Detail panel shows its
# enqueue-only state. Never blocks the bake.
try:
    import shutil as _sh
    _tdir = os.path.join(ROOT, "theses", "baked")
    _tout = os.path.join(OUT, "theses")
    _tfiles = sorted(f for f in os.listdir(_tdir)) if os.path.isdir(_tdir) else []
    _tfiles = [f for f in _tfiles if f.endswith(".json")]
    if _tfiles:
        os.makedirs(_tout, exist_ok=True)
        _tindex = {}
        for _tf in _tfiles:
            _sh.copy2(os.path.join(_tdir, _tf), os.path.join(_tout, _tf))
            _tk = _tf.split("_")[0].upper()
            _e = _tindex.setdefault(_tk, {"files": []})
            _e["files"].append(_tf)
        for _tk, _e in _tindex.items():
            _e["latest"] = _e["files"][-1]  # sorted → date+version ascending
            _e["count"] = len(_e["files"])
        json.dump(_tindex, open(f"{OUT}/theses_index.json", "w"))
        log(f"wrote theses_index.json ({len(_tindex)} tickers, {len(_tfiles)} theses)")
except Exception as e:
    log(f"theses bake skipped: {e}")

# ── AI Bubble Watch monthly snapshots (handoff §4, 2026-07-20) ──
# bubblewatch/snapshots/*.json are produced monthly by
# build_bubblewatch_snapshot.py (data layer — never depends on AI);
# bubblewatch/commentary/*.json by the Claude Code queue (commentary layer).
# Ship both + an index; the page shows "commentary pending" when a month has
# data but no commentary. Never blocks the bake.
try:
    import shutil as _sh2
    _bdir = os.path.join(ROOT, "bubblewatch")
    _bsnap = os.path.join(_bdir, "snapshots")
    _bcomm = os.path.join(_bdir, "commentary")
    _bout = os.path.join(OUT, "bubblewatch")
    _snaps = sorted(f for f in os.listdir(_bsnap) if f.endswith(".json")) if os.path.isdir(_bsnap) else []
    if _snaps:
        os.makedirs(_bout, exist_ok=True)
        _comms = sorted(f for f in os.listdir(_bcomm) if f.endswith(".json")) if os.path.isdir(_bcomm) else []
        for _f in _snaps:
            _sh2.copy2(os.path.join(_bsnap, _f), os.path.join(_bout, _f))
        for _f in _comms:
            _sh2.copy2(os.path.join(_bcomm, _f), os.path.join(_bout, f"commentary_{_f}"))
        json.dump({
            "months": [f[:-5] for f in _snaps],
            "latest": _snaps[-1][:-5],
            "commentary_months": [f[:-5] for f in _comms],
        }, open(f"{OUT}/bubblewatch_index.json", "w"))
        log(f"wrote bubblewatch_index.json ({len(_snaps)} snapshots, {len(_comms)} commentaries)")
except Exception as e:
    log(f"bubblewatch bake skipped: {e}")

# ── ticker -> Markets-Engine anchor map (engine-wiring Phase 1, 2026-07-20) ──
# Generated from each ticker's baked sector + the VERIFIED engine anchor manifest
# (see ticker_anchor_map.py provenance header). Drives the Stock Detail entry
# point: mapped tickers get gate-validated pre-filled queries; `none` renders a
# disabled state so the app never provokes an engine refusal from a button.
try:
    import ticker_anchor_map as _tam
    _amap = _tam.build_map(base_raw)
    json.dump(_amap, open(f"{OUT}/ticker_anchor_map.json", "w"))
    _n_none = sum(1 for v in _amap.values() if v["mapping_kind"] == "none")
    log(f"wrote ticker_anchor_map.json ({len(_amap)} tickers; {_n_none} unmapped/none)")
except Exception as e:
    log(f"ticker_anchor_map.json skipped: {e}")

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
# Macro inputs (CPI/Unemployment) were hardcoded in macro.MACRO_DATA (last_updated
# 2026-04-20) and had drifted off the app's own FRED feed — CPI especially (static
# 2.4% vs live ~4%+ YoY), which materially skews the earnings forecast. We now VERIFY
# each against live FRED AT BAKE TIME and override with the real value + its as-of
# date. ISM is NOT published on FRED (delisted years ago), so it stays a manual
# constant but is labeled with its source + last-updated date — never silently stale.
try:
    import macro as _mc, sentiment as _sent
    import urllib.request as _ur4
    _md = dict(_mc.MACRO_DATA)  # copy — don't mutate the imported module dict

    def _fred_rows(sid, _retries=4):
        # Retry with backoff: the keyless fredgraph endpoint intermittently times out from CI/bake
        # IPs, and a single failure used to drop CPI/Unemp back to stale static values. Keep trying.
        _u = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        _last = None
        for _a in range(_retries):
            try:
                _rq = _ur4.Request(_u, headers={"User-Agent": "Mozilla/5.0 (compatible; QuantDashboard/2.0)"})
                with _ur4.urlopen(_rq, timeout=30) as _r:
                    _txt = _r.read().decode()
                _out = []
                for _ln in _txt.strip().split("\n")[1:]:
                    _p = _ln.split(",")
                    if len(_p) < 2 or _p[1] in ("", "."):
                        continue
                    try:
                        _out.append((_p[0], float(_p[1])))
                    except ValueError:
                        continue
                if _out:
                    return _out
            except Exception as _e:
                _last = _e
                _time.sleep(1.5 * (_a + 1))
        if _last:
            raise _last
        return []

    _static_asof = _md.get("last_updated")
    # Unemployment — UNRATE, direct latest value.
    try:
        _un = _fred_rows("UNRATE")
        if _un:
            _md["unemployment_current"], _md["unemployment_asof"] = _un[-1][1], _un[-1][0]
            if len(_un) >= 2:
                _md["unemployment_prior"] = _un[-2][1]
            _md["unemployment_source"] = "FRED UNRATE (live)"
    except Exception as _e:
        _md["unemployment_source"] = f"static (FRED UNRATE fetch failed: {_e})"
        _md.setdefault("unemployment_asof", _static_asof)
    # CPI YoY — CPIAUCNS index, headline (NSA) year-over-year, date-aligned 12-mo prior.
    try:
        _cpi = _fred_rows("CPIAUCNS")
        def _yoy(rows, idx):
            _d, _v = rows[idx]
            _ty = f"{int(_d[:4]) - 1}{_d[4:]}"  # same month, prior year
            _prev = next((vv for dd, vv in rows if dd == _ty), None)
            return round((_v / _prev - 1) * 100, 1) if _prev else None
        if len(_cpi) >= 13:
            _md["cpi_current"], _md["cpi_asof"] = _yoy(_cpi, -1), _cpi[-1][0]
            _md["cpi_prior"] = _yoy(_cpi, -2)
            _md["cpi_source"] = "FRED CPIAUCNS YoY (live)"
    except Exception as _e:
        _md["cpi_source"] = f"static (FRED CPIAUCNS fetch failed: {_e})"
        _md.setdefault("cpi_asof", _static_asof)
    # ISM — not on FRED (licensing prohibits derivative feeds; no compliant free API).
    # Two candidate sources per component, freshest period wins (tie → manual):
    #   1. macro_baked.json  — Bradley's manual entry (update_ism.py, 1st/3rd biz day)
    #   2. manual_macro.json — monthly grounded Gemini fetch (best-effort backstop;
    #      it demonstrably missed the 2026-07-06 holiday-shifted services release)
    # Fall back to the labeled macro.py constant only when both are absent. Each
    # component carries its OWN period so the UI never conflates mfg/svcs vintages;
    # ism_asof (the composite's label + staleness-badge input) = the OLDER period.
    _md["ism_source"] = "ISM PMI (manual — not published on FRED)"
    _md["ism_asof"] = _static_asof

    def _ism_candidate(fname, key, period_field):
        try:
            _j = json.load(open(os.path.join(ROOT, fname)))
            _e = _j.get(key) or {}
            if isinstance(_e.get("value"), (int, float)) and _e.get(period_field):
                return {"value": _e["value"], "period": str(_e[period_field]),
                        "source": _e.get("source") or fname,
                        "entered": _e.get("entered")}
        except Exception:
            pass
        return None

    def _ism_pick(key):
        _baked = _ism_candidate("macro_baked.json", key, "period")
        _gem = _ism_candidate("manual_macro.json", key, "ref_month")
        if _baked and _gem:
            return _baked if _baked["period"] >= _gem["period"] else _gem
        return _baked or _gem

    _mfg, _svc = _ism_pick("ism_mfg"), _ism_pick("ism_svcs")
    if _mfg and _svc:
        _md["ism_manufacturing"], _md["ism_services"] = _mfg["value"], _svc["value"]
        _md["ism_composite"] = round(0.11 * _mfg["value"] + 0.89 * _svc["value"], 1)
        _md["ism_mfg_asof"], _md["ism_svcs_asof"] = _mfg["period"], _svc["period"]
        _md["ism_mfg_source"], _md["ism_svcs_source"] = _mfg["source"], _svc["source"]
        _md["ism_entered"] = _mfg.get("entered") or _svc.get("entered")
        _md["ism_asof"] = min(_mfg["period"], _svc["period"])
        _md["ism_source"] = f"mfg: {_mfg['source']} · svcs: {_svc['source']}"

    market_static = {
        "macro_data": _md,
        "earnings_forecast": _mc.compute_earnings_forecast(
            _md.get("cpi_current"), _md.get("unemployment_current"), _md.get("ism_composite")),
        "fed_outlook": _mc.get_fed_rate_outlook(),
        "economic_calendar": _mc.fetch_economic_calendar(),
        "coming_soon_indicators": getattr(_sent, "COMING_SOON_INDICATORS", []),
        "us_gdp_trillions": _mc.MACRO_DATA.get("us_gdp_trillions", 29.7),
    }
    log(f"  macro verified vs FRED: CPI={_md.get('cpi_current')}% ({_md.get('cpi_source')}, "
        f"as-of {_md.get('cpi_asof')}), Unemp={_md.get('unemployment_current')}% "
        f"(as-of {_md.get('unemployment_asof')}), ISM={_md.get('ism_composite')} (manual)")
    try:
        from fed_calendar import _FALLBACK_2026_MEETINGS, _FALLBACK_2027_MEETINGS
        market_static["fomc_meetings"] = list(_FALLBACK_2026_MEETINGS) + list(_FALLBACK_2027_MEETINGS)
    except Exception:
        market_static["fomc_meetings"] = []

    # ── Macro signals + forward earnings path (keyless FRED, CI-safe) ──────────
    # Idea #4: yield curve / credit spreads / breakevens / jobless claims — the
    # free FRED series the Market Regime tab was missing (curve was hardcoded).
    # Idea #3: a 1-year-ahead earnings TRAJECTORY from the Fed SEP's forward macro
    # projections instead of a single static point estimate. Both best-effort and
    # keyless (CI has no FRED_API_KEY); absent → omitted, never invented.
    try:
        import macro_forecasts as _mf2
        market_static["macro_signals"] = _mf2.build_macro_signals()
        _sep = _mf2.fetch_fred_sep()
        if _sep:
            _fedvals = _sep["row"]["values"]
            _fwd = []
            for _yr in (str(end.year), str(end.year + 1), str(end.year + 2)):
                _infl = _fedvals.get("inflation", {}).get(_yr)
                _unemp = _fedvals.get("unemployment", {}).get(_yr)
                if _infl is None or _unemp is None:
                    continue
                _ef = _mc.compute_earnings_forecast(_infl, _unemp, _md.get("ism_composite"))
                _fwd.append({"year": _yr, "pce_inflation": _infl, "unemployment": _unemp,
                             "ism_assumed": _md.get("ism_composite"),
                             "sp500_earnings_growth": _ef["sp500_earnings_growth"]})
            if _fwd:
                market_static["forward_earnings"] = {
                    "as_of": _sep["row"].get("as_of"),
                    "source": "Fed SEP forward projections (FRED Release 326); ISM held at current level",
                    "note": ("Model's inflation term fed with SEP PCE (the Fed's gauge); "
                             "the Fed does not project ISM, so it is held at the current reading."),
                    "path": _fwd,
                }
        log(f"  macro_signals: {len(market_static['macro_signals']['signals'])} series; "
            f"forward_earnings: {len(market_static.get('forward_earnings', {}).get('path', []))} yrs")
    except Exception as _se:
        log(f"  macro_signals/forward_earnings skipped: {_se}")

    json.dump(deep_clean(market_static), open(f"{OUT}/market_static.json", "w"), indent=2)
    log("wrote market_static.json")
except Exception as e:
    log(f"market_static.json skipped: {e}")

# ── Macro forecasts: cross-institution consensus panel + FOMC dot plot ─────────
# Fed SEP (FRED Release 326, keyless), World Bank GEP (Data360), IMF WEO
# (DataMapper) fetched live at bake time; bank/strategist house views are dated
# curated snapshots (macro_house_views.json). Each forecaster row carries
# source + as_of + live; missing cells stay null (DATA_INTEGRITY_STANDARD).
# Powers the Macro Outlook tab (consensus table + dot plot).
try:
    import macro_forecasts as _mf
    _fc = _mf.build_macro_forecasts()
    json.dump(deep_clean(_fc), open(f"{OUT}/macro_forecasts.json", "w"), indent=2)
    _n_live = sum(1 for s in _fc.get("sources", []) if s.get("live"))
    log(f"wrote macro_forecasts.json ({len(_fc['consensus']['forecasters'])} forecasters, "
        f"{_n_live} live, dot_plot={'yes' if _fc.get('dot_plot') else 'no'}, "
        f"years={_fc['consensus']['years']})")
    try:
        _mp = f"{OUT}/freshness_manifest.json"
        _man = json.load(open(_mp)) if os.path.exists(_mp) else {}
        _man.setdefault("sources", {})["macro_forecasts"] = {
            "source": ("macro_forecasts.build_macro_forecasts — FRED SEP (Release 326) + "
                       "World Bank GEP + IMF WEO live; bank house views curated"),
            "as_of": datetime.now().strftime("%Y-%m-%d"),
            "forecasters": [s["name"] for s in _fc.get("sources", [])],
            "n_live": _n_live,
            "consumed_by": "Macro Outlook tab (consensus panel + FOMC dot plot)",
            "check_status": "ok",
        }
        json.dump(_man, open(_mp, "w"), indent=2)
    except Exception as _me:
        log(f"  freshness_manifest macro_forecasts upsert skipped: {_me}")
except Exception as e:
    log(f"macro_forecasts.json skipped: {e}")

# ── Mirror macro artifacts into the pro-v2 frontend (parity; pro-v2 has no bake) ──
# quant-dashboard-pro-v2 is a second React frontend that CONSUMES baked data but
# produces none. Keep its Macro Outlook tab + Market Regime additions fed: copy
# macro_forecasts.json verbatim and MERGE the macro_signals + forward_earnings keys
# into its market_static.json (preserving any pro-v2-specific fields — never a blind
# overwrite). Best-effort and guarded: absent sibling dir → skip, never fail the bake.
try:
    _v2 = os.path.join(os.path.dirname(ROOT), "quant-dashboard-pro-v2", "public", "data")
    if os.path.isdir(_v2):
        import shutil as _sh2
        for _fn in ("macro_forecasts.json", "risk_radar.json", "house_views_freshness.json"):
            _srcf = f"{OUT}/{_fn}"
            if os.path.exists(_srcf):
                _sh2.copyfile(_srcf, os.path.join(_v2, _fn))
        _src_ms_p = f"{OUT}/market_static.json"
        if os.path.exists(_src_ms_p):
            _src_ms = json.load(open(_src_ms_p))
            _v2_ms_p = os.path.join(_v2, "market_static.json")
            _v2_ms = json.load(open(_v2_ms_p)) if os.path.exists(_v2_ms_p) else {}
            for _k in ("macro_signals", "forward_earnings"):
                if _k in _src_ms:
                    _v2_ms[_k] = _src_ms[_k]
            json.dump(_v2_ms, open(_v2_ms_p, "w"), indent=2)
        log("mirrored macro artifacts -> quant-dashboard-pro-v2 (macro_forecasts.json + risk_radar.json + market_static macro keys)")
    else:
        log("pro-v2 mirror skipped: quant-dashboard-pro-v2/public/data not found")
except Exception as e:
    log(f"pro-v2 mirror skipped: {e}")

# ── PGI money-market AUM (FRED MMMFFAQ027S, quarterly) — baked with an as-of date ──
# The Potential Growth Indicator card divides money-market fund AUM by total market
# cap. The live /api/market edge fetch to FRED is unreliable from Vercel edge IPs and
# was silently freezing on a hardcoded $7.00T "fallback estimate" for months. We have
# proven FRED's keyless CSV is reachable from the bake host, so bake the REAL latest
# observation (value + its observation date) here; the card prefers a live FRED hit
# when it succeeds, else this dated baked value, and only shows the hardcoded estimate
# (clearly flagged) when both are absent. Quarterly series → publish-lag is expected
# and surfaced via the as-of date, never hidden.
try:
    import urllib.request as _ur3
    _u3 = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MMMFFAQ027S"
    _req3 = _ur3.Request(_u3, headers={"User-Agent": "Mozilla/5.0 (compatible; QuantDashboard/2.0)"})
    with _ur3.urlopen(_req3, timeout=20) as _r3:
        _txt3 = _r3.read().decode()
    _mm_asof, _mm_val = None, None
    for _ln in reversed(_txt3.strip().split("\n")[1:]):  # skip header; walk newest→oldest
        _parts = _ln.split(",")
        if len(_parts) < 2:
            continue
        try:
            _mm_val = float(_parts[1])
        except ValueError:
            continue
        _mm_asof = _parts[0]
        break
    if _mm_val is not None and 1e6 <= _mm_val <= 20e6:  # series is in $millions; sane $1T–$20T band
        _mm_t = round(_mm_val / 1e6, 3)
        json.dump({
            "ok": True,
            "money_market_t": _mm_t,
            "as_of": _mm_asof,
            "source": "FRED MMMFFAQ027S",
            "source_desc": "Money market funds; total financial assets (quarterly)",
            "units": "USD trillions",
            "fetched_at": datetime.now().date().isoformat(),
        }, open(f"{OUT}/pgi_money_market.json", "w"))
        log(f"wrote pgi_money_market.json (MMMFFAQ027S = ${_mm_t}T as-of {_mm_asof})")
    else:
        log(f"pgi_money_market.json skipped: MMMFFAQ027S value out-of-band ({_mm_val})")
except Exception as e:
    log(f"pgi_money_market.json skipped: {e}")

# PGI freshness override: FRED's MMMFFAQ027S is quarterly (~6wk lag); prefer the fresher ICI
# money-market total from the monthly grounded fetch (build_manual_macro.py) when present.
try:
    _mmj = json.load(open(os.path.join(ROOT, "manual_macro.json")))
    _mmf = _mmj.get("mmf_total_t") or {}
    if isinstance(_mmf.get("value"), (int, float)) and 4.0 <= _mmf["value"] <= 12.0:
        json.dump({
            "ok": True,
            "money_market_t": round(_mmf["value"], 3),
            "as_of": _mmf.get("as_of"),
            "source": "ICI weekly money market fund assets",
            "source_desc": _mmf.get("source") or "ICI total money market fund net assets (weekly)",
            "units": "USD trillions",
            "fetched_at": datetime.now().date().isoformat(),
        }, open(f"{OUT}/pgi_money_market.json", "w"))
        log(f"pgi_money_market.json overridden with fresher ICI ${round(_mmf['value'], 3)}T as-of {_mmf.get('as_of')}")
except Exception as _e:
    log(f"PGI ICI override skipped: {_e}")

# ── Realistic swing backtest: strategy equity curve vs REAL buy-&-hold SPY ──
# Source = the monthly swing backtest (top-10 basket, ~63-day holds, after costs).
# This is a DIFFERENT, stricter record than the validated TOP-25 quarterly CAGR
# table the UI shows separately — labeled as such, never conflated.
# Source selection is PROGRAMMATIC and defensive — a file is NEVER trusted by name:
#   * only canonical result files are considered (research variants are excluded),
#   * candidates below a populated-checkpoint sanity floor are REFUSED (this is what
#     stops a 6-row placeholder from winning just because it has the canonical name),
#   * among survivors, prefer most-populated, breaking ties by latest end-date,
#   * the chosen file name + checkpoint count + full date range is logged every bake.
# The SPY line is a TRUE buy-&-hold curve pulled from the app's own Yahoo v8 feed
# (simulated-market consistent), NOT the file's spy_return_pct — those are overlapping
# ~63-day forward returns sampled monthly and do not compound to a valid wealth curve.
# Live fetch failure falls back to the file's series, explicitly flagged as such.
try:
    import json as _json, urllib.request as _ur, calendar as _cal, datetime as _dt
    _BT_FLOOR = 24  # ≥2y of monthly checkpoints; rejects degenerate placeholders
    # Canonical files only. backtest_variant_*.json are hypothesis runs, NOT headline.
    _bt_candidates = ["quant_backtest_results.json", "backtest_results.json",
                      "quant_backtest_results_quarterly_full.json"]
    _cands = []
    for _name in _bt_candidates:
        _p = os.path.join(ROOT, _name)
        if not os.path.exists(_p):
            continue
        try:
            _d = _json.load(open(_p))
        except Exception:
            continue
        _pop = [r for r in (_d.get("monthly_results") or []) if r.get("portfolio_return_realistic") is not None]
        if len(_pop) < _BT_FLOOR:
            log(f"  backtest candidate {_name} REJECTED ({len(_pop)} populated < floor {_BT_FLOOR})")
            continue
        _end = max((r.get("date") or "") for r in _pop)
        _cands.append((len(_pop), _end, _name, _d, _pop))
    if not _cands:
        log("quant_backtest.json skipped: no candidate cleared the sanity floor")
    else:
        _cands.sort(key=lambda c: (c[0], c[1]), reverse=True)  # most-populated, then latest end
        _nn, _end_date, _name, _d, _pop = _cands[0]
        _rows = sorted(_pop, key=lambda x: x.get("date", ""))
        _start_date, _end_date = _rows[0].get("date"), _rows[-1].get("date")

        # Strategy equity curve: compound realistic per-checkpoint returns from $100.
        curve, cum_q = [{"date": _start_date, "quant": 100.0, "spy": 100.0}], 100.0
        for m in _rows:
            rq = m.get("portfolio_return_realistic")
            if rq is not None:
                cum_q *= (1 + rq / 100)
            curve.append({"date": m.get("date"), "quant": round(cum_q, 2), "spy": None})

        # Real buy-&-hold SPY over the same span, from the app's own Yahoo v8 feed.
        spy_source, spy_asof = "overlapping_fallback", None
        def _ep(s):
            y, mo, d = (int(x) for x in s[:10].split("-"))
            return int(_cal.timegm(_dt.date(y, mo, d).timetuple()))
        try:
            _u = (f"https://query1.finance.yahoo.com/v8/finance/chart/SPY"
                  f"?period1={_ep(_start_date) - 45 * 86400}&period2={_ep(_end_date) + 45 * 86400}&interval=1mo")
            _req = _ur.Request(_u, headers={"User-Agent": "Mozilla/5.0 (compatible; QuantDashboard/2.0)"})
            with _ur.urlopen(_req, timeout=12) as _resp:
                _r0 = _json.load(_resp)["chart"]["result"][0]
            _adj = (_r0.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
            _vals = _adj or _r0["indicators"]["quote"][0]["close"]
            _by_ym = {}
            for _t, _v in zip(_r0["timestamp"], _vals):
                if _v:
                    _by_ym[_dt.datetime.utcfromtimestamp(_t).strftime("%Y-%m")] = _v
            _ordered = sorted(_by_ym)
            def _spy_at(ym):  # nearest month at-or-before ym (forward fill)
                _prev = None
                for _k in _ordered:
                    if _k <= ym:
                        _prev = _k
                    else:
                        break
                return _by_ym.get(_prev or (_ordered[0] if _ordered else None))
            _base = _spy_at(_start_date[:7]) if _ordered else None
            if _base:
                for _pt in curve:
                    _sv = _spy_at(_pt["date"][:7])
                    _pt["spy"] = round(100.0 * _sv / _base, 2) if _sv else None
                spy_source, spy_asof = "buyhold_yahoo_v8", _ordered[-1]
        except Exception as _e:
            log(f"  SPY buy-&-hold fetch failed ({_e}); falling back to file spy_return_pct")
        if spy_source == "overlapping_fallback":  # not a true wealth curve; flagged
            cum_spy = 100.0
            curve[0]["spy"] = 100.0
            for _i, m in enumerate(_rows, start=1):
                rs = m.get("spy_return_pct")
                if rs is not None:
                    cum_spy *= (1 + rs / 100)
                curve[_i]["spy"] = round(cum_spy, 2)

        # Honest total-return + CAGR over the populated span.
        def _yrs(a, b):
            return max((int(b[:4]) + (int(b[5:7]) - 1) / 12) - (int(a[:4]) + (int(a[5:7]) - 1) / 12), 1e-6)
        _span = _yrs(_start_date, _end_date)
        _q_end = curve[-1]["quant"]
        _s_end = next((c["spy"] for c in reversed(curve) if c["spy"] is not None), None)
        _real = (_d.get("aggregate_metrics", {}) or {}).get("realistic_strategy", {}) or {}
        json.dump({
            "ok": True,
            "source_file": _name,
            "n_checkpoints": len(_rows),
            "n_populated": _nn,
            "populated_range": [_start_date, _end_date],
            "date_range": [_start_date, _end_date],
            "span_years": round(_span, 1),
            "spy_source": spy_source,
            "spy_asof": spy_asof,
            "strategy_label": _d.get("strategy_label") or "Realistic swing strategy · top-10 · ~63-day holds · after costs",
            "caveat": _d.get("caveat"),
            "source_meta": _d.get("source"),
            "coverage": _d.get("coverage"),
            "headline": {
                "quant_total_pct": round(_q_end - 100, 1),
                "spy_total_pct": round(_s_end - 100, 1) if _s_end is not None else None,
                "quant_cagr_pct": round(_real["cagr_pct"], 1) if _real.get("cagr_pct") is not None else round(((_q_end / 100) ** (1 / _span) - 1) * 100, 1),
                "spy_cagr_pct": round(((_s_end / 100) ** (1 / _span) - 1) * 100, 1) if _s_end else None,
                "win_rate_pct": _real.get("win_rate_pct"),
                "n_periods": _nn,
            },
            # per-preset recomputed headlines (2026-07-02 builder) — same source that
            # feeds meta.presets provenance="recomputed"; absent on legacy candidates.
            "presets": _d.get("presets") or None,
            "curve": curve,
        }, open(f"{OUT}/quant_backtest.json", "w"))
        log(f"wrote quant_backtest.json (src={_name}, {len(_rows)} checkpoints, "
            f"{_nn} populated, {_start_date}→{_end_date}, spy={spy_source})")
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
        # DISABLED 2026-06-27: c78q_app_data.json is the ETL's TOP-8 research variant (config A_top8).
        # The LIVE c78q is top-3 / 1st-of-month, written directly to web/public/data/c78q.json by
        # quant-historical's _c78q_top3_rebake.py and committed. Copying the top-8 here OVERWRITES the
        # live top-3 strategy — do NOT. c78q.json is left as committed.
        log(f"c78q.json: kept committed (live top-3); NOT overwriting with ETL top-8 ({_src})")
    else:
        log("c78q.json: kept committed (no ETL payload found)")
except Exception as e:
    log(f"c78q.json skipped: {e}")


# ── regime_timeseries.json: ML regime classifier history for the RegimeRibbon ──
# Run-length segments of dominant_regime from quant-historical's classifier
# (5 states: early_bull/late_bull/range_bound/correction/panic; the frontend
# collapses them to risk-on/neutral/drawdown display states in theme.ts).
try:
    import pandas as _rg_pd
    _rg_path = os.path.join(os.path.dirname(ROOT), "quant-historical",
                            "mlpred_v7_data", "regime", "classifications",
                            "regime_classifications.parquet")
    if os.path.exists(_rg_path):
        _rg = _rg_pd.read_parquet(_rg_path, columns=["date", "dominant_regime"]).sort_values("date")
        _rg["date"] = _rg_pd.to_datetime(_rg["date"]).dt.strftime("%Y-%m-%d")
        _rg_segs = []
        for _d, _r in zip(_rg["date"], _rg["dominant_regime"]):
            if _rg_segs and _rg_segs[-1]["regime"] == _r:
                _rg_segs[-1]["end"] = _d
            else:
                _rg_segs.append({"start": _d, "end": _d, "regime": str(_r)})
        _rg_out = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": _rg["date"].iloc[-1],
            "source": "mlpred_v7_data/regime/classifications/regime_classifications.parquet",
            "note": "dominant_regime run-length segments, daily grid; 5 ML states, frontend maps to risk_on/neutral/drawdown",
            "states": sorted(_rg["dominant_regime"].astype(str).unique().tolist()),
            "segments": _rg_segs,
        }
        json.dump(_rg_out, open(f"{OUT}/regime_timeseries.json", "w"), separators=(",", ":"))
        log(f"wrote regime_timeseries.json ({len(_rg_segs)} segments, as_of {_rg_out['as_of']})")
        try:
            _mp = f"{OUT}/freshness_manifest.json"
            _man = json.load(open(_mp)) if os.path.exists(_mp) else {}
            _man.setdefault("sources", {})["regime_timeseries"] = {
                "source": "quant-historical regime_classifications.parquet (ML regime classifier)",
                "as_of": _rg_out["as_of"],
                "n_segments": len(_rg_segs),
                "consumed_by": "RegimeRibbon (strategies hub hero, Katalepsis backtest)",
                "check_status": "ok",
            }
            json.dump(_man, open(_mp, "w"), indent=2)
        except Exception as _rme:
            log(f"  freshness_manifest regime_timeseries upsert skipped: {_rme}")
    else:
        log("regime_timeseries.json skipped: classifications parquet not found")
except Exception as _rge:
    log(f"regime_timeseries.json skipped: {_rge}")


# ── AI earnings reviews: pre-bake the LLM cache so Vercel == Streamlit ─────────
# earnings_reviewer.py caches generated 8-K reviews to ai_earnings_cache.json,
# keyed {TICKER}_{filing_date}; each entry carries full_text + verdict + filing_date.
# Vercel has no live LLM key, so we copy the cache to earnings_reviews.json.
# INTEGRITY GUARD (handoff): an 8-K whose figures the parser couldn't extract yields
# a review full of "Not disclosed" fields (Intel's exhibit layout) — that is NOT real
# analysis, so we EXCLUDE such reviews (and any not ok / too-short) rather than ship an
# empty HOLD to a public portfolio piece. React keys lookups by {TICKER}_{reported-
# quarter YYYY-MM}, which won't equal the filing-date month — so besides the filing-date
# key we emit a per-ticker {TICKER}_LATEST (newest by filing_date), which is what the
# single-ticker Stock Detail view actually wants. Graceful skip when absent/empty.
def _is_empty_review(_txt):
    if not _txt or len(str(_txt).strip()) < 120:
        return True
    import re as _re
    return len(_re.findall(r"not disclosed|not in the provided 8-?k|not provided in|not specified|\bn/a\b",
                           str(_txt), _re.I)) >= 4
try:
    _ae_candidates = [
        os.path.join(ROOT, "ai_earnings_cache.json"),
        os.path.join(os.path.dirname(ROOT), "quant-historical", "ai_earnings_cache.json"),
    ]
    _ae_src = next((p for p in _ae_candidates if os.path.exists(p)), None)
    if _ae_src:
        _cache = json.load(open(_ae_src))
        _reviews = {}
        _latest = {}  # ticker -> (filing_date, review) newest kept
        _skipped = []
        for _k, _rv in (_cache or {}).items():
            if not isinstance(_rv, dict):
                continue
            _txt = _rv.get("full_text") or _rv.get("text") or ""
            if _rv.get("ok") is False or _is_empty_review(_txt):
                _skipped.append(_k)
                continue  # never bake unparsed/empty reviews
            _tk = str(_rv.get("ticker") or _k.split("_")[0]).upper()
            _fd = str(_rv.get("filing_date") or "")
            _reviews[_k] = _rv  # original {TICKER}_{filing_date} key
            if len(_fd) >= 7:
                _reviews[f"{_tk}_{_fd[:7]}"] = _rv  # filing-month alias
            if _tk and (_tk not in _latest or _fd > _latest[_tk][0]):
                _latest[_tk] = (_fd, _rv)
        for _tk, (_fd, _rv) in _latest.items():
            _reviews[f"{_tk}_LATEST"] = _rv
        json.dump(deep_clean(_reviews), open(f"{OUT}/earnings_reviews.json", "w"), indent=2)
        log(f"wrote earnings_reviews.json ({len(_cache)} cached, {len(_latest)} kept, "
            f"{len(_skipped)} skipped empty/unparsed{(' ' + ','.join(_skipped[:8])) if _skipped else ''}, "
            f"{len(_reviews)} keys, from {_ae_src})")
        try:
            _mp = f"{OUT}/freshness_manifest.json"
            _man = json.load(open(_mp)) if os.path.exists(_mp) else {}
            _man.setdefault("sources", {})["earnings_reviews"] = {
                "source": f"ai_earnings_cache.json ({os.path.basename(_ae_src)}) — pre-baked LLM 8-K reviews",
                "n_cached": len(_cache),
                "n_kept": len(_latest),
                "n_skipped_empty": len(_skipped),
                "note": "empty/unparsed reviews excluded; keyed {TICKER}_{filing-YYYY-MM} + {TICKER}_LATEST",
                "check_status": "ok",
            }
            json.dump(_man, open(_mp, "w"), indent=2)
        except Exception as _me:
            log(f"  freshness_manifest earnings_reviews upsert skipped: {_me}")
    else:
        log("earnings_reviews.json skipped: no ai_earnings_cache.json found "
            "(no reviews generated yet — populate via Streamlit Stock Detail)")
except Exception as e:
    log(f"earnings_reviews.json skipped: {e}")


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


# ── system_status.json: the landing page's single source of truth ──────────────
# The de-IP TRI-STAR landing reads this instead of the old hardcoded mock (which
# shipped a fake PPI 55 and a fabricated c78q P&L). Every field here traces to a
# real baked artifact or returns null/false honestly when the source is missing —
# NO invented values (DATA_INTEGRITY_STANDARD).
#   bake     : did THIS bake run, and when (fresh = this process reached here).
#   ppi      : the live c78q PPI (c78q.json ppi block) — score + level, verbatim.
#   c78q     : nextRebalance from the strategy state; pnl is null unless we can
#              mark live positions to a price newer than entry (we can't today:
#              positions are stale-marked and the baked chart closes predate the
#              2026-06-01 deployment) — so pnl stays null rather than fabricated.
#   engines  : binary = c78q P(beat) target as-of; return = MLPred effective date.
#              `current` = source dated within 10 days of this bake.
#   market   : a bake-time snapshot of the US session (rth/pre/after/closed). The
#              landing recomputes this client-side from the live clock; this is the
#              SSR/fallback default only.
try:
    from datetime import timezone as _tz
    try:
        from zoneinfo import ZoneInfo as _ZI
        _et_now = datetime.now(_tz.utc).astimezone(_ZI("America/New_York"))
    except Exception:
        _et_now = datetime.now(_tz.utc) - timedelta(hours=4)  # crude EDT fallback
    _bake_now = datetime.now()

    def _session(dt):
        # weekend → closed (market holidays handled client-side via calendar)
        if dt.weekday() >= 5:
            return "closed"
        _mins = dt.hour * 60 + dt.minute
        if 4 * 60 <= _mins < 9 * 60 + 30:   return "pre"
        if 9 * 60 + 30 <= _mins < 16 * 60:  return "rth"
        if 16 * 60 <= _mins < 20 * 60:      return "after"
        return "closed"

    def _is_current(iso_date, days=10):
        if not iso_date:
            return False, None
        try:
            _d = datetime.fromisoformat(str(iso_date)[:10])
            return (_bake_now - _d).days <= days, _d.strftime("%Y-%m-%d")
        except Exception:
            return False, None

    # --- PPI: computed LIVE/daily, DECOUPLED from the monthly c78q ETL. Inputs are
    # only live market data (SPY/VIX/VVIX from keyless Yahoo) + baked-universe breadth
    # — NO c78q.json, NO quant-historical — so it runs in CI on every bake (previously
    # CI lacked c78q.json, leaving system_status.ppi=None and the landing on a fallback).
    _ppi = {"score": None, "level": None}
    _ppi_as_of = None
    _ppi_breadth = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import ppi as _ppimod
        _uni = json.load(open(f"{OUT}/universe_floor0.json"))   # breadth from the rows we just baked
        _m50 = [(r.get("raw") or {}).get("momentum_vs_sma50") for r in _uni.get("rows", [])]
        _m50 = [v for v in _m50 if isinstance(v, (int, float))]
        _ppi_breadth = (100.0 * sum(1 for v in _m50 if v > 0) / len(_m50)) if _m50 else None
        _spy, _vix, _vvix = _ppimod.fetch_market()
        _pr = _ppimod.compute_ppi(_spy, _vix, _vvix, _ppi_breadth)
        if _pr:
            _ppi = {"score": _pr["score"], "level": _pr["level"]}
            _ppi_as_of = _bake_now.strftime("%Y-%m-%d")
            log(f"  PPI computed live: {_pr['score']} {_pr['level']} "
                f"(breadth {_ppi_breadth:.0f}% >50SMA, SPY {len(_spy or [])}d, VIX {len(_vix or [])}d)")
        else:
            log("  PPI: insufficient market data (SPY fetch failed?) — ppi stays null")
    except Exception as _pe:
        log(f"  PPI compute failed ({_pe}) — ppi stays null")

    # --- c78q STRATEGY data stays MONTHLY (nextRebalance, binary target as-of). When
    # c78q.json is absent (CI), these stay null — they do NOT block the decoupled PPI.
    _c78q = {"pnl": None, "nextRebalance": None}
    _binary_asof = None
    try:
        _c = json.load(open(f"{OUT}/c78q.json"))
        _st = _c.get("state") or {}
        _c78q["nextRebalance"] = _st.get("next_rebalance")
        _binary_asof = (_c.get("target") or {}).get("as_of")
    except Exception:
        pass

    # --- engine currency: binary = c78q target, return = mlpred effective date ----
    _mlpred_eff = _eff if "_eff" in dir() else None
    _bin_cur, _bin_d = _is_current(_binary_asof)
    _ret_cur, _ret_d = _is_current(_mlpred_eff)

    # --- per-strategy status: THE single declared source (2026-07-01 directive). ---
    # book_type comes from the ledger-driven strategy JSONs: "live" = broker-confirmed
    # positions; "paper" = signal-derived research book, never held at a broker.
    # Retired scouts (axia/horme/krasis): ledgers still advance as research scouts, but
    # holdings are redundant with the deployed sleeves (2026-06 combined-book audit) —
    # they are paper-only and excluded from every combined-book/basket view.
    _strategies = {}
    try:
        _kt = json.load(open(f"{OUT}/c78q.json")).get("target") or {}
        _strategies["katalepsis"] = {"book_type": _kt.get("book_type", "live"),
                                     "status": "deployed", "as_of": _kt.get("as_of")}
    except Exception:
        pass
    for _slug in ("aristeia", "auxo", "prosodos", "pronoia"):
        try:
            _ch = json.load(open(f"{OUT}/{_slug}_strategy.json")).get("current_holdings") or {}
            _sbt = _ch.get("book_type", "paper")
            _strategies[_slug] = {"book_type": _sbt,
                                  "status": "deployed" if _sbt == "live" else "paper-track (deployment deferred)",
                                  "as_of": _ch.get("as_of")}
        except Exception:
            pass
    for _slug in ("axia", "horme", "krasis"):
        _strategies[_slug] = {"book_type": "paper", "status": "research-scout, holdings-redundant"}

    # --- watchdog flag: ops/chain_watchdog.py (quant-historical) drops watchdog_status.json
    # into public/data on every run; fold it in so the landing HUD FRESH/STALE badge can
    # reflect pipeline health on the next bake. Absent file = watchdog state unknown (null).
    _watchdog = None
    try:
        if os.path.exists(f"{OUT}/watchdog_status.json"):
            _wd = json.load(open(f"{OUT}/watchdog_status.json"))
            _watchdog = {"ok": bool(_wd.get("ok")), "alerts": _wd.get("alerts") or [],
                         "checked_at": _wd.get("checked_at")}
    except Exception:
        pass

    _status = {
        "bake": {"fresh": True, "at": _bake_now.replace(microsecond=0).isoformat()},
        "engines": {
            "binary": {"current": _bin_cur, "asOf": _bin_d},
            "return": {"current": _ret_cur, "asOf": _ret_d},
        },
        "ppi": _ppi,
        "c78q": _c78q,
        "strategies": _strategies,
        "watchdog": _watchdog,
        "market": {"state": _session(_et_now)},
        "_meta": {
            "ppi_as_of": _ppi_as_of,
            "ppi_breadth_pct": round(_ppi_breadth, 1) if _ppi_breadth is not None else None,
            "source": "PPI computed live (SPY/VIX/VVIX + baked-universe breadth, decoupled from c78q); "
                      "c78q nextRebalance from monthly ETL; mlpred effective_date; US session snapshot",
            "pnl_note": "null — no live mark newer than entry; not fabricated",
        },
    }
    json.dump(deep_clean(_status), open(f"{OUT}/system_status.json", "w"), indent=2)
    log(f"wrote system_status.json (ppi={_ppi.get('score')} {_ppi.get('level')}, "
        f"market={_status['market']['state']}, mlpred_asof={_ret_d}, c78q_rebal={_c78q['nextRebalance']})")

    # keep the freshness manifest in sync (upsert, never clobber sibling entries)
    try:
        _mp = f"{OUT}/freshness_manifest.json"
        _man = json.load(open(_mp)) if os.path.exists(_mp) else {}
        _man.setdefault("sources", {})["system_status"] = {
            "source": "bake.py system_status block (c78q.json ppi+state, mlpred effective_date, US session snapshot)",
            "as_of": _bake_now.strftime("%Y-%m-%d"),
            "ppi": f"{_ppi.get('score')} {_ppi.get('level')} (live c78q PPI, as-of {_ppi_as_of})",
            "c78q_pnl": "null — no live mark newer than entry; not fabricated"
                        if _c78q["pnl"] is None else _c78q["pnl"],
            "consumed_by": "TRI-STAR landing (LandingDemoTab)",
            "check_status": "ok",
        }
        json.dump(_man, open(_mp, "w"), indent=2)
        log("  refreshed freshness_manifest.json: system_status")
    except Exception as _me:
        log(f"  freshness_manifest system_status upsert skipped: {_me}")
except Exception as e:
    log(f"system_status.json skipped: {e}")

# ── vintage stamps (audit §1.2): the 15 silent-staleness files get a top-level generated_at ──
# Rule: stamp ONLY files this run actually wrote (mtime >= bake start) — a kept-committed /
# pass-through file must never get a fresh stamp its content didn't earn. Every stamped file
# also gets a freshness_manifest.sources entry so the <AsOf> badge can read one source of truth.
try:
    _VINTAGE_FILES = [
        "universe_floor0.json", "universe_floor1.json", "universe_floor10.json",
        "quarterly.json", "snapshots.json", "quant_backtest.json", "earnings_reviews.json",
        "correlations_cache.json", "doppelganger.json", "etf.json", "market_static.json",
        "pundits.json", "help.json", "detail_timeseries_fv_excluded.json",
        "paper_track_event_pead.json",
    ]
    _vstamp = datetime.now().replace(microsecond=0).isoformat()
    _mp = f"{OUT}/freshness_manifest.json"
    _man = json.load(open(_mp)) if os.path.exists(_mp) else {}
    _man.setdefault("sources", {})
    _stamped, _skipped = [], []
    for _vf in _VINTAGE_FILES:
        _vp = os.path.join(OUT, _vf)
        _key = _vf[:-5]
        if not os.path.exists(_vp):
            _skipped.append(f"{_vf} (missing)")
            continue
        if os.path.getmtime(_vp) < BAKE_START_TS:
            # Not this run's output — never stamp it, but if its PRODUCER stamped it
            # (e.g. paper_track_event_pead.json), surface that vintage in the manifest.
            try:
                _pj = json.load(open(_vp, encoding="utf-8"))
                _pg = _pj.get("generated_at") if isinstance(_pj, dict) else None
            except Exception:
                _pg = None
            if _pg:
                _man["sources"][_key] = {"source": "producer-stamped (not written by bake)",
                                         "as_of": str(_pg)[:10], "generated_at": _pg,
                                         "check_status": "ok"}
                _skipped.append(f"{_vf} (producer-stamped {str(_pg)[:10]} - manifest updated)")
            else:
                _skipped.append(f"{_vf} (not regenerated this run - left unstamped)")
            continue
        try:
            _vj = json.load(open(_vp, encoding="utf-8"))
        except Exception:
            _skipped.append(f"{_vf} (unreadable)")
            continue
        if isinstance(_vj, dict):
            if not _vj.get("generated_at"):
                _vj["generated_at"] = _vstamp
                json.dump(_vj, open(_vp, "w"), separators=(",", ":"))
            _stamped.append(_vf)
        else:
            # list-shaped (detail_timeseries_fv_excluded): can't stamp in-file without a
            # shape change — the manifest entry below carries its vintage instead.
            _stamped.append(f"{_vf} (manifest-only, list shape)")
        _man["sources"][_key] = {"source": "bake.py vintage pass", "as_of": _vstamp[:10],
                                 "generated_at": _vstamp, "check_status": "ok"}
    _man["generated_at"] = _vstamp
    json.dump(_man, open(_mp, "w"), indent=2)
    log(f"vintage pass: stamped {len(_stamped)} files, skipped {len(_skipped)} "
        f"({'; '.join(_skipped) if _skipped else 'none'})")
except Exception as e:
    log(f"vintage pass skipped: {e}")

log("DONE")
