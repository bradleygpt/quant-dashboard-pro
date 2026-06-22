"""AI #11 — Earnings quality signal. Derives a QUALITY flag from each baked earnings review's text
(margin trend, guidance, beat composition, accel/decel) — a heuristic over text the LLM already
wrote, so it's free + deterministic (no second LLM pass over 1,241 filings). The verdict says
buy/hold/trim; this says whether the quarter's quality backs it up. Writes earnings_quality.json.

  python build_earnings_quality.py   (reads earnings_reviews.json from a frontend, writes back)
"""
import json, re
from pathlib import Path

DASH = [Path(r"C:\Users\bmhar\code\quant-dashboard-pro-v2\public\data"),
        Path(r"C:\Users\bmhar\code\quant-dashboard-react\web\public\data")]
src = next((d / "earnings_reviews.json" for d in DASH if (d / "earnings_reviews.json").exists()), None)
reviews = json.load(open(src)) if src else {}

POS = [r"margin expan", r"margin.{0,12}(improv|expand)", r"raised.{0,15}guidance", r"guidance.{0,15}(raised|up)",
       r"accelerat", r"beat", r"exceed", r"record", r"strong", r"improv", r"above expectations"]
NEG = [r"margin compress", r"margin.{0,12}(declin|contract|compress)", r"cut.{0,15}guidance", r"lowered.{0,15}guidance",
       r"guidance.{0,15}(cut|lower|reduc)", r"decelerat", r"miss", r"below expectations", r"weak", r"disappoint", r"soft"]

def signal(txt):
    t = (txt or "").lower()
    pos = sum(1 for p in POS if re.search(p, t))
    neg = sum(1 for p in NEG if re.search(p, t))
    net = pos - neg
    if net >= 2:
        return "High", f"clean beat — {pos} positive quality signals, {neg} negative"
    if net <= -1:
        return "Low", f"low-quality — {neg} negative signals vs {pos} positive (watch margins/guidance)"
    return "Medium", f"mixed — {pos} positive / {neg} negative quality signals"

out = {}
for k, rv in reviews.items():
    if not isinstance(rv, dict):
        continue
    txt = rv.get("full_text") or rv.get("text") or ""
    if len(txt) < 120:
        continue
    q, reason = signal(txt)
    out[k] = {"quality": q, "reason": reason, "verdict": rv.get("verdict")}

from collections import Counter
dist = Counter(v["quality"] for v in out.values())
payload = {"generated_at": __import__("time").strftime("%Y-%m-%d"),
           "method": "heuristic over the baked review text (margin/guidance/beat/accel language) — deterministic, no LLM",
           "quality": out}
for repo in DASH:
    if repo.exists():
        json.dump(payload, open(repo / "earnings_quality.json", "w"), separators=(",", ":"))
print(f"DONE: {len(out)} earnings-quality signals -> earnings_quality.json | distribution: {dict(dist)}")
