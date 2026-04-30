"""
Pullback Pressure Index
=======================

Composite 0-100 score indicating short-term correction risk.
Higher = more likely to see a pullback in next 4-8 weeks.

This is a RISK indicator, not a market timing signal. Even at extreme
pressure, markets can keep rising for weeks. Use it to inform position
sizing on new deployments, NOT to liquidate existing positions.

Components (weighted):
- VIX level (40%): Low VIX = complacency
- SPY vs 50-SMA (20%): Stretched short-term
- SPY vs 200-SMA (20%): Stretched long-term
- Breadth (10%): % of stocks above 50-SMA in scored universe
- 3-month momentum (10%): Run-up without correction
"""

import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st


# Component weights
WEIGHTS = {
    "vix": 0.40,
    "vs_50sma": 0.20,
    "vs_200sma": 0.20,
    "breadth": 0.10,
    "momentum": 0.10,
}


@st.cache_data(ttl=3600, show_spinner=False)  # 1-hour cache
def compute_pullback_pressure(scored_df=None):
    """
    Compute the composite pullback pressure index (0-100).

    Returns dict with:
        score: 0-100 composite
        level: "Low" / "Moderate" / "Elevated" / "Extreme"
        components: dict of individual signal scores
        deploy_pct: recommended % to deploy now (vs. holding back / DCA)
        deploy_strategy: text describing recommended approach
        components_detail: list of dicts for UI display
    """
    components = {}
    components_detail = []

    # ── 1. VIX level (40% weight) ──
    try:
        vix = yf.Ticker("^VIX").history(period="5d")
        if not vix.empty:
            vix_now = float(vix["Close"].iloc[-1])
            # VIX scoring: <12 extreme low (90), 14 (75), 18 (50), 22 (25), >28 (10)
            vix_score = float(np.clip(100 - ((vix_now - 10) * 5), 0, 100))
            components["vix"] = vix_score
            components_detail.append({
                "name": "VIX",
                "value": f"{vix_now:.1f}",
                "score": vix_score,
                "interp": _vix_interp(vix_now),
            })
    except Exception:
        components["vix"] = 50  # neutral fallback
        components_detail.append({"name": "VIX", "value": "n/a", "score": 50, "interp": "Could not fetch"})

    # ── 2. SPY vs 50-SMA (20% weight) ──
    try:
        spy = yf.Ticker("SPY").history(period="1y")
        if not spy.empty and len(spy) > 200:
            spy_now = float(spy["Close"].iloc[-1])
            sma50 = float(spy["Close"].rolling(50).mean().iloc[-1])
            sma200 = float(spy["Close"].rolling(200).mean().iloc[-1])

            pct_above_50 = ((spy_now - sma50) / sma50) * 100
            # Score: 0% above = 50 neutral, +5% = 75, +8% = 90, -5% = 25
            score_50 = float(np.clip(50 + pct_above_50 * 5, 0, 100))
            components["vs_50sma"] = score_50
            components_detail.append({
                "name": "SPY vs 50-SMA",
                "value": f"{pct_above_50:+.1f}%",
                "score": score_50,
                "interp": _sma_interp(pct_above_50, "short-term"),
            })

            pct_above_200 = ((spy_now - sma200) / sma200) * 100
            # Score: 0% above = 50, +10% = 80, +15% = 95, -10% = 20
            score_200 = float(np.clip(50 + pct_above_200 * 3, 0, 100))
            components["vs_200sma"] = score_200
            components_detail.append({
                "name": "SPY vs 200-SMA",
                "value": f"{pct_above_200:+.1f}%",
                "score": score_200,
                "interp": _sma_interp(pct_above_200, "long-term"),
            })

            # ── 5. 3-month momentum ──
            if len(spy) >= 63:  # ~3 months of trading days
                spy_3mo_ago = float(spy["Close"].iloc[-63])
                pct_3mo = ((spy_now - spy_3mo_ago) / spy_3mo_ago) * 100
                # Score: 0% = 50, +10% = 80, +15% = 95, -5% = 30
                mom_score = float(np.clip(50 + pct_3mo * 3, 0, 100))
                components["momentum"] = mom_score
                components_detail.append({
                    "name": "SPY 3-month return",
                    "value": f"{pct_3mo:+.1f}%",
                    "score": mom_score,
                    "interp": _momentum_interp(pct_3mo),
                })
            else:
                components["momentum"] = 50
        else:
            components["vs_50sma"] = 50
            components["vs_200sma"] = 50
            components["momentum"] = 50
    except Exception:
        components["vs_50sma"] = 50
        components["vs_200sma"] = 50
        components["momentum"] = 50

    # ── 4. Breadth (% of scored universe above 50-SMA) ──
    breadth_score = 50  # default neutral
    breadth_pct_value = None
    try:
        if scored_df is not None and not scored_df.empty:
            # Field is momentum_vs_sma50 (decimal, e.g., 0.05 = 5% above)
            if "momentum_vs_sma50" in scored_df.columns:
                col = scored_df["momentum_vs_sma50"].dropna()
                if len(col) > 0:
                    above = (col > 0).sum()
                    breadth_pct_value = (above / len(col)) * 100
                    # Score: 50% breadth = 50 (neutral)
                    # 75%+ = 70 (extended/overheated)
                    # <35% = 30 (often a buy zone)
                    if breadth_pct_value > 75:
                        breadth_score = 70
                    elif breadth_pct_value > 65:
                        breadth_score = 60
                    elif breadth_pct_value < 35:
                        breadth_score = 30
                    else:
                        breadth_score = 50
    except Exception:
        pass

    components["breadth"] = breadth_score
    if breadth_pct_value is not None:
        components_detail.append({
            "name": "Universe breadth",
            "value": f"{breadth_pct_value:.0f}% above 50-SMA",
            "score": breadth_score,
            "interp": _breadth_interp(breadth_pct_value),
        })
    else:
        components_detail.append({"name": "Universe breadth", "value": "n/a", "score": 50, "interp": "Insufficient data"})

    # ── Composite score ──
    composite = sum(components.get(k, 50) * w for k, w in WEIGHTS.items())
    composite = float(np.clip(composite, 0, 100))

    # ── Level interpretation ──
    if composite >= 75:
        level = "Extreme"
        level_color = "#D32F2F"  # red
    elif composite >= 60:
        level = "Elevated"
        level_color = "#FF9800"  # orange
    elif composite >= 40:
        level = "Moderate"
        level_color = "#FFC107"  # yellow
    elif composite >= 25:
        level = "Low"
        level_color = "#8BC34A"  # light green
    else:
        level = "Very Low"
        level_color = "#00C805"  # green

    # ── Deployment recommendation ──
    deploy_pct, deploy_strategy = _deploy_recommendation(composite)

    return {
        "score": round(composite, 1),
        "level": level,
        "level_color": level_color,
        "components": components,
        "components_detail": components_detail,
        "deploy_pct": deploy_pct,
        "deploy_strategy": deploy_strategy,
    }


