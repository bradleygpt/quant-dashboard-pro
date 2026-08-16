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

HARDENED 2026-08-15 after auditing the 2026-08-01 run, where 3 of 4 drafted URLs were
unusable and 2 of 9 institutions failed with an uninformative error:

  URL HYGIENE      The model's URL used to be written through untouched. It produced a
                   goldmansachs.com path with Tamil characters spliced into it, a
                   vertexaisearch grounding redirect (those expire), and a dead link.
                   resolve_url() now strips non-ASCII and retries, follows redirects to
                   the publisher URL, records the HTTP status, and flags links that land
                   on a login/subscribe page (those answer 200, so status alone calls a
                   paywall healthy — that is how Yardeni looked fine while being unreadable).

  DRAFT-CHECK      Quotes were drafted but never checked against the page, so the
                   downstream verifier spent its whole run discovering broken links
                   instead of judging figures. Each drafted quote is now matched against
                   the resolved page using the PROMOTER'S OWN matcher (imported, never
                   reimplemented) and annotated quote_found / QUOTE_NOT_IN_SOURCE /
                   unreadable, plus a `qualifier` when the source hedges the number
                   ("around 2 percent" is not a point estimate). Advisory only: nothing is
                   deleted, and promotion is still the promoter's decision.

  ERROR DETAIL     An empty Gemini response surfaced as `No JSON found: ` with nothing
                   after the colon — which is how BOTH Fannie Mae and Vanguard failed,
                   leaving no way to tell a safety block from a token cut-off. The error
                   now carries finishReason and promptFeedback, and max_tokens was raised
                   3000 -> 8000 because a full JSON of verbatim quotes can exceed 3000.

