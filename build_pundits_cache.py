"""
Pundit Views Fetcher
====================

Runs once daily via GitHub Actions. Makes 2 Gemini calls:
1. "Find the most active equity market commentators this week and summarize their views"
2. "Find the most active crypto commentators this week and summarize their views"

Writes results to pundits_cache.json with timestamp.

The Streamlit app reads from this JSON cache — zero live API calls during user sessions.

Usage:
    python build_pundits_cache.py

Environment variables required:
    GEMINI_API_KEY
"""

import os
import json
import sys
from datetime import datetime, timezone

import requests


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

CACHE_FILE = "pundits_cache.json"


def fetch_current_market_context():
    """Get current S&P 500, BTC, ETH prices to provide context to Gemini."""
    try:
        import yfinance as yf
        spy = yf.Ticker("SPY").history(period="5d")
        btc = yf.Ticker("BTC-USD").history(period="5d")
        eth = yf.Ticker("ETH-USD").history(period="5d")

        spy_price = float(spy["Close"].iloc[-1]) if not spy.empty else None
        btc_price = float(btc["Close"].iloc[-1]) if not btc.empty else None
        eth_price = float(eth["Close"].iloc[-1]) if not eth.empty else None

        sp500_level = spy_price * 10 if spy_price else None

        return {
            "spy_price": spy_price,
            "sp500_level": sp500_level,
            "btc_price": btc_price,
            "eth_price": eth_price,
        }
    except Exception as e:
        print(f"Warning: could not fetch market context: {e}", file=sys.stderr)
        return {}


def call_gemini_with_search(prompt, max_tokens=4000):
    """Call Gemini with web search grounding enabled."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": max_tokens,
        },
    }

    response = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=120)

    if response.status_code != 200:
        raise RuntimeError(f"Gemini API error {response.status_code}: {response.text[:500]}")

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"No candidates in response: {json.dumps(data)[:500]}")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    return text


def build_equity_prompt(market_ctx):
    """Build the single-call prompt for equity commentators."""
    sp500 = market_ctx.get("sp500_level")
    sp500_str = f"~{sp500:,.0f}" if sp500 else "current level"
    today = datetime.now().strftime("%B %d, %Y")

    return f"""Search the web for the most active and influential US stock market commentators in the LAST 7 DAYS. Focus on people who have made public statements (CNBC, Bloomberg, X/Twitter, Substack, podcasts, research notes) within the past week about the broader equity market outlook.

CURRENT CONTEXT:
- Today's date: {today}
- Current S&P 500 level: {sp500_str}

Identify the 5-15 commentators who have made the MOST NOTABLE statements this week. Mix bullish, bearish, and neutral views — represent the full spectrum of credible voices currently in the discussion. Examples of commentators to consider include (but are not limited to): Tom Lee, Mike Wilson, David Rosenberg, Cathie Wood, Jeremy Siegel, Marko Kolanovic, Savita Subramanian, Jim Cramer, Mohamed El-Erian, Liz Ann Sonders, Tony Dwyer, Brian Belski, Lisa Shalett, Jurrien Timmer, Lance Roberts, Stanley Druckenmiller, Ray Dalio, Howard Marks, Nouriel Roubini.

For each commentator you select, return their actual recent statements — do not fabricate. If a price target is mentioned, ensure it directionally matches the stance: a target ABOVE {sp500_str} = bullish, BELOW = bearish.

Return ONLY a JSON object in this exact format, no other text:

{{
  "commentators": [
    {{
      "name": "Name",
      "firm": "Firm or affiliation",
      "stance": "Bullish | Cautiously Bullish | Neutral | Cautious | Bearish",
      "key_quote": "Direct quote of 15-25 words from recent statement",
      "quote_source": "Publication or platform",
      "quote_date": "Specific date or 'Last week'",
      "key_views": ["View 1", "View 2", "View 3"],
      "price_target_or_view": "Specific S&P 500 target with implied direction, or qualitative view"
    }}
  ],
  "synthesis": "2-3 sentence overview of where consensus and disagreement are this week",
  "themes": ["Top theme 1", "Top theme 2", "Top theme 3"]
}}

