"""
Quantitative Strategy Dashboard v2 (Pro)
Sector-relative scoring + Portfolio Analyzer + Monte Carlo
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

from config import (
    DEFAULT_PILLAR_WEIGHTS,
    PILLAR_METRICS,
    GRADE_COLORS,
    RATING_COLORS,
    GRADE_SCORES,
    DEFAULT_MARKET_CAP_FLOOR_B,
    MIN_MARKET_CAP_FLOOR_B,
    MAX_MARKET_CAP_FLOOR_B,
)
from data_fetcher import (
    get_broad_universe,
    fetch_universe_data,
    fetch_single_ticker,
    load_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
)
from scoring import (
    score_universe,
    get_pillar_detail,
    get_top_stocks,
    get_sector_stats,
)
from portfolio import (
    analyze_portfolio,
    run_monte_carlo,
    generate_suggestions,
    parse_fidelity_csv,
)

# ── Page Config ────────────────────────────────────────────────────

st.set_page_config(
    page_title="Quant Dashboard Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .grade-badge { display:inline-block; padding:2px 10px; border-radius:4px; font-weight:700; font-size:0.85em; text-align:center; min-width:36px; color:#111; }
    .main-header { font-size:1.8em; font-weight:800; background:linear-gradient(90deg,#00D4AA,#00A3FF); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom:0; }
    .sub-header { color:#888; font-size:0.95em; margin-top:-8px; }
    .suggestion-card { background:#1A1F2E; border-radius:10px; padding:14px; margin-bottom:10px; }
    .suggestion-warning { border-left:4px solid #FF5722; }
    .suggestion-info { border-left:4px solid #FFC107; }
    .suggestion-opportunity { border-left:4px solid #00C805; }
</style>
""", unsafe_allow_html=True)

# ── Session State ──────────────────────────────────────────────────

if "scored_df" not in st.session_state:
    st.session_state.scored_df = None
if "raw_data" not in st.session_state:
    st.session_state.raw_data = None
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None
if "compare_tickers" not in st.session_state:
    st.session_state.compare_tickers = []
if "weights" not in st.session_state:
    st.session_state.weights = DEFAULT_PILLAR_WEIGHTS.copy()
if "sector_relative" not in st.session_state:
    st.session_state.sector_relative = True
if "portfolio_holdings" not in st.session_state:
    st.session_state.portfolio_holdings = []

# ── Helpers ────────────────────────────────────────────────────────

def format_market_cap(cap_b):
    if cap_b >= 1000: return f"${cap_b/1000:.1f}T"
    return f"${cap_b:.1f}B"

def make_radar_chart(pillar_scores, ticker):
    cats = list(pillar_scores.keys())
    vals = [pillar_scores[c] for c in cats] + [pillar_scores[cats[0]]]
    cats = cats + [cats[0]]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=vals, theta=cats, fill="toself",
        fillcolor="rgba(0,212,170,0.2)", line=dict(color="#00D4AA", width=2), name=ticker))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,12],
        tickvals=[3,6,9,12], ticktext=["D","C","B","A+"], gridcolor="#2a2f3e"),
        angularaxis=dict(gridcolor="#2a2f3e"), bgcolor="rgba(0,0,0,0)"),
        showlegend=False, margin=dict(l=60,r=60,t=30,b=30), height=320,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#e0e0e0"))
    return fig

def make_comparison_radar(tickers_data):
    colors = ["#00D4AA","#FF6B6B","#4ECDC4","#FFE66D","#A8E6CF"]
    fig = go.Figure()
    pillars = list(PILLAR_METRICS.keys())
    for i, (ticker, scores) in enumerate(tickers_data.items()):
        vals = [scores.get(p,0) for p in pillars] + [scores.get(pillars[0],0)]
        cats = pillars + [pillars[0]]
        c = colors[i%len(colors)]
        fig.add_trace(go.Scatterpolar(r=vals, theta=cats, fill="toself",
            fillcolor=f"rgba({','.join(str(int(c[j:j+2],16)) for j in (1,3,5))},0.1)",
            line=dict(color=c, width=2), name=ticker))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,12],
        tickvals=[3,6,9,12], ticktext=["D","C","B","A+"], gridcolor="#2a2f3e"),
        angularaxis=dict(gridcolor="#2a2f3e"), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=60,r=60,t=40,b=40), height=400,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#e0e0e0"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5))
    return fig

