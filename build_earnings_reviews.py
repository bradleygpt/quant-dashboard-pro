"""
build_earnings_reviews.py — batch-generate 8-K earnings reviews to populate ai_earnings_cache.json
(the deep, structured reviews the dashboard's bake copies to earnings_reviews.json for Vercel).

Run with an LLM key set in the environment — GEMINI_API_KEY (free tier), ANTHROPIC_API_KEY, or a
local Ollama. earnings_reviewer.generate_earnings_review fetches the current+prior 8-K from SEC
EDGAR, calls the LLM, and caches per filing — so this is safely re-runnable (cached names skip the
LLM). Reads names/context from the baked universe.

  python build_earnings_reviews.py            # whole universe
  python build_earnings_reviews.py 50          # first 50 (smoke test)
  python build_earnings_reviews.py MU CRM SNOW # specific tickers
"""
import sys, json, time
from earnings_reviewer import generate_earnings_review

UNIVERSE = r"C:\Users\bmhar\code\quant-dashboard-pro-v2\public\data\universe_floor0.json"
rows = [r for r in json.load(open(UNIVERSE))["rows"] if r.get("sector") != "ETF"]
rowmap = {r["ticker"]: r for r in rows}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def context_for(r: dict) -> dict:
    return {
        "sector": r.get("sector") or "unknown",
        "quant_rating": r.get("rating") or "n/a",
        "composite_score": _num((r.get("byPreset", {}).get("equal", {}) or {}).get("c")),
        "current_price": _num(r.get("price")),
        "fair_value": _num(r.get("fv")),
        "buy_point": _num(r.get("qbp")),
    }


def run(tickers):
    ok = newc = fail = 0
    t0 = time.time()
    for i, tk in enumerate(tickers):
        r = rowmap.get(tk)
        if not r:
            print(f"  {tk}: not in universe", file=sys.stderr)
            continue
        try:
            res = generate_earnings_review(tk, r.get("name") or tk, context_for(r))
            if res.get("ok"):
                ok += 1
                if not res.get("cached"):
                    newc += 1
                tag = "cached" if res.get("cached") else f"NEW {res.get('verdict', '')}"
            else:
                fail += 1
                tag = f"FAIL {str(res.get('error', ''))[:48]}"
        except Exception as e:
            fail += 1
            tag = f"EXC {e!r}"[:60]
        if i % 10 == 0 or "NEW" in tag or "FAIL" in tag:
            print(f"  {i+1}/{len(tickers)} {tk}: {tag}  ({time.time()-t0:.0f}s)", file=sys.stderr)
        time.sleep(0.5)  # gentle on SEC EDGAR + the LLM free tier
    print(f"DONE: {ok} ok ({newc} newly generated), {fail} failed, {time.time()-t0:.0f}s "
          f"-> ai_earnings_cache.json (bake copies it to earnings_reviews.json)", file=sys.stderr)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0].isdigit():
        tks = list(rowmap)[: int(args[0])]
    elif args:
        tks = [a.upper() for a in args]
    else:
        tks = list(rowmap)
    print(f"Generating earnings reviews for {len(tks)} names "
          f"(LLM key required: GEMINI_API_KEY / ANTHROPIC_API_KEY / Ollama)...", file=sys.stderr)
    run(tks)
