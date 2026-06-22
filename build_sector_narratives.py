"""AI #1 — Sector narratives. Per-sector quant aggregates -> a 2-3 sentence Ollama narrative
explaining the quant's posture. NUMBERS-ONLY-FED: the model sees only pre-computed sector stats
and is told never to invent figures/grades/tickers. Zero cost via local Ollama.

  $env:AI_PROVIDER="ollama"; $env:OLLAMA_MODEL="qwen2.5:7b"; python build_sector_narratives.py

Writes sector_narratives.json to both frontends. Run after the bake refreshes universe_floor0.json.
"""
import json, time, logging, os
from pathlib import Path
from collections import Counter, defaultdict

logging.getLogger("streamlit").setLevel(logging.ERROR)
import ai_assistant
# Bypass the Streamlit login gate; call the configured provider directly (Ollama by default here).
def _llm(prompt, max_tokens=300, temperature=0.4, provider=None, feature="sector"):
    p = provider or ai_assistant._provider()
    fn = {"gemini": ai_assistant._call_gemini, "claude": ai_assistant._call_claude,
          "ollama": ai_assistant._call_ollama, "openai": ai_assistant._call_openai}.get(p)
    return fn(prompt, max_tokens, temperature) if fn else {"error": f"unknown provider {p}"}
ai_assistant.call_llm = _llm

DASH = [Path(r"C:\Users\bmhar\code\quant-dashboard-pro-v2\public\data"),
        Path(r"C:\Users\bmhar\code\quant-dashboard-react\web\public\data")]
rows = json.load(open(DASH[0] / "universe_floor0.json"))["rows"]
stocks = [r for r in rows if r.get("sector") and r.get("sector") != "ETF"]

GRADE_NUM = {"A+": 12, "A": 11, "A-": 10, "B+": 9, "B": 8, "B-": 7, "C+": 6, "C": 5, "C-": 4, "D+": 3, "D": 2, "D-": 1, "F": 0}
NUM_GRADE = {v: k for k, v in GRADE_NUM.items()}
PILLARS = ["Valuation", "Growth", "Profitability", "Momentum", "EPS Revisions"]
RATINGS = ["Strong Buy+", "Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]

def avg_grade(gs):
    ns = [GRADE_NUM[g] for g in gs if g in GRADE_NUM]
    return NUM_GRADE.get(round(sum(ns) / len(ns)), "—") if ns else "—"
def score(r): return (r.get("byPreset", {}).get("equal", {}) or {}).get("c")
def rating(r): return (r.get("byPreset", {}).get("equal", {}) or {}).get("r")

bysec = defaultdict(list)
for r in stocks:
    if score(r) is not None:
        bysec[r["sector"]].append(r)

out = {}
for sec, rs in sorted(bysec.items()):
    if len(rs) < 3:
        continue
    n = len(rs)
    rc = Counter(rating(r) for r in rs)
    buyish = sum(rc.get(k, 0) for k in ("Strong Buy+", "Strong Buy", "Buy"))
    pillar_avgs = {p: avg_grade([(r.get("grades") or {}).get(p) for r in rs]) for p in PILLARS}
    top = sorted(rs, key=lambda r: -score(r))[:3]
    bot = sorted(rs, key=lambda r: score(r))[:2]
    stats = {"sector": sec, "n": n, "avg_score": round(sum(score(r) for r in rs) / n, 2),
             "buy_rated_pct": round(100 * buyish / n),
             "rating_dist": {k: rc.get(k, 0) for k in RATINGS},
             "avg_pillar_grades": pillar_avgs,
             "top_names": [f"{r['ticker']} ({score(r):.1f})" for r in top],
             "weak_names": [f"{r['ticker']} ({score(r):.1f})" for r in bot]}
    prompt = f"""You are a sector strategist. Quant stats for the {sec} sector (composite scores 0-10, pillar grades A+ to F):
- {n} names; average composite {stats['avg_score']}; {stats['buy_rated_pct']}% Buy-rated or better
- rating distribution: {stats['rating_dist']}
- average pillar grades: {pillar_avgs}
- highest-scored: {', '.join(stats['top_names'])}
- weakest: {', '.join(stats['weak_names'])}

Write 2-3 sentences on what the quant says about {sec}: overall posture (constructive / neutral / cautious), the standout strength or weakness pillar, and the names that stand out. Use ONLY the stats above — never invent figures, grades, or tickers. Plain and concrete, no preamble."""
    res = ai_assistant.call_llm(prompt, max_tokens=300, temperature=0.4) or {}
    txt = (res.get("text") or "").strip()
    out[sec] = {"narrative": txt, "stats": stats}
    print(f"  {sec}: {'ok ' + str(len(txt)) + 'ch' if txt else 'FAIL ' + str(res.get('error', ''))[:50]}")
    time.sleep(0.2)

payload = {"generated_at": time.strftime("%Y-%m-%d"),
           "model": os.getenv("OLLAMA_MODEL", "ollama"),
           "note": "AI narrative — fed only pre-computed sector stats, never invents figures",
           "sectors": out}
for repo in DASH:
    if repo.exists():
        json.dump(payload, open(repo / "sector_narratives.json", "w"), indent=2)
print(f"DONE: {len(out)} sector narratives -> sector_narratives.json")