# ── Sidebar ────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## Settings")
    st.markdown("---")
    market_cap_floor = st.slider("Min Market Cap ($B)", MIN_MARKET_CAP_FLOOR_B, MAX_MARKET_CAP_FLOOR_B, DEFAULT_MARKET_CAP_FLOOR_B, 1)

    st.markdown("---")
    sector_relative = st.toggle("Sector-Relative Scoring", value=True,
        help="ON: ranked within sector. OFF: ranked against full universe.")
    st.session_state.sector_relative = sector_relative

    st.markdown("---")
    st.markdown("### Pillar Weights")
    w_val = st.slider("Valuation", 0.0, 1.0, st.session_state.weights["Valuation"], 0.05, key="w_val")
    w_gro = st.slider("Growth", 0.0, 1.0, st.session_state.weights["Growth"], 0.05, key="w_gro")
    w_pro = st.slider("Profitability", 0.0, 1.0, st.session_state.weights["Profitability"], 0.05, key="w_pro")
    w_mom = st.slider("Momentum", 0.0, 1.0, st.session_state.weights["Momentum"], 0.05, key="w_mom")
    w_eps = st.slider("EPS Revisions", 0.0, 1.0, st.session_state.weights["EPS Revisions"], 0.05, key="w_eps")
    total_w = w_val + w_gro + w_pro + w_mom + w_eps
    if total_w > 0:
        st.session_state.weights = {
            "Valuation": w_val/total_w, "Growth": w_gro/total_w,
            "Profitability": w_pro/total_w, "Momentum": w_mom/total_w,
            "EPS Revisions": w_eps/total_w,
        }

    st.markdown("---")
    new_ticker = st.text_input("Add to Watchlist", placeholder="e.g. AAPL").upper().strip()
    if st.button("Add", key="sb_wl") and new_ticker:
        add_to_watchlist(new_ticker)
        st.success(f"Added {new_ticker}")
        st.rerun()

    st.markdown("---")
    if st.button("Refresh Data", key="sb_ref"):
        st.cache_data.clear()
        st.session_state.scored_df = None
        st.session_state.raw_data = None
        import os
        try:
            f = os.path.join("data_cache", "fundamentals_cache.json")
            if os.path.exists(f): os.utime(f, (0,0))
        except Exception: pass
        st.rerun()

# ── Header ─────────────────────────────────────────────────────────

st.markdown('<p class="main-header">Quant Strategy Dashboard Pro</p>', unsafe_allow_html=True)
mode = "Sector-Relative" if st.session_state.sector_relative else "Universe-Wide"
st.markdown(f'<p class="sub-header">{mode} scoring: Valuation . Growth . Profitability . Momentum . EPS Revisions</p>', unsafe_allow_html=True)

tab_screener, tab_watchlist, tab_detail, tab_compare, tab_portfolio, tab_monte_carlo = st.tabs([
    "Screener", "Watchlist", "Stock Detail", "Compare", "Portfolio Analyzer", "Monte Carlo"
])

# ── Data Loading ───────────────────────────────────────────────────

@st.cache_data(ttl=43200, show_spinner=False)
def load_and_score(mcap, wt, sr):
    w = dict(zip(DEFAULT_PILLAR_WEIGHTS.keys(), wt))
    tickers = get_broad_universe(mcap)
    progress = st.progress(0, text="Loading...")
    raw = fetch_universe_data(tickers, mcap, lambda p,m: progress.progress(p, text=m))
    progress.empty()
    scored = score_universe(raw, w, sector_relative=sr)
    ss = get_sector_stats(scored) if not scored.empty else {}
    return raw, scored, ss

