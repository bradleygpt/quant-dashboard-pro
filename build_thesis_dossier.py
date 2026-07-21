"""Build a thesis dossier: a full snapshot of everything the baked app knows
about a ticker, written to theses/queue/<T>_<YYYYMMDD>.json.

This is the canonical enqueue for the Investment Thesis feature (handoff §2.1,
2026-07-20). The app's "Generate Thesis" button assembles the same shape
client-side and downloads it; either path lands the file in theses/queue/.
Generation then happens in Claude Code per theses/PROMPT_PACK.md — the app
never calls an LLM.

Missing inputs are "N/A", never 0 (standing convention). snapshot_hash is a
sha256 over the canonical inputs payload — the post-mortem substrate keys on it.

Usage: python build_thesis_dossier.py AAPL [NVDA ...]
"""
import hashlib
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "web", "public", "data")
QUEUE = os.path.join(ROOT, "theses", "queue")

NA = "N/A"


def _load(rel):
    try:
        return json.load(open(os.path.join(DATA, rel), encoding="utf-8"))
    except Exception:
        return None


def _shard_name(tk):
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    return (tk + "_") if tk.upper() in reserved else tk


def build_dossier(tk, universe, quarterly, c78q):
    rows = universe.get("rows") if isinstance(universe, dict) else universe
    row = next((r for r in rows if r.get("ticker") == tk), None) if rows else None
    if row is None:
        print(f"  {tk}: not in universe_floor0.json — skipped", file=sys.stderr)
        return None

    detail = _load(f"detail/floor0/{_shard_name(tk)}.json") or {}
    qhist = (quarterly or {}).get(tk) or NA

    # sector context: composite rank among same-sector names (default preset)
    sector = row.get("sector") or NA
    peers = [r for r in rows if r.get("sector") == sector]

    def _comp(r):
        # universe rows carry byPreset = {preset: {"c": composite, "r": rating}}
        bp = r.get("byPreset") or {}
        first = bp.get("equal") or (next(iter(bp.values())) if bp else None)
        if isinstance(first, dict):
            return first.get("c", first.get("composite"))
        return first

    comps = sorted((c for c in (_comp(r) for r in peers) if isinstance(c, (int, float))), reverse=True)
    my = _comp(row)
    sector_ctx = NA
    if comps and isinstance(my, (int, float)):
        sector_ctx = {
            "n_sector": len(comps),
            "rank_in_sector": comps.index(my) + 1 if my in comps else NA,
            "sector_median_composite": comps[len(comps) // 2],
        }

    # c78q book membership (posterior/rank per arbitrary ticker lives in local
    # signal caches, not the baked outputs — book position is what the app knows)
    c78q_ctx = NA
    if isinstance(c78q, dict):
        pos = (c78q.get("state") or {}).get("positions") or []
        hit = next((p for p in pos if (p.get("ticker") or p.get("symbol")) == tk), None)
        c78q_ctx = {"in_book": bool(hit), "position": hit or NA}

    # Book provenance at snapshot time (A2-addendum Task 3, S5): which LIVE strategy
    # books held this name when the dossier was built, with each book's as-of date.
    # A thesis must always read as "what the books were when this was written" —
    # unreconstructable later if not captured now. Empty list = none.
    books = []
    if isinstance(c78q, dict):
        t78 = c78q.get("target") or {}
        if t78.get("book_type") == "live" and tk in [r.get("ticker") for r in t78.get("rows", [])]:
            books.append({"book": "c78q", "label": "Katalepsis", "as_of": t78.get("as_of")})
    _ari = _load("aristeia_strategy.json")
    if isinstance(_ari, dict):
        ch = _ari.get("current_holdings") or {}
        if ch.get("book_type") == "live" and tk in (ch.get("tickers") or []):
            books.append({"book": "aristeia", "label": "Aristeia", "as_of": ch.get("as_of")})

    inputs = {
        "name": row.get("name", NA),
        "sector": sector,
        "industry": row.get("industry", NA),
        "price": row.get("price", NA),
        "market_cap_b": row.get("marketCapB", NA),
        "composite_by_preset": row.get("byPreset", NA),
        "pillars": row.get("pillars", NA),
        "grades": row.get("grades", NA),
        "raw_metrics": row.get("raw", NA),
        "fair_value": detail.get("fv", row.get("fv", NA)),
        "fv_premium_pct": row.get("fvPremium", NA),
        "fv_verdict": row.get("fvVerdict", NA),
        "buy_point": detail.get("qbp", row.get("qbp", NA)),
        "qbp_distance_pct": row.get("qbpDistance", NA),
        "qbp_signal": row.get("qbpSignal", NA),
        "pillar_detail": detail.get("pillar_detail", NA),
        "quarterly": qhist,
        "c78q": c78q_ctx,
        "books": books,
        "sector_context": sector_ctx,
    }
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), default=str)
    return {
        "ticker": tk,
        "built_at": datetime.now().replace(microsecond=0).isoformat(),
        "builder": "build_thesis_dossier.py v1",
        "snapshot_hash": hashlib.sha256(canonical.encode()).hexdigest()[:16],
        "inputs": inputs,
    }


def main():
    tickers = [t.upper() for t in sys.argv[1:]]
    if not tickers:
        print(__doc__, file=sys.stderr)
        raise SystemExit(1)
    os.makedirs(QUEUE, exist_ok=True)
    universe = _load("universe_floor0.json")
    if not universe:
        raise SystemExit("universe_floor0.json missing — run the bake first")
    quarterly = _load("quarterly.json")
    c78q = _load("c78q.json")
    stamp = datetime.now().strftime("%Y%m%d")
    for tk in tickers:
        d = build_dossier(tk, universe, quarterly, c78q)
        if d is None:
            continue
        out = os.path.join(QUEUE, f"{tk}_{stamp}.json")
        json.dump(d, open(out, "w"), indent=1, default=str)
        print(f"queued {out} (snapshot {d['snapshot_hash']})")


if __name__ == "__main__":
    main()
