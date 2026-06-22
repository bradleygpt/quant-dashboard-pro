"""AI #7 — Macro→sector rotation. One Ollama call over the already-generated risk radar + macro
forecasts → which sectors the macro setup favors / pressures. NUMBERS-ONLY-FED (only the flagged
risks + forecast figures). Writes macro_rotation.json.
  $env:AI_PROVIDER="ollama"; $env:OLLAMA_MODEL="qwen2.5:7b"; python build_macro_rotation.py
"""
import json, time, logging, os
from pathlib import Path

logging.getLogger("streamlit").setLevel(logging.ERROR)
import ai_assistant
def _llm(prompt, mt=400, tp=0.4, provider=None, feature="rotation"):
    p = provider or ai_assistant._provider()
    fn = {"gemini": ai_assistant._call_gemini, "claude": ai_assistant._call_claude, "ollama": ai_assistant._call_ollama, "openai": ai_assistant._call_openai}.get(p)
    return fn(prompt, mt, tp) if fn else {"error": f"unknown provider {p}"}
ai_assistant.call_llm = _llm

DASH = [Path(r"C:\Users\bmhar\code\quant-dashboard-pro-v2\public\data"), Path(r"C:\Users\bmhar\code\quant-dashboard-react\web\public\data")]
def load(name):
    for d in DASH:
        p = d / name
        if p.exists():
            try: return json.load(open(p))
            except Exception: pass
    return None

radar = load("risk_radar.json") or {}
fc = load("macro_forecasts.json") or {}
risks = [{"title": r.get("title"), "category": r.get("category"), "severity": r.get("severity")}
         for r in (radar.get("risks") or [])][:8]
# consensus direction: pull the live-feed forecaster rows' near-year figures if present
cons = (fc.get("consensus") or {})
years = cons.get("years", [])
feeds = [{"name": f.get("name"), "values": {m: f.get("values", {}).get(m) for m in ("gdp", "inflation", "fed_funds")}}
         for f in (cons.get("forecasters") or []) if f.get("live")][:4]

if not risks and not feeds:
    print("no risk_radar/macro_forecasts data — skipping (run those builders first)")
    payload = {"generated_at": time.strftime("%Y-%m-%d"), "rotation": "", "note": "awaiting risk_radar/macro_forecasts"}
else:
    prompt = f"""You are a macro strategist. Current backdrop (already-sourced):
Risks flagged by institutions: {json.dumps(risks)}
Live consensus forecasts ({years}): {json.dumps(feeds)}

In 3-4 sentences, give the SECTOR ROTATION this macro setup implies: which sectors are favored and which are pressured, tied to the specific risks/forecasts above. Use ONLY the risks and figures provided — never invent data. Concrete sector calls, no preamble."""
    res = ai_assistant.call_llm(prompt, mt=400) or {}
    txt = (res.get("text") or "").strip()
    payload = {"generated_at": time.strftime("%Y-%m-%d"), "model": os.getenv("OLLAMA_MODEL", "ollama"),
               "rotation": txt, "risks_used": risks}
    print(f"macro rotation: {'ok ' + str(len(txt)) + 'ch' if txt else 'FAIL ' + str(res.get('error',''))[:40]} | {len(risks)} risks, {len(feeds)} feeds")

for repo in DASH:
    if repo.exists(): json.dump(payload, open(repo / "macro_rotation.json", "w"), indent=2)
