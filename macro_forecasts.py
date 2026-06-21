"""
Macro Forecasts — cross-institution economic outlook for the Quant Dashboard.

Assembles a "Forecast Consensus" panel + the FOMC dot plot from official,
free, refreshable data sources. The product value is the *spread* across
forecasters that none of them publishes on its own.

Sources (live-first, graceful-null on failure — NEVER fabricate):
  • Federal Reserve SEP   FRED Release 326 (keyed API). Full real multi-year
                          grid: median / central-tendency / range for the
                          fed funds rate, real GDP, unemployment, PCE inflation.
                          This also powers the dot plot. (4×/yr)
  • World Bank GEP        Data360 WB_GEP dataset (no key). Real GDP growth. (2×/yr)
  • IMF WEO               DataMapper API, best-effort (often IP-gated from CI;
                          returns null rather than invented numbers). (~4×/yr)
  • CBO                   GitHub mirror (US-CBO), best-effort. (~annual)
  • House views           Bank/strategist outlooks (JPM, Wells Fargo, …) are
                          narrative PDFs with no feed — curated, dated snapshots
                          loaded from macro_house_views.json (same model as the
                          existing pundits cache). Empty until curated; never faked.

Every forecaster row carries {source, as_of, live} so the UI shows provenance
honestly and the freshness manifest can audit it. Run standalone to test:
    python macro_forecasts.py            # prints a summary + writes the JSON next to it
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional

# Reuse certifi's trust store if available so api.imf.org / data360 TLS verifies
# on hosts whose default store is incomplete (Windows). Falls back to the default
# context; we never disable verification.
try:
    import certifi  # type: ignore
    _SSL_CTX: Optional[ssl.SSLContext] = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = None

_UA = "Mozilla/5.0 (compatible; QuantDashboard/2.0; +macro_forecasts)"

# Metrics tracked across forecasters. Sparse by nature — each forecaster fills
# only the cells it actually publishes; the rest stay null (shown as "—").
METRICS = ["gdp", "inflation", "unemployment", "fed_funds", "sp500_target"]
METRIC_LABELS = {
    "gdp": "Real GDP",
    "inflation": "Inflation",
    "unemployment": "Unemployment",
    "fed_funds": "Fed Funds (YE)",
    "sp500_target": "S&P 500 Target",
}
METRIC_UNITS = {
    "gdp": "% y/y", "inflation": "% y/y", "unemployment": "%",
    "fed_funds": "%", "sp500_target": "level",
}


def _get(url: str, timeout: int = 25, accept: str = "application/json") -> Optional[str]:
    """GET → text, or None on any failure (status, timeout, TLS, DNS)."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def _fred_key() -> Optional[str]:
    return os.environ.get("FRED_API_KEY")


# ───────────────────────────────────────────────────────────────────────────
# 1) Federal Reserve — Summary of Economic Projections (FRED Release 326)
#    The star source: a real, fully-machine-readable multi-year SEP grid.
# ───────────────────────────────────────────────────────────────────────────

# Median projection series, by metric. Each is ANNUAL: one observation per
# projected year (obs date = the year), value = the median FOMC dot. The latest
# vintage carries the current + next two years; *MDLR carries the longer run.
_SEP_MEDIAN = {
    "fed_funds":    "FEDTARMD",
    "gdp":          "GDPC1MD",
    "unemployment": "UNRATEMD",
    "inflation":    "PCECTPIMD",   # Fed projects PCE inflation (not CPI)
}
_SEP_LONGRUN = {
    "fed_funds":    "FEDTARMDLR",
    "gdp":          "GDPC1MDLR",
    "unemployment": "UNRATEMDLR",
    "inflation":    "PCECTPIMDLR",
}
# Fed funds central tendency + range (for the dot-plot bands)
_SEP_BANDS = {
    "ct_high": "FEDTARCTH", "ct_low": "FEDTARCTL",
    "range_high": "FEDTARRH", "range_low": "FEDTARRL",
}


