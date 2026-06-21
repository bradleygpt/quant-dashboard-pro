"""
fcf_quality_universe.py — run the FCF distortion engine over the scored universe.
EDGAR for fundamentals (point-in-time TTM), BAKED universe rows for price/market-cap/sector
(no per-name yfinance — too slow/flaky at universe scale). Emits a ranked fcf_distortion.json
to the dashboards.  `python fcf_quality_universe.py [LIMIT]`  (LIMIT = test on first N names).
"""
from __future__ import annotations
import json, sys, time
from datetime import datetime
from pathlib import Path

from fcf_quality import Inputs, compute_distortion, TAGS, VERSION
from edgar_fundamentals import get_cik_for_ticker, fetch_companyfacts, _get_ttm_value

DASH = [Path(r"C:\Users\bmhar\code\quant-dashboard-pro-v2\public\data"),
        Path(r"C:\Users\bmhar\code\quant-dashboard-react\web\public\data")]
SRC = DASH[0]


def edgar_ttm(ticker: str, target: datetime) -> dict:
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return {}
    facts = fetch_companyfacts(ticker, cik)
    if not facts:
        return {}
    out = {}
    for key in ("ocf", "capex", "sbc", "cash_taxes", "pretax_income"):
        r = _get_ttm_value(facts, TAGS[key], target)
        out[key] = (r[0] if r else None)
    if out.get("capex") is not None:
        out["capex"] = abs(out["capex"])
    return out


def main(limit=None):
    target = datetime.now()
    rows_in = [r for r in json.load(open(SRC / "universe_floor0.json"))["rows"] if r.get("sector") != "ETF"]
    if limit:
        rows_in = rows_in[:limit]
    out, errors = [], 0
    t0 = time.time()
    for i, r in enumerate(rows_in):
        tk = r["ticker"]
        try:
            f = edgar_ttm(tk, target)
        except Exception:
            f = {}; errors += 1
        price, mc = r.get("price"), r.get("marketCap")
        shares = (mc / price) if (mc and price) else None
        inp = Inputs(ticker=tk, sector=r.get("sector"), price=price, shares=shares, market_cap=mc,
                     ocf=f.get("ocf"), capex=f.get("capex"), sbc=f.get("sbc"),
                     cash_taxes=f.get("cash_taxes"), pretax_income=f.get("pretax_income"),
                     asof=target.strftime("%Y-%m-%d"))
        d = compute_distortion(inp)
        d["name"] = r.get("name")
        out.append(d)
        if i % 50 == 0:
            print(f"  {i+1}/{len(rows_in)} {tk}  ({time.time()-t0:.0f}s, {errors} err)", file=sys.stderr)
        time.sleep(0.04)
    out.sort(key=lambda x: (x["sbc_pct_mktcap"] is None, -(x["sbc_pct_mktcap"] or 0)))
    n_sbc = sum(1 for x in out if x["sbc"] is not None)
    # slim rows for the client fetch (the panel + a future screen need ~these fields, not the
    # full nested schema) — keeps fcf_distortion.json ~halved.
    KEEP = ["ticker", "name", "sector", "market_cap", "fcf_reported", "fcf_fully_adjusted", "sbc",
            "sbc_pct_ocf", "sbc_pct_mktcap", "reported_fcf_yield", "true_fcf_yield",
            "total_distortion_usd", "total_distortion_pct_mktcap", "cash_tax_below_normal",
            "fully_adjusted_complete", "applicable", "exclude_reason"]
    payload = {"generated_at": target.strftime("%Y-%m-%d"), "version": VERSION,
               "n": len(out), "n_with_sbc": n_sbc, "sort": "sbc_pct_mktcap desc",
               "note": "true FCF = OCF-capex-SBC (SBC expensed). EDGAR point-in-time TTM; price/mktcap from the baked universe. Cash-tax flagged not subtracted (v1).",
               "rows": [{k: r.get(k) for k in KEEP} for r in out]}
    for repo in DASH:
        if repo.exists():
            json.dump(payload, open(repo / "fcf_distortion.json", "w"), separators=(",", ":"), default=str)
    print(f"DONE: {len(out)} names, {n_sbc} with SBC data, {errors} errors, {time.time()-t0:.0f}s", file=sys.stderr)
    # show the top 12 by SBC/mktcap
    print("\nTop 12 by SBC / market cap:", file=sys.stderr)
    for x in out[:12]:
        if x["sbc_pct_mktcap"] is not None:
            print(f"  {x['ticker']:6} SBC/mc {x['sbc_pct_mktcap']*100:4.1f}%  SBC/OCF {(x['sbc_pct_ocf'] or 0)*100:5.1f}%  repFCF {(x['fcf_reported'] or 0)/1e9:7.1f}B -> true {(x['fcf_fully_adjusted'] or 0)/1e9:7.1f}B", file=sys.stderr)


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(lim)
