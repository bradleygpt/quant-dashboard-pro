"""AI #3 — Anomaly callouts. Flag stocks whose quant PILLARS most diverge (e.g. strong momentum but
weak valuation — the classic 'is this sustainable?' tension) and have Ollama name the thesis risk +
what to watch. NUMBERS-ONLY-FED: the model sees only the stock's pillar grades + composite and is
told never to invent figures. Zero cost via local Ollama.

  $env:AI_PROVIDER="ollama"; $env:OLLAMA_MODEL="qwen2.5:7b"; python build_anomalies.py
Writes anomalies.json to both frontends.
"""
import json, time, logging, os
from pathlib import Path

logging.getLogger("streamlit").setLevel(logging.ERROR)
import ai_assistant
def _llm(prompt, max_tokens=200, temperature=0.4, provider=None, feature="anomaly"):
    p = provider or ai_assistant._provider()
    fn = {"gemini": ai_assistant._call_gemini, "claude": ai_assistant._call_claude,
          "ollama": ai_assistant._call_ollama, "openai": ai_assistant._call_openai}.get(p)
    return fn(prompt, max_tokens, temperature) if fn else {"error": f"unknown provider {p}"}
ai_assistant.call_llm = _llm

DASH = [Path(r"C:\Users\bmhar\code\quant-dashboard-pro-v2\public\data"),
        Path(r"C:\Users\bmhar\code\quant-dashboard-react\web\public\data")]
rows = json.load(open(DASH[0] / "universe_floor0.json"))["rows"]
stocks = [r for r in rows if r.get("sector") and r.get("sector") != "ETF"]
PILLARS = ["Valuation", "Growth", "Profitability", "Momentum", "EPS Revisions"]
TOP_N = 18

def score(r): return (r.get("byPreset", {}).get("equal", {}) or {}).get("c")

cands = []
for r in stocks:
    pn = {p: v for p in PILLARS if isinstance((v := (r.get("pillars") or {}).get(p)), (int, float))}
    sc = score(r)
    if len(pn) < 4 or sc is None or sc < 5.0:  # only names worth discussing
        continue
    hi, lo = max(pn, key=pn.get), min(pn, key=pn.get)
    cands.append((pn[hi] - pn[lo], r, hi, lo))
cands.sort(key=lambda x: -x[0])

out = []
for spread, r, hi, lo in cands[:TOP_N]:
    g = r.get("grades") or {}
    sc = score(r)
    grades = {p: g.get(p) for p in PILLARS}
    prompt = f"""{r['ticker']} ({r['name']}, {r['sector']}) — quant pillar grades {grades}, composite {sc:.1f}.
The sharpest divergence is strong {hi} vs weak {lo}.
In 1-2 sentences, name the thesis risk this tension implies and the single thing to watch. Use ONLY these grades — never invent figures or events. No preamble."""
    res = ai_assistant.call_llm(prompt, max_tokens=200, temperature=0.4) or {}
    txt = (res.get("text") or "").strip()
    out.append({"ticker": r["ticker"], "name": r["name"], "sector": r["sector"], "composite": round(sc, 1),
                "strong": hi, "weak": lo, "grades": grades, "rating": (r.get("byPreset", {}).get("equal", {}) or {}).get("r"),
                "warning": txt})
    print(f"  {r['ticker']}: {hi}>{lo} — {'ok ' + str(len(txt)) + 'ch' if txt else 'FAIL ' + str(res.get('error', ''))[:50]}")
    time.sleep(0.2)

payload = {"generated_at": time.strftime("%Y-%m-%d"), "model": os.getenv("OLLAMA_MODEL", "ollama"),
           "note": "AI anomaly callouts — fed only the stock's pillar grades, never invents figures/events",
           "anomalies": out}
for repo in DASH:
    if repo.exists():
        json.dump(payload, open(repo / "anomalies.json", "w"), indent=2)
print(f"DONE: {len(out)} anomaly callouts -> anomalies.json")