try:
    raw_data, scored_df, sector_stats = load_and_score(
        market_cap_floor, tuple(st.session_state.weights.values()), st.session_state.sector_relative)
except Exception as e:
    st.error(f"Error: {e}")
    st.stop()

if scored_df is None or scored_df.empty:
    st.warning("No data. Click Refresh Data.")
    st.stop()

# ── TAB: Screener ──────────────────────────────────────────────────

with tab_screener:
    c1,c2,c3 = st.columns(3)
    with c1:
        sectors = ["All"] + sorted(scored_df["sector"].dropna().unique().tolist())
        sel_sector = st.selectbox("Sector", sectors)
    with c2:
        sel_rating = st.selectbox("Rating", ["All","Strong Buy","Buy","Hold","Sell","Strong Sell"])
    with c3:
        top_n = st.selectbox("Show Top", [50,100,250,500], index=3)

    filtered = get_top_stocks(scored_df, top_n, sel_sector, sel_rating)

    if not filtered.empty:
        s1,s2,s3,s4 = st.columns(4)
        with s1: st.metric("Universe", f"{len(scored_df):,}")
        with s2: st.metric("Strong Buys", len(scored_df[scored_df["overall_rating"]=="Strong Buy"]))
        with s3: st.metric("Avg Score", f"{scored_df['composite_score'].mean():.1f}")
        with s4: st.metric("Showing", f"{len(filtered):,}")

        dcols = ["shortName","sector","marketCapB","currentPrice"]
        for p in PILLAR_METRICS: dcols.append(f"{p}_grade")
        dcols += ["composite_score","overall_rating"]
        ddf = filtered[dcols].copy()
        ddf.columns = ["Company","Sector","Mkt Cap ($B)","Price","Valuation","Growth","Profit","Momentum","EPS Rev","Score","Rating"]
        st.dataframe(ddf, use_container_width=True, height=700)

        st.markdown("---")
        det = st.selectbox("Quick preview", filtered.index.tolist(),
            format_func=lambda x: f"{x} -- {filtered.loc[x,'shortName']}", key="scr_det")
        if det:
            detail = get_pillar_detail(det, scored_df, sector_stats)
            if detail:
                st.plotly_chart(make_radar_chart({p:d["pillar_score"] for p,d in detail.items()}, det),
                    use_container_width=True, key="scr_radar")
                for pn, pd_ in detail.items():
                    with st.expander(f"{pn} | {pd_['pillar_grade']} | {pd_['pillar_score']:.1f}/12"):
                        for m in pd_["metrics"]:
                            mc1,mc2,mc3,mc4,mc5,mc6 = st.columns([2.5,1.2,0.8,0.8,1.2,1.2])
                            with mc1: st.markdown(f"{m['metric']}"); st.caption("higher better" if m["higher_is_better"] else "lower better")
                            with mc2: st.markdown(f"**{m['value']}**")
                            with mc3:
                                g=m["grade"]; gc=GRADE_COLORS.get(g,"#666")
                                st.markdown(f'<span style="background:{gc};padding:2px 8px;border-radius:4px;font-weight:700;color:#111;">{g}</span>', unsafe_allow_html=True)
                            with mc4: st.markdown(m["percentile"])
                            with mc5: st.markdown(m["sector_avg"])
                            with mc6: st.markdown(f'**{m["a_threshold"]}**')

# ── TAB: Watchlist ─────────────────────────────────────────────────

