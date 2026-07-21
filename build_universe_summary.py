"""AI #10 — Daily universe summary ("the market in one paragraph"). One Ollama call over
universe-wide aggregates. NUMBERS-ONLY-FED. Writes universe_summary.json.
  $env:AI_PROVIDER="ollama"; $env:OLLAMA_MODEL="qwen2.5:7b"; python build_universe_summary.py
"""
import json, time, logging, os
from pathlib import Path
from collections import Counter

logging.getLogger("streamlit").setLevel(logging.ERROR)
import ai_assistant
def _llm(prompt, mt=300, tp=0.4, provider=None, feature="universe"):
    p = provider or ai_assistant._provider()
    fn = {"gemini": ai_assistant._call_gemini, "claude": ai_assistant._call_claude, "ollama": ai_assistant._call_ollama, "openai": ai_assistant._call_openai}.get(p)
    return fn(prompt, mt, tp) if fn else {"error": f"unknown provider {p}"}
ai_assistant.call_llm = _llm

DASH = [Path(r"C:\Users\bmhar\code\quant-dashboard-pro-v2\public\data"), Path(r"C:\Users\bmhar\code\quant-dashboard-react\web\public\data")]
# universe_floor0.json is blob-stored in pro-v2 since the git-slim phase; read from
# whichever checkout still has a local bake copy (same fix as build_etf_lookthrough).
_SRC = next((p for p in DASH if (p / "universe_floor0.json").exists()), DASH[1])
rows = [r for r in json.load(open(_SRC / "universe_floor0.json"))["rows"] if r.get("sector") and r.get("sector") != "ETF"]
def comp(r): return (r.get("byPreset", {}).get("equal", {}) or {}).get("c")
def rat(r): return (r.get("byPreset", {}).get("equal", {}) or {}).get("r")

scored = [r for r in rows if comp(r) is not None]
rc = Counter(rat(r) for r in scored)
buyish = sum(rc.get(k, 0) for k in ("Strong Buy+", "Strong Buy", "Buy"))
prem = [r.get("fvPremium") for r in scored if isinstance(r.get("fvPremium"), (int, float))]
secavg = {}
from collections import defaultdict
bysec = defaultdict(list)
for r in scored: bysec[r["sector"]].append(comp(r))
secavg = {s: round(sum(v) / len(v), 2) for s, v in bysec.items()}
top_sec = sorted(secavg, key=secavg.get, reverse=True)[:3]
bot_sec = sorted(secavg, key=secavg.get)[:3]
mom = sorted(scored, key=lambda r: -((r.get("raw") or {}).get("momentum_12m") or -9))[:5]
stats = {"n": len(scored), "buy_tier_pct": round(100 * buyish / len(scored)),
         "rating_dist": {k: rc.get(k, 0) for k in ("Strong Buy+", "Strong Buy", "Buy", "Hold", "Sell", "Strong Sell")},
         "median_fv_premium_pct": round(sorted(prem)[len(prem) // 2], 1) if prem else None,
         "strongest_sectors": [f"{s} ({secavg[s]})" for s in top_sec],
         "weakest_sectors": [f"{s} ({secavg[s]})" for s in bot_sec],
         "momentum_leaders": [r["ticker"] for r in mom]}
prompt = f"""You are a market strategist. Today's quant snapshot across {stats['n']} US stocks (composite 0-10):
- {stats['buy_tier_pct']}% Buy-tier; rating distribution {stats['rating_dist']}
- median fair-value premium {stats['median_fv_premium_pct']}% (positive = trading above fair value)
- strongest sectors by avg score: {stats['strongest_sectors']}; weakest: {stats['weakest_sectors']}
- 12-month momentum leaders: {stats['momentum_leaders']}

Write a tight 3-4 sentence "market in a paragraph": the overall posture (risk-on / neutral / cautious), valuation backdrop, where strength vs weakness sits, and the rotation it implies. Use ONLY these stats — never invent figures or tickers. No preamble."""
res = ai_assistant.call_llm(prompt, mt=320) or {}
txt = (res.get("text") or "").strip()
payload = {"generated_at": time.strftime("%Y-%m-%d"), "model": os.getenv("OLLAMA_MODEL", "ollama"), "summary": txt, "stats": stats}
for repo in DASH:
    if repo.exists(): json.dump(payload, open(repo / "universe_summary.json", "w"), indent=2)
print(f"universe summary: {'ok ' + str(len(txt)) + 'ch' if txt else 'FAIL ' + str(res.get('error',''))[:40]} | {stats['buy_tier_pct']}% buy-tier, top {stats['strongest_sectors']}")
