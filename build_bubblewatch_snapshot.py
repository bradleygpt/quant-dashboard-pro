"""AI Bubble Watch monthly snapshot (handoff §4.1, 2026-07-20).

Design rule: data layer and commentary layer are separate; data NEVER depends
on AI. This writes a dated snapshot with raw inputs + computed indicators so
the page can chart the series as months accumulate.

Inputs (all free):
  - Hyperscaler capex: SEC companyfacts (PaymentsToAcquirePropertyPlantAndEquipment),
    quarterly via direct 80-100d periods + cumulative differencing (10-Q capex is
    fiscal-YTD), TTM = last 4 quarters. Live fetch of 6 tickers — CI-safe, no
    dependence on the local 4GB edgar_cache.
  - Valuations: yfinance fwd P/E / EV/S / mcap for the AI complex; omitted on
    fetch failure, never invented.
  - Credit: FRED HY OAS (BAMLH0A0HYM2) via the same keyless fredgraph.csv
    pattern the bake uses.
  - Composite: historical-analog framework recomputed on fresh inputs —
    components normalized against analog-era peaks (documented inline).

Outputs:
  bubblewatch/snapshots/<YYYY-MM>.json   (committed; bake ships them to the app)
  bubblewatch/queue/<YYYY-MM>.json       (commentary diff-dossier for Claude Code,
                                          same queue mechanism as theses/)

Usage: python build_bubblewatch_snapshot.py
Runs monthly via .github/workflows/refresh-bubblewatch.yml.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.join(ROOT, "bubblewatch", "snapshots")
QUEUE_DIR = os.path.join(ROOT, "bubblewatch", "queue")

HYPERSCALERS = ["MSFT", "AMZN", "GOOGL", "META", "ORCL", "NVDA"]
AI_COMPLEX = ["NVDA", "MSFT", "GOOGL", "AMZN", "META", "ORCL", "AVGO", "AMD", "TSM", "PLTR"]
CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets"]
UA = {"User-Agent": "QuantDashboard research bradleygpt (bmhartnett1990@gmail.com)"}

# Analog-era normalization anchors (documented, adjustable):
#   capex/GDP: late-1800s railway peak ~10% of GDP -> 100
#   valuation: median EV/S of the complex vs ~30x (dot-com large-cap peak zone) -> 100
#   credit: HY OAS 2.5% (max froth) -> 100, 10% (distress) -> 0
RAIL_PEAK_CAPEX_GDP_PCT = 10.0
DOTCOM_EVS_PEAK = 30.0
OAS_TIGHT, OAS_WIDE = 2.5, 10.0


def _get(url, timeout=30, retries=3):
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(1.5 * (a + 1))
    raise last


def cik_map():
    j = json.loads(_get("https://www.sec.gov/files/company_tickers.json"))
    return {v["ticker"].upper(): int(v["cik_str"]) for v in j.values()}


def _tag_quarters(node):
    """One tag's quarterly series {end: usd} — direct 80-100d periods + cumulative
    diffs (10-Q capex is fiscal-YTD; diffing recovers Q2-Q4)."""
    direct, latest = {}, {}
    for e in (node or {}).get("units", {}).get("USD", []) or []:
        try:
            s = date.fromisoformat(e["start"]); en = date.fromisoformat(e["end"])
            f = e.get("filed", ""); v = float(e["val"])
        except Exception:
            continue
        if 80 <= (en - s).days <= 100:
            if en not in direct or f > direct[en][0]:
                direct[en] = (f, v)
        k = (s, en)
        if k not in latest or f > latest[k][0]:
            latest[k] = (f, v)
    by_start = {}
    for (s, en), (_f, v) in latest.items():
        by_start.setdefault(s, []).append((en, v))
    out = {}
    for s, evs in by_start.items():
        evs.sort()
        for (e1, v1), (e2, v2) in zip(evs, evs[1:]):
            if 80 <= (e2 - e1).days <= 100:
                out[e2] = v2 - v1
    out.update({en: v for en, (_f, v) in direct.items()})
    return out


def quarterly_capex(cik):
    """Quarterly capex [(end_date, usd)]. Companies switch tags mid-history
    (AMZN/NVDA moved PP&E -> ProductiveAssets in 2017/2020), so merge across
    tags: the tag whose series extends latest wins any same-quarter overlap."""
    j = json.loads(_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"))
    us = j.get("facts", {}).get("us-gaap", {})
    series = [(tag, _tag_quarters(us.get(tag))) for tag in CAPEX_TAGS]
    series = [(t, q) for t, q in series if q]
    series.sort(key=lambda x: max(x[1]), reverse=True)
    out = {}
    for _tag, q in series:
        for en, v in q.items():
            out.setdefault(en, v)
    return sorted(out.items())


def fred_latest(sid):
    txt = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}").decode()
    rows = [ln.split(",") for ln in txt.strip().split("\n")[1:]]
    rows = [(d, float(v)) for d, v in rows if v not in ("", ".")]
    return rows[-1] if rows else None


def yf_valuations():
    try:
        import yfinance as yf
    except ImportError:
        return {}
    out = {}
    for tk in AI_COMPLEX:
        try:
            info = yf.Ticker(tk).info or {}
            out[tk] = {
                "fwd_pe": info.get("forwardPE"),
                "ev_s": info.get("enterpriseToRevenue"),
                "mcap_bn": round(info["marketCap"] / 1e9, 1) if info.get("marketCap") else None,
            }
            time.sleep(0.6)
        except Exception:
            out[tk] = {"fwd_pe": None, "ev_s": None, "mcap_bn": None}
    return out


def main():
    os.makedirs(SNAP_DIR, exist_ok=True)
    os.makedirs(QUEUE_DIR, exist_ok=True)
    month = datetime.now().strftime("%Y-%m")

    print("fetching SEC capex...", file=sys.stderr)
    cmap = cik_map()
    capex = {}
    for tk in HYPERSCALERS:
        cik = cmap.get(tk)
        try:
            q = quarterly_capex(cik) if cik else []
        except Exception as e:
            print(f"  {tk}: capex fetch failed ({e}) — omitted", file=sys.stderr)
            q = []
        recent = q[-8:]
        ttm = sum(v for _d, v in q[-4:]) / 1e9 if len(q) >= 4 else None
        capex[tk] = {
            "ttm_usd_bn": round(ttm, 1) if ttm else None,
            "quarters": [{"end": d.isoformat(), "usd_bn": round(v / 1e9, 2)} for d, v in recent],
        }
        time.sleep(0.4)

    print("fetching valuations (yfinance)...", file=sys.stderr)
    vals = yf_valuations()

    print("fetching HY OAS (FRED)...", file=sys.stderr)
    try:
        oas_date, oas = fred_latest("BAMLH0A0HYM2")
        credit = {"hy_oas_pct": oas, "asof": oas_date, "source": "FRED BAMLH0A0HYM2"}
    except Exception as e:
        credit = {"hy_oas_pct": None, "asof": None, "source": f"fetch failed: {e}"}

    # GDP for the capex share — same figure the bake uses (macro.MACRO_DATA)
    try:
        sys.path.insert(0, ROOT)
        import macro
        gdp_t = macro.MACRO_DATA.get("us_gdp_trillions", 29.7)
    except Exception:
        gdp_t = 29.7

    # ── composite (historical-analog framework recomputed on fresh inputs) ──
    comps = {}
    ttm_total = sum(c["ttm_usd_bn"] for c in capex.values() if c["ttm_usd_bn"])
    if ttm_total:
        pct_gdp = ttm_total / (gdp_t * 1000) * 100
        comps["capex_intensity"] = {
            "value": round(pct_gdp, 2), "unit": "% of GDP (hyperscaler TTM capex)",
            "score": round(min(100, pct_gdp / RAIL_PEAK_CAPEX_GDP_PCT * 100), 1),
            "anchor": f"railway-era peak ~{RAIL_PEAK_CAPEX_GDP_PCT}% of GDP = 100",
        }
    evs = sorted(v["ev_s"] for v in vals.values() if isinstance(v.get("ev_s"), (int, float)))
    if evs:
        med = evs[len(evs) // 2]
        comps["valuation"] = {
            "value": round(med, 1), "unit": "median EV/S of the AI complex",
            "score": round(min(100, med / DOTCOM_EVS_PEAK * 100), 1),
            "anchor": f"dot-com large-cap peak zone ~{DOTCOM_EVS_PEAK}x EV/S = 100",
        }
    if credit.get("hy_oas_pct") is not None:
        o = credit["hy_oas_pct"]
        comps["credit_froth"] = {
            "value": o, "unit": "HY OAS %",
            "score": round(max(0, min(100, 100 - (o - OAS_TIGHT) / (OAS_WIDE - OAS_TIGHT) * 100)), 1),
            "anchor": f"OAS {OAS_TIGHT}% (max froth) = 100, {OAS_WIDE}% (distress) = 0",
        }
    scores = [c["score"] for c in comps.values()]
    composite = {
        "reading": round(sum(scores) / len(scores), 1) if scores else None,
        "components": comps,
        "method": "unweighted mean of available component scores; components normalized to historical-analog peaks (anchors stored per component). Raw inputs stored so the composite can be recomputed under different anchors.",
    }

    snap = {
        "month": month,
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "capex": capex,
        "capex_ttm_total_bn": round(ttm_total, 1) if ttm_total else None,
        "valuations": vals,
        "credit": credit,
        "gdp_trillions_used": gdp_t,
        "composite": composite,
        "sources": {
            "capex": "SEC companyfacts PaymentsToAcquirePropertyPlantAndEquipment (10-Q/10-K, cumulative-diffed)",
            "valuations": "yfinance .info (fwd P/E, EV/S, mcap)",
            "credit": "FRED BAMLH0A0HYM2 (keyless CSV)",
        },
    }
    out = os.path.join(SNAP_DIR, f"{month}.json")
    json.dump(snap, open(out, "w"), indent=1)
    print(f"wrote {out} (composite {composite['reading']})")

    # ── commentary diff-dossier (§4.2 — same Claude Code queue mechanism as theses/) ──
    months = sorted(f[:-5] for f in os.listdir(SNAP_DIR) if f.endswith(".json"))
    prior = months[-2] if len(months) >= 2 else None
    six = months[-7] if len(months) >= 7 else (months[0] if months and months[0] != month else None)
    dossier = {
        "month": month,
        "built_at": snap["generated_at"],
        "this_month": snap,
        "last_month": json.load(open(os.path.join(SNAP_DIR, f"{prior}.json"))) if prior else "N/A",
        "six_month_ref": json.load(open(os.path.join(SNAP_DIR, f"{six}.json"))) if six else "N/A",
        "instructions": "Write bubblewatch/commentary/<YYYY-MM>.json: {month, generated_at, generator, summary (3-6 sentences), watch_items[2-4]}. Ground every claim in the diff numbers; no filler. See theses/PROMPT_PACK.md style bans.",
    }
    qout = os.path.join(QUEUE_DIR, f"{month}.json")
    json.dump(dossier, open(qout, "w"), indent=1)
    print(f"queued commentary dossier {qout}")


if __name__ == "__main__":
    main()
