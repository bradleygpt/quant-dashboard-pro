"""
fcf_quality_run.py — I/O + driver for the FCF distortion engine (Layer 1).
Separated from the pure math (fcf_quality.compute_distortion) per the spec: EDGAR pulls the
point-in-time fundamentals, yfinance supplies price/market-cap (a quote, not a restatement-prone
line item), the loop assembles rows. `python fcf_quality_run.py [TICKERS...]` (default = sanity 5).
"""
from __future__ import annotations
import sys, math
from datetime import datetime

from fcf_quality import Inputs, compute_distortion, TAGS, VERSION
from edgar_fundamentals import get_cik_for_ticker, fetch_companyfacts, _get_ttm_value, _get_concept_value_at_date, CONCEPT_MAPPING


def fetch_inputs(ticker: str, target_date: datetime | None = None) -> Inputs:
    target = target_date or datetime.now()
    cik = get_cik_for_ticker(ticker)
    facts = fetch_companyfacts(ticker, cik) if cik else None

    def ttm(key):
        if not facts:
            return None
        r = _get_ttm_value(facts, TAGS[key], target)
        return r[0] if r else None

    ocf, sbc, cash_taxes, pretax = ttm("ocf"), ttm("sbc"), ttm("cash_taxes"), ttm("pretax_income")
    capex = ttm("capex")
    if capex is not None:
        capex = abs(capex)  # Payments* tags are outflow magnitudes; some filers sign them negative

    price = mcap = shares = None
    sector = None
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        fi = t.fast_info
        price = float(fi.get("lastPrice") or fi.get("last_price") or 0) or None
        mcap = float(fi.get("marketCap") or fi.get("market_cap") or 0) or None
        if price and mcap:
            shares = mcap / price
        try:
            sector = t.info.get("sector")
        except Exception:
            pass
    except Exception:
        pass

    return Inputs(ticker=ticker, sector=sector, price=price, shares=shares, market_cap=mcap,
                  ocf=ocf, capex=capex, sbc=sbc, cash_taxes=cash_taxes, pretax_income=pretax,
                  asof=target.strftime("%Y-%m-%d"))


def _b(x):  # $ -> $B string
    return "—" if x is None else f"{x/1e9:,.2f}"

def _pct(x):
    return "—" if x is None else f"{x*100:.1f}%"


def main(tickers):
    pairs = []  # (Inputs, row)
    for tk in tickers:
        try:
            inp = fetch_inputs(tk)
            pairs.append((inp, compute_distortion(inp)))
        except Exception as e:
            print(f"{tk}: FAILED {e!r}", file=sys.stderr)
    print(f"\nFCF QUALITY — distortion engine v{VERSION}  (EDGAR point-in-time TTM; SBC expensed)\n")
    hdr = f"{'TKR':5} {'OCF$B':>8} {'capex':>7} {'repFCF':>8} {'SBC$B':>7} {'trueFCF':>8} {'SBC/OCF':>8} {'SBC/mc':>7} {'repYld':>7} {'trueYld':>8} {'cashTax<21':>10} {'cmpl':>4}"
    print(hdr); print("-" * len(hdr))
    for inp, r in sorted(pairs, key=lambda p: (p[1]['sbc_pct_mktcap'] is None, -(p[1]['sbc_pct_mktcap'] or 0))):
        print(f"{r['ticker']:5} {_b(inp.ocf):>8} {_b(inp.capex):>7} {_b(r['fcf_reported']):>8} {_b(r['sbc']):>7} "
              f"{_b(r['fcf_fully_adjusted']):>8} {_pct(r['sbc_pct_ocf']):>8} "
              f"{_pct(r['sbc_pct_mktcap']):>7} {_pct(r['reported_fcf_yield']):>7} {_pct(r['true_fcf_yield']):>8} "
              f"{('flag' if r['cash_tax_below_normal'] else '—'):>10} {('Y' if r['fully_adjusted_complete'] else 'n'):>4}")
    print("\nRanked by SBC / market cap (the stable, thesis-aimed denominator).")
    print("repFCF = OCF-capex; trueFCF = repFCF-SBC (v1's defensible adjustment). cashTax<21 = cash tax running")
    print("below a 21% normal (FLAG only — not subtracted in v1; EDGAR cash-tax tags too inconsistent). WC + capdev = NA hooks.")
    if pairs:
        import json
        print("\n--- full row (first ticker, full schema) ---")
        print(json.dumps(pairs[0][1], indent=1, default=str))


if __name__ == "__main__":
    tks = [t.upper() for t in sys.argv[1:]] or ["AAPL", "GOOGL", "META", "CRM", "SNOW"]
    main(tks)