with tab_watchlist:
    wl = load_watchlist()
    if not wl:
        st.info("Watchlist empty. Add tickers from sidebar or screener.")
    else:
        st.markdown(f"### Watchlist ({len(wl)} stocks)")
        for entry in wl:
            t = entry["ticker"]
            if t in scored_df.index:
                r = scored_df.loc[t]
                rating = r.get("overall_rating","N/A")
                rc = RATING_COLORS.get(rating,"#666")
                c1,c2,c3,c4,c5 = st.columns([1.5,2.5,1.5,1.5,0.8])
                with c1: st.markdown(f"**{t}**")
                with c2: st.markdown(r.get("shortName",""))
                with c3: st.markdown(f'<span style="background:{rc};padding:2px 10px;border-radius:4px;font-weight:700;color:#111;">{rating}</span>', unsafe_allow_html=True)
                with c4: st.markdown(f"Score: **{r.get('composite_score',0):.1f}**")
                with c5:
                    if st.button("X", key=f"wl_{t}"): remove_from_watchlist(t); st.rerun()
            else:
                c1,c2,c3 = st.columns([1.5,4,0.8])
                with c1: st.markdown(f"**{t}**")
                with c2: st.caption("Not in universe")
                with c3:
                    if st.button("X", key=f"wl_{t}_o"): remove_from_watchlist(t); st.rerun()
            st.markdown("---")

# ── TAB: Stock Detail ──────────────────────────────────────────────