def _deploy_recommendation(score):
    """Translate pressure score to deployment recommendation."""
    if score >= 80:
        return 25, "Conditions stretched. Deploy 25% now, hold 75% for pullback or DCA over 8-12 weeks."
    elif score >= 65:
        return 50, "Elevated risk. Deploy 50% now, hold 50% for opportunistic adds on weakness."
    elif score >= 45:
        return 75, "Mixed signals. Deploy 75% now, keep 25% reserve for tactical deployment."
    elif score >= 25:
        return 100, "Conditions favorable. Deploy fully now."
    else:
        return 100, "Market under pressure / fear. Deploy fully — historically these are good entry points."


def _vix_interp(vix):
    if vix < 12:
        return "⚠️ Extreme complacency"
    elif vix < 15:
        return "⚠️ Low — complacency"
    elif vix < 20:
        return "✓ Normal range"
    elif vix < 28:
        return "⚠️ Elevated fear"
    else:
        return "🔻 Extreme fear (often a buy signal)"


def _sma_interp(pct, label):
    if pct > 10:
        return f"⚠️ Very stretched {label}"
    elif pct > 5:
        return f"⚠️ Stretched {label}"
    elif pct > 0:
        return f"✓ Above {label} trend"
    elif pct > -5:
        return f"⚠️ Below {label} trend"
    else:
        return f"🔻 Well below {label} (often a buy signal)"