# FRED access is KEYLESS-FIRST: the public fredgraph.csv endpoint returns the same
# data (incl. the latest SEP multi-year grid) without an API key, so this works in
# CI where no FRED_API_KEY secret is set — matching how bake.py fetches CPI/Unemp.
# The keyed API is used only as an optional enhancement for the precise SEP vintage.
def _fred_csv_rows(series_id: str, retries: int = 3) -> List[tuple]:
    """[(date, value_float), ...] for a series via the keyless CSV, missing dropped."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    for _ in range(retries):
        txt = _get(url, accept="text/csv")
        if not txt:
            continue
        out = []
        for line in txt.strip().split("\n")[1:]:
            parts = line.split(",")
            if len(parts) < 2 or parts[1] in ("", "."):
                continue
            try:
                out.append((parts[0], float(parts[1])))
            except ValueError:
                continue
        if out:
            return out
    return []


def _year_map(series_id: str) -> Dict[str, float]:
    """{'2026': 3.8, ...} from a FRED series (keyless), keyed by observation year."""
    return {d[:4]: v for d, v in _fred_csv_rows(series_id)}


def _fred_latest(series_id: str) -> Optional[tuple]:
    """(date, value) of the newest observation, or None."""
    rows = _fred_csv_rows(series_id)
    return rows[-1] if rows else None


def _sep_asof() -> Optional[str]:
    """Precise latest SEP release date via the keyed ALFRED endpoint (key optional)."""
    key = _fred_key()
    if not key:
        return None
    txt = _get(f"https://api.stlouisfed.org/fred/series/vintagedates?series_id=FEDTARMD"
               f"&api_key={key}&file_type=json&sort_order=desc&limit=1")
    if not txt:
        return None
    try:
        vds = json.loads(txt).get("vintage_dates") or []
        return vds[0] if vds else None
    except Exception:
        return None


def _sep_asof_heuristic() -> str:
    """Coarse SEP date when keyless: the most recent quarterly FOMC-projection month
    (Mar/Jun/Sep/Dec). Labelled approximate by the caller's source string."""
    now = datetime.now()
    sep_months = [m for m in (3, 6, 9, 12) if m <= now.month]
    m = sep_months[-1] if sep_months else 12
    y = now.year if sep_months else now.year - 1
    return f"{y}-{m:02d}"


def fetch_fred_sep() -> Optional[Dict]:
    """Full SEP: a forecaster row (median path per metric) + the dot-plot bands.

    Keyless-first (works in CI). Returns {"row":..., "dot_plot":...} or None.
    """
    medians = {m: _year_map(sid) for m, sid in _SEP_MEDIAN.items()}
    if not medians.get("fed_funds"):
        return None  # core series missing → treat the whole SEP as unavailable

    # Longer-run = a single most-recent value per metric (the CSV is oldest→newest,
    # so take the latest observation, not the first).
    longrun = {m: (_fred_latest(sid) or (None, None))[1] for m, sid in _SEP_LONGRUN.items()}
    as_of = _sep_asof() or _sep_asof_heuristic()

    # Forecaster row: median projection per metric, keyed by year (forward years only).
    cur_year = datetime.now().year
    fwd_years = [str(cur_year), str(cur_year + 1), str(cur_year + 2)]
    row_values: Dict[str, Dict[str, float]] = {}
    for m in ("gdp", "inflation", "unemployment", "fed_funds"):
        ym = medians.get(m, {})
        cells = {y: ym[y] for y in fwd_years if y in ym}
        # fold the longer-run median in under a "LR" pseudo-year
        if longrun.get(m) is not None:
            cells["LR"] = longrun[m]
        if cells:
            row_values[m] = cells
    row_values["sp500_target"] = {}  # the Fed does not project equities

    fed_row = {
        "id": "fed_sep", "name": "Federal Reserve (SEP)", "kind": "official",
        "live": True, "as_of": as_of, "source": "FRED Release 326 (FOMC SEP)",
        "url": "https://fred.stlouisfed.org/release?rid=326",
        "notes": "Inflation = PCE (the Fed's gauge), not CPI. Median dot per year.",
        "values": row_values,
    }

    # Dot plot: median + central-tendency band + full range, for fed funds.
    bands = {k: _year_map(sid) for k, sid in _SEP_BANDS.items()}
    lr_ff = longrun.get("fed_funds")
    years = list(fwd_years)
    median_path = [medians["fed_funds"].get(y) for y in years]
    if lr_ff is not None:
        years.append("Longer Run")
        median_path.append(lr_ff)

    def _band(key_name: str) -> List[Optional[float]]:
        vals = [bands.get(key_name, {}).get(y) for y in fwd_years]
        if lr_ff is not None:  # no published band for the longer-run column
            vals.append(None)
        return vals

    target_range = _fred_target_range()
    dot_plot = {
        "live": True, "as_of": as_of, "source": "FRED Release 326 (FOMC SEP)",
        "url": "https://fred.stlouisfed.org/release?rid=326",
        "years": years,
        "median": median_path,
        "central_tendency": {"high": _band("ct_high"), "low": _band("ct_low")},
        "range": {"high": _band("range_high"), "low": _band("range_low")},
        "current_target_range": target_range.get("range_str") if target_range else None,
        "current_target_mid": target_range.get("mid") if target_range else None,
    }
    return {"row": fed_row, "dot_plot": dot_plot}