with tab_detail:
    all_t = sorted(scored_df.index.tolist())
    di = 0
    if st.session_state.selected_ticker in all_t:
        di = all_t.index(st.session_state.selected_ticker)
    sel = st.selectbox("Ticker", all_t, index=di,
        format_func=lambda x: f"{x} -- {scored_df.loc[x,'shortName']}" if x in scored_df.index else x, key="det_sel")

    if sel and sel in scored_df.index:
        row = scored_df.loc[sel]
        detail = get_pillar_detail(sel, scored_df, sector_stats)
        h1,h2,h3,h4 = st.columns(4)
        with h1: st.markdown(f"## {sel}"); st.caption(row.get("shortName",""))
        with h2: st.metric("Price", f"${row.get('currentPrice',0):.2f}")
        with h3: st.metric("Mkt Cap", format_market_cap(row.get("marketCapB",0)))
        with h4:
            rat = row.get("overall_rating","Hold")
            st.metric("Score", f"{row.get('composite_score',0):.1f}/12")
            st.markdown(f'<span style="background:{RATING_COLORS.get(rat,"#666")};padding:4px 14px;border-radius:6px;font-weight:700;color:#111;">{rat}</span>', unsafe_allow_html=True)

        st.markdown(f"**Sector:** {row.get('sector','N/A')} | **Industry:** {row.get('industry','N/A')}")
        st.markdown("---")

        if detail:
            cc,cg = st.columns(2)
            with cc: st.plotly_chart(make_radar_chart({p:d["pillar_score"] for p,d in detail.items()}, sel), use_container_width=True, key="det_radar")
            with cg:
                for pn in PILLAR_METRICS:
                    g=row.get(f"{pn}_grade","N/A"); s=row.get(f"{pn}_score",0); gc=GRADE_COLORS.get(g,"#666"); bw=(s/12)*100
                    st.markdown(f'<div style="margin-bottom:8px;"><div style="display:flex;justify-content:space-between;margin-bottom:4px;"><span style="color:#ccc;">{pn}</span><span style="background:{gc};padding:2px 10px;border-radius:4px;font-weight:700;color:#111;">{g}</span></div><div style="background:#2a2f3e;border-radius:4px;height:8px;"><div style="background:{gc};border-radius:4px;height:8px;width:{bw}%;"></div></div></div>', unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### Full Metric Breakdown")
            for pn, pd_ in detail.items():
                with st.expander(f"{pn} | {pd_['pillar_grade']} | {pd_['pillar_score']:.1f}/12"):
                    hc1,hc2,hc3,hc4,hc5,hc6 = st.columns([2.5,1.2,0.8,0.8,1.2,1.2])
                    with hc1: st.markdown("**Metric**")
                    with hc2: st.markdown("**Value**")
                    with hc3: st.markdown("**Grade**")
                    with hc4: st.markdown("**%ile**")
                    with hc5: st.markdown("**Sector Avg**")
                    with hc6: st.markdown("**A Threshold**")
                    st.markdown("---")
                    for m in pd_["metrics"]:
                        mc1,mc2,mc3,mc4,mc5,mc6 = st.columns([2.5,1.2,0.8,0.8,1.2,1.2])
                        with mc1: st.markdown(m["metric"]); st.caption("higher better" if m["higher_is_better"] else "lower better")
                        with mc2: st.markdown(f"**{m['value']}**")
                        with mc3:
                            g=m["grade"]; gc=GRADE_COLORS.get(g,"#666")
                            st.markdown(f'<span style="background:{gc};padding:2px 8px;border-radius:4px;font-weight:700;color:#111;">{g}</span>', unsafe_allow_html=True)
                        with mc4: st.markdown(m["percentile"])
                        with mc5: st.markdown(m["sector_avg"])
                        with mc6: st.markdown(f'**{m["a_threshold"]}**')

# ── TAB: Compare ───────────────────────────────────────────────────

with tab_compare:
    sel_cmp = st.multiselect("Select 2-5 tickers", sorted(scored_df.index.tolist()),
        default=st.session_state.compare_tickers[:5], max_selections=5,
        format_func=lambda x: f"{x} -- {scored_df.loc[x,'shortName']}" if x in scored_df.index else x, key="cmp_ms")
    st.session_state.compare_tickers = sel_cmp

    if len(sel_cmp) >= 2:
        td = {}
        for t in sel_cmp:
            d = get_pillar_detail(t, scored_df, sector_stats)
            if d: td[t] = {p:v["pillar_score"] for p,v in d.items()}
        if td: st.plotly_chart(make_comparison_radar(td), use_container_width=True, key="cmp_radar")

        rows = []
        for t in sel_cmp:
            if t in scored_df.index:
                r = scored_df.loc[t]
                rd = {"Ticker":t, "Company":r.get("shortName","")}
                for p in PILLAR_METRICS: rd[p] = f"{r.get(f'{p}_grade','N/A')} ({r.get(f'{p}_score',0):.1f})"
                rd["Composite"] = f"{r.get('composite_score',0):.1f}"
                rd["Rating"] = r.get("overall_rating","N/A")
                rows.append(rd)
        if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        bar_data = []
        for t in sel_cmp:
            if t in scored_df.index:
                r = scored_df.loc[t]
                for p in PILLAR_METRICS:
                    bar_data.append({"Ticker":t, "Pillar":p, "Score":r.get(f"{p}_score",0)})
        if bar_data:
            fig = px.bar(pd.DataFrame(bar_data), x="Pillar", y="Score", color="Ticker", barmode="group",
                color_discrete_sequence=["#00D4AA","#FF6B6B","#4ECDC4","#FFE66D","#A8E6CF"])
            fig.update_layout(yaxis=dict(range=[0,12]), height=400,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#e0e0e0"))
            st.plotly_chart(fig, use_container_width=True, key="cmp_bar")


# ── TAB: Portfolio Analyzer ────────────────────────────────────────

with tab_portfolio:
    st.markdown("### Portfolio Analyzer")
    st.caption("Enter your holdings to get a full portfolio diagnostic with actionable suggestions.")

    input_method = st.radio("Input method", ["Manual Entry", "CSV Upload (Fidelity)"], horizontal=True)

    if input_method == "CSV Upload (Fidelity)":
        uploaded = st.file_uploader("Upload Fidelity Positions CSV", type=["csv"])
        if uploaded:
            content = uploaded.read().decode("utf-8")
            parsed = parse_fidelity_csv(content)
            if parsed:
                st.session_state.portfolio_holdings = parsed
                st.success(f"Parsed {len(parsed)} holdings from CSV")
            else:
                st.error("Could not parse CSV. Check the format.")
    else:
        st.markdown("Enter holdings below (one per row):")
        n_rows = st.number_input("Number of holdings", 1, 50, min(len(st.session_state.portfolio_holdings) or 5, 50), key="n_hold")

        holdings = []
        for i in range(int(n_rows)):
            c1,c2,c3 = st.columns([1.5,1,1])
            default_ticker = st.session_state.portfolio_holdings[i]["ticker"] if i < len(st.session_state.portfolio_holdings) else ""
            default_shares = st.session_state.portfolio_holdings[i]["shares"] if i < len(st.session_state.portfolio_holdings) else 0.0
            default_cost = st.session_state.portfolio_holdings[i].get("cost_basis") if i < len(st.session_state.portfolio_holdings) else None

            with c1: ticker = st.text_input("Ticker", value=default_ticker, key=f"pt_{i}").upper().strip()
            with c2: shares = st.number_input("Shares", value=float(default_shares), min_value=0.0, key=f"ps_{i}")
            with c3: cost = st.number_input("Cost Basis ($)", value=float(default_cost or 0), min_value=0.0, key=f"pc_{i}")

            if ticker and shares > 0:
                holdings.append({"ticker": ticker, "shares": shares, "cost_basis": cost if cost > 0 else None})

        if st.button("Analyze Portfolio", key="analyze_btn"):
            st.session_state.portfolio_holdings = holdings

    # Run analysis if we have holdings
    if st.session_state.portfolio_holdings:
        analysis = analyze_portfolio(st.session_state.portfolio_holdings, scored_df, sector_stats)

        if "error" in analysis:
            st.error(analysis["error"])
        elif analysis:
            # ── Summary Metrics ────────────────────────────────
            st.markdown("---")
            st.markdown("### Portfolio Summary")

            m1,m2,m3,m4,m5 = st.columns(5)
            with m1: st.metric("Total Value", f"${analysis['total_value']:,.0f}")
            with m2: st.metric("Holdings", analysis["num_holdings"])
            with m3:
                wr = analysis["weighted_rating"]
                st.metric("Portfolio Rating", wr)
            with m4: st.metric("Composite Score", f"{analysis['weighted_composite']:.1f}/12")
            with m5: st.metric("Concentration", analysis["concentration_level"])

            if analysis["num_unmatched"] > 0:
                st.caption(f"Unmatched tickers: {', '.join(analysis['unmatched_tickers'])}")

            # ── Factor Tilts ───────────────────────────────────
            st.markdown("---")
            st.markdown("### Factor Tilts vs Universe")

            tilt_data = []
            for pillar, td in analysis["factor_tilts"].items():
                tilt_data.append({
                    "Pillar": pillar,
                    "Portfolio": td["portfolio"],
                    "Universe Avg": td["universe"],
                    "Diff": td["diff"],
                    "Tilt": td["tilt"],
                })

            tilt_df = pd.DataFrame(tilt_data)

            fig_tilt = go.Figure()
            fig_tilt.add_trace(go.Bar(name="Your Portfolio", x=tilt_df["Pillar"], y=tilt_df["Portfolio"],
                marker_color="#00D4AA"))
            fig_tilt.add_trace(go.Bar(name="Universe Avg", x=tilt_df["Pillar"], y=tilt_df["Universe Avg"],
                marker_color="#555"))
            fig_tilt.update_layout(barmode="group", yaxis=dict(range=[0,12], title="Score"),
                height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e0e0e0"),
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
            st.plotly_chart(fig_tilt, use_container_width=True, key="port_tilt")

            # ── Sector Breakdown ───────────────────────────────
            st.markdown("### Sector Allocation")
            sec_data = analysis["sector_weights"]
            if sec_data:
                sec_df = pd.DataFrame([
                    {"Sector": s, "Weight": d["weight"]*100, "Holdings": d["count"], "Avg Score": round(d["avg_score"],1)}
                    for s,d in sec_data.items()
                ]).sort_values("Weight", ascending=False)

                fig_sec = px.pie(sec_df, values="Weight", names="Sector",
                    color_discrete_sequence=px.colors.qualitative.Set2, hole=0.4)
                fig_sec.update_layout(height=350, paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#e0e0e0"))
                st.plotly_chart(fig_sec, use_container_width=True, key="port_sec")

                st.dataframe(sec_df, use_container_width=True, hide_index=True)

            # ── Top/Bottom Holdings ────────────────────────────
            st.markdown("### Best & Worst Rated Holdings")
            tc1, tc2 = st.columns(2)
            with tc1:
                st.markdown("**Top Rated**")
                for h in analysis["top_rated"]:
                    st.markdown(f"**{h['ticker']}** -- Score: {h['composite_score']:.1f} ({h['overall_rating']}) -- {h['weight']*100:.1f}%")
            with tc2:
                st.markdown("**Bottom Rated**")
                for h in analysis["bottom_rated"]:
                    st.markdown(f"**{h['ticker']}** -- Score: {h['composite_score']:.1f} ({h['overall_rating']}) -- {h['weight']*100:.1f}%")

            # ── Suggestions ────────────────────────────────────
            st.markdown("---")
            st.markdown("### Suggestions")
            suggestions = generate_suggestions(analysis, scored_df)

            if not suggestions:
                st.success("Your portfolio looks well-balanced. No urgent suggestions.")
            else:
                for sug in suggestions:
                    css_class = f"suggestion-{sug['type']}"
                    icon = {"warning": "!!", "info": "i", "opportunity": "++"}.get(sug["type"], "")
                    st.markdown(f"""
                    <div class="suggestion-card {css_class}">
                        <strong>{icon} {sug['title']}</strong><br>
                        <span style="color:#aaa;">{sug['detail']}</span>
                    </div>
                    """, unsafe_allow_html=True)


# ── TAB: Monte Carlo ──────────────────────────────────────────────

with tab_monte_carlo:
    st.markdown("### Monte Carlo Simulation")
    st.caption("Simulate 5,000 possible 1-year outcomes for your portfolio based on historical momentum and estimated volatility.")

    if not st.session_state.portfolio_holdings:
        st.info("Enter your holdings in the Portfolio Analyzer tab first.")
    else:
        analysis = analyze_portfolio(st.session_state.portfolio_holdings, scored_df, sector_stats)
        if "error" in analysis or not analysis:
            st.warning("Could not analyze portfolio. Check your holdings.")
        else:
            holdings_df = analysis.get("holdings_df", pd.DataFrame())

            mc1, mc2 = st.columns(2)
            with mc1:
                n_sims = st.selectbox("Simulations", [1000, 5000, 10000], index=1)
            with mc2:
                n_days = st.selectbox("Time Horizon", [63, 126, 252], index=2,
                    format_func=lambda x: {63:"3 Months", 126:"6 Months", 252:"1 Year"}[x])

            if st.button("Run Simulation", key="mc_run"):
                with st.spinner("Running Monte Carlo simulation..."):
                    mc = run_monte_carlo(holdings_df, scored_df, n_simulations=n_sims, n_days=n_days)

                if mc:
                    st.markdown("---")

                    # Summary stats
                    r1,r2,r3,r4 = st.columns(4)
                    with r1: st.metric("Expected Return", f"{mc['expected_annual_return']}%")
                    with r2: st.metric("Est. Volatility", f"{mc['estimated_annual_vol']}%")
                    with r3: st.metric("Prob. of Gain", f"{mc['prob_positive']}%")
                    with r4: st.metric("Prob. of 20%+ Loss", f"{mc['prob_loss_20']}%")

                    # Probability table
                    st.markdown("### Outcome Probabilities")
                    prob_data = {
                        "Scenario": ["Gain 50%+", "Gain 20%+", "Any Gain", "Loss up to 10%", "Loss 10-20%", "Loss 20%+"],
                        "Probability": [
                            f"{mc['prob_gain_50']}%",
                            f"{mc['prob_gain_20']}%",
                            f"{mc['prob_positive']}%",
                            f"{100 - mc['prob_positive'] - mc['prob_loss_10']:.1f}%",
                            f"{mc['prob_loss_10'] - mc['prob_loss_20']:.1f}%",
                            f"{mc['prob_loss_20']}%",
                        ]
                    }
                    st.dataframe(pd.DataFrame(prob_data), use_container_width=True, hide_index=True)

                    # Fan chart
                    st.markdown("### Simulation Fan Chart")
                    paths = mc["path_percentiles"]
                    days = list(range(1, n_days + 1))

                    fig_fan = go.Figure()
                    # 5-95% band
                    fig_fan.add_trace(go.Scatter(x=days, y=paths["p95"].tolist(),
                        mode="lines", line=dict(width=0), showlegend=False))
                    fig_fan.add_trace(go.Scatter(x=days, y=paths["p5"].tolist(),
                        mode="lines", line=dict(width=0), fill="tonexty",
                        fillcolor="rgba(0,212,170,0.1)", name="5th-95th %ile"))
                    # 25-75% band
                    fig_fan.add_trace(go.Scatter(x=days, y=paths["p75"].tolist(),
                        mode="lines", line=dict(width=0), showlegend=False))
                    fig_fan.add_trace(go.Scatter(x=days, y=paths["p25"].tolist(),
                        mode="lines", line=dict(width=0), fill="tonexty",
                        fillcolor="rgba(0,212,170,0.25)", name="25th-75th %ile"))
                    # Median
                    fig_fan.add_trace(go.Scatter(x=days, y=paths["p50"].tolist(),
                        mode="lines", line=dict(color="#00D4AA", width=2), name="Median"))
                    # Starting value line
                    fig_fan.add_hline(y=mc["total_value"], line_dash="dash", line_color="#666",
                        annotation_text="Starting Value")

                    fig_fan.update_layout(
                        yaxis=dict(title="Portfolio Value ($)", tickformat="$,.0f"),
                        xaxis=dict(title="Trading Days"),
                        height=450, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#e0e0e0"),
                        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
                    )
                    st.plotly_chart(fig_fan, use_container_width=True, key="mc_fan")

                    # Terminal distribution
                    st.markdown("### Terminal Value Distribution")
                    fig_hist = go.Figure()
                    fig_hist.add_trace(go.Histogram(
                        x=mc["terminal_values"], nbinsx=80,
                        marker_color="#00D4AA", opacity=0.7,
                    ))
                    fig_hist.add_vline(x=mc["total_value"], line_dash="dash", line_color="#FF6B6B",
                        annotation_text="Starting Value")
                    fig_hist.add_vline(x=mc["terminal_median"], line_dash="dash", line_color="#00D4AA",
                        annotation_text="Median Outcome")
                    fig_hist.update_layout(
                        xaxis=dict(title="Terminal Portfolio Value ($)", tickformat="$,.0f"),
                        yaxis=dict(title="Frequency"),
                        height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#e0e0e0"),
                    )
                    st.plotly_chart(fig_hist, use_container_width=True, key="mc_hist")

                    # Percentile table
                    st.markdown("### Value at Risk Percentiles")
                    pct_data = {
                        "Percentile": ["5th (worst case)", "25th", "50th (median)", "75th", "95th (best case)"],
                        "Portfolio Value": [f"${v:,.0f}" for v in [
                            mc["percentiles"]["p5"], mc["percentiles"]["p25"],
                            mc["percentiles"]["p50"], mc["percentiles"]["p75"],
                            mc["percentiles"]["p95"],
                        ]],
                        "Return": [f"{(v/mc['total_value']-1)*100:+.1f}%" for v in [
                            mc["percentiles"]["p5"], mc["percentiles"]["p25"],
                            mc["percentiles"]["p50"], mc["percentiles"]["p75"],
                            mc["percentiles"]["p95"],
                        ]],
                    }
                    st.dataframe(pd.DataFrame(pct_data), use_container_width=True, hide_index=True)


# ── Footer ─────────────────────────────────────────────────────────

st.markdown("---")
st.caption("Quant Strategy Dashboard Pro v2.0 | Not financial advice")