def _breadth_interp(breadth_pct):
    if breadth_pct > 75:
        return "⚠️ Extended — many stocks already up"
    elif breadth_pct > 60:
        return "✓ Healthy participation"
    elif breadth_pct > 45:
        return "✓ Mixed"
    elif breadth_pct > 30:
        return "⚠️ Weak breadth"
    else:
        return "🔻 Most stocks below 50-SMA (often a buy signal)"


def _momentum_interp(pct):
    if pct > 12:
        return "⚠️ Strong run-up — mean reversion pressure"
    elif pct > 6:
        return "⚠️ Solid gains"
    elif pct > 0:
        return "✓ Modest gains"
    elif pct > -6:
        return "⚠️ Recent weakness"
    else:
        return "🔻 Recent decline (often a buy signal)"


# ── UI helpers ──

def render_pullback_panel(scored_df=None, compact=False):
    """
    Render the Pullback Pressure panel in Streamlit.

    Args:
        scored_df: scored universe for breadth calculation
        compact: if True, render compact version (just score + recommendation)
    """
    pp = compute_pullback_pressure(scored_df)

    if compact:
        # Compact version: just key metrics
        c1, c2, c3 = st.columns([1, 2, 2])
        with c1:
            st.markdown(
                f'<div style="text-align: center; padding: 10px; border-radius: 8px; '
                f'background: {pp["level_color"]}22; border: 2px solid {pp["level_color"]};">'
                f'<div style="font-size: 0.85rem; opacity: 0.7;">Pullback Pressure</div>'
                f'<div style="font-size: 2rem; font-weight: 700; color: {pp["level_color"]};">{pp["score"]:.0f}</div>'
                f'<div style="font-size: 0.9rem; color: {pp["level_color"]};">{pp["level"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with c2:
            st.markdown(f"**Recommended deployment:** {pp['deploy_pct']}%")
            st.caption(pp["deploy_strategy"])
        with c3:
            with st.expander("Why?"):
                for d in pp["components_detail"]:
                    st.markdown(f"**{d['name']}** ({d['value']}): {d['interp']}")
        return pp

    # Full version
    st.markdown("### 🌡️ Pullback Pressure Index")
    st.caption("Short-term correction risk. Higher = more stretched market conditions.")

    main_cols = st.columns([1, 2])
    with main_cols[0]:
        st.markdown(
            f'<div style="text-align: center; padding: 20px; border-radius: 12px; '
            f'background: {pp["level_color"]}22; border: 3px solid {pp["level_color"]};">'
            f'<div style="font-size: 1rem; opacity: 0.8;">Pressure Score</div>'
            f'<div style="font-size: 3.5rem; font-weight: 800; color: {pp["level_color"]}; line-height: 1;">{pp["score"]:.0f}</div>'
            f'<div style="font-size: 0.9rem; opacity: 0.6;">/ 100</div>'
            f'<div style="font-size: 1.2rem; font-weight: 600; color: {pp["level_color"]}; margin-top: 8px;">{pp["level"]}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with main_cols[1]:
        st.markdown(f"#### Suggested Deployment: **{pp['deploy_pct']}%** of new capital")
        st.info(pp["deploy_strategy"])

    # Components breakdown
    with st.expander("📊 Component breakdown"):
        for d in pp["components_detail"]:
            cc1, cc2, cc3 = st.columns([2, 1, 3])
            with cc1: st.markdown(f"**{d['name']}**")
            with cc2: st.markdown(d["value"])
            with cc3: st.markdown(d["interp"])

    # Honest disclaimer
    st.caption(
        "⚠️ This is a risk indicator, not a sell signal. Even at high pressure, "
        "markets can keep rising for weeks. Use it to inform position sizing on new "
        "deployments, not to liquidate existing positions. Past patterns do not guarantee future outcomes."
    )

    return pp
