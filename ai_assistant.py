"""
AI Integration Layer
Pluggable LLM provider framework. Default: Google Gemini free tier.
Swap providers by changing PROVIDER env var or config.

Providers supported:
- gemini (free tier available)
- claude (requires ANTHROPIC_API_KEY)
- openai (requires OPENAI_API_KEY)
- ollama (local, free, requires Ollama running)

Usage:
    from ai_assistant import generate_analysis
    result = generate_analysis(prompt, context_data)
"""

import os
import json
import requests
import streamlit as st
from datetime import datetime


# ── Configuration ──────────────────────────────────────────────────

PROVIDER = os.getenv("AI_PROVIDER", "gemini")  # Default to free Gemini

# API key loading with Streamlit secrets fallback
def _get_key(name):
    """Try env var first, then Streamlit secrets."""
    val = os.getenv(name)
    if val:
        return val
    try:
        return st.secrets.get(name)
    except Exception:
        return None


GEMINI_API_KEY = _get_key("GEMINI_API_KEY")
ANTHROPIC_API_KEY = _get_key("ANTHROPIC_API_KEY")
OPENAI_API_KEY = _get_key("OPENAI_API_KEY")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


# ── Provider-specific API calls ────────────────────────────────────

def _call_gemini(prompt, max_tokens=800, temperature=0.7):
    """Call Google Gemini API. Using gemini-flash-latest for best free tier limits (10 RPM, 250 RPD on 2.0 Flash; 15 RPM on Flash Lite)."""
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY not configured. Get a free key at https://aistudio.google.com/apikey"}

    # Use gemini-2.5-flash-lite for higher free tier quotas (15 RPM, 1000 RPD)
    # Fallback to gemini-2.0-flash-exp if needed
    model = "gemini-2.5-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 429:
            return {"error": "Gemini free tier quota exceeded. Limits reset daily. Consider waiting or switching models in ai_assistant.py."}
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return {"text": text, "provider": "gemini", "model": model}
    except requests.HTTPError as e:
        return {"error": f"Gemini API error: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Gemini call failed: {str(e)}"}


def _call_claude(prompt, max_tokens=800, temperature=0.7):
    """Call Anthropic Claude API."""
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured."}
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"]
        return {"text": text, "provider": "claude", "model": payload["model"]}
    except Exception as e:
        return {"error": f"Claude call failed: {str(e)}"}


def _call_ollama(prompt, max_tokens=800, temperature=0.7):
    """Call local Ollama (free, requires Ollama running locally)."""
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": "llama3.2",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"text": data["response"], "provider": "ollama", "model": "llama3.2"}
    except Exception as e:
        return {"error": f"Ollama call failed (is Ollama running at {OLLAMA_HOST}?): {str(e)}"}


def _call_openai(prompt, max_tokens=800, temperature=0.7):
    """Call OpenAI API."""
    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY not configured."}
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return {"text": data["choices"][0]["message"]["content"], "provider": "openai", "model": "gpt-4o-mini"}
    except Exception as e:
        return {"error": f"OpenAI call failed: {str(e)}"}


# ── Unified Interface ─────────────────────────────────────────────

def call_llm(prompt, max_tokens=800, temperature=0.7, provider=None, feature="general"):
    """Unified LLM call with user permission check. Returns {text, provider, model} or {error}."""
    # Check user permission
    try:
        from auth import can_use_ai, log_ai_call, is_logged_in
        if not is_logged_in():
            return {"error": "Please log in to use AI features."}
        allowed, msg = can_use_ai()
        if not allowed:
            return {"error": msg}
    except ImportError:
        pass  # Auth module optional

    p = provider or PROVIDER
    if p == "gemini":
        result = _call_gemini(prompt, max_tokens, temperature)
    elif p == "claude":
        result = _call_claude(prompt, max_tokens, temperature)
    elif p == "ollama":
        result = _call_ollama(prompt, max_tokens, temperature)
    elif p == "openai":
        result = _call_openai(prompt, max_tokens, temperature)
    else:
        return {"error": f"Unknown provider: {p}"}

    # Log successful call
    if "error" not in result:
        try:
            from auth import log_ai_call
            log_ai_call(feature_name=feature)
        except ImportError:
            pass

    return result


