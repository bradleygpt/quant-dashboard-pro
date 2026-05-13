"""
AI Earnings Reviewer module.

Generates a structured earnings review for a stock using:
- Current quarter 8-K (extracted metrics + forward guidance)
- Prior quarter 8-K (what was guided last time, for thesis-check)
- LLM synthesis into hybrid E format with BUY/HOLD/TRIM/EXIT verdict

Zero-cost: uses free SEC EDGAR + free Gemini tier (with Claude/Ollama fallback
via the existing ai_assistant.call_llm router).

Cache: writes to ai_earnings_cache.json keyed by {ticker}_{fiscal_period}.
Same earnings = same review forever; safe to cache aggressively.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

# Cache file location (created on first use)
CACHE_FILE = Path("ai_earnings_cache.json")

# SEC EDGAR headers (User-Agent required by SEC fair-access rules)
_SEC_HEADERS = {
    "User-Agent": "QuantDashboardPro bmhartnett@yahoo.com",
    "Accept-Encoding": "gzip, deflate",
}

# Approved earnings-related 8-K item types
_EARNINGS_8K_ITEMS = {"2.02", "7.01", "8.01"}


# ───────────────────────────────────────────────────────────────
# Cache helpers
# ───────────────────────────────────────────────────────────────

def _load_cache() -> Dict:
    """Load the local JSON cache. Returns empty dict if no cache yet."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: Dict) -> None:
    """Persist cache to disk."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, default=str)
    except OSError:
        pass


def _cache_key(ticker: str, period: str) -> str:
    """Build a stable cache key."""
    return f"{ticker.upper()}_{period}"


def get_cached_review(ticker: str, period: str) -> Optional[Dict]:
    """Return cached review for a ticker + period, or None."""
    cache = _load_cache()
    return cache.get(_cache_key(ticker, period))


def save_review(ticker: str, period: str, review: Dict) -> None:
    """Store a generated review in the cache."""
    cache = _load_cache()
    cache[_cache_key(ticker, period)] = {
        **review,
        "ticker": ticker.upper(),
        "period": period,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_cache(cache)


def get_all_recent_reviews(days: int = 90, min_verdict_rank: int = 4) -> List[Dict]:
    """Return all cached reviews from last `days` days with verdict rank >= min_verdict_rank.

    Verdict ranks:
      5 = BUY ON STRENGTH
      4 = BUY
      3 = HOLD
      2 = TRIM
      1 = EXIT
    Default min_verdict_rank=4 returns only BUY and BUY ON STRENGTH.
    """
    cache = _load_cache()
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    out = []
    for key, review in cache.items():
        cached_at = review.get("cached_at")
        if not cached_at:
            continue
        try:
            ts = datetime.fromisoformat(cached_at.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            continue
        if ts < cutoff:
            continue
        rank = _verdict_rank(review.get("verdict", ""))
        if rank < min_verdict_rank:
            continue
        out.append(review)
    # Sort newest first
    out.sort(key=lambda r: r.get("cached_at", ""), reverse=True)
    return out


def _verdict_rank(verdict: str) -> int:
    """Map verdict label to rank for filtering/sorting."""
    if not verdict:
        return 0
    v = verdict.upper().strip()
    if "BUY ON STRENGTH" in v:
        return 5
    if v == "BUY" or v.startswith("BUY"):
        return 4
    if "HOLD" in v:
        return 3
    if "TRIM" in v:
        return 2
    if "EXIT" in v:
        return 1
    return 0


# ───────────────────────────────────────────────────────────────
# SEC EDGAR 8-K fetcher
# ───────────────────────────────────────────────────────────────

def _get_cik(ticker: str) -> Optional[str]:
    """Lookup CIK for a ticker via EDGAR's company_tickers.json."""
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_SEC_HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return str(entry["cik_str"]).zfill(10)
    except Exception:
        return None
    return None


def _list_recent_8ks(cik: str, limit: int = 10) -> List[Dict]:
    """Return list of recent 8-K filings for a CIK.

    Each item: {accession, filing_date, items, primary_doc_url}
    """
    try:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        r = requests.get(url, headers=_SEC_HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        items_list = recent.get("items", [])
        primary_docs = recent.get("primaryDocument", [])

        out = []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            items = items_list[i] if i < len(items_list) else ""
            # Filter to earnings-related 8-Ks
            item_set = set(re.findall(r"\d+\.\d+", items))
            if not item_set & _EARNINGS_8K_ITEMS:
                continue
            accession = accessions[i]
            accession_clean = accession.replace("-", "")
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            out.append({
                "accession": accession,
                "filing_date": dates[i] if i < len(dates) else "",
                "items": items,
                "primary_doc_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/{primary_doc}",
            })
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def _fetch_8k_text(url: str, max_chars: int = 20000) -> str:
    """Fetch an 8-K primary document and extract readable text.

    SEC docs are HTML; we strip tags and limit length to control LLM token usage.
    """
    try:
        r = requests.get(url, headers=_SEC_HEADERS, timeout=15)
        if r.status_code != 200:
            return ""
        text = r.text
        # Strip HTML tags
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode common HTML entities
        text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                     .replace("&nbsp;", " ").replace("&#160;", " ").replace("&quot;", '"'))
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


