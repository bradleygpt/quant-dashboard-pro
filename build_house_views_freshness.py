"""
House-Views Freshness Watchdog
==============================

The bank/strategist house views in the Forecast Consensus panel are hand-transcribed
from narrative PDFs with NO data feed (macro_house_views.json). Their failure mode is
STALENESS: a bank drops a new outlook and the transcription silently rots.

This watchdog runs twice-monthly (1st + 15th via GitHub Actions). For each tracked
institution it makes ONE grounded Gemini call (web-search enabled, mirroring
build_risk_radar_cache.py) to find the MOST RECENT published outlook + its publication
month + URL, and compares that to the transcribed `as_of` in macro_house_views.json:

  current   transcription matches the latest report  -> no action
  stale     a NEWER report exists than transcribed    -> re-transcribe
  new       never transcribed yet                      -> draft for review
  unknown   couldn't verify a dated report             -> no crying wolf

It ALSO drafts the candidate figures from the newer report — but ONLY with the verbatim
quoted sentence each number came from, written to a SEPARATE staging file
(macro_house_views_candidates.json). These are UNVERIFIED and NEVER feed the live panel;
a human verifies each quote against the PDF and promotes it into macro_house_views.json.

NEVER invent: the prompt forces a verbatim quote per figure and omits anything not
explicitly stated — same integrity stance as the risk-radar/pundit builders.

Usage:  python build_house_views_freshness.py
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

HOUSE_VIEWS_FILE = "macro_house_views.json"
FRESHNESS_FILE = "house_views_freshness.json"
CANDIDATES_FILE = "macro_house_views_candidates.json"

# Metrics mirror macro_forecasts.METRICS (kept in sync by hand — small + stable).
METRICS = ["gdp", "inflation", "unemployment", "fed_funds", "sp500_target"]

# The watchdog tracks whatever house views are actually curated in macro_house_views.json
# (the Fed SEP / World Bank / IMF rows are live-fetched at bake time and never go stale, so
# they are NOT in that file and not watched here). Deriving the target list from the file —
# rather than hardcoding it — means newly-added forecasters are tracked automatically and we
# never waste a call on an institution that was dropped.
def load_targets():
    if not os.path.exists(HOUSE_VIEWS_FILE):
        return []
    try:
        data = json.load(open(HOUSE_VIEWS_FILE))
    except Exception:
        return []
    targets = []
    for f in data.get("forecasters", []) if isinstance(data, dict) else []:
        if not isinstance(f, dict) or not f.get("id"):
            continue
        name, src = f.get("name") or f["id"], f.get("source") or ""
        targets.append({
            "id": f["id"], "name": name, "prior_as_of": f.get("as_of"),
            "search_hint": (f"{name}: find the SINGLE most recent published economic/market outlook "
                            f"(the latest update to, or successor of, '{src}'). Extract: real US GDP %, "
                            f"CPI or PCE inflation %, unemployment %, year-end fed funds %, S&P 500 year-end target."),
        })
    return targets


def call_gemini_with_search(prompt, max_tokens=3000):
    """Single Gemini call with google_search grounding. Mirrors build_risk_radar_cache."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens},
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
    """Extract JSON from an LLM response, tolerating ``` fences. (Same as risk_radar.)"""
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


def build_prompt(target, years, prior_as_of):
    today = datetime.now().strftime("%B %d, %Y")
    yrs = ", ".join(years)
    prior = prior_as_of or "none on file yet"
    return f"""You are checking whether a hand-transcribed economic forecast is STALE.

INSTITUTION: {target['name']}
WHAT TO FIND: {target['search_hint']}
TODAY: {today}
ALREADY TRANSCRIBED FROM A REPORT DATED: {prior}

Step 1 — Search the web for the SINGLE MOST RECENT published economic/market outlook from {target['name']} (as of today). Identify its exact title, its publication month (YYYY-MM), and the direct URL to the report or its landing page.

Step 2 — From THAT report only, extract the forecast figures it explicitly states for years {yrs}, for these metrics:
- gdp: real US GDP growth, % year-over-year
- inflation: CPI (or PCE — note which) inflation, % year-over-year
- unemployment: US unemployment rate, %
- fed_funds: year-end federal funds rate, %
- sp500_target: S&P 500 price target (year-end index level)

CRITICAL INTEGRITY RULES — this drafts numbers a human will verify, so NEVER invent:
- Include a metric/year ONLY if the report EXPLICITLY states that number. If it is not stated, omit it.
- For EVERY figure you include, provide the VERBATIM sentence or phrase from the report it came from, in "quote".
- If you cannot confidently identify a real, dated report, set "report_month" to null and return empty values. Do NOT guess a date or any figure.
- It is far better to return the report date with zero figures than to fabricate a single number.

Return ONLY this JSON, no other text:

{{
  "found": true/false,
  "report_title": "exact title or null",
  "report_month": "YYYY-MM or null",
  "url": "direct URL or null",
  "inflation_basis": "CPI | PCE | unknown",
  "values": {{
    "gdp": {{ "{years[0]}": {{"value": 0.0, "quote": "verbatim text"}} }},
    "sp500_target": {{ "{years[0]}": {{"value": 0, "quote": "verbatim text"}} }}
  }},
  "notes": "any caveat (e.g. range given, basis, vintage)"
}}
Only include metric/year keys you actually found a stated number + quote for."""


