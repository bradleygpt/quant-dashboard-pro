"""Build quarterly_deep.json v2: ~4 years of quarterly revenue / net income /
diluted EPS / shares outstanding / market cap per ticker, from the local EDGAR
companyfacts cache (edgar_cache/{T}_facts.json).

v1 (2026-07-20) fixed the one-bar YoY chart (depth). v2 (2026-07-21, earnings-chart
rework) adds the EPS-bars + market-cap-line substrate:

  epsDiluted   Reported diluted EPS (EarningsPerShareDiluted), SPLIT-ADJUSTED to the
               current share basis (as-reported EPS is not split-adjusted; the
               cumulative factor of splits AFTER the quarter end divides it). Direct
               80-100d entries; Q4 = FY − ΣQ1..Q3 within the fiscal year when the
               direct entry is absent — such points carry epsDerived=true and the
               tooltip must say so (never derived-and-silent).
  sharesOut    Shares outstanding AS OF that quarter (dei EntityCommonStockShares-
               Outstanding cover-page value nearest after quarter end, fallback
               us-gaap instant/weighted-diluted), converted to the CURRENT basis —
               never the current count backfilled (buybacks/dilution history).
  mcapB        Quarter-end close (adjusted/current basis, from the quant-historical
               daily panel; yfinance fallback for names not yet in the panel)
               × current-basis sharesOut. Price and shares in the SAME basis.

Split source: yfinance .splits per ticker, cached in splits_cache.json (splits are
rare; --refresh-splits re-fetches all).

Output: quarterly_deep.json at the repo root (committed), newest first per ticker:
  { "TICKER": [ {date, revenue, netIncome, epsDiluted, epsDerived?, sharesOut,
                 mcapB}, ... ], "generated_at": iso }

Run locally (needs edgar_cache/ + the quant-historical panel):
  python build_quarterly_deep.py [--refresh-splits]
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

from edgar_fundamentals import CONCEPT_MAPPING

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT, "edgar_cache")
OUT_PATH = os.path.join(ROOT, "quarterly_deep.json")
FUND_CACHE = os.path.join(ROOT, "fundamentals_cache.json")
SPLITS_CACHE = os.path.join(ROOT, "splits_cache.json")
PANEL = r"C:\Users\bmhar\code\quant-historical\stage5_output\daily_panel_CLEAN.parquet"

MAX_QUARTERS = 18          # 13 displayed + 4 for the YoY base + 1 slack
MAX_AGE_DAYS = 54 * 30 + 15  # ignore quarters older than ~4.5 years
MAX_PRICE_FALLBACK = 25    # yfinance price fetches for panel-absent names (CRDO/LITE...)

CONCEPTS = {"revenue": "revenue", "netIncome": "net_income"}
EPS_TAG = "EarningsPerShareDiluted"
SHARES_DEI = "EntityCommonStockSharesOutstanding"
SHARES_FALLBACKS = ["CommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding"]


def _parse_d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _entries(node, unit):
    for e in (node or {}).get("units", {}).get(unit, []) or []:
        end = _parse_d(e.get("end"))
        start = _parse_d(e.get("start"))
        filed = _parse_d(e.get("filed")) or date(1900, 1, 1)
        val = e.get("val")
        if end is not None and isinstance(val, (int, float)):
            yield start, end, filed, float(val)


def _quarters_for_concept(usgaap, tags):
    """{end_date: value} for one flow concept — direct 80-100d entries + cumulative
    differencing (recovers Q4 / YTD-only filers); latest filed wins; higher-priority
    tags never overwritten by lower ones."""
    out = {}
    for tag in tags:
        node = usgaap.get(tag)
        if not node:
            continue
        direct, latest = {}, {}
        for start, end, filed, val in _entries(node, "USD"):
            if start is None:
                continue
            if 80 <= (end - start).days <= 100:
                if end not in direct or filed > direct[end][0]:
                    direct[end] = (filed, val)
            k = (start, end)
            if k not in latest or filed > latest[k][0]:
                latest[k] = (filed, val)
        by_start = {}
        for (start, end), (_f, val) in latest.items():
            by_start.setdefault(start, []).append((end, val))
        derived = {}
        for start, evs in by_start.items():
            evs.sort()
            for (e1, v1), (e2, v2) in zip(evs, evs[1:]):
                if 80 <= (e2 - e1).days <= 100:
                    derived[e2] = v2 - v1
        for end, (_f, val) in direct.items():
            out.setdefault(end, val)
        for end, val in derived.items():
            out.setdefault(end, val)
    return out


def _eps_quarters(usgaap, splits):
    """{end: (eps_current_basis, derived)} — direct 80-100d diluted EPS, plus
    Q4 = FY − ΣQ1..3 (flagged derived).

    BASIS RULE (the NVDA 10:1 verification caught this): GAAP restates prior-period
    EPS in later filings' comparative columns, so the same quarter-end appears in
    MULTIPLE share bases. An entry's basis is the basis at its FILED date — convert
    every entry to the CURRENT basis (val / splits-after-filed) BEFORE any
    latest-filed selection or FY derivation. Adjusting by quarter end instead
    double-divides restated entries; mixing bases corrupts derived Q4s."""
    node = usgaap.get(EPS_TAG)
    if not node:
        return {}
    direct, fy = {}, {}
    for start, end, filed, val in _entries(node, "USD/shares"):
        if start is None:
            continue
        adj = val / factor_after(filed, splits)
        period = (end - start).days
        if 80 <= period <= 100:
            if end not in direct or filed > direct[end][0]:
                direct[end] = (filed, adj)
        elif 350 <= period <= 380:
            k = (start, end)
            if k not in fy or filed > fy[k][0]:
                fy[k] = (filed, adj)
    out = {end: (val, False) for end, (_f, val) in direct.items()}
    for (start, end), (_f, fyval) in fy.items():
        if end in out:
            continue
        inside = [v for e, (_fl, v) in direct.items() if start <= e < end]
        if len(inside) == 3:
            out[end] = (fyval - sum(inside), True)
    return out


def _shares_series(facts):
    """[(asof_date, shares)] ascending — dei cover-page count preferred, us-gaap
    instant / weighted-diluted fallback. Values are in the basis OF THEIR DATE."""
    for section, tag in ([("dei", SHARES_DEI)] +
                         [("us-gaap", t) for t in [SHARES_DEI] + SHARES_FALLBACKS]):
        node = (facts.get("facts", {}).get(section, {}) or {}).get(tag)
        if not node:
            continue
        latest = {}
        for start, end, filed, val in _entries(node, "shares"):
            if val <= 0:
                continue
            if end not in latest or filed > latest[end][0]:
                latest[end] = (filed, val)
        if latest:
            return sorted((d, v) for d, (_f, v) in latest.items())
    return []


# ── splits (yfinance, cached — splits are rare) ─────────────────────────────
def load_splits(tickers, refresh=False):
    cache = {}
    if os.path.exists(SPLITS_CACHE) and not refresh:
        cache = json.load(open(SPLITS_CACHE))
    missing = [t for t in tickers if t not in cache]
    if missing:
        import yfinance as yf
        print(f"fetching splits for {len(missing)} tickers...", file=sys.stderr)
        for i, tk in enumerate(missing, 1):
            try:
                s = yf.Ticker(tk).splits
                cache[tk] = [[str(d.date()), float(r)] for d, r in s.items() if r and r > 0]
            except Exception:
                cache[tk] = []
            if i % 100 == 0:
                print(f"  splits {i}/{len(missing)}", file=sys.stderr)
            time.sleep(0.25)
        json.dump(cache, open(SPLITS_CACHE, "w"))
    return cache


def factor_after(d, splits):
    """Cumulative split factor for splits strictly AFTER date d (current basis =
    old basis × factor)."""
    f = 1.0
    for sd, ratio in splits:
        if _parse_d(sd) > d:
            f *= ratio
    return f


# ── quarter-end adjusted close (panel first, yfinance fallback) ─────────────
class PriceStore:
    def __init__(self):
        self.panel = None
        self.fallback = {}
        self.fallback_count = 0

    def _load_panel(self):
        if self.panel is None:
            import pandas as pd
            print("loading price panel...", file=sys.stderr)
            dp = pd.read_parquet(PANEL, columns=["ticker", "date", "adj_close"])
            dp["date"] = pd.to_datetime(dp["date"]).dt.date
            self.panel = {tk: g.sort_values("date")[["date", "adj_close"]].values.tolist()
                          for tk, g in dp.groupby("ticker")}
        return self.panel

    def _yf_series(self, tk):
        if tk in self.fallback:
            return self.fallback[tk]
        if self.fallback_count >= MAX_PRICE_FALLBACK:
            self.fallback[tk] = []
            return []
        try:
            import yfinance as yf
            df = yf.Ticker(tk).history(period="5y", auto_adjust=True)
            self.fallback[tk] = [[d.date(), float(c)] for d, c in df["Close"].items()]
            self.fallback_count += 1
        except Exception:
            self.fallback[tk] = []
        return self.fallback[tk]

    def close_at(self, tk, end):
        rows = self._load_panel().get(tk) or self._yf_series(tk)
        best = None
        for d, c in rows:
            if d <= end and (best is None or d > best[0]):
                if (end - d).days <= 10:
                    best = (d, c)
        return best[1] if best else None


def build_ticker(tk, facts, splits, prices):
    usgaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    if not usgaap:
        return []
    series = {out_key: _quarters_for_concept(usgaap, CONCEPT_MAPPING[ck])
              for out_key, ck in CONCEPTS.items()}
    eps = _eps_quarters(usgaap, splits)
    shares = _shares_series(facts)
    ends = sorted(set().union(*[s.keys() for s in series.values()], eps.keys()), reverse=True)
    cutoff = date.today() - timedelta(days=MAX_AGE_DAYS)
    rows = []
    for end in ends:
        if end < cutoff or len(rows) >= MAX_QUARTERS:
            break
        row = {"date": end.isoformat(),
               "revenue": series["revenue"].get(end),
               "netIncome": series["netIncome"].get(end)}
        e = eps.get(end)
        if e is not None:
            # already converted to current basis per-entry (see _eps_quarters basis rule)
            row["epsDiluted"] = round(e[0], 4)
            if e[1]:
                row["epsDerived"] = True
        # shares as-of: cover-page date nearest AFTER quarter end (filing ~30-45d later);
        # tolerate up to 75d after, else nearest within 45d before
        cand_after = [(d, v) for d, v in shares if end <= d <= end + timedelta(days=75)]
        cand_before = [(d, v) for d, v in shares if end - timedelta(days=45) <= d < end]
        pick = min(cand_after)[0:2] if cand_after else (max(cand_before) if cand_before else None)
        if pick:
            sh_cur = pick[1] * factor_after(pick[0], splits)
            row["sharesOut"] = int(sh_cur)
            close = prices.close_at(tk, end)
            if close:
                row["mcapB"] = round(sh_cur * close / 1e9, 2)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-splits", action="store_true")
    a = ap.parse_args()

    tickers = sorted(json.load(open(FUND_CACHE)).keys()) if os.path.exists(FUND_CACHE) else []
    if not tickers:
        tickers = sorted(f[:-len("_facts.json")] for f in os.listdir(CACHE_DIR)
                         if f.endswith("_facts.json"))
    have_facts = [t for t in tickers if os.path.exists(os.path.join(CACHE_DIR, f"{t.upper()}_facts.json"))]
    splits_map = load_splits(have_facts, refresh=a.refresh_splits)
    prices = PriceStore()

    out, missing, empty = {}, 0, 0
    n_eps = n_mcap = 0
    for i, tk in enumerate(tickers, 1):
        p = os.path.join(CACHE_DIR, f"{tk.upper()}_facts.json")
        if not os.path.exists(p):
            missing += 1
            continue
        try:
            rows = build_ticker(tk, json.load(open(p)), splits_map.get(tk, []), prices)
        except Exception:
            rows = []
        if rows:
            out[tk] = rows
            if any("epsDiluted" in r for r in rows):
                n_eps += 1
            if any("mcapB" in r for r in rows):
                n_mcap += 1
        else:
            empty += 1
        if i % 200 == 0:
            print(f"  {i}/{len(tickers)}...", file=sys.stderr)

    out["generated_at"] = datetime.now().replace(microsecond=0).isoformat()
    json.dump(out, open(OUT_PATH, "w"))
    n = len(out) - 1
    print(f"wrote {OUT_PATH}: {n} tickers ({n_eps} with EPS, {n_mcap} with mcap; "
          f"{missing} no facts file, {empty} empty)")


if __name__ == "__main__":
    main()