Be accurate. Better to return fewer commentators with verified quotes than more with fabricated content. Aim for 5-15 high-quality entries, mixed across the bullish/bearish spectrum."""


def build_crypto_prompt(market_ctx):
    """Build the single-call prompt for crypto commentators."""
    btc = market_ctx.get("btc_price")
    eth = market_ctx.get("eth_price")
    btc_str = f"~${btc:,.0f}" if btc else "current price"
    eth_str = f"~${eth:,.0f}" if eth else "current price"
    today = datetime.now().strftime("%B %d, %Y")

    return f"""Search the web for the most active and influential cryptocurrency commentators in the LAST 7 DAYS. Focus on people who have made public statements (X/Twitter, podcasts, CNBC, Bloomberg, Substack, research) within the past week about Bitcoin, Ethereum, or the broader crypto market.

CURRENT CONTEXT:
- Today's date: {today}
- Current BTC price: {btc_str}
- Current ETH price: {eth_str}

Identify the 5-15 commentators who have made the MOST NOTABLE statements this week. Mix bullish, bearish, and neutral views — represent the full spectrum of credible voices. Examples to consider (not exhaustive): Michael Saylor, Anthony Pompliano, Tom Lee, PlanB, Cathie Wood, Raoul Pal, Arthur Hayes, Willy Woo, Peter Schiff, Nouriel Roubini, Vitalik Buterin, Balaji Srinivasan, Mike Novogratz, Lyn Alden, Caitlin Long, Jim Chanos, Jamie Dimon, Nic Carter, Andreas Antonopoulos.

For each commentator, return their actual recent statements — do not fabricate. If a price target is mentioned, verify it directionally matches the stance.

Return ONLY a JSON object in this exact format, no other text:

{{
  "commentators": [
    {{
      "name": "Name",
      "firm": "Firm or affiliation",
      "stance": "Very Bullish | Bullish | Cautiously Bullish | Neutral | Cautious | Bearish | Very Bearish",
      "key_quote": "Direct quote of 15-25 words from recent statement",
      "quote_source": "Publication or platform",
      "quote_date": "Specific date or 'Last week'",
      "key_views": ["View 1", "View 2", "View 3"],
      "btc_view": "Specific BTC view or 'Not specified'",
      "eth_view": "Specific ETH view or 'Not specified'",
      "price_target": "Specific target with implied direction, or qualitative view"
    }}
  ],
  "synthesis": "2-3 sentence overview of crypto consensus and disagreement this week",
  "themes": ["Top theme 1", "Top theme 2", "Top theme 3"]
}}

