"""AI #2 — Strategy rebalance rationale. For each of the 5 strategies, explain WHAT alpha driver
its current holdings share + why the basket fits the strategy's thesis. NUMBERS-ONLY-FED: the model
sees each holding's sector + pillar grades + composite (from the universe) and is told never to
invent tickers/figures. Zero cost via local Ollama.

  $env:AI_PROVIDER="ollama"; $env:OLLAMA_MODEL="qwen2.5:7b"; python build_strategy_rationale.py
Writes strategy_rationale.json to both frontends.
"""
import json, time, logging, os
from pathlib import Path
from collections import Counter

logging.getLogger("streamlit").setLevel(logging.ERROR)
import ai_assistant
def _llm(prompt, max_tokens=300, temperature=0.4, provider=None, feature="strategy"):
    p = provider or ai_assistant._provider()
    fn = {"gemini": ai_assistant._call_gemini, "claude": ai_assistant._call_claude,
          "ollama": ai_assistant._call_ollama, "openai": ai_assistant._call_openai}.get(p)
    return fn(prompt, max_tokens, temperature) if fn else {"error": f"unknown provider {p}"}
ai_assistant.call_llm = _llm

DASH = [Path(r"C:\Users\bmhar\code\quant-dashboard-pro-v2\public\data"),
        Path(r"C:\Users\bmhar\code\quant-dashboard-react\web\public\data")]
DATA = DASH[0]
uni = {r["ticker"]: r for r in json.load(open(DATA / "universe_floor0.json"))["rows"]}

STRATS = [("Katalepsis", "c78q"), ("Aristeia", "aristeia"), ("Auxo", "auxo"),
          ("Prosodos", "prosodos"), ("Pronoia", "pronoia")]

def load(slug):
    if slug == "c78q":
        d = json.load(open(DATA / "c78q.json"))
        tks = [r["ticker"] for r in d.get("target", {}).get("rows", [])]
        thesis = (d.get("spec", {}) or {}).get("description") or "Posterior-ranked conviction book (c78q signal blend)."
        return tks, thesis
    d = json.load(open(DATA / f"{slug}_strategy.json"))
    tks = (d.get("current_holdings", {}) or {}).get("tickers", [])
    thesis = d.get("tagline") or d.get("character") or ((d.get("config", {}) or {}).get("description")) or ""
    return tks, thesis

def holding_desc(tk):
    r = uni.get(tk)
    if not r:
        return f"{tk}"
    g = r.get("grades") or {}
    sc = (r.get("byPreset", {}).get("equal", {}) or {}).get("c")
    grades = "/".join(f"{p[0]}:{g.get(p, '—')}" for p in ["Valuation", "Growth", "Profitability", "Momentum"])
    return f"{tk} [{r.get('sector', '?')}, score {sc:.1f}, {grades}]" if sc is not None else f"{tk} [{r.get('sector', '?')}]"

out = {}
for label, slug in STRATS:
    try:
        tks, thesis = load(slug)
    except Exception as e:
        print(f"  {label}: load failed ({e})"); continue
    if not tks:
        print(f"  {label}: no holdings"); continue
    held = [t for t in tks if t in uni]
    secs = Counter(uni[t]["sector"] for t in held if uni[t].get("sector"))
    lines = "\n".join(f"  - {holding_desc(t)}" for t in tks)
    prompt = f"""You are explaining a quant strategy's current book to an investor.
Strategy: {label}. Thesis: {thesis}
Sector mix: {dict(secs)}
Current holdings (sector, 0-10 composite, pillar grades V/G/P/M):
{lines}

In 2-3 sentences, explain what alpha driver / common thread these names share and why this basket fits {label}'s thesis. Use ONLY the data above — never invent tickers, sectors, grades, or figures. Plain and concrete, no preamble."""
    res = ai_assistant.call_llm(prompt, max_tokens=300, temperature=0.4) or {}
    txt = (res.get("text") or "").strip()
    out[label] = {"rationale": txt, "holdings": tks, "sector_mix": dict(secs), "thesis": thesis}
    print(f"  {label}: {len(tks)} names — {'ok ' + str(len(txt)) + 'ch' if txt else 'FAIL ' + str(res.get('error', ''))[:50]}")
    time.sleep(0.2)

payload = {"generated_at": time.strftime("%Y-%m-%d"), "model": os.getenv("OLLAMA_MODEL", "ollama"),
           "note": "AI rationale — fed only the strategy's holdings + their quant characteristics, never invents",
           "strategies": out}
for repo in DASH:
    if repo.exists():
        json.dump(payload, open(repo / "strategy_rationale.json", "w"), indent=2)
print(f"DONE: {len(out)} strategy rationales -> strategy_rationale.json")