def get_recent_earnings_8ks(ticker: str, n: int = 2) -> List[Dict]:
    """Get the N most recent earnings-related 8-Ks for a ticker.

    Returns list of dicts with: filing_date, items, text (truncated), url.
    """
    cik = _get_cik(ticker)
    if not cik:
        return []
    filings = _list_recent_8ks(cik, limit=n * 2)  # Fetch more, then prune
    out = []
    for f in filings[:n]:
        text = _fetch_8k_text(f["primary_doc_url"])
        if text:
            out.append({
                "filing_date": f["filing_date"],
                "items": f["items"],
                "text": text,
                "url": f["primary_doc_url"],
            })
    return out


# ───────────────────────────────────────────────────────────────
# LLM-driven review generation
# ───────────────────────────────────────────────────────────────

_REVIEW_PROMPT_TEMPLATE = """You are a sober buy-side equity analyst writing a structured earnings review for {ticker} ({company_name}).

You have access to TWO earnings filings:

CURRENT QUARTER 8-K (filed {current_date}):
{current_8k}

PRIOR QUARTER 8-K (filed {prior_date}) — used to check whether prior guidance was met:
{prior_8k}

CONTEXT (current quant snapshot):
- Sector: {sector}
- Quant rating: {quant_rating}
- Composite score: {composite_score}/12
- Current price: ${current_price}
- Fair Value estimate: {fair_value}
- Quant Buy Point: {buy_point}

Generate a structured review with EXACTLY these sections. Use the exact section headers below. Be specific with numbers when available. If a number isn't in the filing, say "not disclosed" rather than guessing.

VERDICT: [one of: BUY ON STRENGTH, BUY, HOLD, TRIM, EXIT]
[2-3 sentences: WHY this verdict. Tie to actuals vs prior guidance + forward implications.]

HEADLINE
[1-2 sentences: the single most important fact about this earnings.]

KEY METRICS
- Revenue: $X.XB (beat/miss by Y% vs analyst consensus if known, or vs prior guide)
- EPS: $X.XX (beat/miss by Y% vs estimates or guide)
- Gross margin / Operating margin: [if disclosed]
- Segment highlights: [if disclosed, max 2 segments]

GUIDANCE
- Forward quarter / year guidance: [specific numbers when given]
- Direction: RAISED / MAINTAINED / LOWERED / NEW (vs what was previously guided)

THESIS CHECK (vs prior quarter's guidance)
[Compare actuals reported THIS quarter to what management guided LAST quarter. State explicitly: "Last quarter guided X; actual was Y; variance Z." If prior guidance is not extractable, say so.]

CALLOUTS
- [2-3 bullets: specific non-obvious facts the market should care about. E.g., new product traction, regulatory shifts, capex commitments, capital returns, management changes.]

BOTTOM LINE
[1-2 sentences: net effect on the investment thesis. Stay neutral; don't recommend the stock — that's the user's call.]

CRITICAL RULES:
- The VERDICT must be ONE of the five labels exactly as written.
- Do not invent numbers. If the filing doesn't disclose something, say "not disclosed".
- Tie the verdict reasoning to specific facts in the filing, not vibes.
- Keep total output under 400 words.
"""


def _build_prompt(
    ticker: str,
    company_name: str,
    current_8k: Dict,
    prior_8k: Optional[Dict],
    context: Dict,
) -> str:
    """Construct the LLM prompt for an earnings review."""
    current_text = current_8k.get("text", "")[:8000]
    current_date = current_8k.get("filing_date", "unknown")

    if prior_8k:
        prior_text = prior_8k.get("text", "")[:8000]
        prior_date = prior_8k.get("filing_date", "unknown")
    else:
        prior_text = "(No prior 8-K available — this is the earliest available filing or prior filings could not be retrieved.)"
        prior_date = "n/a"

    fair_value = context.get("fair_value")
    fv_str = f"${fair_value:.2f}" if fair_value else "not available"
    buy_point = context.get("buy_point")
    bp_str = f"${buy_point:.2f}" if buy_point else "not available"

    return _REVIEW_PROMPT_TEMPLATE.format(
        ticker=ticker,
        company_name=company_name or ticker,
        current_date=current_date,
        current_8k=current_text,
        prior_date=prior_date,
        prior_8k=prior_text,
        sector=context.get("sector", "unknown"),
        quant_rating=context.get("quant_rating", "unknown"),
        composite_score=f"{context.get('composite_score', 0):.1f}",
        current_price=f"{context.get('current_price', 0):.2f}",
        fair_value=fv_str,
        buy_point=bp_str,
    )