def _ym(s):
    """'YYYY-MM' (or 'YYYY-MM-..') -> comparable 'YYYY-MM', else ''."""
    if not s or not isinstance(s, str):
        return ""
    s = s.strip()
    return s[:7] if len(s) >= 7 and s[4] == "-" else ""


def _clean_values(raw):
    """Keep only figures that carry a numeric value AND a non-empty verbatim quote."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for metric, byyear in raw.items():
        if metric not in METRICS or not isinstance(byyear, dict):
            continue
        for year, cell in byyear.items():
            if not isinstance(cell, dict):
                continue
            val, quote = cell.get("value"), (cell.get("quote") or "").strip()
            if isinstance(val, (int, float)) and quote:  # integrity: number must be quoted
                out.setdefault(metric, {})[str(year)] = {"value": val, "quote": quote}
    return out


def classify(report_month, prior_as_of):
    rm, pm = _ym(report_month), _ym(prior_as_of)
    if not rm:
        return "unknown"
    if not pm:
        return "new"            # never transcribed — here's a draft
    if rm > pm:
        return "stale"          # a newer report exists than transcribed
    return "current"            # transcription is up to date


def check_one(target, prior_as_of, years):
    text = call_gemini_with_search(build_prompt(target, years, prior_as_of))
    p = parse_json_response(text)
    report_month = p.get("report_month") if p.get("found") else None
    status = classify(report_month, prior_as_of)
    values = _clean_values(p.get("values")) if status in ("stale", "new") else {}
    return {
        "id": target["id"], "name": target["name"],
        "prior_as_of": prior_as_of, "report_month": report_month,
        "report_title": p.get("report_title"), "url": p.get("url"),
        "inflation_basis": p.get("inflation_basis"), "notes": p.get("notes"),
        "status": status, "values": values,
    }


def main():
    print(f"[{datetime.now().isoformat()}] House-views freshness check starting")
    cur = datetime.now().year
    years = [str(cur), str(cur + 1)]

    targets = load_targets()
    if not targets:
        print(f"  no forecasters in {HOUSE_VIEWS_FILE} — nothing to check", file=sys.stderr)

    results, errors = [], 0
    for t in targets:
        try:
            res = check_one(t, t["prior_as_of"], years)
            print(f"  {t['name']}: {res['status']} (report {res['report_month']} vs transcribed {t['prior_as_of']}, {sum(len(v) for v in res['values'].values())} figures)")
            results.append(res)
        except Exception as e:
            errors += 1
            print(f"  {t['name']}: ERROR {str(e)[:160]}", file=sys.stderr)
            results.append({"id": t["id"], "name": t["name"], "status": "error",
                            "error": str(e)[:200], "prior_as_of": t["prior_as_of"], "values": {}})

    needs_action = [r for r in results if r["status"] in ("stale", "new")]
    now = datetime.now(timezone.utc)

    # 1) freshness report (status board the dashboard badge reads)
    freshness = {
        "checked_utc": now.isoformat(),
        "checked_human": now.strftime("%Y-%m-%d %H:%M UTC"),
        "status": "ok" if errors < len(targets) else "failed",
        "needs_action_count": len(needs_action),
        "forecasters": [{k: r.get(k) for k in
                         ("id", "name", "status", "prior_as_of", "report_month", "report_title", "url", "error")}
                        for r in results],
    }
    json.dump(freshness, open(FRESHNESS_FILE, "w"), indent=2)
    print(f"[{datetime.now().isoformat()}] Wrote {FRESHNESS_FILE}: {len(needs_action)} need action, {errors} errors")

    # 2) UNVERIFIED candidate figures (separate staging file — never feeds the live panel)
    candidates = {
        "generated_utc": now.isoformat(),
        "_warning": ("UNVERIFIED LLM-drafted figures. Verify EACH against the cited source PDF "
                     "before promoting into macro_house_views.json. Never merge a figure whose "
                     "quote does not plainly state the number. The live panel reads ONLY "
                     "macro_house_views.json, never this file."),
        "candidates": [
            {"id": r["id"], "name": r["name"], "kind": "house", "status": r["status"],
             "as_of": _ym(r["report_month"]), "prior_as_of": r["prior_as_of"],
             "source": r.get("report_title"), "url": r.get("url"),
             "inflation_basis": r.get("inflation_basis"), "notes": r.get("notes"),
             "values": r["values"]}
            for r in needs_action
        ],
    }
    json.dump(candidates, open(CANDIDATES_FILE, "w"), indent=2)
    print(f"[{datetime.now().isoformat()}] Wrote {CANDIDATES_FILE}: {len(needs_action)} candidate rows")

    if targets and errors == len(targets):
        print("ERROR: every institution check failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
