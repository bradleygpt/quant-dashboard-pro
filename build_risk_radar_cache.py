"""
Risk Radar Cache Builder
========================

The narrative half of the Macro Outlook feature. The bank/consultancy/academic
outlooks (Fed, IMF, World Bank, CBO, JPMorgan, Guggenheim, KPMG, Wells Fargo,
Stanford SIEPR) publish their "what to watch" risks as prose PDFs with NO data
feed — so we summarize them with a single grounded LLM call (web-search enabled)
into a structured Risk Radar, exactly like build_pundits_cache.py does for
market commentators.

Runs daily via GitHub Actions (shares the pundits workflow + GEMINI_API_KEY).
Writes risk_radar_cache.json with status tracking (fresh / stale / failed);
the bake copies it to web/public/data/risk_radar.json. Zero live API calls in
user sessions. NEVER fabricate — the prompt forces source attribution and
"omit rather than invent", mirroring the pundit builder's integrity stance.

Usage:  python build_risk_radar_cache.py
Env:    GEMINI_API_KEY
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

CACHE_FILE = "risk_radar_cache.json"

# Canonical category + severity vocabularies the frontend colors by.
CATEGORIES = ["Inflation", "Growth", "Policy", "Labor", "Fiscal", "Geopolitical", "Markets", "Trade"]
SEVERITIES = ["High", "Medium", "Low"]


def call_gemini_with_search(prompt, max_tokens=4000):
    """Single Gemini call with google_search grounding. Mirrors build_pundits_cache."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.25, "maxOutputTokens": max_tokens},
    }
    r = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini API error {r.status_code}: {r.text[:500]}")
    cands = r.json().get("candidates", [])
    if not cands:
        raise RuntimeError(f"No candidates: {json.dumps(r.json())[:400]}")
    parts = cands[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


def parse_json_response(text):
    """Extract JSON from an LLM response, tolerating ``` fences. (Same as pundits.)"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise RuntimeError(f"No JSON found: {text[:300]}")


def build_prompt():
    today = datetime.now().strftime("%B %d, %Y")
    cats = " / ".join(CATEGORIES)
    return f"""Search the web for the MOST RECENT (2026) economic outlook publications from these institutions and extract the key risks they flag for the US and global economy:
- Federal Reserve (FOMC statement / SEP / minutes)
- IMF (World Economic Outlook)
- World Bank (Global Economic Prospects)
- Congressional Budget Office (Budget and Economic Outlook)
- JPMorgan (Mid-Year Outlook 2026)
- Guggenheim Investments (Economic Outlook / macro themes)
- KPMG (Economic Compass)
- Wells Fargo Investment Institute (outlook)
- Stanford SIEPR ("US Economy 2026: What to Watch")

TODAY: {today}

Build a "Risk Radar" — the 6 to 10 most important, distinct risks these sources are collectively watching RIGHT NOW. Synthesize across sources (if several flag the same risk, merge them and list all). For EACH risk, attribute it to the specific institution(s) that raised it — do NOT invent attributions. If you cannot verify which source raised a risk, omit that risk rather than guessing.

Return ONLY a JSON object in this EXACT format, no other text:

{{
  "as_of_window": "e.g. June 2026",
  "risks": [
    {{
      "title": "Short risk name (6-10 words)",
      "category": "{cats}",
      "severity": "High | Medium | Low",
      "direction": "downside | upside | two-sided",
      "horizon": "near-term | 2026 | 2027 | structural",
      "summary": "1-2 sentence plain-English explanation of the risk and why it matters.",
      "watch_for": "The specific data release, event, or threshold to watch.",
      "sources": ["Institution name (report, month)", "..."]
    }}
  ],
  "consensus_note": "2-3 sentences on the dominant risk narrative and where the outlooks disagree.",
  "themes": ["Cross-cutting theme 1", "theme 2", "theme 3"]
}}

Rules: 6-10 risks, ordered most-to-least important. Use ONLY the category and severity values listed. Every risk MUST have at least one real, named source. Better to return 6 well-sourced risks than 10 with any fabricated attribution."""


def _validate(parsed):
    """Drop malformed/unsourced risks; clamp category/severity to the known vocab."""
    risks = []
    for r in parsed.get("risks", []) if isinstance(parsed, dict) else []:
        if not isinstance(r, dict):
            continue
        title = (r.get("title") or "").strip()
        sources = [s for s in (r.get("sources") or []) if isinstance(s, str) and s.strip()]
        if not title or not sources:
            continue  # integrity guard: a risk with no named source is dropped
        r["category"] = r.get("category") if r.get("category") in CATEGORIES else "Markets"
        r["severity"] = r.get("severity") if r.get("severity") in SEVERITIES else "Medium"
        risks.append(r)
    parsed["risks"] = risks
    return parsed


def fetch_risk_radar():
    print(f"[{datetime.now().isoformat()}] Calling Gemini for risk radar...")
    text = call_gemini_with_search(build_prompt(), max_tokens=4000)
    print(f"[{datetime.now().isoformat()}] Got response, length {len(text)}")
    return _validate(parse_json_response(text))


def main():
    print(f"[{datetime.now().isoformat()}] Starting risk radar cache build")

    existing = None
    if os.path.exists(CACHE_FILE):
        try:
            existing = json.load(open(CACHE_FILE))
        except Exception:
            pass

    data, error = None, None
    try:
        data = fetch_risk_radar()
        print(f"[{datetime.now().isoformat()}] Got {len(data.get('risks', []))} risks")
    except Exception as e:
        error = str(e)[:300]
        print(f"[{datetime.now().isoformat()}] Risk radar fetch failed: {error}", file=sys.stderr)

    cache = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "last_updated_human": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    if data and data.get("risks"):
        cache.update(data)
        cache["status"] = "fresh"
    elif existing and existing.get("risks"):
        cache.update({k: existing[k] for k in ("as_of_window", "risks", "consensus_note", "themes") if k in existing})
        cache["status"] = "stale"
        cache["last_fresh"] = existing.get("last_updated_utc", "unknown")
        cache["error"] = error
    else:
        cache.update({"as_of_window": None, "risks": [], "consensus_note": "", "themes": []})
        cache["status"] = "failed"
        cache["error"] = error

    json.dump(cache, open(CACHE_FILE, "w"), indent=2)
    print(f"[{datetime.now().isoformat()}] Wrote {CACHE_FILE}: {cache['status']} ({len(cache.get('risks', []))} risks)")

    if cache["status"] == "failed":
        print("ERROR: fetch failed and no existing cache to fall back to", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