Usage:  python build_house_views_freshness.py
Env:    GEMINI_API_KEY
"""

import json
import re
import os
import sys
from datetime import datetime, timezone

import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# The promoter owns quote-matching; the generator borrows it so a drafted quote is
# judged by exactly the rule that will later gate it. Optional so a missing file or
# dependency degrades to "no draft-check" instead of taking the whole run down.
try:
    import verify_and_promote_house_views as _V
except Exception:                                   # noqa: BLE001
    _V = None

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


def call_gemini_with_search(prompt, max_tokens=8000):
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
    body = r.json()
    cands = body.get("candidates", [])
    if not cands:
        fb = body.get("promptFeedback") or {}
        raise RuntimeError(f"Gemini returned no candidates (promptFeedback={json.dumps(fb)[:200]})")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        # THE 2026-08-01 FAILURE: Fannie Mae and Vanguard both died here and the only
        # trace was "No JSON found: " with nothing after the colon — an empty response
        # reported as a parse error, so nobody could tell whether it was a safety block,
        # a token cut-off, or a grounding miss. Say which.
        raise RuntimeError(
            f"Gemini returned no text (finishReason={cands[0].get('finishReason')!r}, "
            f"parts={len(parts)}, promptFeedback={json.dumps(body.get('promptFeedback') or {})[:150]}). "
            f"finishReason MAX_TOKENS means the JSON was truncated — raise max_tokens.")
    return text


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


# ── URL hygiene ────────────────────────────────────────────────────────────
# Every URL in the 2026-08-01 run was passed through from the model untouched, and
# three of four were unusable: goldmansachs.com/insights/<TAMIL CHARACTERS>/... ,
# a vertexaisearch grounding redirect that only happened to still resolve, and a
# 404. The downstream verifier then spent its whole run on link quality instead of
# figure accuracy. A drafted URL is now resolved and probed before it is written.

def resolve_url(url, timeout=25):
    """Return (final_url, status, note). Never raises — a bad URL is data, not a crash."""
    if not url or not isinstance(url, str):
        return None, None, "no url returned"
    url = url.strip()
    note = None

    bad = [c for c in url if ord(c) > 127]
    if bad:
        # Model-injected junk mid-path (observed: Tamil script inside a GS path).
        # Strip and retry rather than discard: the rest of the path is usually right.
        stripped = "".join(c for c in url if ord(c) < 128).replace("//", "//", 1)
        note = f"URL contained {len(bad)} non-ASCII char(s) ({''.join(bad)[:12]!r}); retried stripped"
        url = re.sub(r"(?<!:)/{2,}", "/", stripped)

    try:
        r = requests.get(url, headers={"User-Agent": BROWSER_UA,
                                       "Accept-Language": "en-US,en;q=0.9"},
                         timeout=timeout, allow_redirects=True)
        final = r.url
        if "vertexaisearch" in url and "vertexaisearch" not in final:
            note = ((note + "; ") if note else "") + "resolved grounding redirect to publisher URL"
        if "vertexaisearch" in final:
            note = ((note + "; ") if note else "") + \
                   "STILL a grounding redirect (expires — replace with the publisher link)"
        # A paywall redirect answers 200, so status alone calls it healthy. Yardeni's
        # link resolves to /login and would otherwise sit on the board looking fine.
        if re.search(r"/(login|signin|sign-in|subscribe|register)\b", final, re.I):
            note = ((note + "; ") if note else "") + \
                   "redirects to a LOGIN/SUBSCRIBE page — content not publicly readable"
        return final, r.status_code, note
    except Exception as e:
        return url, None, ((note + "; ") if note else "") + f"unreachable: {type(e).__name__}"


def classify(report_month, prior_as_of):
    rm, pm = _ym(report_month), _ym(prior_as_of)
    if not rm:
        return "unknown"
    if not pm:
        return "new"            # never transcribed — here's a draft
    if rm > pm:
        return "stale"          # a newer report exists than transcribed
    return "current"            # transcription is up to date


def draft_check(values, url):
    """Check each drafted quote against the resolved page, using the SAME matcher the
    promoter uses (imported, not reimplemented — two copies would drift and the draft
    would start disagreeing with the gate it feeds).

    This is advisory: it annotates, it never deletes. A figure that fails here is still
    written to the candidates file, flagged, because a drafted number that the page does
    not support is exactly what a human needs to see. Promotion remains the promoter's
    job and its verdict is the one that counts."""
    if _V is None or not values or not url:
        return values, "draft-check skipped (verifier module or url unavailable)"
    try:
        text, _final = _V.fetch_text(url)
    except Exception as e:
        summary = f"draft-check could not read source: {type(e).__name__}"
        for byyear in values.values():
            for cell in byyear.values():
                cell["draft_check"] = "unreadable"
        return values, summary

    wall = _V.looks_like_interstitial(text, url)
    ok = miss = 0
    for byyear in values.values():
        for cell in byyear.values():
            if wall:
                cell["draft_check"] = "unreadable"
                continue
            if _V.quote_is_verified(cell.get("quote", ""), text):
                cell["draft_check"] = "quote_found"
                ok += 1
            else:
                cell["draft_check"] = "QUOTE_NOT_IN_SOURCE"
                miss += 1
            qual = _V.quote_qualifier(cell.get("quote", ""), cell.get("value"))
            if qual:
                cell["qualifier"] = qual      # "around 2%" is not a point estimate
    if wall:
        return values, f"draft-check could not read source: {wall}"
    return values, f"draft-check: {ok} quote(s) found, {miss} not in source"


def check_one(target, prior_as_of, years):
    text = call_gemini_with_search(build_prompt(target, years, prior_as_of))
    p = parse_json_response(text)
    report_month = p.get("report_month") if p.get("found") else None
    status = classify(report_month, prior_as_of)
    values = _clean_values(p.get("values")) if status in ("stale", "new") else {}

    final_url, http_status, url_note = resolve_url(p.get("url"))
    check_note = None
    if status in ("stale", "new") and values and http_status == 200:
        values, check_note = draft_check(values, final_url)
    elif values:
        check_note = f"draft-check skipped (url http {http_status})"

    return {
        "id": target["id"], "name": target["name"],
        "prior_as_of": prior_as_of, "report_month": report_month,
        "report_title": p.get("report_title"),
        "url": final_url, "url_http_status": http_status, "url_note": url_note,
        "draft_check": check_note,
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
            print(f"  {t['name']}: {res['status']} (report {res['report_month']} vs transcribed "
                  f"{t['prior_as_of']}, {sum(len(v) for v in res['values'].values())} figures)"
                  + (f" | url http {res.get('url_http_status')}" if res.get("url_http_status") else "")
                  + (f" | {res['url_note']}" if res.get("url_note") else "")
                  + (f" | {res['draft_check']}" if res.get("draft_check") else ""))
            results.append(res)
        except Exception as e:
            errors += 1
            print(f"  {t['name']}: ERROR {str(e)[:160]}", file=sys.stderr)
            results.append({"id": t["id"], "name": t["name"], "status": "error",
                            "error": str(e)[:200], "prior_as_of": t["prior_as_of"], "values": {}})

    needs_action = [r for r in results if r["status"] in ("stale", "new")]
    now = datetime.now(timezone.utc)

    # A TOTAL failure carries no information about any institution, but the old code
    # still wrote both files — so one bad run (an unset key, a revoked token, an API
    # outage) replaced a good board with an all-errors board and emptied the candidates
    # file, destroying the very state a human was working from. Proven the hard way:
    # a keyless smoke-test on 2026-08-16 wiped 4 candidate rows and the 08-01 report.
    # Fail loudly, keep the last good state.
    if targets and errors == len(targets):
        print(f"ERROR: every institution check failed ({errors}/{len(targets)}). "
              f"Leaving {FRESHNESS_FILE} and {CANDIDATES_FILE} UNTOUCHED — a run that "
              f"learned nothing must not overwrite the last run that did.", file=sys.stderr)
        for r in results[:3]:
            print(f"  e.g. {r['name']}: {str(r.get('error'))[:120]}", file=sys.stderr)
        sys.exit(1)

    # 1) freshness report (status board the dashboard badge reads)
    freshness = {
        "checked_utc": now.isoformat(),
        "checked_human": now.strftime("%Y-%m-%d %H:%M UTC"),
        "status": "ok" if errors < len(targets) else "failed",
        "needs_action_count": len(needs_action),
        "forecasters": [{k: r.get(k) for k in
                         ("id", "name", "status", "prior_as_of", "report_month", "report_title", "url",
                          "url_http_status", "url_note", "draft_check", "error")}
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
             "url_http_status": r.get("url_http_status"), "url_note": r.get("url_note"),
             "draft_check": r.get("draft_check"),
             "inflation_basis": r.get("inflation_basis"), "notes": r.get("notes"),
             "values": r["values"]}
            for r in needs_action
        ],
    }
    json.dump(candidates, open(CANDIDATES_FILE, "w"), indent=2)
    print(f"[{datetime.now().isoformat()}] Wrote {CANDIDATES_FILE}: {len(needs_action)} candidate rows")



if __name__ == "__main__":
    main()
