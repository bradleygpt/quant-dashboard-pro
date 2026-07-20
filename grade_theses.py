"""Grade baked theses at +3/6/12 months (post-mortem substrate, handoff §2.4).

For each theses/baked/*.json whose horizon has elapsed and whose grading slot is
still null, fill:
    grading.h{3m,6m,12m} = {
        "graded_at": iso, "realized_return_pct": x,
        "winner": "bull" | "bear" | "push",
        "falsifiers_triggered": []   # manual review field — starts empty
    }
Winner rule (mechanical baseline): realized return >= +10% → bull, <= -10% → bear,
else push. Falsifier triggering is qualitative — review in Claude Code and edit
the list; the mechanical grade never overwrites a hand-filled slot.

Prices come from the baked per-ticker price shards (web/public/data/prices/).
Run monthly (piggybacks fine on the rebalance checklist). Honest constraint:
input-stickiness analysis needs ~30-50 graded theses — don't run it before that.

Usage: python grade_theses.py [--dry-run]
"""
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
BAKED = os.path.join(ROOT, "theses", "baked")
PRICES = os.path.join(ROOT, "web", "public", "data", "prices")

HORIZONS = {"h3m": 91, "h6m": 182, "h12m": 365}
WIN, LOSE = 10.0, -10.0


def price_on_or_after(series, target):
    """series: [(date_str, close)] ascending; return first close on/after target date."""
    for d, c in series:
        if d >= target:
            return c
    return None


def load_prices(tk):
    try:
        j = json.load(open(os.path.join(PRICES, f"{tk}.json"), encoding="utf-8"))
        dates, closes = j.get("dates") or [], j.get("close") or j.get("closes") or []
        if dates and closes and len(dates) == len(closes):
            return sorted(zip(dates, closes))
    except Exception:
        pass
    return None


def main():
    dry = "--dry-run" in sys.argv
    if not os.path.isdir(BAKED):
        print("no theses/baked/ — nothing to grade")
        return
    now = datetime.now()
    graded = skipped = 0
    for f in sorted(os.listdir(BAKED)):
        if not f.endswith(".json"):
            continue
        p = os.path.join(BAKED, f)
        t = json.load(open(p, encoding="utf-8"))
        gen = t.get("generated_at", "")[:10]
        tk = t.get("ticker")
        if not gen or not tk:
            continue
        gen_dt = datetime.fromisoformat(gen)
        series = None
        changed = False
        for h, days in HORIZONS.items():
            due = gen_dt + timedelta(days=days)
            if now < due or t.get("grading", {}).get(h) is not None:
                continue
            series = series or load_prices(tk)
            if not series:
                print(f"  {f}: no price shard for {tk} — skipped")
                skipped += 1
                break
            p0 = price_on_or_after(series, gen)
            p1 = price_on_or_after(series, due.strftime("%Y-%m-%d"))
            if not p0 or not p1:
                print(f"  {f}: {h} price window not covered yet — skipped")
                skipped += 1
                continue
            ret = round((p1 / p0 - 1) * 100, 2)
            t.setdefault("grading", {})[h] = {
                "graded_at": now.replace(microsecond=0).isoformat(),
                "realized_return_pct": ret,
                "winner": "bull" if ret >= WIN else "bear" if ret <= LOSE else "push",
                "falsifiers_triggered": [],
            }
            changed = True
            print(f"  {f}: {h} -> {ret:+.1f}% ({t['grading'][h]['winner']})")
        if changed and not dry:
            json.dump(t, open(p, "w"), indent=1)
            graded += 1
    print(f"graded {graded} file(s), {skipped} skipped{' (dry-run, nothing written)' if dry else ''}")


if __name__ == "__main__":
    main()