def _fred_target_range() -> Optional[Dict]:
    """Current fed funds target range (DFEDTARU/DFEDTARL, keyless) → {lower, upper, mid, range_str}."""
    up = _fred_latest("DFEDTARU")
    lo = _fred_latest("DFEDTARL")
    if not up or not lo:
        return None
    l, u = lo[1], up[1]
    return {"lower": l, "upper": u, "mid": round((u + l) / 2, 3), "range_str": f"{l:.2f}%-{u:.2f}%"}


# ───────────────────────────────────────────────────────────────────────────
# 2) World Bank — Global Economic Prospects (Data360 WB_GEP, no key)
# ───────────────────────────────────────────────────────────────────────────

def fetch_worldbank_gep() -> Optional[Dict]:
    """World Bank GEP real GDP growth for the US (the only metric WB_GEP exposes)."""
    url = ("https://data360api.worldbank.org/data360/data?DATABASE_ID=WB_GEP"
           "&INDICATOR=WB_GEP_NYGDPMKTPKDZ&REF_AREA=USA&per_page=30")
    txt = _get(url)
    if not txt:
        return None
    try:
        rows = json.loads(txt).get("value", [])
    except Exception:
        return None
    cur_year = datetime.now().year
    gdp: Dict[str, float] = {}
    for v in rows:
        t, val = str(v.get("TIME_PERIOD", "")), v.get("OBS_VALUE")
        if t.isdigit() and int(t) >= cur_year and val not in (None, ""):
            try:
                gdp[t] = round(float(val), 1)
            except ValueError:
                continue
    if not gdp:
        return None
    return {
        "id": "worldbank_gep", "name": "World Bank (GEP)", "kind": "official",
        "live": True, "as_of": _wb_gep_release(cur_year), "source": "World Bank Data360 WB_GEP",
        "url": "https://data360.worldbank.org/en/dataset/WB_GEP",
        "notes": "GEP publishes GDP growth forecasts (no CPI/unemployment in this dataset).",
        "values": {"gdp": gdp},
    }


def _wb_gep_release(year: int) -> str:
    """GEP ships in January and June; label with whichever is the latest passed."""
    return f"{year}-06" if datetime.now().month >= 6 else f"{year}-01"


# ───────────────────────────────────────────────────────────────────────────
# 3) IMF WEO — DataMapper API (best-effort; null when IP-gated, never invented)
# ───────────────────────────────────────────────────────────────────────────

# DataMapper indicator codes: NGDP_RPCH = real GDP growth, PCPIPCH = CPI inflation,
# LUR = unemployment rate. One call returns all years for a country.
_IMF_INDICATORS = {"gdp": "NGDP_RPCH", "inflation": "PCPIPCH", "unemployment": "LUR"}


def fetch_imf_weo() -> Optional[Dict]:
    """IMF WEO US forecasts via DataMapper. Returns null on failure (no fabrication)."""
    got: Dict[str, Dict[str, float]] = {}
    cur_year = datetime.now().year
    for metric, code in _IMF_INDICATORS.items():
        txt = _get(f"https://www.imf.org/external/datamapper/api/v1/{code}/USA")
        if not txt:
            continue
        try:
            series = json.loads(txt).get("values", {}).get(code, {}).get("USA", {})
        except Exception:
            continue
        cells = {}
        for y, val in series.items():
            if y.isdigit() and int(y) >= cur_year and val is not None:
                try:
                    cells[y] = round(float(val), 1)
                except (ValueError, TypeError):
                    continue
        if cells:
            got[metric] = cells
    if not got:
        return None
    return {
        "id": "imf_weo", "name": "IMF (WEO)", "kind": "official",
        "live": True, "as_of": _imf_weo_release(), "source": "IMF WEO (DataMapper)",
        "url": "https://www.imf.org/en/Publications/WEO",
        "notes": "Inflation = CPI. WEO full update Apr/Oct, interim Jan/Jul.",
        "values": got,
    }


def _imf_weo_release() -> str:
    m = datetime.now().month
    y = datetime.now().year
    # most recent of the Apr / Oct full databases
    return f"{y}-10" if m >= 10 else (f"{y}-04" if m >= 4 else f"{y - 1}-10")


# ───────────────────────────────────────────────────────────────────────────
# 4) Curated house views (banks/strategists) + CBO snapshot.
#    Real published, dated figures only — loaded from macro_house_views.json.
#    Absent file → no rows (honest), never invented.
# ───────────────────────────────────────────────────────────────────────────

