"""
Manual-Macro Monthly Fetcher
============================

Two macro inputs the dashboard can't get from FRED keep going stale:
  - ISM Manufacturing + Services PMI  (proprietary — NOT on FRED; was hardcoded in macro.py)
  - Money-market fund total assets    (the PGI "dry powder" gauge — FRED's MMMFFAQ027S is
                                       QUARTERLY with a ~6wk lag; the weekly H.6 series died in 2021)

This runs monthly via GitHub Actions and fetches the latest published values with ONE grounded
Gemini call (web-search enabled), the same zero-cost pattern as build_risk_radar_cache.py /
build_house_views_freshness.py. It writes manual_macro.json; the bake reads it to override the
ISM constants (macro_data) and the PGI money-market figure, falling back to the prior values if a
fetch is uncertain.

INTEGRITY: every figure must come back with a named source and land in a plausible range, else it
is dropped (prior value kept) — never invented. Mirrors the risk-radar "omit rather than guess".

Usage:  python build_manual_macro.py
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

OUT_FILE = "manual_macro.json"

# Plausible ranges — a returned value outside its band is treated as a bad parse and dropped.
RANGES = {"ism_mfg": (30, 70), "ism_svcs": (30, 70), "mmf_total_t": (4.0, 12.0)}


def call_gemini_with_search(prompt, max_tokens=2000):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.05, "maxOutputTokens": max_tokens},
    }
    r = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini API error {r.status_code}: {r.text[:400]}")
    cands = r.json().get("candidates", [])
    if not cands:
        raise RuntimeError(f"No candidates: {json.dumps(r.json())[:300]}")
    parts = cands[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


def parse_json_response(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines and lines[-1].startswith("```") else lines[1:])
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
    return f"""Search the web for the THREE most recent published macro figures below. TODAY: {today}.

1. ISM Manufacturing PMI — the latest monthly headline index from the Institute for Supply Management (released the 1st business day of each month). Report the index value and the month it refers to.
2. ISM Services PMI (a.k.a. Services Business Activity / Non-Manufacturing) — the latest monthly headline index (released the 3rd business day of each month). Value + reference month.
3. Total U.S. money market fund assets — the latest figure from ICI (Investment Company Institute), which publishes total money market fund net assets weekly. Report in TRILLIONS of dollars and the report date.

INTEGRITY RULES — these values feed a live dashboard, so NEVER invent:
- Report a value ONLY if you can attribute it to a specific named source (ISM release / ICI weekly report) with a date. Include the source string.
- If you cannot confirm a current figure, set it to null (do not guess a number or a date).
- ISM values are index points (typically 40-60). The money-market total is in trillions (currently ~$7T).

Return ONLY this JSON, no other text:
{{
  "ism_mfg":     {{"value": 0.0, "ref_month": "YYYY-MM", "source": "ISM ... (Mon YYYY)"}},
  "ism_svcs":    {{"value": 0.0, "ref_month": "YYYY-MM", "source": "ISM ... (Mon YYYY)"}},
  "mmf_total_t": {{"value": 0.0, "as_of": "YYYY-MM-DD", "source": "ICI weekly MMF ... (date)"}}
}}
Use null for any field you cannot source confidently."""


def _accept(key, cell):
    """Keep a figure only if it's a number, in-range, and carries a named source."""
    if not isinstance(cell, dict):
        return None
    v, src = cell.get("value"), (cell.get("source") or "").strip()
    lo, hi = RANGES[key]
    if isinstance(v, (int, float)) and lo <= v <= hi and src:
        return cell
    return None


def main():
    print(f"[{datetime.now().isoformat()}] Manual-macro fetch starting")
    prior = {}
    if os.path.exists(OUT_FILE):
        try:
            prior = json.load(open(OUT_FILE))
        except Exception:
            prior = {}

    parsed, error = {}, None
    try:
        parsed = parse_json_response(call_gemini_with_search(build_prompt()))
    except Exception as e:
        error = str(e)[:200]
        print(f"  fetch failed: {error}", file=sys.stderr)

    now = datetime.now(timezone.utc)
    out = {"fetched_utc": now.isoformat(), "fetched_human": now.strftime("%Y-%m-%d %H:%M UTC"),
           "source": "grounded Gemini web search (ISM releases + ICI weekly MMF)"}
    kept, dropped = [], []
    for key in ("ism_mfg", "ism_svcs", "mmf_total_t"):
        good = _accept(key, parsed.get(key)) if isinstance(parsed, dict) else None
        if good:
            out[key] = good
            kept.append(f"{key}={good['value']}")
        elif key in prior and isinstance(prior.get(key), dict):
            out[key] = prior[key]          # keep last good value rather than blank the card
            out[key]["_stale"] = True
            dropped.append(f"{key}(kept prior)")
        else:
            dropped.append(f"{key}(none)")

    out["status"] = "ok" if kept else "failed"
    if error:
        out["error"] = error
    json.dump(out, open(OUT_FILE, "w"), indent=2)
    print(f"[{datetime.now().isoformat()}] Wrote {OUT_FILE}: kept [{', '.join(kept) or 'none'}], "
          f"dropped [{', '.join(dropped) or 'none'}]")

    if not kept:
        print("ERROR: no figures fetched and no prior to fall back to", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