Be accurate. Aim for 5-15 high-quality entries mixed across the bullish/bearish spectrum.
Focus on cryptocurrency views, not equities or general macro."""


def parse_json_response(text):
    """Extract JSON from Gemini response, handling code fences."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        if lines[-1].startswith("```"):
            text = "\n".join(lines[1:-1])
        else:
            text = "\n".join(lines[1:])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try regex fallback
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Could not parse JSON: {e}")
        raise RuntimeError(f"No JSON found in response: {text[:300]}")


def validate_directional(commentator, current_level, key="price_target_or_view"):
    """Add validation warning if stance contradicts price target direction."""
    if not current_level:
        return commentator

    target_text = commentator.get(key, "")
    stance = commentator.get("stance", "")

    if not target_text or not stance:
        return commentator

    # Extract numeric target
    import re
    candidates = []
    for match in re.findall(r'\b(\d[\d,]*\d|\d)\b', target_text.replace(",", "")):
        try:
            n = int(match)
            # Reasonable range: S&P 500 (3000-15000), BTC ($10k-$500k), ETH ($500-$10k)
            if 500 <= n <= 500000:
                candidates.append(n)
        except ValueError:
            pass

    if not candidates:
        return commentator

    target = candidates[0]
    pct_move = ((target - current_level) / current_level) * 100

    is_bullish = stance in ("Bullish", "Cautiously Bullish", "Very Bullish")
    is_bearish = stance in ("Bearish", "Cautious", "Very Bearish")

    if pct_move <= -5 and is_bullish:
        commentator["_validation_warning"] = (
            f"Stance auto-corrected: target {target:,} implies {pct_move:.1f}% downside "
            f"from current ~{current_level:,.0f}, conflicts with '{stance}' stance."
        )
        commentator["stance"] = "Bearish" if pct_move <= -10 else "Cautious"
    elif pct_move >= 5 and is_bearish:
        commentator["_validation_warning"] = (
            f"Stance auto-corrected: target {target:,} implies {pct_move:+.1f}% upside "
            f"from current ~{current_level:,.0f}, conflicts with '{stance}' stance."
        )
        commentator["stance"] = "Bullish" if pct_move >= 10 else "Cautiously Bullish"

    return commentator


def fetch_equity_pundits(market_ctx):
    """Fetch equity pundits via single Gemini call."""
    prompt = build_equity_prompt(market_ctx)
    print(f"[{datetime.now().isoformat()}] Calling Gemini for equity pundits...")
    text = call_gemini_with_search(prompt, max_tokens=4000)
    print(f"[{datetime.now().isoformat()}] Got equity response, length: {len(text)}")

    parsed = parse_json_response(text)

    # Apply directional validation to each
    sp500 = market_ctx.get("sp500_level")
    if sp500 and "commentators" in parsed:
        parsed["commentators"] = [
            validate_directional(c, sp500, key="price_target_or_view")
            for c in parsed["commentators"]
        ]

    return parsed


def fetch_crypto_pundits(market_ctx):
    """Fetch crypto pundits via single Gemini call."""
    prompt = build_crypto_prompt(market_ctx)
    print(f"[{datetime.now().isoformat()}] Calling Gemini for crypto pundits...")
    text = call_gemini_with_search(prompt, max_tokens=4000)
    print(f"[{datetime.now().isoformat()}] Got crypto response, length: {len(text)}")

    parsed = parse_json_response(text)

    # Apply directional validation against BTC for crypto pundits
    btc = market_ctx.get("btc_price")
    if btc and "commentators" in parsed:
        parsed["commentators"] = [
            validate_directional(c, btc, key="price_target")
            for c in parsed["commentators"]
        ]

    return parsed


def main():
    """Build the pundits cache and write to JSON file."""
    print(f"[{datetime.now().isoformat()}] Starting pundits cache build")

    market_ctx = fetch_current_market_context()
    print(f"[{datetime.now().isoformat()}] Market context: {market_ctx}")

    # Try to load existing cache as fallback
    existing_cache = None
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                existing_cache = json.load(f)
        except Exception:
            pass

    # Fetch equity
    equity_data = None
    equity_error = None
    try:
        equity_data = fetch_equity_pundits(market_ctx)
        n = len(equity_data.get("commentators", []))
        print(f"[{datetime.now().isoformat()}] Equity: got {n} commentators")
    except Exception as e:
        equity_error = str(e)[:300]
        print(f"[{datetime.now().isoformat()}] Equity fetch failed: {equity_error}", file=sys.stderr)

    # Fetch crypto
    crypto_data = None
    crypto_error = None
    try:
        crypto_data = fetch_crypto_pundits(market_ctx)
        n = len(crypto_data.get("commentators", []))
        print(f"[{datetime.now().isoformat()}] Crypto: got {n} commentators")
    except Exception as e:
        crypto_error = str(e)[:300]
        print(f"[{datetime.now().isoformat()}] Crypto fetch failed: {crypto_error}", file=sys.stderr)

    # Build cache - preserve old data if new fetch failed for that section
    cache = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "last_updated_human": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "market_context": market_ctx,
    }

    if equity_data:
        cache["equity"] = equity_data
        cache["equity_status"] = "fresh"
    elif existing_cache and "equity" in existing_cache:
        cache["equity"] = existing_cache["equity"]
        cache["equity_status"] = "stale"
        cache["equity_last_fresh"] = existing_cache.get("last_updated_utc", "unknown")
        cache["equity_error"] = equity_error
    else:
        cache["equity"] = {"commentators": [], "synthesis": "", "themes": []}
        cache["equity_status"] = "failed"
        cache["equity_error"] = equity_error

    if crypto_data:
        cache["crypto"] = crypto_data
        cache["crypto_status"] = "fresh"
    elif existing_cache and "crypto" in existing_cache:
        cache["crypto"] = existing_cache["crypto"]
        cache["crypto_status"] = "stale"
        cache["crypto_last_fresh"] = existing_cache.get("last_updated_utc", "unknown")
        cache["crypto_error"] = crypto_error
    else:
        cache["crypto"] = {"commentators": [], "synthesis": "", "themes": []}
        cache["crypto_status"] = "failed"
        cache["crypto_error"] = crypto_error

    # Write
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"[{datetime.now().isoformat()}] Wrote {CACHE_FILE}")
    print(f"  Equity: {cache['equity_status']} ({len(cache['equity'].get('commentators', []))} commentators)")
    print(f"  Crypto: {cache['crypto_status']} ({len(cache['crypto'].get('commentators', []))} commentators)")

    # Exit non-zero if BOTH failed and we had no fallback
    if cache["equity_status"] == "failed" and cache["crypto_status"] == "failed":
        print("ERROR: Both fetches failed and no existing cache to fall back to", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