def _parse_verdict(text: str) -> str:
    """Extract the verdict label from the LLM output."""
    # Look for "VERDICT: ..." line
    match = re.search(r"VERDICT:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if not match:
        return "HOLD"
    verdict_line = match.group(1).strip()
    # Normalize: pick the first known label that appears
    v_upper = verdict_line.upper()
    if "BUY ON STRENGTH" in v_upper:
        return "BUY ON STRENGTH"
    if v_upper.startswith("BUY"):
        return "BUY"
    if "EXIT" in v_upper:
        return "EXIT"
    if "TRIM" in v_upper:
        return "TRIM"
    if "HOLD" in v_upper:
        return "HOLD"
    return "HOLD"


def _parse_headline(text: str) -> str:
    """Extract the HEADLINE section from the LLM output."""
    match = re.search(
        r"HEADLINE\s*\n+(.+?)(?:\n\s*(?:KEY METRICS|GUIDANCE|THESIS CHECK|CALLOUTS|BOTTOM LINE)|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()[:300]
    return ""


def generate_earnings_review(
    ticker: str,
    company_name: str,
    context: Dict,
    force_regenerate: bool = False,
) -> Dict:
    """Generate (or retrieve cached) earnings review for a ticker.

    Returns dict:
      ok: bool
      verdict: str
      headline: str
      full_text: str
      filing_date: str
      filing_url: str
      cached: bool (True if from cache, False if freshly generated)
      provider: str (LLM provider used)
      error: str (if ok=False)
    """
    # Fetch 8-Ks first to determine the period key
    filings = get_recent_earnings_8ks(ticker, n=2)
    if not filings:
        return {
            "ok": False,
            "error": "No recent earnings 8-K filings found via SEC EDGAR.",
        }

    current_8k = filings[0]
    prior_8k = filings[1] if len(filings) > 1 else None
    period_key = current_8k["filing_date"]

    # Check cache (unless force_regenerate)
    if not force_regenerate:
        cached = get_cached_review(ticker, period_key)
        if cached:
            return {**cached, "cached": True}

    # Build prompt and call LLM
    prompt = _build_prompt(ticker, company_name, current_8k, prior_8k, context)

    try:
        # Import here to avoid circular imports
        from ai_assistant import call_llm
        llm_result = call_llm(
            prompt,
            max_tokens=1200,
            temperature=0.3,
            feature="earnings_review",
        )
    except Exception as e:
        return {
            "ok": False,
            "error": f"LLM call failed: {str(e)[:200]}",
        }

    if "error" in llm_result:
        return {
            "ok": False,
            "error": llm_result["error"],
        }

    full_text = llm_result.get("text", "")
    if not full_text or len(full_text) < 50:
        return {
            "ok": False,
            "error": "LLM returned empty or too-short response.",
        }

    verdict = _parse_verdict(full_text)
    headline = _parse_headline(full_text)

    review = {
        "ok": True,
        "verdict": verdict,
        "headline": headline,
        "full_text": full_text,
        "filing_date": current_8k["filing_date"],
        "filing_url": current_8k["url"],
        "prior_filing_date": prior_8k["filing_date"] if prior_8k else "n/a",
        "company_name": company_name,
        "provider": llm_result.get("provider", "unknown"),
        "model": llm_result.get("model", ""),
        "cached": False,
    }

    # Persist to cache (period_key = current filing date for stability)
    save_review(ticker, period_key, review)

    return review


# ───────────────────────────────────────────────────────────────
# Verdict styling helpers (used by UI rendering)
# ───────────────────────────────────────────────────────────────

VERDICT_COLORS = {
    "BUY ON STRENGTH": "#10b981",  # bright green
    "BUY": "#22c55e",                # green
    "HOLD": "#94a3b8",               # gray
    "TRIM": "#f97316",               # orange
    "EXIT": "#ef4444",               # red
}


def get_verdict_color(verdict: str) -> str:
    """Map a verdict label to a display color."""
    return VERDICT_COLORS.get(verdict, "#94a3b8")