def is_ai_available():
    """Check if any AI provider is configured."""
    if PROVIDER == "gemini" and GEMINI_API_KEY:
        return True
    if PROVIDER == "claude" and ANTHROPIC_API_KEY:
        return True
    if PROVIDER == "openai" and OPENAI_API_KEY:
        return True
    if PROVIDER == "ollama":
        try:
            requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
            return True
        except Exception:
            return False
    return False


# ── Specialized Prompts ───────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def generate_stock_research_note(ticker, stock_data, fv_data, sector_avgs=None):
    """Generate an AI research note for a stock."""
    prompt = f"""You are a senior equity analyst. Write a concise 4-paragraph research note for {ticker} ({stock_data.get('shortName', ticker)}).

STOCK DATA:
- Sector: {stock_data.get('sector', 'N/A')}, Industry: {stock_data.get('industry', 'N/A')}
- Market Cap: ${stock_data.get('marketCapB', 0):.1f}B
- Price: ${stock_data.get('currentPrice', 0):.2f}
- Composite Quant Score: {stock_data.get('composite_score', 0):.1f}/12 ({stock_data.get('overall_rating', 'N/A')})
- Pillar Grades: Valuation={stock_data.get('Valuation_grade', 'N/A')}, Growth={stock_data.get('Growth_grade', 'N/A')}, Profitability={stock_data.get('Profitability_grade', 'N/A')}, Momentum={stock_data.get('Momentum_grade', 'N/A')}, EPS Revisions={stock_data.get('EPS Revisions_grade', 'N/A')}
- Key Metrics: P/E={stock_data.get('trailingPE', 'N/A')}, PEG={stock_data.get('pegRatio', 'N/A')}, Rev Growth={stock_data.get('revenueGrowth', 'N/A')}, Profit Margin={stock_data.get('profitMargins', 'N/A')}
- Momentum: 1M={stock_data.get('momentum_1m', 'N/A')}, 3M={stock_data.get('momentum_3m', 'N/A')}, 12M={stock_data.get('momentum_12m', 'N/A')}

FAIR VALUE ANALYSIS:
- Fair Value: ${fv_data.get('composite_fair_value', 0):.2f}
- Premium/Discount: {fv_data.get('premium_discount_pct', 0):+.1f}%
- Verdict: {fv_data.get('verdict', 'N/A')}

Write in 4 paragraphs (NO headers, NO bullet points, NO em dashes):
1. Investment thesis summary (strengths, moat, opportunity)
2. Key risks and concerns (honest, direct)
3. Valuation perspective (is current price justified?)
4. Bottom line recommendation with timeframe

Keep it punchy. 350 words max. Write like a Morgan Stanley analyst, not marketing copy."""
    return call_llm(prompt, max_tokens=600, temperature=0.5, feature="stock_research")


@st.cache_data(ttl=43200, show_spinner=False)
def interpret_thesis(thesis_text, universe_summary):
    """Use AI to parse a free-form investment thesis."""
    prompt = f"""You are an investment analyst. A user has the following investment thesis:

"{thesis_text}"

Universe context: {universe_summary}

Parse this thesis and respond in JSON format ONLY (no other text):
{{
  "primary_factor": "one of: oil_price, interest_rates, tech_sector, geopolitical, inflation, fed_policy, china_trade, ai_capex, consumer_spending, employment, dollar_strength, gold_prices, treasury_yields, credit_spreads, or other",
  "direction": "bullish or bearish",
  "magnitude": "small, moderate, or large",
  "time_horizon": "days, weeks, months, or years",
  "key_stocks_benefited": ["ticker1", "ticker2", "ticker3"],
  "key_stocks_hurt": ["ticker1", "ticker2", "ticker3"],
  "sectors_benefited": ["Technology", "Energy", etc],
  "sectors_hurt": ["Financials", "Utilities", etc],
  "reasoning": "2-3 sentence explanation of the logic",
  "confidence": "low, medium, or high"
}}"""
    result = call_llm(prompt, max_tokens=500, temperature=0.3, feature="thesis")
    if "error" in result:
        return result
    try:
        text = result["text"].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text.strip())
        parsed["provider"] = result.get("provider")
        return parsed
    except Exception as e:
        return {"error": f"Could not parse AI response as JSON: {str(e)}", "raw": result.get("text", "")}


