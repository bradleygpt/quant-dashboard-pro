"""Build quarterly_deep.json: ~4 years of quarterly revenue / net income per ticker,
extracted from the local EDGAR companyfacts cache (edgar_cache/{T}_facts.json).

Why this exists (earnings-chart depth fix, 2026-07-20): the Stock Detail
"Quarterly Earnings & Revenue Growth (YoY)" chart computes YoY growth from
build_cache.py's quarterly_history, but yfinance quarterly statements only
reach back 5-6 quarters — so a YoY join (needs the same quarter one year back)
leaves exactly ONE renderable growth point per ticker and the chart shows a
single bar. EDGAR companyfacts carries the full filing history; this script
distills it to a small committed artifact the CI bake can merge (the 4+ GB
edgar_cache itself never ships to CI).

Output: quarterly_deep.json at the repo root (committed), shape
  { "TICKER": [ {"date": "YYYY-MM-DD", "revenue": float|None,
                 "netIncome": float|None}, ... newest first ],
    "generated_at": iso-stamp }

Extraction per concept (revenue, net_income — tag priority from
edgar_fundamentals.CONCEPT_MAPPING):
  - direct quarters: entries with an 80-100 day period (10-Q flows)
  - cumulative differencing: entries sharing a start date (Q2/Q3 YTD, FY)
    diffed against the previous end when the gap is 80-100 days — this is
    what recovers Q4 (FY minus 9-month YTD) and filers who only report YTD
  - direct beats derived; for the same quarter-end the latest `filed` wins
    (restatements); higher-priority tags win over lower ones
Run locally (needs edgar_cache/): python build_quarterly_deep.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

from edgar_fundamentals import CONCEPT_MAPPING

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT, "edgar_cache")
OUT_PATH = os.path.join(ROOT, "quarterly_deep.json")
FUND_CACHE = os.path.join(ROOT, "fundamentals_cache.json")

MAX_QUARTERS = 18          # 13 displayed + 4 for the YoY base + 1 slack
MAX_AGE_DAYS = 54 * 30 + 15  # ignore quarters older than ~4.5 years

CONCEPTS = {"revenue": "revenue", "netIncome": "net_income"}


def _parse_d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _quarters_for_concept(usgaap, tags):
    """Return {end_date: value} of quarterly values for one concept.

    Tag priority: a quarter-end already filled by an earlier (higher-priority)
    tag is never overwritten by a later tag. Within a tag, direct 80-100d
    entries beat cumulative-diff derivations, and later `filed` beats earlier.
    """
    out = {}
    for tag in tags:
        node = usgaap.get(tag)
        if not node:
            continue
        entries = []
        for e in node.get("units", {}).get("USD", []) or []:
            end = _parse_d(e.get("end"))
            start = _parse_d(e.get("start"))
            filed = _parse_d(e.get("filed")) or date(1900, 1, 1)
            val = e.get("val")
            if end is None or start is None or not isinstance(val, (int, float)):
                continue
            entries.append((start, end, filed, float(val)))

        # direct quarterly periods, latest filing wins per end-date
        direct = {}
        for start, end, filed, val in entries:
            period = (end - start).days
            if 80 <= period <= 100:
                if end not in direct or filed > direct[end][0]:
                    direct[end] = (filed, val)

        # cumulative differencing within a shared start date (recovers Q4 and
        # YTD-only filers). Use the latest filing per (start, end) first.
        by_start = {}
        latest = {}
        for start, end, filed, val in entries:
            k = (start, end)
            if k not in latest or filed > latest[k][0]:
                latest[k] = (filed, val)
        for (start, end), (_f, val) in latest.items():
            by_start.setdefault(start, []).append((end, val))

        derived = {}
        for start, evs in by_start.items():
            evs.sort()
            for (e1, v1), (e2, v2) in zip(evs, evs[1:]):
                gap = (e2 - e1).days
                if 80 <= gap <= 100:
                    derived[e2] = v2 - v1

        for end, (_f, val) in direct.items():
            out.setdefault(end, val)
        for end, val in derived.items():
            out.setdefault(end, val)
    return out


def build_ticker(facts):
    usgaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    if not usgaap:
        return []
    series = {out_key: _quarters_for_concept(usgaap, CONCEPT_MAPPING[ck])
              for out_key, ck in CONCEPTS.items()}
    ends = sorted(set().union(*[s.keys() for s in series.values()]), reverse=True)
    cutoff = date.today() - timedelta(days=MAX_AGE_DAYS)
    rows = []
    for end in ends:
        if end < cutoff or len(rows) >= MAX_QUARTERS:
            break
        rows.append({"date": end.isoformat(),
                     "revenue": series["revenue"].get(end),
                     "netIncome": series["netIncome"].get(end)})
    return rows


def main():
    tickers = sorted(json.load(open(FUND_CACHE)).keys()) if os.path.exists(FUND_CACHE) else []
    if not tickers:
        tickers = sorted(f[:-len("_facts.json")] for f in os.listdir(CACHE_DIR)
                         if f.endswith("_facts.json"))
    out, missing, empty = {}, 0, 0
    for i, tk in enumerate(tickers, 1):
        p = os.path.join(CACHE_DIR, f"{tk.upper()}_facts.json")
        if not os.path.exists(p):
            missing += 1
            continue
        try:
            rows = build_ticker(json.load(open(p)))
        except Exception:
            rows = []
        if rows:
            out[tk] = rows
        else:
            empty += 1
        if i % 200 == 0:
            print(f"  {i}/{len(tickers)}...", file=sys.stderr)

    out["generated_at"] = datetime.now().replace(microsecond=0).isoformat()
    json.dump(out, open(OUT_PATH, "w"))
    n = len(out) - 1
    sizes = sorted(len(v) for k, v in out.items() if k != "generated_at")
    med = sizes[len(sizes) // 2] if sizes else 0
    print(f"wrote {OUT_PATH}: {n} tickers (median {med} quarters; "
          f"{missing} no facts file, {empty} no extractable quarters)")


if __name__ == "__main__":
    main()