HOUSE_VIEWS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "macro_house_views.json")


def load_house_views() -> List[Dict]:
    """Curated forecaster rows (JPM, Wells Fargo, CBO snapshot, …) from disk.

    Schema per row mirrors the live rows: {id, name, kind, as_of, source, url,
    notes, values:{metric:{year:val}}}. `live` is forced False (these are
    point-in-time snapshots a human curates from the published PDFs/files).
    """
    if not os.path.exists(HOUSE_VIEWS_FILE):
        return []
    try:
        data = json.load(open(HOUSE_VIEWS_FILE))
    except Exception:
        return []
    rows = data.get("forecasters", []) if isinstance(data, dict) else data
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("id") or not r.get("values"):
            continue
        r = dict(r)
        r["live"] = False
        r.setdefault("kind", "house")
        out.append(r)
    return out


# ───────────────────────────────────────────────────────────────────────────
# Macro-signal snapshot (keyless) — yield curve, credit spreads, breakevens,
# jobless claims. Mirrors fred_data.get_macro_signals() but keyless so it
# populates in CI (no FRED_API_KEY secret). Powers the Market Regime additions.
# ───────────────────────────────────────────────────────────────────────────

def build_macro_signals() -> Dict:
    """Latest value + date per free macro-signal series, fetched keyless."""
    from fred_data import MACRO_SIGNALS  # single source of truth for the series list
    out, newest = [], ""
    for sid, label, unit, risk_dir in MACRO_SIGNALS:
        latest = _fred_latest(sid)
        if not latest:
            continue
        d, v = latest
        if sid == "ICSA":  # persons → thousands for display
            v = round(v / 1000.0, 1)
        out.append({"id": sid, "label": label, "unit": unit, "risk_dir": risk_dir,
                    "value": round(v, 3), "date": d})
        if d > newest:
            newest = d
    return {"signals": out, "as_of": newest or None, "source": "FRED (keyless fredgraph)"}


# ───────────────────────────────────────────────────────────────────────────
# Assembly
# ───────────────────────────────────────────────────────────────────────────

def build_macro_forecasts() -> Dict:
    """Assemble the full macro_forecasts payload. Each source is best-effort."""
    forecasters: List[Dict] = []
    dot_plot: Optional[Dict] = None
    sources: List[Dict] = []

    sep = fetch_fred_sep()
    if sep:
        forecasters.append(sep["row"])
        dot_plot = sep["dot_plot"]

    for fetch in (fetch_worldbank_gep, fetch_imf_weo):
        try:
            row = fetch()
        except Exception:
            row = None
        if row:
            forecasters.append(row)

    forecasters.extend(load_house_views())

    # Table columns: the near-term window (current year + next two) — the SEP
    # horizon and where forecasters actually overlap. IMF's out-years (e.g.
    # 2029–31) stay in each row's raw values but don't bloat the comparison grid.
    present = set()
    for f in forecasters:
        for cells in f.get("values", {}).values():
            present.update(k for k in cells if k != "LR")
    cur = datetime.now().year
    year_cols = [str(y) for y in range(cur, cur + 3) if str(y) in present]

    for f in forecasters:
        sources.append({"id": f["id"], "name": f["name"], "as_of": f.get("as_of"),
                        "live": f.get("live", False), "source": f.get("source"),
                        "url": f.get("url"), "kind": f.get("kind")})

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "consensus": {
            "metrics": METRICS,
            "metric_labels": METRIC_LABELS,
            "metric_units": METRIC_UNITS,
            "years": year_cols,
            "forecasters": forecasters,
        },
        "dot_plot": dot_plot,
        "sources": sources,
        "integrity_note": ("Live rows fetched at bake time; curated rows are dated "
                           "snapshots of published outlooks. Missing cells are null, "
                           "never invented (DATA_INTEGRITY_STANDARD)."),
    }


if __name__ == "__main__":
    payload = build_macro_forecasts()
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "macro_forecasts_preview.json")
    json.dump(payload, open(out_path, "w"), indent=2)
    c = payload["consensus"]
    print(f"forecasters: {len(c['forecasters'])}  | year cols: {c['years']}")
    for f in c["forecasters"]:
        live = "live" if f.get("live") else "snap"
        cov = ",".join(k for k in f["values"] if f["values"][k])
        print(f"  [{live}] {f['name']:24s} as_of={f.get('as_of')}  covers: {cov}")
    dp = payload["dot_plot"]
    if dp:
        print(f"dot plot ({dp['as_of']}): years={dp['years']} median={dp['median']} "
              f"range={dp['current_target_range']}")
    print(f"wrote {out_path}")