@st.cache_data(ttl=86400, show_spinner=False)
def generate_doppelganger_narrative(current_ticker, current_data, match_ticker, match_era, match_data, similarity_score):
    """Generate narrative comparing current stock to historical doppelganger."""
    prompt = f"""You are a financial historian. Compare these two companies/situations:

CURRENT: {current_ticker} ({current_data.get('shortName', '')}) in 2026
- Sector: {current_data.get('sector', 'N/A')}
- Market Cap: ${current_data.get('marketCapB', 0):.1f}B
- P/E: {current_data.get('trailingPE', 'N/A')}, P/S: {current_data.get('priceToSalesTrailing12Months', 'N/A')}
- Revenue Growth: {current_data.get('revenueGrowth', 'N/A')}
- Profit Margin: {current_data.get('profitMargins', 'N/A')}
- 12M Return: {current_data.get('momentum_12m', 'N/A')}

HISTORICAL ANALOG: {match_ticker} in {match_era}
- Context: {match_data.get('context', 'N/A')}
- Market Cap at that time: {match_data.get('marketCapB', 'N/A')}
- P/E at that time: {match_data.get('trailingPE', 'N/A')}
- P/S at that time: {match_data.get('priceToSalesTrailing12Months', 'N/A')}
- Revenue Growth: {match_data.get('revenueGrowth', 'N/A')}
- Key narrative: {match_data.get('narrative', 'N/A')}
- What happened next: {match_data.get('outcome', 'N/A')}

Similarity Score: {similarity_score:.2f}/1.0

Write 3 concise paragraphs (NO headers, NO bullets, NO em dashes):
1. Why these two situations are similar (2-3 key parallels)
2. Where they differ (2-3 key divergences, what makes this cycle different)
3. What lessons from the historical outcome might apply (with appropriate caveats)

250 words max. Be analytical, not speculative. End with a clear one-sentence takeaway."""
    return call_llm(prompt, max_tokens=500, temperature=0.6, feature="doppelganger")


@st.cache_data(ttl=43200, show_spinner=False)
def generate_portfolio_optimization(portfolio_summary, universe_summary, objective="growth"):
    """Generate AI-powered portfolio optimization recommendations."""
    prompt = f"""You are a portfolio manager. Analyze this portfolio and recommend specific actions.

PORTFOLIO:
{portfolio_summary}

OBJECTIVE: {objective}

TOP OPPORTUNITIES IN UNIVERSE (not currently held):
{universe_summary}

Provide exactly 5 specific, actionable recommendations. Use this JSON format:
{{
  "recommendations": [
    {{
      "action": "BUY, SELL, TRIM, ADD, or HOLD",
      "ticker": "TICKER",
      "suggested_allocation_pct": 5.0,
      "reasoning": "1-2 sentence why",
      "priority": "high, medium, or low"
    }},
    ...
  ],
  "overall_assessment": "2-3 sentence portfolio health summary",
  "biggest_risk": "one sentence identifying the top risk",
  "biggest_opportunity": "one sentence identifying the top opportunity"
}}

Rules:
- Be specific with ticker and allocation
- Flag any position >20% as concentration risk
- Flag any position <1% as "consolidate or remove"
- Consider sector concentration
- Don't recommend buying stocks already in portfolio"""
    result = call_llm(prompt, max_tokens=1000, temperature=0.4, feature="portfolio_opt")
    if "error" in result:
        return result
    try:
        text = result["text"].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text.strip())
        parsed["provider"] = result.get("provider")
        return parsed
    except Exception as e:
        return {"error": f"Could not parse AI response: {str(e)}", "raw": result.get("text", "")}


def get_provider_status():
    """Return current provider status for UI display."""
    return {
        "provider": PROVIDER,
        "available": is_ai_available(),
        "gemini_configured": bool(GEMINI_API_KEY),
        "claude_configured": bool(ANTHROPIC_API_KEY),
        "openai_configured": bool(OPENAI_API_KEY),
    }
