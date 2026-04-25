"""
Quantitative Strategy Dashboard Pro v3.5
14 tabs: Home Dashboard, Doppelganger Analysis, AI-powered research notes and thesis,
enhanced prescriptive suggestions, click-to-navigate ticker links.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import yfinance as yf
from datetime import datetime

from config import (
    DEFAULT_PILLAR_WEIGHTS, PILLAR_METRICS, GRADE_COLORS, RATING_COLORS,
    GRADE_SCORES, DEFAULT_MARKET_CAP_FLOOR_B, MIN_MARKET_CAP_FLOOR_B, MAX_MARKET_CAP_FLOOR_B,
)
from data_fetcher import (
    get_broad_universe, fetch_universe_data, load_watchlist, add_to_watchlist, remove_from_watchlist,
)
from scoring import score_universe, get_pillar_detail, get_top_stocks, get_sector_stats
from portfolio import analyze_portfolio, run_monte_carlo, generate_suggestions, parse_fidelity_csv
from sectors import get_sector_overview, get_sector_detail
from fairvalue import compute_fair_value
from sentiment import fetch_index_data, fetch_vix_data, fetch_buffett_indicator, compute_market_breadth, compute_fear_greed, compute_pgi, COMING_SOON_INDICATORS
from advanced_screener import apply_advanced_filters, compute_fair_values_batch, PRESET_SCREENS, FILTERABLE_METRICS
from etf_screener import load_etf_data, get_etf_categories, filter_etfs, get_etf_detail
from buy_point import compute_buy_point, compute_buy_points_batch
from macro import get_macro_summary, get_fed_rate_outlook, fetch_economic_calendar, fetch_yield_curve
from swing_trader import scan_swing_candidates, get_swing_methodology, compute_swing_signals
from ai_assistant import generate_stock_research_note, interpret_thesis, generate_doppelganger_narrative, generate_portfolio_optimization, is_ai_available, get_provider_status
from doppelganger import find_doppelgangers, get_database_stats, get_tags_list, HISTORICAL_ANALOGS
from doppelganger_returns import get_forward_returns, aggregate_forward_returns
from fmp_data import is_fmp_configured, get_combined_earnings_data
from suggestions_v2 import generate_suggestions_v2, format_suggestion_card
from auth import is_logged_in, is_auth_configured, render_login_page, render_user_sidebar, get_current_user, get_user_tier, can_use_ai
from portfolio_persistence import save_portfolio, load_portfolios, delete_portfolio, get_portfolio_by_id
from help_content import GETTING_STARTED, PILLAR_METHODOLOGY, RATING_SYSTEM, FAIR_VALUE, BUY_POINT, SWING_TRADER, DOPPELGANGER, MONTE_CARLO, PGI, PRO_CHARTS, ETF_CENTER, GLOSSARY, BEST_PRACTICES, DATA_SOURCES, DISCLAIMER
from pro_charts import fetch_chart_data, compute_indicators, build_candlestick_chart, get_quick_quote, get_watchlist_quotes, get_market_movers
from etf_center import PORTFOLIO_TEMPLATES, get_portfolio_template, list_templates, calculate_template_metrics, compare_etfs, get_sector_etf_map, get_theme_etf_map, load_raw_cache, get_etf_universe

st.set_page_config(page_title="Quant Dashboard Pro", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.main-header{font-size:1.8em;font-weight:800;background:linear-gradient(90deg,#00D4AA,#00A3FF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:0}
.sub-header{color:#888;font-size:0.95em;margin-top:-8px}
</style>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# AUTH GATE - App requires login to access
# ═══════════════════════════════════════════════════════════════════
if not is_logged_in():
    render_login_page()
    st.stop()

# ═══════════════════════════════════════════════════════════════════
# AUTHENTICATED APP BELOW
# ═══════════════════════════════════════════════════════════════════

for k,v in [("scored_df",None),("raw_data",None),("selected_ticker",None),("compare_tickers",[]),("weights",DEFAULT_PILLAR_WEIGHTS.copy()),("sector_relative",True),("portfolio_holdings",[]),("current_portfolio_id",None),("current_portfolio_name",None),("portfolio_autoloaded",False)]:
    if k not in st.session_state: st.session_state[k]=v

# Auto-load most recent saved portfolio on first login (one-time per session)
if not st.session_state.portfolio_autoloaded and not st.session_state.portfolio_holdings:
    _saved=load_portfolios()
    if _saved:
        most_recent=_saved[0]
        st.session_state.portfolio_holdings=most_recent["holdings"]
        st.session_state.current_portfolio_id=most_recent["id"]
        st.session_state.current_portfolio_name=most_recent["name"]
    st.session_state.portfolio_autoloaded=True

def fmt_mcap(b): return f"${b/1000:.1f}T" if b>=1000 else f"${b:.1f}B"

def make_gauge(value,title,mn=0,mx=100,invert=False):
    if invert: steps=[dict(range=[0,25],color="#00C805"),dict(range=[25,45],color="#8BC34A"),dict(range=[45,55],color="#FFC107"),dict(range=[55,75],color="#FF5722"),dict(range=[75,100],color="#D32F2F")]
    else: steps=[dict(range=[0,25],color="#D32F2F"),dict(range=[25,45],color="#FF5722"),dict(range=[45,55],color="#FFC107"),dict(range=[55,75],color="#8BC34A"),dict(range=[75,100],color="#00C805")]
    fig=go.Figure(go.Indicator(mode="gauge+number",value=value,title=dict(text=title,font=dict(size=14,color="#e0e0e0")),number=dict(font=dict(size=28,color="#e0e0e0")),gauge=dict(axis=dict(range=[mn,mx],tickcolor="#666"),bar=dict(color="#00D4AA",thickness=0.3),bgcolor="#1A1F2E",steps=steps,threshold=dict(line=dict(color="white",width=2),thickness=0.8,value=value))))
    fig.update_layout(height=200,margin=dict(l=20,r=20,t=40,b=10),paper_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"))
    return fig

def radar(ps,t):
    cats=list(ps.keys());vals=[ps[c] for c in cats]+[ps[cats[0]]];cats=cats+[cats[0]]
    fig=go.Figure();fig.add_trace(go.Scatterpolar(r=vals,theta=cats,fill="toself",fillcolor="rgba(0,212,170,0.2)",line=dict(color="#00D4AA",width=2),name=t))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True,range=[0,12],tickvals=[3,6,9,12],ticktext=["D","C","B","A+"],gridcolor="#2a2f3e"),angularaxis=dict(gridcolor="#2a2f3e"),bgcolor="rgba(0,0,0,0)"),showlegend=False,margin=dict(l=60,r=60,t=30,b=30),height=320,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"))
    return fig

def multi_radar(td):
    colors=["#00D4AA","#FF6B6B","#4ECDC4","#FFE66D","#A8E6CF"];fig=go.Figure();pillars=list(PILLAR_METRICS.keys())
    for i,(t,s) in enumerate(td.items()):
        v=[s.get(p,0) for p in pillars]+[s.get(pillars[0],0)];c_=pillars+[pillars[0]];cl=colors[i%len(colors)]
        fig.add_trace(go.Scatterpolar(r=v,theta=c_,fill="toself",fillcolor=f"rgba({','.join(str(int(cl[j:j+2],16)) for j in (1,3,5))},0.1)",line=dict(color=cl,width=2),name=t))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True,range=[0,12],tickvals=[3,6,9,12],ticktext=["D","C","B","A+"],gridcolor="#2a2f3e"),angularaxis=dict(gridcolor="#2a2f3e"),bgcolor="rgba(0,0,0,0)"),margin=dict(l=60,r=60,t=40,b=40),height=400,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),legend=dict(orientation="h",yanchor="bottom",y=-0.15,xanchor="center",x=0.5))
    return fig

render_user_sidebar()

with st.sidebar:
    st.markdown("## Settings")
    st.markdown("---")
    market_cap_floor=st.slider("Min Market Cap ($B)",MIN_MARKET_CAP_FLOOR_B,MAX_MARKET_CAP_FLOOR_B,DEFAULT_MARKET_CAP_FLOOR_B,1)
    st.markdown("---")
    sector_relative=st.toggle("Sector-Relative Scoring",value=True);st.session_state.sector_relative=sector_relative
    st.markdown("---")
    st.markdown("### Pillar Weights")
    w_val=st.slider("Valuation",0.0,1.0,st.session_state.weights["Valuation"],0.05,key="w_val")
    w_gro=st.slider("Growth",0.0,1.0,st.session_state.weights["Growth"],0.05,key="w_gro")
    w_pro=st.slider("Profitability",0.0,1.0,st.session_state.weights["Profitability"],0.05,key="w_pro")
    w_mom=st.slider("Momentum",0.0,1.0,st.session_state.weights["Momentum"],0.05,key="w_mom")
    w_eps=st.slider("EPS Revisions",0.0,1.0,st.session_state.weights["EPS Revisions"],0.05,key="w_eps")
    tw=w_val+w_gro+w_pro+w_mom+w_eps
    if tw>0: st.session_state.weights={"Valuation":w_val/tw,"Growth":w_gro/tw,"Profitability":w_pro/tw,"Momentum":w_mom/tw,"EPS Revisions":w_eps/tw}
    st.markdown("---")
    nt=st.text_input("Add to Watchlist",placeholder="e.g. AAPL").upper().strip()
    if st.button("Add",key="sb_wl") and nt: add_to_watchlist(nt);st.success(f"Added {nt}");st.rerun()
    st.markdown("---")
    if st.button("Refresh Data",key="sb_ref"):
        st.cache_data.clear();st.session_state.scored_df=None;st.session_state.raw_data=None;st.rerun()

st.markdown('<p class="main-header">Quant Strategy Dashboard Pro</p>',unsafe_allow_html=True)
mode="Sector-Relative" if st.session_state.sector_relative else "Universe-Wide"
st.markdown(f'<p class="sub-header">{mode} scoring across 5 pillars</p>',unsafe_allow_html=True)

tabs=st.tabs(["🏠 Home","Macro Economy","Market Sentiment","Advanced Screener","Swing Trader","Sector Overview","Stock Detail","📈 Pro Charts","Doppelganger","Portfolio","Monte Carlo","ETF Center","📖 Help"])
tab_home,tab_macro,tab_sentiment,tab_advanced,tab_swing,tab_sectors,tab_detail,tab_procharts,tab_doppel,tab_portfolio,tab_mc,tab_etfs,tab_help=tabs

@st.cache_data(ttl=43200,show_spinner=False)
def load_and_score(mcap,wt,sr):
    w=dict(zip(DEFAULT_PILLAR_WEIGHTS.keys(),wt));tickers=get_broad_universe(mcap)
    progress=st.progress(0,text="Loading...");raw=fetch_universe_data(tickers,mcap,lambda p,m:progress.progress(p,text=m));progress.empty()
    scored=score_universe(raw,w,sector_relative=sr);ss=get_sector_stats(scored) if not scored.empty else {}
    return raw,scored,ss

try: raw_data,scored_df,sector_stats=load_and_score(market_cap_floor,tuple(st.session_state.weights.values()),st.session_state.sector_relative)
except Exception as e: st.error(f"Error: {e}");st.stop()
if scored_df is None or scored_df.empty: st.warning("No data.");st.stop()

# ═══ TAB 0: HOME DASHBOARD ════════════════════════════════════════
with tab_home:
    st.markdown("### Dashboard Overview")
    st.caption("Your portfolio and market at a glance")

    # Top-line market metrics
    with st.spinner("Loading market overview..."):
        hm_index=fetch_index_data();hm_vix=fetch_vix_data();hm_breadth=compute_market_breadth(scored_df);hm_buffett=fetch_buffett_indicator()
        hm_fg=compute_fear_greed(hm_vix,hm_breadth,hm_index,hm_buffett)

    st.markdown("#### Market Health")
    mh1,mh2,mh3,mh4,mh5=st.columns(5)
    with mh1: st.metric("Fear & Greed",f"{hm_fg['score']:.0f}/100",hm_fg["classification"])
    with mh2:
        sp_dist=0
        for idx in hm_index:
            if idx["name"]=="S&P 500": sp_dist=idx["distance_from_ath_pct"];break
        st.metric("S&P vs ATH",f"{sp_dist:+.1f}%")
    with mh3:
        if hm_vix: st.metric("VIX",f"{hm_vix['current']:.1f}",hm_vix.get("level","N/A"))
    with mh4:
        if hm_breadth: st.metric("Above 200-SMA",f"{hm_breadth['pct_above_200sma']:.0f}%")
    with mh5:
        if hm_buffett: st.metric("Buffett Ind.",f"{hm_buffett['ratio']:.0f}%",hm_buffett.get("level","N/A"))

    st.markdown("---")

    # Portfolio snapshot if holdings exist
    if st.session_state.portfolio_holdings:
        analysis_h=analyze_portfolio(st.session_state.portfolio_holdings,scored_df,sector_stats)
        if "error" not in analysis_h and analysis_h:
            st.markdown("#### Your Portfolio")
            ph1,ph2,ph3,ph4,ph5=st.columns(5)
            with ph1: st.metric("Value",f"${analysis_h['total_value']:,.0f}")
            with ph2: st.metric("Holdings",analysis_h["num_holdings"])
            with ph3: st.metric("Rating",analysis_h["weighted_rating"])
            with ph4: st.metric("Score",f"{analysis_h['weighted_composite']:.1f}/12")
            with ph5: st.metric("Concentration",analysis_h["concentration_level"])

            # Top 3 actionable suggestions
            sugs_h=generate_suggestions_v2(analysis_h,scored_df,max_suggestions=3)
            if sugs_h:
                st.markdown("**Top Actions:**")
                for sug in sugs_h:
                    card=format_suggestion_card(sug)
                    st.markdown(f'<div style="background:#1A1F2E;border-left:4px solid {card["color"]};padding:12px;margin-bottom:8px;border-radius:4px;"><strong style="color:{card["color"]};">{card["icon"]} {card["title"]}</strong><br><span style="color:#fff;">→ {card["action"]}</span><br><span style="color:#aaa;font-size:0.9em;">{card["reasoning"]}</span></div>',unsafe_allow_html=True)

    st.markdown("---")

    # Sector heatmap
    st.markdown("#### Sector Heatmap")
    non_etf=scored_df[scored_df["sector"]!="ETF"].copy()
    if not non_etf.empty:
        tmap=non_etf.groupby("sector").agg(count=("composite_score","count"),avg_score=("composite_score","mean"),total_cap=("marketCapB","sum")).reset_index()
        fig_tm=go.Figure(go.Treemap(
            labels=tmap["sector"],
            parents=[""]*len(tmap),
            values=tmap["total_cap"],
            customdata=tmap[["count","avg_score"]].values,
            marker=dict(colors=tmap["avg_score"],colorscale=[[0,"#D32F2F"],[0.5,"#FFC107"],[1,"#00C805"]],cmid=6.5,showscale=True,colorbar=dict(title="Avg Score")),
            texttemplate="<b>%{label}</b><br>%{customdata[0]} stocks<br>Score: %{customdata[1]:.1f}",
            hovertemplate="<b>%{label}</b><br>Stocks: %{customdata[0]}<br>Avg Score: %{customdata[1]:.1f}<br>Total Cap: $%{value:,.0f}B<extra></extra>"
        ))
        fig_tm.update_layout(height=450,paper_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig_tm,use_container_width=True,key="home_heatmap")

    st.markdown("---")

    # Top movers today
    st.markdown("#### Top Rated Opportunities")
    top5=scored_df[(scored_df["overall_rating"]=="Strong Buy")&(scored_df["sector"]!="ETF")].nlargest(5,"composite_score")
    if not top5.empty:
        top_cols=st.columns(5)
        for i,(tk,rw) in enumerate(top5.iterrows()):
            with top_cols[i]:
                st.markdown(f"**{tk}**")
                st.caption(rw.get("shortName",""))
                st.metric("Score",f"{rw.get('composite_score',0):.1f}",rw.get("sector","")[:12])

    # ═══ Stock Screener ═══
    st.markdown("---")
    st.markdown("#### Stock Screener")
    st.caption("Browse and filter the scored universe.")
    sc1,sc2,sc3=st.columns(3)
    with sc1: home_sec=st.selectbox("Sector",["All"]+sorted(scored_df["sector"].dropna().unique().tolist()),key="home_screen_sec")
    with sc2: home_rat=st.selectbox("Rating",["All","Strong Buy","Buy","Hold","Sell","Strong Sell"],key="home_screen_rat")
    with sc3: home_top=st.selectbox("Show Top",[50,100,250,500],index=1,key="home_screen_top")
    home_filtered=get_top_stocks(scored_df,home_top,home_sec,home_rat)
    if not home_filtered.empty:
        hs1,hs2,hs3,hs4,hs5,hs6=st.columns(6)
        with hs1: st.metric("Universe",f"{len(scored_df):,}")
        with hs2: st.metric("Strong Buys",len(scored_df[scored_df["overall_rating"]=="Strong Buy"]))
        with hs3: st.metric("Buys",len(scored_df[scored_df["overall_rating"]=="Buy"]))
        with hs4: st.metric("Holds",len(scored_df[scored_df["overall_rating"]=="Hold"]))
        with hs5: st.metric("Sells",len(scored_df[scored_df["overall_rating"]=="Sell"]))
        with hs6: st.metric("Strong Sells",len(scored_df[scored_df["overall_rating"]=="Strong Sell"]))
        hdc=["shortName","sector","marketCapB","currentPrice"]
        for p in PILLAR_METRICS: hdc.append(f"{p}_grade")
        hdc+=["composite_score","overall_rating"]
        hdd=home_filtered[hdc].copy()
        hdd.columns=["Company","Sector","Mkt Cap ($B)","Price","Valuation","Growth","Profit","Momentum","EPS Rev","Score","Rating"]
        st.dataframe(hdd,use_container_width=True,height=500)

    # AI Status Diagnostic
    st.markdown("---")
    st.markdown("#### Service Status")
    ai_status=get_provider_status()
    can_use_now,ai_msg=can_use_ai()

    # Row 1: AI status
    ai_c1,ai_c2,ai_c3=st.columns(3)
    with ai_c1:
        if ai_status["available"]:
            st.success(f"✓ AI Provider: {ai_status['provider'].title()}")
        else:
            st.error("✗ AI provider not configured")
            st.caption("Add GEMINI_API_KEY to Streamlit secrets")
    with ai_c2:
        if can_use_now:
            st.success(f"✓ {ai_msg}")
        else:
            st.warning(f"⚠ {ai_msg}")
    with ai_c3:
        if ai_status["available"] and can_use_now:
            st.info("AI buttons appear in: Stock Detail, Doppelganger, Portfolio")
        else:
            st.caption("Fix the issues at left to unlock AI features")

    # Row 2: Data sources
    ds_c1,ds_c2,ds_c3=st.columns(3)
    with ds_c1:
        if is_fmp_configured():
            st.success("✓ FMP Earnings Data")
            st.caption("5-10 years of quarterly EPS available")
        else:
            st.warning("⚠ FMP not configured")
            st.caption("Add FMP_API_KEY to secrets for full earnings history. Falls back to Yahoo Finance (~5 quarters).")
    with ds_c2:
        if is_auth_configured():
            st.success("✓ Supabase Auth & Storage")
            st.caption("Saved portfolios, watchlist, usage tracking")
        else:
            st.warning("⚠ Supabase not configured")
    with ds_c3:
        st.info("📊 Yahoo Finance: Always available")
        st.caption("Primary source for prices, quotes, fundamentals")

# ═══ TAB 1: MACRO ECONOMICS ══════════════════════════════════════
with tab_macro:
    st.markdown("### Macroeconomic Dashboard")
    st.caption("3-factor earnings model (CPI + Unemployment + ISM) | Based on BMO & Federal Reserve research")
    macro=get_macro_summary()
    health=macro["health_score"]
    earnings=macro["earnings_forecast"]
    fed=get_fed_rate_outlook()
    yc=fetch_yield_curve()

    # Health gauge
    st.markdown("---")
    hg1,hg2=st.columns([1,2])
    with hg1: st.plotly_chart(make_gauge(health["score"],"Macro Health",0,100),use_container_width=True,key="mh_g")
    with hg2:
        st.markdown(f'### <span style="color:{health["color"]}">{health["classification"]}</span>',unsafe_allow_html=True)
        for c in health["components"]:
            st.markdown(f"**{c['name']}**: {c['value']} ({c['interpretation']})");st.progress(c["score"]/100)

    # Key indicators
    st.markdown("---")
    st.markdown("### Key Economic Indicators")
    ki1,ki2,ki3,ki4,ki5,ki6=st.columns(6)
    with ki1: st.metric("CPI (YoY)",f"{macro['cpi_current']}%",f"{macro['cpi_current']-macro['cpi_prior']:+.1f}%")
    with ki2: st.metric("Unemployment",f"{macro['unemployment_current']}%",f"{macro['unemployment_current']-macro['unemployment_prior']:+.1f}%",delta_color="inverse")
    with ki3: st.metric("ISM Composite",f"{macro['ism_composite']:.1f}","Expanding" if macro['ism_composite']>50 else "Contracting")
    with ki4: st.metric("GDP Growth",f"{macro['gdp_latest_qoq_annualized']}%",macro['gdp_quarter'])
    with ki5: st.metric("Fed Rate",fed["current_rate"])
    with ki6:
        if yc: st.metric("Yield Curve",f"{yc['spread_10y_2y']:+.2f}%","Normal" if yc['spread_10y_2y']>0 else "INVERTED",delta_color="normal" if yc['spread_10y_2y']>0 else "inverse")

    # Earnings forecast
    st.markdown("---")
    st.markdown("### S&P 500 Earnings Growth Forecast")
    st.markdown(f"**Model Output: {earnings['sp500_earnings_growth']:+.1f}%** (based on current macro conditions)")
    st.caption("Model: Intercept + CPI effect + Unemployment effect + ISM effect")

    # Scenario table
    st.markdown("#### Scenario Analysis")
    srows=[]
    for sn,sd in earnings["scenarios"].items():
        srows.append({"Scenario":sn,"CPI":f"{sd['cpi']:.1f}%","Unemployment":f"{sd['unemployment']:.1f}%","ISM":f"{sd['ism']:.1f}","Earnings Growth":f"{sd['earnings_growth']:+.1f}%","Description":sd["description"]})
    st.dataframe(pd.DataFrame(srows),use_container_width=True,hide_index=True)

    # Sector earnings forecasts
    st.markdown("#### Sector Earnings Forecast (based on macro model)")
    sf=earnings["sector_forecasts"]
    sf_df=pd.DataFrame([{"Sector":k,"Forecast":f"{v:+.1f}%"} for k,v in sorted(sf.items(),key=lambda x:x[1],reverse=True)])
    fig_sf=px.bar(sf_df,x="Sector",y=[float(r.replace("%","")) for r in sf_df["Forecast"]],color=[float(r.replace("%","")) for r in sf_df["Forecast"]],color_continuous_scale=["#D32F2F","#FFC107","#00C805"])
    fig_sf.update_layout(yaxis=dict(title="Earnings Growth %"),height=400,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),coloraxis_showscale=False,showlegend=False)
    st.plotly_chart(fig_sf,use_container_width=True,key="sf_bar")

    # Fed rate outlook
    st.markdown("---")
    st.markdown("### Federal Reserve Rate Outlook")
    fr1,fr2,fr3,fr4=st.columns(4)
    with fr1: st.metric("Current Rate",fed["current_rate"])
    with fr2: st.metric("Next Meeting",fed["next_meeting"])
    with fr3: st.metric("Year-End Dots",fed["year_end_dots"])
    with fr4: st.markdown(f"**Bias:** {fed['bias']}")
    fp1,fp2,fp3=st.columns(3)
    with fp1: st.metric("Cut Probability",f"{fed['cut_probability']}%")
    with fp2: st.metric("Hold Probability",f"{fed['hold_probability']}%")
    with fp3: st.metric("Hike Probability",f"{fed['hike_probability']}%")
    st.caption(fed["note"])

    # Economic calendar
    st.markdown("---")
    with st.expander("Key Economic Releases Calendar"):
        cal=fetch_economic_calendar()
        for ev in cal:
            imp_color={"Critical":"#FF5722","High":"#FFC107","Medium":"#8BC34A"}.get(ev["importance"],"#666")
            st.markdown(f'<span style="color:{imp_color};font-weight:700;">[{ev["importance"]}]</span> **{ev["event"]}** ({ev["date"]})',unsafe_allow_html=True)
            st.caption(ev["description"])

    st.caption(f"Macro data last updated: {macro['last_updated']}. Update macro.py MACRO_DATA dict with latest BLS/ISM releases.")

# ═══ TAB 2: MARKET SENTIMENT ══════════════════════════════════════
with tab_sentiment:
    st.markdown("### Market Sentiment Dashboard")
    with st.spinner("Fetching live market data..."):
        index_data=fetch_index_data();vix_data=fetch_vix_data();breadth_data=compute_market_breadth(scored_df);buffett_data=fetch_buffett_indicator()
        fear_greed=compute_fear_greed(vix_data,breadth_data,index_data,buffett_data)
    fg1,fg2=st.columns([1,1])
    with fg1: st.plotly_chart(make_gauge(fear_greed["score"],"Fear & Greed",0,100),use_container_width=True,key="fg_g")
    with fg2:
        st.markdown(f'### <span style="color:{fear_greed["color"]}">{fear_greed["classification"]}</span>',unsafe_allow_html=True)
        for comp in fear_greed["components"]:
            st.markdown(f"**{comp['name']}**: {comp['value']} ({comp['interpretation']})");st.progress(comp["score"]/100)
    st.markdown("---")
    g1,g2,g3=st.columns(3)
    with g1:
        if vix_data: st.plotly_chart(make_gauge(vix_data["score"],f"VIX: {vix_data['current']}",0,100),use_container_width=True,key="vg")
    with g2:
        if breadth_data: st.plotly_chart(make_gauge(breadth_data["pct_above_50sma"],f"Above 50-SMA: {breadth_data['pct_above_50sma']:.0f}%",0,100),use_container_width=True,key="s5g")
    with g3:
        if breadth_data: st.plotly_chart(make_gauge(breadth_data["pct_above_200sma"],f"Above 200-SMA: {breadth_data['pct_above_200sma']:.0f}%",0,100),use_container_width=True,key="s2g")
    st.markdown("---")
    # PGI (Potential Growth Indicator)
    pgi_data=compute_pgi()
    if pgi_data:
        st.markdown("### Potential Growth Indicator (PGI)")
        st.caption("Measures cash sitting in money markets vs total US stock market cap. Higher PGI = more fear = contrarian buy signal.")
        pg1,pg2=st.columns([1,2])
        with pg1:
            st.plotly_chart(make_gauge(pgi_data["score"],f"PGI: {pgi_data['pgi']:.1f}%",0,100),use_container_width=True,key="pgi_g")
        with pg2:
            st.markdown(f'### <span style="color:{pgi_data["color"]}">{pgi_data["level"]}</span>',unsafe_allow_html=True)
            st.markdown(f"**PGI: {pgi_data['pgi']:.2f}%** (Money Markets: ${pgi_data['money_market_t']}T / US Market Cap: ${pgi_data['total_mkt_cap_t']}T)")
            st.caption(pgi_data["interpretation"])
            st.caption("Above 11.5% = Eager to invest (others fearful) | 9.5-11.5% = Neutral | Below 9.5% = Cautious (others greedy)")
            st.caption(pgi_data["note"])
    st.markdown("---")
    if index_data:
        idf=pd.DataFrame(index_data);dc=["name","current_price","all_time_high","distance_from_ath_pct","change_1d_pct","change_5d_pct","change_1m_pct","change_ytd_pct"]
        st.dataframe(idf[dc].rename(columns={"name":"Asset","current_price":"Price","all_time_high":"ATH","distance_from_ath_pct":"From ATH %","change_1d_pct":"1D%","change_5d_pct":"5D%","change_1m_pct":"1M%","change_ytd_pct":"YTD%"}),use_container_width=True,hide_index=True)
    with st.expander("Coming Soon"):
        for ind in COMING_SOON_INDICATORS:
            st.markdown(f"**{ind['name']}** -- *{ind.get('status','Planned')}*");st.caption(ind["description"])

# ═══ TAB: ADVANCED SCREENER ═════════════════════════════════════
with tab_advanced:
    st.markdown("### Advanced Screener")
    st.caption("Combine rating, fair value, and custom metric filters. Results include Fair Value and Buy Point.")
    preset_names=["Custom"]+list(PRESET_SCREENS.keys())
    selected_preset=st.selectbox("Quick Screens",preset_names,key="adv_preset")
    st.markdown("---")
    fc1,fc2,fc3=st.columns(3)
    preset=PRESET_SCREENS.get(selected_preset,{}) if selected_preset!="Custom" else {}
    with fc1: adv_ratings=st.multiselect("Rating",["Strong Buy","Buy","Hold","Sell","Strong Sell"],default=preset.get("rating_filter",[]),key="adv_rat")
    with fc2: adv_sectors=st.multiselect("Sector",sorted(scored_df["sector"].dropna().unique().tolist()),key="adv_sec")
    with fc3: adv_fv=st.multiselect("Fair Value Verdict",["Deeply Undervalued","Undervalued","Fairly Valued","Overvalued","Significantly Overvalued"],default=preset.get("fair_value_filter",[]),key="adv_fv")
    if preset: st.info(preset.get("description",""))
    st.markdown("#### Metric Filters")
    active_filters=dict(preset.get("metric_filters",{}))
    if selected_preset=="Custom":
        filter_options=[]
        for cat,metrics in FILTERABLE_METRICS.items():
            for m in metrics: filter_options.append(f"{cat}: {m['name']}")
        selected_filters=st.multiselect("Add metric filters",filter_options,key="adv_ms")
        for i,sf in enumerate(selected_filters):
            cat_name,metric_name=sf.split(": ",1)
            for cat,metrics in FILTERABLE_METRICS.items():
                if cat==cat_name:
                    for m in metrics:
                        if m["name"]==metric_name:
                            is_pct=m["type"]=="pct_range"
                            vals=st.slider(f"{m['name']}{' (%)' if is_pct else ''}",float(m["default_min"]),float(m["default_max"]),(float(m["default_min"]),float(m["default_max"])),step=float(m["step"]),key=f"am_{i}")
                            active_filters[m["key"]]=vals
    if st.button("Run Screen",key="adv_run"):
        results=apply_advanced_filters(scored_df,rating_filter=adv_ratings or None,sector_filter=adv_sectors or None,metric_filters=active_filters or None)
        if results.empty: st.warning("No stocks match all filters.")
        else:
            # Always compute fair values
            with st.spinner(f"Computing fair values for {len(results)} stocks..."):
                fv_r=compute_fair_values_batch(scored_df,results.index.tolist())
                results["fv_price"]=results.index.map(lambda t:fv_r.get(t,{}).get("fair_value"))
                results["fv_verdict"]=results.index.map(lambda t:fv_r.get(t,{}).get("verdict","N/A"))
                results["fv_premium"]=results.index.map(lambda t:fv_r.get(t,{}).get("premium_discount"))
            # Compute buy points
            with st.spinner("Computing buy points..."):
                bp_r=compute_buy_points_batch(results.index.tolist()[:100],scored_df)
                results["bp_price"]=results.index.map(lambda t:bp_r.get(t,{}).get("buy_point"))
                results["bp_distance"]=results.index.map(lambda t:bp_r.get(t,{}).get("distance_pct"))
                results["bp_signal"]=results.index.map(lambda t:bp_r.get(t,{}).get("signal","N/A"))
            # Filter by fair value if selected
            if adv_fv:
                results=results[results["fv_verdict"].isin(adv_fv)]
            st.metric("Results",len(results))
            dc2=["shortName","sector","currentPrice","fv_price","fv_verdict","fv_premium","bp_price","bp_distance","bp_signal"]
            for p in PILLAR_METRICS: dc2.append(f"{p}_grade")
            dc2+=["composite_score","overall_rating"]
            avail=[c for c in dc2 if c in results.columns];dd2=results[avail].copy()
            rn={"shortName":"Company","sector":"Sector","currentPrice":"Price","fv_price":"Fair Value","fv_verdict":"FV Verdict","fv_premium":"Prem/Disc %","bp_price":"Buy Point","bp_distance":"BP Dist %","bp_signal":"BP Signal","composite_score":"Score","overall_rating":"Rating"}
            for p in PILLAR_METRICS: rn[f"{p}_grade"]={"Valuation":"Val","Growth":"Grw","Profitability":"Prof","Momentum":"Mom","EPS Revisions":"EPS"}.get(p,p)
            dd2=dd2.rename(columns={c:rn.get(c,c) for c in dd2.columns})
            st.dataframe(dd2,use_container_width=True,height=600)

# ═══ TAB 5: SWING TRADER ═══════════════════════════════════════════
with tab_swing:
    st.markdown("### IBD-Inspired Swing Trader")
    st.caption("Combines fundamental quality (5-pillar score) with technical swing setups. Targets 5-10% gains over 3-10 trading days.")
    methodology=get_swing_methodology()
    with st.expander("Methodology"):
        for comp in methodology["components"]:
            st.markdown(f"**{comp['name']}** ({comp['weight']})")
            st.caption(comp["description"])
        st.markdown("---")
        tp=methodology["trade_plan"]
        st.markdown(f"**Entry:** {tp['entry']}")
        st.markdown(f"**Target:** {tp['profit_target']}")
        st.markdown(f"**Stop:** {tp['stop_loss']}")
        st.markdown(f"**Hold:** {tp['holding_period']}")
        st.markdown(f"**R/R:** {tp['risk_reward']}")
    sw1,sw2=st.columns(2)
    with sw1: sw_min_score=st.slider("Min Quant Score",4.0,10.0,6.5,0.5,key="sw_ms")
    with sw2: sw_max_scan=st.selectbox("Scan Pool",[50,100,150,200],index=2,key="sw_pool",help="Top N stocks by quant score to scan for setups")
    if st.button("Scan for Swing Setups",key="sw_run"):
        with st.spinner(f"Scanning top {sw_max_scan} stocks for swing setups..."):
            swing_results=scan_swing_candidates(scored_df,max_scan=sw_max_scan,min_score=sw_min_score)
        if not swing_results:
            st.info("No swing setups found with current filters. Try lowering the minimum quant score.")
        else:
            st.success(f"Found {len(swing_results)} swing candidates")
            # Summary metrics
            a_setups=len([s for s in swing_results if s["setup"] in ["A+ Setup","Strong Setup"]])
            avg_rr=np.mean([s["risk_reward"] for s in swing_results])
            st.markdown(f"**Strong+ setups:** {a_setups} | **Avg R/R:** {avg_rr:.1f}:1")
            # Results table
            sw_rows=[]
            for s in swing_results:
                sw_rows.append({
                    "Ticker":s["ticker"],"Company":s.get("shortName","")[:25],
                    "Sector":s["sector"],"Price":f"${s['price']:.2f}",
                    "Setup":s["setup"],"Swing":s["swing_score"],
                    "Quant":f"{s['composite_score']:.1f}","Combined":s["combined_score"],
                    "Target":f"${s['target_price']} (+{s['target_pct']}%)",
                    "Stop":f"${s['stop_price']} (-{s['stop_pct']}%)",
                    "R/R":f"{s['risk_reward']}:1",
                    "RSI":s["rsi_14"],"Vol Ratio":s["volume_ratio"],
                    "21-EMA Dist":f"{s['dist_from_ema21_pct']:+.1f}%",
                    "Trend":s["trend"],
                })
            sw_df=pd.DataFrame(sw_rows)
            st.dataframe(sw_df,use_container_width=True,height=500,hide_index=True)
            # Detail view for top pick
            if swing_results:
                st.markdown("---")
                top=swing_results[0]
                st.markdown(f"### Top Pick: {top['ticker']} ({top['shortName']})")
                tc1,tc2,tc3,tc4,tc5,tc6=st.columns(6)
                with tc1: st.metric("Price",f"${top['price']}")
                with tc2: st.metric("Setup",top["setup"])
                with tc3: st.metric("Target",f"${top['target_price']}",f"+{top['target_pct']}%")
                with tc4: st.metric("Stop",f"${top['stop_price']}",f"-{top['stop_pct']}%",delta_color="inverse")
                with tc5: st.metric("R/R",f"{top['risk_reward']}:1")
                with tc6: st.metric("RSI",f"{top['rsi_14']}")
                ti1,ti2,ti3,ti4=st.columns(4)
                with ti1: st.metric("21-EMA",f"${top['ema_21']}",f"{top['dist_from_ema21_pct']:+.1f}%")
                with ti2: st.metric("Volume Ratio",f"{top['volume_ratio']}x","Surging" if top['volume_ratio']>1.3 else "Normal")
                with ti3: st.metric("Channel Pos",f"{top['channel_position']}%")
                with ti4: st.metric("From 20d High",f"{top['pct_from_20d_high']:+.1f}%")
                flags=[]
                if top["is_pullback"]: flags.append("Pullback detected")
                if top["is_bouncing"]: flags.append("Bounce confirmed")
                if top["trend"]=="Uptrend": flags.append("Uptrend intact")
                if flags: st.info(" | ".join(flags))

# ═══ TAB 6: SECTOR OVERVIEW ═══════════════════════════════════════
with tab_sectors:
    st.markdown("### Sector Overview")
    overview=get_sector_overview(scored_df)
    if not overview.empty:
        # ── Sector Aggregates: Market Cap + Earnings combo chart ──
        st.markdown("#### Sector Aggregates: Market Cap & Earnings")
        st.caption("Combined market cap (line) and aggregate trailing 12-month earnings (bars) per sector. Shows scale and profitability of each sector population.")
        non_etf_universe=scored_df[scored_df["sector"]!="ETF"].copy()
        sec_agg=non_etf_universe.groupby("sector").agg(
            total_mcap=("marketCapB","sum"),
            stock_count=("composite_score","count"),
            avg_score=("composite_score","mean"),
            median_score=("composite_score","median"),
            std_score=("composite_score","std"),
        ).reset_index()
        # Compute aggregate earnings: market cap * (1/PE) gives net income
        non_etf_universe["est_earnings"]=non_etf_universe.apply(
            lambda r: (r["marketCapB"]/r["trailingPE"]) if pd.notna(r.get("trailingPE")) and r.get("trailingPE",0)>0 else 0,
            axis=1
        )
        sec_earnings=non_etf_universe.groupby("sector")["est_earnings"].sum().reset_index()
        sec_combo=sec_agg.merge(sec_earnings,on="sector").sort_values("total_mcap",ascending=False)

        from plotly.subplots import make_subplots
        fig_sa=make_subplots(specs=[[{"secondary_y":True}]])
        fig_sa.add_trace(go.Bar(x=sec_combo["sector"],y=sec_combo["est_earnings"],name="Aggregate TTM Earnings ($B)",marker_color="#FFC107",opacity=0.7,hovertemplate="<b>%{x}</b><br>Earnings: $%{y:.0f}B<extra></extra>"),secondary_y=False)
        fig_sa.add_trace(go.Scatter(x=sec_combo["sector"],y=sec_combo["total_mcap"],name="Total Market Cap ($B)",mode="lines+markers",line=dict(color="#00D4AA",width=3),marker=dict(size=10),hovertemplate="<b>%{x}</b><br>Market Cap: $%{y:,.0f}B<extra></extra>"),secondary_y=True)
        fig_sa.update_layout(height=400,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),legend=dict(orientation="h",yanchor="bottom",y=-0.3,xanchor="center",x=0.5,bgcolor="rgba(0,0,0,0)"),margin=dict(l=60,r=60,t=20,b=80),hovermode="x unified")
        fig_sa.update_xaxes(gridcolor="#2a2f3e",tickangle=-30)
        fig_sa.update_yaxes(title_text="Earnings ($B)",tickformat="$,.0f",gridcolor="#2a2f3e",secondary_y=False)
        fig_sa.update_yaxes(title_text="Market Cap ($B)",tickformat="$,.0f",showgrid=False,secondary_y=True)
        st.plotly_chart(fig_sa,use_container_width=True,key="sec_agg_combo")

        # ── Sector P/E quick view ──
        sec_combo["agg_pe"]=sec_combo["total_mcap"]/sec_combo["est_earnings"].replace(0,float("nan"))
        st.markdown("#### Sector Valuation Snapshot")
        st.caption("Aggregate P/E = total market cap / total earnings across the sector population.")
        snap_df=sec_combo[["sector","stock_count","total_mcap","est_earnings","agg_pe","avg_score","std_score"]].copy()
        snap_df.columns=["Sector","Stocks","Mkt Cap ($B)","Earnings ($B)","Agg P/E","Avg Score","Score Dispersion"]
        snap_df["Mkt Cap ($B)"]=snap_df["Mkt Cap ($B)"].apply(lambda x: f"${x:,.0f}B")
        snap_df["Earnings ($B)"]=snap_df["Earnings ($B)"].apply(lambda x: f"${x:,.0f}B")
        snap_df["Agg P/E"]=snap_df["Agg P/E"].apply(lambda x: f"{x:.1f}x" if pd.notna(x) else "N/A")
        snap_df["Avg Score"]=snap_df["Avg Score"].apply(lambda x: f"{x:.1f}")
        snap_df["Score Dispersion"]=snap_df["Score Dispersion"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")
        st.dataframe(snap_df,use_container_width=True,hide_index=True)

        st.markdown("---")
        st.markdown("#### Sector Quality Distribution")
        st.caption("Percentage of A-rated stocks (Strong Buy + Buy) by sector. This shows where the highest-conviction opportunities are concentrated.")
        # % of strong buy + buy per sector
        rating_dist=non_etf_universe.groupby(["sector","overall_rating"]).size().unstack(fill_value=0)
        for col in ["Strong Buy","Buy","Hold","Sell","Strong Sell"]:
            if col not in rating_dist.columns: rating_dist[col]=0
        rating_dist["Total"]=rating_dist.sum(axis=1)
        rating_dist["A-rated %"]=(rating_dist["Strong Buy"]+rating_dist["Buy"])/rating_dist["Total"]*100
        rating_dist=rating_dist.sort_values("A-rated %",ascending=False).reset_index()
        fig_q=go.Figure()
        fig_q.add_trace(go.Bar(x=rating_dist["sector"],y=rating_dist["A-rated %"],marker=dict(color=rating_dist["A-rated %"],colorscale=[[0,"#D32F2F"],[0.5,"#FFC107"],[1,"#00C805"]],cmin=0,cmax=50),text=rating_dist["A-rated %"].apply(lambda x: f"{x:.0f}%"),textposition="outside",hovertemplate="<b>%{x}</b><br>A-rated: %{y:.1f}%<extra></extra>"))
        fig_q.update_layout(height=350,yaxis=dict(title="% A-rated (Strong Buy + Buy)",gridcolor="#2a2f3e"),xaxis=dict(gridcolor="#2a2f3e",tickangle=-30),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),showlegend=False,margin=dict(l=60,r=20,t=20,b=80))
        st.plotly_chart(fig_q,use_container_width=True,key="sec_qual")

        st.markdown("---")
        st.markdown("#### Full Sector Detail")
        rc=["Rank","Sector","Stocks","composite_avg","Strong Buy","Buy","Hold","Sell","Strong Sell"]
        for p in PILLAR_METRICS: rc.append(f"{p}_grade")
        rc+=["best_stock","worst_stock"];ac=[c for c in rc if c in overview.columns]
        rn2={"composite_avg":"Avg Score","best_stock":"Best","worst_stock":"Worst"}
        for p in PILLAR_METRICS: rn2[f"{p}_grade"]={"Valuation":"Val","Growth":"Grw","Profitability":"Prof","Momentum":"Mom","EPS Revisions":"EPS"}.get(p,p)
        st.dataframe(overview[ac].rename(columns=rn2),use_container_width=True,hide_index=True)
        st.markdown("#### Sector Deep Dive")
        ss2=st.selectbox("Select sector",overview["Sector"].tolist(),key="sec_drill")
        if ss2:
            sd=get_sector_detail(ss2,scored_df)
            if sd:
                m1,m2,m3=st.columns(3)
                with m1: st.metric("Stocks",sd["num_stocks"])
                with m2: st.metric("Avg Score",f"{sd['composite_avg']:.1f}")
                with m3: st.metric("Median",f"{sd['composite_median']:.1f}")
                cm={"shortName":"Company","currentPrice":"Price","marketCapB":"Mkt Cap","composite_score":"Score","overall_rating":"Rating"}
                for p in PILLAR_METRICS: cm[f"{p}_grade"]={"Valuation":"Val","Growth":"Grw","Profitability":"Prof","Momentum":"Mom","EPS Revisions":"EPS"}.get(p,p)
                st.dataframe(sd["stocks_df"].rename(columns={c:cm.get(c,c) for c in sd["stocks_df"].columns}),use_container_width=True,height=500)

# ═══ TAB 6: STOCK DETAIL ═════════════════════════════════════════
with tab_detail:
    all_t=sorted(scored_df.index.tolist());di=0
    if st.session_state.selected_ticker in all_t: di=all_t.index(st.session_state.selected_ticker)
    sel=st.selectbox("Ticker",all_t,index=di,format_func=lambda x:f"{x} -- {scored_df.loc[x,'shortName']}" if x in scored_df.index else x,key="det_sel")
    if sel and sel in scored_df.index:
        row=scored_df.loc[sel];detail=get_pillar_detail(sel,scored_df,sector_stats)
        h1,h2,h3,h4=st.columns(4)
        with h1: st.markdown(f"## {sel}");st.caption(row.get("shortName",""))
        with h2: st.metric("Price",f"${row.get('currentPrice',0):.2f}")
        with h3: st.metric("Mkt Cap",fmt_mcap(row.get("marketCapB",0)))
        with h4: rat=row.get("overall_rating","Hold");st.metric("Score",f"{row.get('composite_score',0):.1f}/12");st.markdown(f'<span style="background:{RATING_COLORS.get(rat,"#666")};padding:4px 14px;border-radius:6px;font-weight:700;color:#111;">{rat}</span>',unsafe_allow_html=True)
        st.markdown(f"**Sector:** {row.get('sector','N/A')} | **Industry:** {row.get('industry','N/A')}")
        # ═══ Combined Price + Quarterly Earnings Chart ═══
        st.markdown("---")
        st.markdown("### Price & Quarterly Earnings")
        st.caption("Stock price line with quarterly EPS bars overlaid. Green bars = beat estimates, red = missed, gray = no estimate available.")
        chart_period=st.selectbox("Period",["1y","2y","3y","5y","10y","max"],index=3,key="price_period")
        try:
            t_obj=yf.Ticker(sel)
            price_hist=t_obj.history(period=chart_period)
            if not price_hist.empty:
                ph_close=price_hist["Close"]
                sma50=ph_close.rolling(50).mean() if len(ph_close)>=50 else None
                sma200=ph_close.rolling(200).mean() if len(ph_close)>=200 else None

                chart_start=price_hist.index.min().tz_localize(None) if price_hist.index.tz is not None else price_hist.index.min()

                # ── Get quarterly EPS - FMP first, yfinance fallback ──
                quarterly_eps=None
                surprises_series=None
                eps_source=""
                fmp_revenue_df=None
                fmp_error_msg=None  # Capture FMP error to display

                # PRIMARY SOURCE: FMP (5+ years of real quarterly EPS with surprises)
                if is_fmp_configured():
                    fmp_data=get_combined_earnings_data(sel,period_start=chart_start)
                    fmp_earnings=fmp_data.get("earnings_df")
                    if fmp_earnings is not None and not fmp_earnings.empty:
                        quarterly_eps=fmp_earnings["reported_eps"]
                        if "surprise_pct" in fmp_earnings.columns:
                            surprises_series=fmp_earnings["surprise_pct"]
                        eps_source="fmp"
                    elif fmp_data.get("earnings_error"):
                        fmp_error_msg=fmp_data["earnings_error"]
                    fmp_revenue_df=fmp_data.get("revenue_df")
                    if isinstance(fmp_revenue_df,dict):
                        fmp_revenue_df=None

                # FALLBACK 1: yfinance earnings_dates
                if quarterly_eps is None or (hasattr(quarterly_eps,'empty') and quarterly_eps.empty):
                    try:
                        ed=t_obj.earnings_dates
                        if ed is not None and not ed.empty:
                            if ed.index.tz is not None:
                                ed.index=ed.index.tz_localize(None)
                            now=pd.Timestamp.now()
                            ed_past=ed[ed.index<=now]
                            ed_past=ed_past[ed_past.index>=chart_start]
                            eps_col="Reported EPS" if "Reported EPS" in ed_past.columns else None
                            if eps_col:
                                eps_series=ed_past[eps_col].dropna()
                                if not eps_series.empty:
                                    quarterly_eps=eps_series
                                    eps_source="yfinance_earnings_dates"
                                    if "Surprise(%)" in ed_past.columns:
                                        surprises_series=ed_past.loc[eps_series.index,"Surprise(%)"]
                    except Exception:
                        pass

                # FALLBACK 2: yfinance quarterly income statement
                if quarterly_eps is None or (hasattr(quarterly_eps,'empty') and quarterly_eps.empty):
                    try:
                        qis=t_obj.quarterly_income_stmt
                        if qis is not None and not qis.empty:
                            for row_name in ["Diluted EPS","Basic EPS"]:
                                if row_name in qis.index:
                                    eps_from_stmt=qis.loc[row_name].dropna()
                                    if not eps_from_stmt.empty:
                                        quarterly_eps=eps_from_stmt.sort_index()
                                        eps_source="yfinance_income_stmt"
                                        break
                    except Exception:
                        pass

                # ── Build combo chart ──
                from plotly.subplots import make_subplots
                fig_combo=make_subplots(specs=[[{"secondary_y":True}]])

                # Earnings bars FIRST (so they render behind the price line)
                if quarterly_eps is not None and not quarterly_eps.empty:
                    bar_colors=[]
                    if surprises_series is not None:
                        for idx in quarterly_eps.index:
                            s=surprises_series.get(idx) if hasattr(surprises_series,"get") else None
                            if s is None or pd.isna(s): bar_colors.append("#888")
                            elif s>0: bar_colors.append("#22C55E")
                            else: bar_colors.append("#EF4444")
                    else:
                        # Color by EPS direction (growing = green, declining = red)
                        eps_sorted=quarterly_eps.sort_index()
                        prev=None
                        for v in eps_sorted.values:
                            if prev is None or v>=prev: bar_colors.append("#22C55E")
                            else: bar_colors.append("#EF4444")
                            prev=v

                    fig_combo.add_trace(
                        go.Bar(
                            x=quarterly_eps.index,
                            y=quarterly_eps.values,
                            name="Quarterly EPS",
                            marker_color=bar_colors,
                            opacity=0.55,
                            width=86400000*60,
                            hovertemplate="<b>%{x|%b %Y}</b><br>EPS: $%{y:.2f}<extra></extra>",
                        ),
                        secondary_y=True,
                    )

                # Price line on primary y-axis
                fig_combo.add_trace(
                    go.Scatter(x=price_hist.index,y=ph_close,mode="lines",name="Price",
                               line=dict(color="#00D4AA",width=2.5),
                               hovertemplate="<b>%{x|%b %d, %Y}</b><br>Price: $%{y:.2f}<extra></extra>"),
                    secondary_y=False,
                )
                if sma50 is not None:
                    fig_combo.add_trace(go.Scatter(x=price_hist.index,y=sma50,mode="lines",name="50-SMA",line=dict(color="#FFC107",width=1,dash="dot")),secondary_y=False)
                if sma200 is not None:
                    fig_combo.add_trace(go.Scatter(x=price_hist.index,y=sma200,mode="lines",name="200-SMA",line=dict(color="#FF6B6B",width=1,dash="dot")),secondary_y=False)

                fig_combo.update_layout(
                    height=500,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#e0e0e0"),
                    legend=dict(orientation="h",yanchor="bottom",y=-0.2,xanchor="center",x=0.5,bgcolor="rgba(0,0,0,0)"),
                    margin=dict(l=60,r=60,t=20,b=40),
                    hovermode="x unified",
                    bargap=0.3,
                )
                fig_combo.update_xaxes(gridcolor="#2a2f3e",showgrid=True)
                fig_combo.update_yaxes(title_text="Price ($)",tickformat="$,.2f",gridcolor="#2a2f3e",secondary_y=False)
                fig_combo.update_yaxes(title_text="EPS ($)",tickformat="$,.2f",showgrid=False,secondary_y=True)

                st.plotly_chart(fig_combo,use_container_width=True,key="price_earnings_combo")

                # Source badge - explicit diagnostics
                if eps_source=="fmp":
                    st.success(f"📊 Earnings data: Financial Modeling Prep ({len(quarterly_eps)} quarters of real data with surprises)")
                elif eps_source.startswith("yfinance"):
                    if not is_fmp_configured():
                        st.warning(f"📊 Using Yahoo Finance fallback ({len(quarterly_eps) if quarterly_eps is not None else 0} quarters). **Add FMP_API_KEY to Streamlit secrets** for 5-10 years of real quarterly history.")
                    elif fmp_error_msg:
                        st.error(f"📊 FMP failed, using Yahoo Finance ({len(quarterly_eps) if quarterly_eps is not None else 0} quarters). **FMP error:** {fmp_error_msg}")
                    else:
                        st.warning(f"📊 FMP returned no data, using Yahoo Finance ({len(quarterly_eps) if quarterly_eps is not None else 0} quarters).")

                # ── Earnings summary ──
                if quarterly_eps is None or quarterly_eps.empty:
                    st.caption("No quarterly earnings data available for this period.")
                else:
                    if surprises_series is not None:
                        sc=surprises_series.dropna() if hasattr(surprises_series,"dropna") else pd.Series([s for s in surprises_series if s is not None and not pd.isna(s)])
                        if not sc.empty:
                            beat_count=int((sc>0).sum())
                            miss_count=int((sc<=0).sum())
                            avg_surprise=float(sc.mean())
                            ec1,ec2,ec3,ec4=st.columns(4)
                            with ec1: st.metric("Quarters",len(quarterly_eps))
                            with ec2: st.metric("Beats",beat_count,f"{beat_count/(beat_count+miss_count)*100:.0f}%" if (beat_count+miss_count)>0 else "")
                            with ec3: st.metric("Misses",miss_count,f"{miss_count/(beat_count+miss_count)*100:.0f}%" if (beat_count+miss_count)>0 else "",delta_color="inverse")
                            with ec4: st.metric("Avg Surprise",f"{avg_surprise:+.1f}%")
                    else:
                        eps_sorted=quarterly_eps.sort_index()
                        latest=float(eps_sorted.iloc[-1])
                        ec1,ec2,ec3=st.columns(3)
                        with ec1: st.metric("Quarters",len(eps_sorted))
                        with ec2: st.metric("Latest EPS",f"${latest:.2f}")
                        if len(eps_sorted)>=5:
                            yoy_eps=eps_sorted.iloc[-1]-eps_sorted.iloc[-5]
                            with ec3: st.metric("YoY EPS Change",f"${yoy_eps:+.2f}")

                # ── Quarterly Revenue Trend (uses FMP if available, else yfinance) ──
                rev_data=None
                rev_in_billions=False
                if fmp_revenue_df is not None and not fmp_revenue_df.empty:
                    rev_data=fmp_revenue_df["revenue"]
                    rev_in_billions=False  # FMP gives raw dollars
                else:
                    try:
                        income_stmt=t_obj.quarterly_income_stmt
                        if income_stmt is not None and not income_stmt.empty and "Total Revenue" in income_stmt.index:
                            rev_data=income_stmt.loc["Total Revenue"].dropna().sort_index()
                            rev_data=rev_data[rev_data.index>=chart_start] if hasattr(rev_data.index,'min') else rev_data
                    except Exception:
                        pass

                if rev_data is not None and len(rev_data)>=2:
                    with st.expander(f"Quarterly Revenue Trend ({len(rev_data)} quarters)"):
                        fig_rev=go.Figure()
                        rev_colors=["#00D4AA" if (i==0 or rev_data.iloc[i]>=rev_data.iloc[i-1]) else "#F97316" for i in range(len(rev_data))]
                        rev_billions=rev_data.values/1e9
                        fig_rev.add_trace(go.Bar(x=rev_data.index,y=rev_billions,marker_color=rev_colors,hovertemplate="<b>%{x|%b %Y}</b><br>Revenue: $%{y:.2f}B<extra></extra>"))
                        fig_rev.update_layout(yaxis=dict(title="Revenue ($B)",tickformat="$,.1f",gridcolor="#2a2f3e"),xaxis=dict(gridcolor="#2a2f3e"),height=300,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),margin=dict(l=60,r=20,t=20,b=40),showlegend=False)
                        st.plotly_chart(fig_rev,use_container_width=True,key="rev_chart")
                        if len(rev_data)>=5:
                            yoy=(rev_data.iloc[-1]/rev_data.iloc[-5]-1)*100
                            qoq=(rev_data.iloc[-1]/rev_data.iloc[-2]-1)*100
                            rg1,rg2,rg3=st.columns(3)
                            with rg1: st.metric("Latest Quarter",f"${rev_data.iloc[-1]/1e9:.2f}B")
                            with rg2: st.metric("YoY Growth",f"{yoy:+.1f}%")
                            with rg3: st.metric("QoQ Growth",f"{qoq:+.1f}%")
        except Exception as e:
            st.caption(f"Chart unavailable: {str(e)[:80]}")
        # Fair Value
        st.markdown("---");st.markdown("### Fair Value Analysis")
        fv=compute_fair_value(sel,scored_df);fv_price=None
        if "error" not in fv:
            fv_price=fv["composite_fair_value"]
            f1,f2,f3,f4=st.columns(4)
            with f1: st.metric("Current",f"${fv['current_price']:.2f}")
            with f2: st.metric("Fair Value",f"${fv['composite_fair_value']:.2f}")
            with f3: st.metric("Premium/Disc",f"{fv['premium_discount_pct']:+.1f}%")
            with f4: st.markdown(f'<span style="background:{fv["verdict_color"]};padding:4px 14px;border-radius:6px;font-weight:700;color:#111;">{fv["verdict"]}</span>',unsafe_allow_html=True)
            if fv.get("north_star_metric"): st.caption(f"Primary: {fv['north_star_metric']}")
            mnames=list(fv["methods"].keys());mvals=[fv["methods"][m]["fair_value"] for m in mnames]
            fig_fv=go.Figure();fig_fv.add_trace(go.Bar(x=mnames,y=mvals,marker_color="#4ECDC4"))
            fig_fv.add_hline(y=fv["current_price"],line_dash="dash",line_color="#FF6B6B",annotation_text=f"Current: ${fv['current_price']}")
            fig_fv.add_hline(y=fv["composite_fair_value"],line_dash="dash",line_color="#00D4AA",annotation_text=f"Fair: ${fv['composite_fair_value']:.0f}")
            fig_fv.update_layout(yaxis=dict(title="$",tickformat="$,.0f"),height=300,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"))
            st.plotly_chart(fig_fv,use_container_width=True,key="fv_bar")
            with st.expander("Method Details"):
                for mn,md in fv["methods"].items():
                    st.markdown(f"**{mn}**: ${md['fair_value']:.2f} ({md['premium_discount_pct']:+.1f}%)")
                    if "assumptions" in md:
                        for ak,av in md["assumptions"].items(): st.caption(f"  {ak}: {av}")
                    st.markdown("---")
        else: st.caption(fv.get("error",""))
        # Buy Point
        st.markdown("---");st.markdown("### Quant Buy Point")
        with st.spinner(f"Computing buy point..."):
            bp=compute_buy_point(sel,scored_df,fair_value=fv_price)
        if "error" not in bp:
            bp1,bp2,bp3,bp4=st.columns(4)
            with bp1: st.metric("Current",f"${bp['current_price']:.2f}")
            with bp2: st.metric("Buy Point",f"${bp['buy_point']:.2f}")
            with bp3: st.metric("Distance",f"{bp['distance_pct']:+.1f}%")
            with bp4: st.markdown(f'<span style="background:{bp["signal_color"]};padding:4px 14px;border-radius:6px;font-weight:700;color:#111;">{bp["signal"]}</span>',unsafe_allow_html=True)
            with st.expander("Buy Point Components"):
                for cn,cd in bp["components"].items(): st.markdown(f"**{cn}**: ${cd['price']:.2f} ({cd['weight']*100:.0f}%)");st.caption(cd["description"])
            with st.expander("Technical Indicators"):
                for tk,tv in bp.get("technicals",{}).items(): st.markdown(f"**{tk}**: {tv}")
        else: st.caption(bp.get("error",""))

        # ═══ AI Research Note ═══
        if is_ai_available():
            st.markdown("---")
            st.markdown("### 🤖 AI Research Note")
            if st.button(f"Generate AI Analysis for {sel}",key="ai_stock_note"):
                with st.spinner("AI analyzing stock..."):
                    ai_note=generate_stock_research_note(sel,row.to_dict(),fv if "error" not in fv else {})
                if "error" in ai_note:
                    st.error(ai_note["error"])
                else:
                    st.markdown(ai_note["text"])
                    st.caption(f"Analysis powered by {ai_note.get('provider','AI')} • {ai_note.get('model','')}")

        # Pillar breakdown
        st.markdown("---")
        if detail:
            cc,cg=st.columns(2)
            with cc: st.plotly_chart(radar({p:d["pillar_score"] for p,d in detail.items()},sel),use_container_width=True,key="det_radar")
            with cg:
                for pn in PILLAR_METRICS:
                    g=row.get(f"{pn}_grade","N/A");s=row.get(f"{pn}_score",0);gc=GRADE_COLORS.get(g,"#666");bw=(s/12)*100
                    st.markdown(f'<div style="margin-bottom:8px;"><div style="display:flex;justify-content:space-between;margin-bottom:4px;"><span style="color:#ccc;">{pn}</span><span style="background:{gc};padding:2px 10px;border-radius:4px;font-weight:700;color:#111;">{g}</span></div><div style="background:#2a2f3e;border-radius:4px;height:8px;"><div style="background:{gc};border-radius:4px;height:8px;width:{bw}%;"></div></div></div>',unsafe_allow_html=True)
            st.markdown("### Full Metric Breakdown")
            for pn,pd_ in detail.items():
                with st.expander(f"{pn} | {pd_['pillar_grade']} | {pd_['pillar_score']:.1f}/12"):
                    for m in pd_["metrics"]:
                        mc1,mc2,mc3,mc4,mc5,mc6=st.columns([2.5,1.2,0.8,0.8,1.2,1.2])
                        with mc1: st.markdown(m["metric"]);st.caption("higher better" if m["higher_is_better"] else "lower better")
                        with mc2: st.markdown(f"**{m['value']}**")
                        with mc3: g2=m["grade"];gc2=GRADE_COLORS.get(g2,"#666");st.markdown(f'<span style="background:{gc2};padding:2px 8px;border-radius:4px;font-weight:700;color:#111;">{g2}</span>',unsafe_allow_html=True)
                        with mc4: st.markdown(m["percentile"])
                        with mc5: st.markdown(m["sector_avg"])
                        with mc6: st.markdown(f'**{m["a_threshold"]}**')

# ═══ TAB: PRO CHARTS ════════════════════════════════════════════════
with tab_procharts:
    st.markdown("### Pro Charts")
    st.caption("Professional candlestick charts with indicators (VWAP, EMAs, RSI, Bollinger Bands) and a live monitoring dashboard.")

    pc_section=st.radio("",["📈 Chart","👁 Live Monitor","🔥 Today's Movers"],horizontal=True,key="pc_section",label_visibility="collapsed")
    st.markdown("---")

    # ── Section 1: Candlestick Chart ──
    if pc_section=="📈 Chart":
        all_tickers=sorted(scored_df.index.tolist())
        pc_default=0
        if st.session_state.selected_ticker in all_tickers:
            pc_default=all_tickers.index(st.session_state.selected_ticker)

        pc1,pc2,pc3=st.columns([2,1,1])
        with pc1: pc_ticker=st.selectbox("Ticker",all_tickers,index=pc_default,format_func=lambda x:f"{x} -- {scored_df.loc[x,'shortName']}" if x in scored_df.index else x,key="pc_ticker")
        with pc2: pc_period=st.selectbox("Period",["1mo","3mo","6mo","1y","2y","5y"],index=2,key="pc_period")
        with pc3: pc_interval=st.selectbox("Interval",["1d","1h","30m","15m"],index=0,key="pc_interval",help="Intraday intervals (1h, 30m, 15m) only available for periods up to 60 days.")

        # Indicators toggles
        st.markdown("**Indicators:**")
        ic1,ic2,ic3,ic4,ic5=st.columns(5)
        with ic1: show_vwap=st.checkbox("VWAP",value=True,key="pc_vwap")
        with ic2: show_emas=st.checkbox("EMAs / SMAs",value=True,key="pc_emas")
        with ic3: show_bb=st.checkbox("Bollinger",value=False,key="pc_bb")
        with ic4: show_volume=st.checkbox("Volume",value=True,key="pc_vol")
        with ic5: show_rsi=st.checkbox("RSI",value=True,key="pc_rsi")

        if pc_ticker:
            with st.spinner(f"Loading {pc_ticker} chart..."):
                df=fetch_chart_data(pc_ticker,period=pc_period,interval=pc_interval)
                if df is not None:
                    df=compute_indicators(df)
                    fig=build_candlestick_chart(df,pc_ticker,show_vwap=show_vwap,show_emas=show_emas,show_bb=show_bb,show_volume=show_volume,show_rsi=show_rsi)
                    if fig:
                        st.plotly_chart(fig,use_container_width=True,key="pc_chart",config={"displaylogo":False,"displayModeBar":True})
                    else:
                        st.warning("Could not build chart.")

                    # Quote summary
                    quote=get_quick_quote(pc_ticker)
                    if quote:
                        st.markdown("##### Current Quote")
                        q1,q2,q3,q4,q5,q6=st.columns(6)
                        with q1: st.metric("Price",f"${quote['price']}",f"{quote['change']:+.2f} ({quote['change_pct']:+.2f}%)")
                        with q2: st.metric("Day Range",f"${quote['day_low']} - ${quote['day_high']}")
                        with q3: st.metric("Range Position",f"{quote['day_range_pos']:.0f}%",help="0=at low, 100=at high")
                        with q4: st.metric("Volume",f"{quote['volume']/1e6:.1f}M",f"{quote['rel_volume_pct']-100:+.0f}% vs avg")
                        with q5:
                            if quote.get("vwap"):
                                st.metric("VWAP",f"${quote['vwap']}",f"{quote['vs_vwap_pct']:+.2f}%")
                            else:
                                st.metric("VWAP","N/A")
                        with q6:
                            if pc_ticker in scored_df.index:
                                st.metric("Quant Score",f"{scored_df.loc[pc_ticker,'composite_score']:.1f}/12",scored_df.loc[pc_ticker,"overall_rating"])
                else:
                    st.error(f"Could not load chart data for {pc_ticker}.")

    # ── Section 2: Live Monitor ──
    elif pc_section=="👁 Live Monitor":
        st.markdown("#### Live Monitor")
        st.caption("Real-time-ish quotes for tickers you're watching. Use this for monitoring during market hours.")

        # Pull from saved monitor list
        if "monitor_tickers" not in st.session_state:
            # Default to portfolio tickers
            default_monitor=[h["ticker"] for h in st.session_state.portfolio_holdings] if st.session_state.portfolio_holdings else ["AAPL","NVDA","MSFT","GOOG","SPY"]
            st.session_state.monitor_tickers=default_monitor[:15]

        mon_tickers=st.multiselect(
            "Tickers to monitor (max 20)",
            sorted(scored_df.index.tolist()),
            default=[t for t in st.session_state.monitor_tickers if t in scored_df.index][:20],
            max_selections=20,
            format_func=lambda x: f"{x} -- {scored_df.loc[x,'shortName'][:30]}" if x in scored_df.index else x,
            key="mon_select"
        )
        st.session_state.monitor_tickers=mon_tickers

        if st.button("🔄 Refresh Quotes",key="mon_refresh"):
            st.cache_data.clear()
            st.rerun()

        if mon_tickers:
            with st.spinner(f"Fetching {len(mon_tickers)} quotes..."):
                quotes=get_watchlist_quotes(mon_tickers)
            if quotes:
                # Build display table
                rows=[]
                for q in quotes:
                    score_data=scored_df.loc[q["ticker"]] if q["ticker"] in scored_df.index else None
                    rows.append({
                        "Ticker": q["ticker"],
                        "Company": q["name"][:25],
                        "Price": f"${q['price']}",
                        "Change": f"{q['change']:+.2f}",
                        "% Change": q["change_pct"],
                        "Day Range %": q["day_range_pos"],
                        "Volume": f"{q['volume']/1e6:.1f}M",
                        "Rel Vol": f"{q['rel_volume_pct']:.0f}%",
                        "VWAP": f"${q['vwap']}" if q.get("vwap") else "N/A",
                        "vs VWAP": f"{q['vs_vwap_pct']:+.2f}%" if q.get("vs_vwap_pct") is not None else "N/A",
                        "Score": f"{score_data['composite_score']:.1f}" if score_data is not None else "N/A",
                        "Rating": score_data["overall_rating"] if score_data is not None else "N/A",
                    })
                mon_df=pd.DataFrame(rows)
                # Simple display - format change column inline (avoids Styler API issues)
                mon_df["% Change"]=mon_df["% Change"].apply(lambda x: f"{x:+.2f}%" if isinstance(x,(int,float)) else x)
                mon_df["Day Range %"]=mon_df["Day Range %"].apply(lambda x: f"{x:.0f}%" if isinstance(x,(int,float)) else x)
                st.dataframe(mon_df,use_container_width=True,hide_index=True,height=min(700,40+len(rows)*36))

                st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')} | Click Refresh to update.")
            else:
                st.warning("Could not fetch quotes. yfinance may be rate-limited.")
        else:
            st.info("Select tickers above to monitor.")

    # ── Section 3: Today's Movers ──
    else:
        st.markdown("#### Today's Top Movers")
        st.caption("Biggest gainers and losers from the scored universe (based on 1-month momentum as a proxy since intraday data isn't cached).")

        movers=get_market_movers(scored_df,top_n=15)
        mvc1,mvc2=st.columns(2)
        with mvc1:
            st.markdown("##### 🟢 Top Gainers")
            if movers["gainers"]:
                gn_rows=[]
                for m in movers["gainers"]:
                    gn_rows.append({
                        "Ticker": m.get("ticker") or m.get("index",""),
                        "Company": (m.get("shortName") or "")[:25],
                        "Sector": m.get("sector",""),
                        "1M %": f"{m['m_1m_pct']:+.1f}%",
                        "Score": f"{m.get('composite_score',0):.1f}",
                        "Rating": m.get("overall_rating",""),
                    })
                st.dataframe(pd.DataFrame(gn_rows),use_container_width=True,hide_index=True)
            else:
                st.info("No gainer data available.")

        with mvc2:
            st.markdown("##### 🔴 Top Losers")
            if movers["losers"]:
                ls_rows=[]
                for m in movers["losers"]:
                    ls_rows.append({
                        "Ticker": m.get("ticker") or m.get("index",""),
                        "Company": (m.get("shortName") or "")[:25],
                        "Sector": m.get("sector",""),
                        "1M %": f"{m['m_1m_pct']:+.1f}%",
                        "Score": f"{m.get('composite_score',0):.1f}",
                        "Rating": m.get("overall_rating",""),
                    })
                st.dataframe(pd.DataFrame(ls_rows),use_container_width=True,hide_index=True)
            else:
                st.info("No loser data available.")

# ═══ TAB: DOPPELGANGER ANALYSIS ════════════════════════════════════
with tab_doppel:
    st.markdown("### Doppelganger Analysis")
    st.caption("Find historical stock setups that resemble current companies. Learn from history.")

    db_stats=get_database_stats()
    with st.expander("About the Historical Database"):
        st.markdown(f"**{db_stats['total_analogs']} curated historical setups** across major inflection points.")
        st.markdown(f"Sectors covered: {', '.join(db_stats['sectors'])}")
        st.markdown("**How it works:** We build a fingerprint from valuation, growth, margins, size, and momentum. Then we find the closest historical match across bubbles, crises, and transformations. Similarity scores range 0-1 (1 = identical profile).")
        st.caption("Remember: History doesn't repeat, but it rhymes. Use these as perspective, not prophecy.")

    dop_tickers=sorted([t for t in scored_df.index if scored_df.loc[t,"sector"]!="ETF"])
    dop_sel=st.selectbox("Select a stock to analyze",dop_tickers,format_func=lambda x:f"{x} -- {scored_df.loc[x,'shortName']}" if x in scored_df.index else x,key="dop_sel")

    dc1,dc2=st.columns(2)
    with dc1:
        sector_mode=st.radio("Match mode",["Same sector (recommended)","Any sector","Specific sector"],index=0,key="dop_mode",horizontal=True)
        if sector_mode=="Specific sector":
            sector_f=st.selectbox("Which sector?",sorted(db_stats["sectors"]),key="dop_sec_pick")
        elif sector_mode=="Same sector (recommended)":
            sector_f="same"
        else:
            sector_f="any"
    with dc2: dop_tag=st.selectbox("Filter by theme (optional)",["All"]+db_stats["tags"],key="dop_tag")

    dop_dedupe=st.checkbox(
        "Deduplicate by era (recommended)",
        value=True,
        key="dop_dedupe",
        help="When enabled, only the single highest-similarity match per historical era is shown. Prevents the aggregate forecast from being skewed by over-representation of any one period (e.g., multiple dot-com stocks). Disable to see all individual matches."
    )

    if dop_sel:
        tag_f=dop_tag if dop_tag!="All" else None
        matches=find_doppelgangers(dop_sel,scored_df,top_n=5,sector_filter=sector_f,tag_filter=tag_f,dedupe_eras=dop_dedupe)

        if not matches:
            cur_sector=scored_df.loc[dop_sel,"sector"]
            if sector_mode=="Same sector (recommended)":
                st.warning(f"No historical analogs in our database match {dop_sel}'s sector ({cur_sector}). Try 'Any sector' mode or check the sector coverage below.")
                st.caption(f"Available sectors in database: {', '.join([f'{s} ({n})' for s,n in db_stats['sector_counts'].items()])}")
            else:
                st.warning("No strong matches found with current filters. Try removing filters.")
        else:
            # Show current stock summary
            cur_row=scored_df.loc[dop_sel]
            st.markdown(f"#### {dop_sel} ({cur_row.get('shortName','')}) Today")
            cur_c1,cur_c2,cur_c3,cur_c4,cur_c5=st.columns(5)
            with cur_c1: st.metric("Mkt Cap",f"${cur_row.get('marketCapB',0):.0f}B")
            with cur_c2: st.metric("P/E",f"{cur_row.get('trailingPE','N/A')}" if cur_row.get('trailingPE') else "N/A")
            with cur_c3: st.metric("P/S",f"{cur_row.get('priceToSalesTrailing12Months','N/A'):.1f}" if cur_row.get('priceToSalesTrailing12Months') else "N/A")
            with cur_c4:
                rg=cur_row.get('revenueGrowth')
                st.metric("Rev Growth",f"{rg*100:+.0f}%" if rg else "N/A")
            with cur_c5:
                m12=cur_row.get('momentum_12m')
                st.metric("12M Return",f"{m12*100:+.0f}%" if m12 else "N/A")

            st.markdown("---")
            st.markdown(f"#### Top {len(matches)} Historical Analogues")
            for i,m in enumerate(matches):
                similarity_bar_pct=int(m["similarity"]*100)
                bar_color="#22C55E" if m["similarity"]>=0.7 else "#EAB308" if m["similarity"]>=0.5 else "#F97316"
                # Get forward returns for this analog
                fwd=get_forward_returns(m["match_key"])
                fwd_label=""
                if fwd:
                    fwd_label=f" | 1Y: {fwd['1yr']:+.0f}% | 5Y: {fwd['5yr']:+.0f}%"
                with st.expander(f"{i+1}. {m['company']} {m['era']} -- Similarity: {similarity_bar_pct}%{fwd_label}",expanded=(i==0)):
                    st.markdown(f'<div style="background:#1A1F2E;padding:10px;border-radius:4px;margin-bottom:10px;"><div style="background:{bar_color};width:{similarity_bar_pct}%;height:6px;border-radius:3px;"></div></div>',unsafe_allow_html=True)

                    ma=m["data"]
                    mc1,mc2,mc3,mc4,mc5=st.columns(5)
                    with mc1: st.metric("Mkt Cap",f"${ma.get('marketCapB',0):.0f}B")
                    with mc2: st.metric("P/E",f"{ma.get('trailingPE','N/A')}")
                    with mc3: st.metric("P/S",f"{ma.get('priceToSalesTrailing12Months','N/A')}")
                    with mc4: st.metric("Rev Growth",f"{ma.get('revenueGrowth',0)*100:+.0f}%" if ma.get('revenueGrowth') else "N/A")
                    with mc5: st.metric("12M Return",f"{ma.get('momentum_12m',0)*100:+.0f}%" if ma.get('momentum_12m') else "N/A")

                    # Forward returns row
                    if fwd:
                        st.markdown("**📈 What happened next:**")
                        fc1,fc2,fc3=st.columns(3)
                        def _fmt_ret(r):
                            color="#22C55E" if r>0 else "#EF4444"
                            return f'<span style="color:{color};font-weight:700;">{r:+.0f}%</span>'
                        with fc1: st.markdown(f'1-Year: {_fmt_ret(fwd["1yr"])}',unsafe_allow_html=True)
                        with fc2: st.markdown(f'3-Year: {_fmt_ret(fwd["3yr"])}',unsafe_allow_html=True)
                        with fc3: st.markdown(f'5-Year: {_fmt_ret(fwd["5yr"])}',unsafe_allow_html=True)
                        st.caption(fwd.get("narrative",""))

                    st.markdown(f"**Context:** {m['context']}")
                    st.markdown(f"**Narrative:** {m['narrative']}")
                    st.markdown(f"**What Happened Next:** {m['outcome']}")
                    st.markdown(f"**Lesson:** {m['lesson']}")
                    st.caption(f"Tags: {', '.join(m['tags'])}")

                    # AI Narrative button (if available)
                    if is_ai_available():
                        if st.button(f"Generate AI Comparison Analysis",key=f"dop_ai_{i}"):
                            with st.spinner("AI analyzing parallels..."):
                                ai_result=generate_doppelganger_narrative(dop_sel,cur_row.to_dict(),m["company"],m["era"],m["data"],m["similarity"])
                            if "error" in ai_result:
                                st.error(ai_result["error"])
                            else:
                                st.markdown("**AI Analysis:**")
                                st.markdown(ai_result["text"])
                                st.caption(f"Powered by {ai_result.get('provider','AI')}")

            # ═══ Aggregate Forward-Looking Analysis ═══
            agg=aggregate_forward_returns(matches)
            if agg and agg["contributing_count"]>=2:
                st.markdown("---")
                st.markdown(f"### 🔮 Predictive Aggregate ({agg['contributing_count']} analogs)")
                st.caption("Similarity-weighted average of what historically happened to similar setups. Use as historical context, not financial prophecy.")

                # Top metrics
                ag1,ag2,ag3=st.columns(3)
                with ag1:
                    color1="#22C55E" if agg["weighted_1yr_pct"]>0 else "#EF4444"
                    st.markdown(f'<div style="background:#1A1F2E;padding:16px;border-radius:6px;border-left:4px solid {color1};"><div style="color:#888;font-size:0.85em;">1-Year (weighted)</div><div style="color:{color1};font-size:1.8em;font-weight:700;">{agg["weighted_1yr_pct"]:+.0f}%</div><div style="color:#666;font-size:0.8em;">Median: {agg["median_1yr_pct"]:+.0f}% | Range: {agg["worst_1yr"]:+.0f}% to {agg["best_1yr"]:+.0f}%</div></div>',unsafe_allow_html=True)
                with ag2:
                    color3="#22C55E" if agg["weighted_3yr_pct"]>0 else "#EF4444"
                    st.markdown(f'<div style="background:#1A1F2E;padding:16px;border-radius:6px;border-left:4px solid {color3};"><div style="color:#888;font-size:0.85em;">3-Year (weighted)</div><div style="color:{color3};font-size:1.8em;font-weight:700;">{agg["weighted_3yr_pct"]:+.0f}%</div><div style="color:#666;font-size:0.8em;">Median: {agg["median_3yr_pct"]:+.0f}%</div></div>',unsafe_allow_html=True)
                with ag3:
                    color5="#22C55E" if agg["weighted_5yr_pct"]>0 else "#EF4444"
                    st.markdown(f'<div style="background:#1A1F2E;padding:16px;border-radius:6px;border-left:4px solid {color5};"><div style="color:#888;font-size:0.85em;">5-Year (weighted)</div><div style="color:{color5};font-size:1.8em;font-weight:700;">{agg["weighted_5yr_pct"]:+.0f}%</div><div style="color:#666;font-size:0.8em;">Median: {agg["median_5yr_pct"]:+.0f}% | Range: {agg["worst_5yr"]:+.0f}% to {agg["best_5yr"]:+.0f}%</div></div>',unsafe_allow_html=True)

                # Aggregate projection chart
                st.markdown("##### Forward Projection")
                current_price=cur_row.get("currentPrice",0)
                if current_price>0:
                    timeline=[0,1,3,5]
                    weighted_path=[current_price,
                                   current_price*(1+agg["weighted_1yr_pct"]/100),
                                   current_price*(1+agg["weighted_3yr_pct"]/100),
                                   current_price*(1+agg["weighted_5yr_pct"]/100)]
                    best_path=[current_price,
                               current_price*(1+agg["best_1yr"]/100),
                               current_price*(1+max(c["ret_3yr"] for c in agg["contributing"])/100),
                               current_price*(1+agg["best_5yr"]/100)]
                    worst_path=[current_price,
                                current_price*(1+agg["worst_1yr"]/100),
                                current_price*(1+min(c["ret_3yr"] for c in agg["contributing"])/100),
                                current_price*(1+agg["worst_5yr"]/100)]

                    fig_proj=go.Figure()
                    # Best/worst envelope
                    fig_proj.add_trace(go.Scatter(x=timeline,y=best_path,mode="lines",line=dict(width=0),showlegend=False,hovertemplate="Best: $%{y:.2f}<extra></extra>"))
                    fig_proj.add_trace(go.Scatter(x=timeline,y=worst_path,mode="lines",line=dict(width=0),fill="tonexty",fillcolor="rgba(0,212,170,0.15)",name="Best/Worst Range",hovertemplate="Worst: $%{y:.2f}<extra></extra>"))
                    # Weighted projection
                    fig_proj.add_trace(go.Scatter(x=timeline,y=weighted_path,mode="lines+markers",line=dict(color="#00D4AA",width=3),marker=dict(size=10),name="Weighted Average",hovertemplate="Year %{x}: $%{y:.2f}<extra></extra>"))
                    # Current
                    fig_proj.add_hline(y=current_price,line_dash="dot",line_color="#666",annotation_text=f"Current: ${current_price:.2f}")

                    fig_proj.update_layout(
                        height=400,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#e0e0e0"),
                        xaxis=dict(title="Years from Now",gridcolor="#2a2f3e",tickvals=[0,1,3,5]),
                        yaxis=dict(title="Projected Price ($)",tickformat="$,.2f",gridcolor="#2a2f3e"),
                        legend=dict(orientation="h",yanchor="bottom",y=-0.2,xanchor="center",x=0.5),
                        margin=dict(l=60,r=20,t=20,b=40),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_proj,use_container_width=True,key="dop_projection")

                # Contributing breakdown
                with st.expander("Contributing Analogs Detail"):
                    contrib_rows=[]
                    for c in agg["contributing"]:
                        # Find the original match to get era_bucket
                        orig_match=next((m for m in matches if m["match_key"]==c["key"]),None)
                        bucket=orig_match["era_bucket"] if orig_match else c["era"]
                        contrib_rows.append({
                            "Company": c["company"],
                            "Era": c["era"],
                            "Era Bucket": bucket,
                            "Similarity": f"{c['similarity']*100:.0f}%",
                            "1Y Return": f"{c['ret_1yr']:+.0f}%",
                            "3Y Return": f"{c['ret_3yr']:+.0f}%",
                            "5Y Return": f"{c['ret_5yr']:+.0f}%",
                        })
                    st.dataframe(pd.DataFrame(contrib_rows),use_container_width=True,hide_index=True)
                    if agg["missing_count"]>0:
                        st.caption(f"Note: {agg['missing_count']} analog(s) had no forward return data and were excluded from the aggregate.")
                    if dop_dedupe:
                        st.caption(f"✓ Era deduplication active: only the highest-similarity match per historical period is shown.")

                st.warning("⚠️ This is descriptive of past outcomes for similar setups, not a prediction. Each stock's future depends on factors not captured in financial fingerprints (management, competition, regulation, macro). Use this as one of many inputs to your investment thesis.")

# ═══ TAB: PORTFOLIO ═══════════════════════════════════════════════
with tab_portfolio:
    st.markdown("### Portfolio Analyzer")

    # ── Saved Portfolios (Supabase) ──
    saved_portfolios=load_portfolios()
    if saved_portfolios:
        st.markdown("#### Your Saved Portfolios")
        sp_cols=st.columns([3,1,1])
        with sp_cols[0]:
            sp_options=["-- Select --"]+[f"{p['name']} ({len(p['holdings'])} holdings)" for p in saved_portfolios]
            sp_choice=st.selectbox("Load saved portfolio",sp_options,key="sp_choice")
        with sp_cols[1]:
            if sp_choice!="-- Select --" and st.button("Load",key="sp_load"):
                idx=sp_options.index(sp_choice)-1
                p=saved_portfolios[idx]
                st.session_state.portfolio_holdings=p["holdings"]
                st.session_state.current_portfolio_id=p["id"]
                st.session_state.current_portfolio_name=p["name"]
                st.success(f"Loaded: {p['name']}")
                st.rerun()
        with sp_cols[2]:
            if sp_choice!="-- Select --" and st.button("Delete",key="sp_del"):
                idx=sp_options.index(sp_choice)-1
                p=saved_portfolios[idx]
                result=delete_portfolio(p["id"])
                if "error" in result: st.error(result["error"])
                else: st.success(f"Deleted: {p['name']}");st.rerun()
        st.markdown("---")

    inp=st.radio("Input",["Manual Entry","CSV Upload (Fidelity)"],horizontal=True)
    if inp=="CSV Upload (Fidelity)":
        up=st.file_uploader("Upload CSV",type=["csv"],key="csv_upload")
        if up is not None:
            csv_key=f"csv_processed_{up.name}_{up.size}"
            if not st.session_state.get(csv_key):
                try:
                    csv_text=up.read().decode("utf-8")
                    parsed=parse_fidelity_csv(csv_text)
                    if parsed and len(parsed)>0:
                        st.session_state.portfolio_holdings=parsed
                        st.session_state[csv_key]=True
                        st.session_state.current_portfolio_id=None
                        st.session_state.current_portfolio_name=f"Imported {datetime.now().strftime('%b %d')}"
                        st.success(f"✓ Parsed {len(parsed)} holdings: {', '.join([h['ticker'] for h in parsed[:10]])}{'...' if len(parsed)>10 else ''}")
                        st.rerun()
                    else:
                        st.error("Could not parse any holdings from this CSV. Make sure it's a Fidelity export with 'Symbol' and 'Quantity' columns.")
                        with st.expander("CSV preview (first 500 chars)"):
                            st.code(csv_text[:500])
                except UnicodeDecodeError:
                    st.error("Could not decode CSV. Make sure it's UTF-8 encoded.")
                except Exception as e:
                    st.error(f"Parse error: {str(e)}")
        if st.session_state.portfolio_holdings:
            st.info(f"Currently loaded: {len(st.session_state.portfolio_holdings)} holdings. Scroll down to analyze.")
    else:
        nr=st.number_input("Holdings",1,50,min(len(st.session_state.portfolio_holdings) or 5,50),key="n_hold")
        holdings=[]
        for i in range(int(nr)):
            c1,c2,c3=st.columns([1.5,1,1])
            dt=st.session_state.portfolio_holdings[i]["ticker"] if i<len(st.session_state.portfolio_holdings) else ""
            ds=st.session_state.portfolio_holdings[i]["shares"] if i<len(st.session_state.portfolio_holdings) else 0.0
            dcb=st.session_state.portfolio_holdings[i].get("cost_basis") if i<len(st.session_state.portfolio_holdings) else None
            with c1: t=st.text_input("Ticker",value=dt,key=f"pt_{i}").upper().strip()
            with c2: s=st.number_input("Shares",value=float(ds),min_value=0.0,key=f"ps_{i}")
            with c3: cb=st.number_input("Cost ($)",value=float(dcb or 0),min_value=0.0,key=f"pc_{i}")
            if t and s>0: holdings.append({"ticker":t,"shares":s,"cost_basis":cb if cb>0 else None})
        if st.button("Analyze",key="ab"): st.session_state.portfolio_holdings=holdings;st.rerun()
    if st.session_state.portfolio_holdings:
        # ── Save to Supabase ──
        st.markdown("---")
        sv1,sv2,sv3=st.columns([2,1,1])
        with sv1:
            default_name=st.session_state.get("current_portfolio_name","Main Portfolio")
            save_name=st.text_input("Portfolio name",value=default_name,key="save_name")
        with sv2:
            current_id=st.session_state.get("current_portfolio_id")
            save_label="Update" if current_id else "Save"
            if st.button(save_label,key="save_pf",use_container_width=True):
                result=save_portfolio(save_name,st.session_state.portfolio_holdings,portfolio_id=current_id)
                if "error" in result: st.error(result["error"])
                else:
                    st.session_state.current_portfolio_id=result["portfolio_id"]
                    st.session_state.current_portfolio_name=save_name
                    st.success(f"{save_label}d!")
                    st.rerun()
        with sv3:
            if current_id and st.button("Save as New",key="save_new",use_container_width=True):
                result=save_portfolio(save_name,st.session_state.portfolio_holdings,portfolio_id=None)
                if "error" in result: st.error(result["error"])
                else:
                    st.session_state.current_portfolio_id=result["portfolio_id"]
                    st.success("Saved as new portfolio!")
                    st.rerun()

        analysis=analyze_portfolio(st.session_state.portfolio_holdings,scored_df,sector_stats)
        if "error" in analysis: st.error(analysis["error"])
        elif analysis:
            m1,m2,m3,m4,m5=st.columns(5)
            with m1: st.metric("Value",f"${analysis['total_value']:,.0f}")
            with m2: st.metric("Holdings",analysis["num_holdings"])
            with m3: st.metric("Rating",analysis["weighted_rating"])
            with m4: st.metric("Score",f"{analysis['weighted_composite']:.1f}/12")
            with m5: st.metric("Concentration",analysis["concentration_level"])
            td2=[];
            for p,t2 in analysis["factor_tilts"].items(): td2.append({"Pillar":p,"Portfolio":t2["portfolio"],"Universe":t2["universe"]})
            fig_t=go.Figure();tdf=pd.DataFrame(td2)
            fig_t.add_trace(go.Bar(name="Portfolio",x=tdf["Pillar"],y=tdf["Portfolio"],marker_color="#00D4AA"))
            fig_t.add_trace(go.Bar(name="Universe",x=tdf["Pillar"],y=tdf["Universe"],marker_color="#555"))
            fig_t.update_layout(barmode="group",yaxis=dict(range=[0,12]),height=350,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"))
            st.plotly_chart(fig_t,use_container_width=True,key="pt")

            # ═══ Portfolio Suggestions v2 (Prescriptive) ═══
            st.markdown("---")
            st.markdown("### 🎯 Actionable Recommendations")
            st.caption("Specific actions with shares, dollar amounts, and reasoning.")
            sugs=generate_suggestions_v2(analysis,scored_df,max_suggestions=12)
            if not sugs:
                st.success("Portfolio looks healthy. No specific actions needed.")
            else:
                # Group by type
                criticals=[s for s in sugs if s["type"]=="critical"]
                warnings=[s for s in sugs if s["type"]=="warning"]
                opportunities=[s for s in sugs if s["type"]=="opportunity"]
                infos=[s for s in sugs if s["type"]=="info"]

                if criticals:
                    st.markdown("##### ⚠️ Critical")
                    for sg in criticals:
                        card=format_suggestion_card(sg)
                        st.markdown(f'<div style="background:#1A1F2E;border-left:5px solid {card["color"]};padding:14px;margin-bottom:10px;border-radius:6px;"><strong style="color:{card["color"]};font-size:1.05em;">{card["icon"]} {card["title"]}</strong><br><span style="color:#fff;font-weight:600;margin-top:8px;display:inline-block;">→ {card["action"]}</span><br><span style="color:#aaa;font-size:0.9em;margin-top:4px;display:inline-block;">{card["reasoning"]}</span></div>',unsafe_allow_html=True)

                if warnings:
                    st.markdown("##### ⚠ Warnings")
                    for sg in warnings:
                        card=format_suggestion_card(sg)
                        st.markdown(f'<div style="background:#1A1F2E;border-left:5px solid {card["color"]};padding:14px;margin-bottom:10px;border-radius:6px;"><strong style="color:{card["color"]};font-size:1.05em;">{card["icon"]} {card["title"]}</strong><br><span style="color:#fff;font-weight:600;margin-top:8px;display:inline-block;">→ {card["action"]}</span><br><span style="color:#aaa;font-size:0.9em;margin-top:4px;display:inline-block;">{card["reasoning"]}</span></div>',unsafe_allow_html=True)

                if opportunities:
                    st.markdown("##### 💡 Opportunities")
                    for sg in opportunities:
                        card=format_suggestion_card(sg)
                        st.markdown(f'<div style="background:#1A1F2E;border-left:5px solid {card["color"]};padding:14px;margin-bottom:10px;border-radius:6px;"><strong style="color:{card["color"]};font-size:1.05em;">{card["icon"]} {card["title"]}</strong><br><span style="color:#fff;font-weight:600;margin-top:8px;display:inline-block;">→ {card["action"]}</span><br><span style="color:#aaa;font-size:0.9em;margin-top:4px;display:inline-block;">{card["reasoning"]}</span></div>',unsafe_allow_html=True)

                if infos:
                    st.markdown("##### ℹ Info")
                    for sg in infos:
                        card=format_suggestion_card(sg)
                        st.markdown(f'<div style="background:#1A1F2E;border-left:5px solid {card["color"]};padding:14px;margin-bottom:10px;border-radius:6px;"><strong style="color:{card["color"]};font-size:1.05em;">{card["icon"]} {card["title"]}</strong><br><span style="color:#fff;font-weight:600;margin-top:8px;display:inline-block;">→ {card["action"]}</span><br><span style="color:#aaa;font-size:0.9em;margin-top:4px;display:inline-block;">{card["reasoning"]}</span></div>',unsafe_allow_html=True)

            # AI Portfolio Optimization (if available)
            if is_ai_available():
                st.markdown("---")
                st.markdown("### 🤖 AI Portfolio Advisor")
                ai_obj=st.selectbox("Investment objective",["growth","income","balanced","defensive"],key="ai_obj")
                if st.button("Get AI Optimization",key="ai_opt"):
                    with st.spinner("AI analyzing your portfolio..."):
                        port_summary=f"Total: ${analysis['total_value']:,.0f} across {analysis['num_holdings']} positions. Top positions: " + ", ".join([f"{r['ticker']} ({r['weight']*100:.0f}%)" for _,r in analysis["holdings_df"].nlargest(5,"weight").iterrows()])
                        available=scored_df[(~scored_df.index.isin([h["ticker"] for h in st.session_state.portfolio_holdings]))&(scored_df["overall_rating"]=="Strong Buy")&(scored_df["sector"]!="ETF")].nlargest(10,"composite_score")
                        univ_summary="; ".join([f"{t}({scored_df.loc[t,'sector'][:5]},Score {scored_df.loc[t,'composite_score']:.1f})" for t in available.index[:10]])
                        ai_opt=generate_portfolio_optimization(port_summary,univ_summary,ai_obj)
                    if "error" in ai_opt:
                        st.error(ai_opt["error"])
                    else:
                        st.markdown(f"**Overall Assessment:** {ai_opt.get('overall_assessment','')}")
                        st.info(f"**Biggest Opportunity:** {ai_opt.get('biggest_opportunity','')}")
                        st.warning(f"**Biggest Risk:** {ai_opt.get('biggest_risk','')}")
                        if "recommendations" in ai_opt:
                            st.markdown("**AI Recommendations:**")
                            for r in ai_opt["recommendations"]:
                                action_colors={"BUY":"#22C55E","ADD":"#84CC16","HOLD":"#EAB308","TRIM":"#F97316","SELL":"#DC2626"}
                                ac=action_colors.get(r.get("action","HOLD"),"#666")
                                st.markdown(f'<div style="background:#1A1F2E;border-left:4px solid {ac};padding:10px;margin-bottom:6px;border-radius:4px;"><strong style="color:{ac};">{r.get("action")} {r.get("ticker")} ({r.get("suggested_allocation_pct",0):.1f}%)</strong><br><span style="color:#ccc;font-size:0.9em;">{r.get("reasoning","")}</span></div>',unsafe_allow_html=True)
                        st.caption(f"Powered by {ai_opt.get('provider','AI')}")
            else:
                st.caption("💡 Configure AI provider (Gemini free tier) in .streamlit/secrets.toml for AI-powered portfolio optimization.")

    # ═══ Watchlist (expandable section) ═══
    st.markdown("---")
    with st.expander("⭐ Watchlist - Stocks You're Researching"):
        st.caption("Track stocks you're researching but don't own yet. Separate from your portfolio.")
        wl=load_watchlist()

        wlc1,wlc2=st.columns([3,1])
        with wlc1:
            wl_options=[""]+sorted([t for t in scored_df.index.tolist() if t not in [w["ticker"] for w in wl]])
            wl_new=st.selectbox(
                "Add ticker to watchlist",
                wl_options,
                format_func=lambda x: f"{x} -- {scored_df.loc[x,'shortName']}" if x and x in scored_df.index else x,
                key="wl_add_select"
            )
        with wlc2:
            st.markdown("&nbsp;")  # spacer
            if wl_new and st.button("➕ Add to Watchlist",key="wl_add_btn",use_container_width=True):
                add_to_watchlist(wl_new)
                st.success(f"Added {wl_new}")
                st.rerun()

        if not wl:
            st.info("Watchlist is empty. Add tickers above.")
        else:
            st.markdown(f"**{len(wl)} stocks watched**")
            wl_rows=[]
            for entry in wl:
                t3=entry["ticker"]
                if t3 in scored_df.index:
                    r=scored_df.loc[t3]
                    wl_rows.append({
                        "Ticker": t3,
                        "Company": r.get("shortName","")[:30],
                        "Sector": r.get("sector",""),
                        "Price": f"${r.get('currentPrice',0):.2f}",
                        "Score": f"{r.get('composite_score',0):.1f}",
                        "Rating": r.get("overall_rating","N/A"),
                        "1M": f"{r.get('momentum_1m',0)*100:+.1f}%" if pd.notna(r.get('momentum_1m')) else "N/A",
                        "12M": f"{r.get('momentum_12m',0)*100:+.1f}%" if pd.notna(r.get('momentum_12m')) else "N/A",
                    })
            if wl_rows:
                st.dataframe(pd.DataFrame(wl_rows),use_container_width=True,hide_index=True)

            st.markdown("**Remove from watchlist:**")
            n_cols=min(len(wl),5)
            rm_cols=st.columns(n_cols)
            for i,entry in enumerate(wl):
                with rm_cols[i%n_cols]:
                    if st.button(f"❌ {entry['ticker']}",key=f"wl_rm_{entry['ticker']}",use_container_width=True):
                        remove_from_watchlist(entry["ticker"])
                        st.rerun()

# ═══ TAB 8: MONTE CARLO v2 ════════════════════════════════════════
with tab_mc:
    st.markdown("### Monte Carlo Simulation")
    st.caption("Geometric Brownian Motion with mean reversion, return caps, and macro scenario adjustment.")
    if not st.session_state.portfolio_holdings: st.info("Enter holdings in Portfolio tab first.")
    else:
        analysis=analyze_portfolio(st.session_state.portfolio_holdings,scored_df,sector_stats)
        if "error" not in analysis and analysis:
            mc1,mc2,mc3=st.columns(3)
            with mc1: ns=st.selectbox("Sims",[1000,5000,10000],index=1)
            with mc2: nd=st.selectbox("Horizon",[63,126,252],index=2,format_func=lambda x:{63:"3 Months",126:"6 Months",252:"1 Year"}[x])
            with mc3: scenario=st.selectbox("Scenario",["Blended","Bull","Base","Bear"],index=0,help="Bull: +8% drift (expansion). Base: neutral. Bear: -12% drift (recession). Blended: 25/50/25 weighted avg.")
            if st.button("Run Simulation",key="mcr"):
                hdf=analysis.get("holdings_df",pd.DataFrame())
                with st.spinner("Simulating..."):
                    mc=run_monte_carlo(hdf,scored_df,n_simulations=ns,n_days=nd,scenario=scenario)
                if mc:
                    r1,r2,r3,r4,r5=st.columns(5)
                    with r1: st.metric("Exp. Return",f"{mc['expected_annual_return']}%")
                    with r2: st.metric("Volatility",f"{mc['estimated_annual_vol']}%")
                    with r3: st.metric("P(Gain)",f"{mc['prob_positive']}%")
                    with r4: st.metric("P(Loss>20%)",f"{mc['prob_loss_20']}%")
                    with r5: st.metric("Scenario",mc["scenario"])
                    # Fan chart
                    paths=mc["path_percentiles"];days=list(range(1,nd+1))
                    fig_f=go.Figure()
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p95"].tolist(),mode="lines",line=dict(width=0),showlegend=False))
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p5"].tolist(),mode="lines",line=dict(width=0),fill="tonexty",fillcolor="rgba(0,212,170,0.1)",name="5-95th"))
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p75"].tolist(),mode="lines",line=dict(width=0),showlegend=False))
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p25"].tolist(),mode="lines",line=dict(width=0),fill="tonexty",fillcolor="rgba(0,212,170,0.25)",name="25-75th"))
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p50"].tolist(),mode="lines",line=dict(color="#00D4AA",width=2),name="Median"))
                    fig_f.add_hline(y=mc["total_value"],line_dash="dash",line_color="#666",annotation_text="Starting Value")
                    fig_f.update_layout(yaxis=dict(title="Value ($)",tickformat="$,.0f"),xaxis=dict(title="Trading Days"),height=450,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"))
                    st.plotly_chart(fig_f,use_container_width=True,key="mcf")
                    # Outcome probabilities
                    st.markdown("### Outcome Probabilities")
                    prob_df=pd.DataFrame({"Outcome":["Gain 50%+","Gain 20%+","Any Gain","Loss <10%","Loss 10-20%","Loss >20%"],
                        "Probability":[f"{mc['prob_gain_50']}%",f"{mc['prob_gain_20']}%",f"{mc['prob_positive']}%",
                        f"{max(0,100-mc['prob_positive']-mc['prob_loss_10']):.1f}%",f"{max(0,mc['prob_loss_10']-mc['prob_loss_20']):.1f}%",f"{mc['prob_loss_20']}%"]})
                    st.dataframe(prob_df,use_container_width=True,hide_index=True)
                    # VaR percentiles
                    st.markdown("### Value at Risk")
                    var_df=pd.DataFrame({"Percentile":["5th (worst)","25th","50th (median)","75th","95th (best)"],
                        "Value":[f"${mc['percentiles']['p5']:,.0f}",f"${mc['percentiles']['p25']:,.0f}",f"${mc['percentiles']['p50']:,.0f}",
                        f"${mc['percentiles']['p75']:,.0f}",f"${mc['percentiles']['p95']:,.0f}"],
                        "Return":[f"{(mc['percentiles']['p5']/mc['total_value']-1)*100:+.1f}%",f"{(mc['percentiles']['p25']/mc['total_value']-1)*100:+.1f}%",
                        f"{(mc['percentiles']['p50']/mc['total_value']-1)*100:+.1f}%",f"{(mc['percentiles']['p75']/mc['total_value']-1)*100:+.1f}%",
                        f"{(mc['percentiles']['p95']/mc['total_value']-1)*100:+.1f}%"]})
                    st.dataframe(var_df,use_container_width=True,hide_index=True)
                    # Per-holding assumptions (transparency)
                    with st.expander("Model Assumptions (per holding)"):
                        if mc.get("holding_details"):
                            ha_df=pd.DataFrame(mc["holding_details"])
                            ha_df.columns=["Ticker","Exp. Return %","Est. Vol %","Weight %"]
                            st.dataframe(ha_df,use_container_width=True,hide_index=True)
                        mp=mc.get("model_params",{})
                        st.caption(f"Mean reversion: {mp.get('mean_reversion_weight',0)*100:.0f}% long-term / {(1-mp.get('mean_reversion_weight',0))*100:.0f}% trailing")
                        st.caption(f"Return cap: {mp.get('max_annual_return_cap',0)*100:.0f}% max per holding")
                        st.caption(f"Long-term equity premium: {mp.get('long_term_premium',0)*100:.0f}%")
                        st.caption(f"Avg cross-correlation: {mp.get('avg_correlation',0):.2f}")
                        st.caption(f"Scenario adjustment: {mp.get('scenario_adjustment',0):+.1f}%")

# ═══ TAB: ETF CENTER ══════════════════════════════════════════════
with tab_etfs:
    st.markdown("### ETF Center")
    st.caption("Build portfolios with ETFs, compare options, and find the right ETF for your sector or theme tilt.")

    etf_section=st.radio("",["📊 Portfolio Builder","🔍 ETF Comparison","🗺️ Sector & Theme Map"],horizontal=True,key="etf_section",label_visibility="collapsed")
    st.markdown("---")

    raw_cache_data=load_raw_cache()

    # ── Section 1: Portfolio Builder ──
    if etf_section=="📊 Portfolio Builder":
        st.markdown("#### Portfolio Builder")
        st.caption("Pre-built ETF allocations across risk profiles. Inspired by Motley Fool's Cautious/Moderate/Aggressive framework.")

        pb1,pb2=st.columns([1,1])
        with pb1: pb_template=st.selectbox("Risk Profile",list_templates(),key="pb_template")
        with pb2: pb_amount=st.number_input("Total Investment ($)",min_value=1000,max_value=10000000,value=100000,step=10000,key="pb_amount")

        result=calculate_template_metrics(pb_template,pb_amount)
        if result:
            tmpl=result["template"]
            pmA,pmB,pmC=st.columns(3)
            with pmA: st.metric("Risk Score",f"{tmpl['risk_score']}/10")
            with pmB: st.metric("Expected Return",tmpl["expected_annual_return"])
            with pmC: st.metric("Max Drawdown Est.",tmpl["max_drawdown_estimate"])

            st.info(tmpl["description"])

            # Allocation table
            alloc_df=pd.DataFrame(result["rows"])
            alloc_df["Amount"]=alloc_df["Amount"].apply(lambda x: f"${x:,.0f}")
            alloc_df["Weight %"]=alloc_df["Weight %"].apply(lambda x: f"{x}%")
            st.dataframe(alloc_df,use_container_width=True,hide_index=True)

            # Donut chart
            chart_data=pd.DataFrame(result["rows"])
            fig_alloc=go.Figure(go.Pie(
                labels=chart_data["Category"],
                values=chart_data["Weight %"] if "Weight %" not in chart_data.columns or chart_data["Weight %"].dtype!=object else [r["weight"] for r in tmpl["allocations"]],
                hole=0.5,
                marker=dict(colors=["#00D4AA","#00A3FF","#A855F7","#FBBF24","#F97316","#EF4444","#22C55E","#6366F1"]),
                textinfo="label+percent",
            ))
            fig_alloc.update_layout(height=400,paper_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),margin=dict(l=20,r=20,t=20,b=20),showlegend=False)
            st.plotly_chart(fig_alloc,use_container_width=True,key="pb_donut")

            with st.expander("How to use this allocation"):
                st.markdown(f"""
                **Implementation steps:**
                1. Open a brokerage account if you don't have one (Fidelity, Schwab, Vanguard recommended for low fees).
                2. For each row above, place a buy order for the listed ETF using the dollar amount shown.
                3. Rebalance quarterly or when any position drifts more than 5% from target.
                4. The "Alternative" column shows substitute ETFs from different providers if your broker doesn't offer the primary.

                **Notes:**
                - Expected returns are based on historical averages and are not guaranteed.
                - Max drawdown estimates reflect what historically happens in market crashes.
                - Tax-efficient placement: hold bonds/REITs in retirement accounts (IRA, 401k) and equities in taxable accounts when possible.
                - This is informational only, not financial advice.
                """)

    # ── Section 2: ETF Comparison ──
    elif etf_section=="🔍 ETF Comparison":
        st.markdown("#### ETF Comparison Tool")
        st.caption("Compare 2-5 ETFs side-by-side: expense ratios, returns across timeframes, AUM, yield, and beta.")

        etf_universe=get_etf_universe(raw_cache_data)
        if not etf_universe:
            st.warning("No ETF data in cache. Run build_cache.py to populate.")
        else:
            cmp_etfs=st.multiselect(
                "Select 2-5 ETFs",
                etf_universe,
                default=etf_universe[:3] if len(etf_universe)>=3 else etf_universe,
                max_selections=5,
                format_func=lambda x: f"{x} -- {raw_cache_data.get(x,{}).get('shortName','')[:40]}",
                key="etf_cmp"
            )

            if len(cmp_etfs)>=2:
                cmp_df=compare_etfs(cmp_etfs,raw_cache_data)
                if cmp_df is not None and not cmp_df.empty:
                    # Format the dataframe for display
                    disp_df=cmp_df.copy()
                    disp_df["Expense Ratio"]=disp_df["Expense Ratio"].apply(lambda x: f"{x*100:.2f}%" if pd.notna(x) and x else "N/A")
                    disp_df["AUM ($B)"]=disp_df["AUM ($B)"].apply(lambda x: f"${x:.1f}B" if x>0 else "N/A")
                    disp_df["Yield %"]=disp_df["Yield %"].apply(lambda x: f"{x:.2f}%" if x>0 else "N/A")
                    for col in ["1M %","3M %","6M %","12M %","YTD %"]:
                        disp_df[col]=disp_df[col].apply(lambda x: f"{x:+.1f}%")
                    disp_df["Beta (3Y)"]=disp_df["Beta (3Y)"].apply(lambda x: f"{x:.2f}" if pd.notna(x) and x else "N/A")
                    disp_df["Price"]=disp_df["Price"].apply(lambda x: f"${x:.2f}" if x>0 else "N/A")
                    st.dataframe(disp_df,use_container_width=True,hide_index=True)

                    # Returns visualization
                    st.markdown("##### Returns Comparison")
                    ret_data=[]
                    for _,row in cmp_df.iterrows():
                        for period in ["1M %","3M %","6M %","12M %","YTD %"]:
                            ret_data.append({"ETF":row["Ticker"],"Period":period.replace(" %",""),"Return":row[period]})
                    ret_df=pd.DataFrame(ret_data)
                    fig_ret=px.bar(ret_df,x="Period",y="Return",color="ETF",barmode="group",
                        color_discrete_sequence=["#00D4AA","#00A3FF","#A855F7","#FBBF24","#F97316"])
                    fig_ret.update_layout(height=400,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),yaxis=dict(title="Return %",gridcolor="#2a2f3e"),xaxis=dict(gridcolor="#2a2f3e"))
                    st.plotly_chart(fig_ret,use_container_width=True,key="etf_cmp_returns")

                    with st.expander("Comparison guide"):
                        st.markdown("""
                        **What to look for:**
                        - **Lower expense ratio** is better (saves money long-term).
                        - **Higher AUM** means more liquidity, tighter bid/ask spreads.
                        - **Yield** matters for income-focused investors.
                        - **Returns** show recent performance, but past performance doesn't predict future.
                        - **Beta** measures volatility vs. the market (1.0 = market, >1 more volatile, <1 less).

                        **Common comparisons:**
                        - VTI vs ITOT vs SPTM: Three near-identical broad market ETFs. Pick the one with lowest expense ratio at your broker.
                        - VOO vs IVV vs SPY: Three S&P 500 ETFs. SPY has highest liquidity for trading; VOO/IVV are best for buy-and-hold.
                        - QQQ vs QQQM: QQQM is cheaper expense ratio but slightly less liquid.
                        """)
            else:
                st.info("Select at least 2 ETFs to compare.")

    # ── Section 3: Sector & Theme Map ──
    else:
        st.markdown("#### Sector & Theme ETF Map")
        st.caption("Quick reference for which ETF to use when tilting your portfolio toward a specific sector or theme.")

        st.markdown("##### Sector ETFs")
        sector_map=get_sector_etf_map()
        sm_rows=[]
        for s in sector_map:
            sm_rows.append({
                "Sector": s["sector"],
                "Primary ETF": s["ticker"],
                "Alternative": s["alternative"] or "",
                "Use Case": s["use_case"],
            })
        st.dataframe(pd.DataFrame(sm_rows),use_container_width=True,hide_index=True)

        st.markdown("---")
        st.markdown("##### Thematic ETFs")
        theme_map=get_theme_etf_map()
        tm_rows=[]
        for t in theme_map:
            tm_rows.append({
                "Theme": t["theme"],
                "Primary ETF": t["ticker"],
                "Alternative": t["alternative"] or "",
                "Use Case": t["use_case"],
            })
        st.dataframe(pd.DataFrame(tm_rows),use_container_width=True,hide_index=True)

        with st.expander("How to use sector and theme tilts"):
            st.markdown("""
            **Sector tilting** means deviating from market-cap-weighted exposure to bet on a specific sector.

            **Example:** Standard S&P 500 has ~30% in Technology. If you believe tech will outperform, you might:
            1. Hold VTI as your core (40% of portfolio).
            2. Add 10-15% in XLK to boost tech exposure to ~35-40% of portfolio.

            **Thematic ETFs** are concentrated bets on long-term trends:
            - Higher conviction needed (these can be volatile)
            - Generally allocate 2-5% per theme, max 10-15% combined
            - Examples: AI (BAI), cybersecurity (CIBR), space (ARKX), nuclear (NLR)

            **Risk:** Sector and theme ETFs reduce diversification. The narrower the focus, the higher the volatility and the more your returns depend on being right about a specific narrative.
            """)

# ═══ TAB: HELP & GLOSSARY ═══════════════════════════════════════════
with tab_help:
    help_section=st.radio(
        "Topic",
        ["Getting Started","Best Practices","5-Pillar Methodology","Rating System","Fair Value","Buy Point","Pro Charts","ETF Center","Swing Trader","Doppelganger","Monte Carlo","PGI","Glossary","Data Sources","Disclaimer"],
        horizontal=True,
        key="help_section"
    )
    st.markdown("---")
    if help_section=="Getting Started":
        st.markdown("# Getting Started")
        st.markdown(GETTING_STARTED)
    elif help_section=="Best Practices":
        st.markdown("# Best Practices")
        st.markdown(BEST_PRACTICES)
    elif help_section=="5-Pillar Methodology":
        st.markdown("# 5-Pillar Quant Methodology")
        st.markdown(PILLAR_METHODOLOGY)
    elif help_section=="Rating System":
        st.markdown("# Rating System")
        st.markdown(RATING_SYSTEM)
    elif help_section=="Fair Value":
        st.markdown("# Fair Value Analysis")
        st.markdown(FAIR_VALUE)
    elif help_section=="Buy Point":
        st.markdown("# Buy Point Analysis")
        st.markdown(BUY_POINT)
    elif help_section=="Pro Charts":
        st.markdown("# Pro Charts")
        st.markdown(PRO_CHARTS)
    elif help_section=="ETF Center":
        st.markdown("# ETF Center")
        st.markdown(ETF_CENTER)
    elif help_section=="Swing Trader":
        st.markdown("# IBD-Inspired Swing Trader")
        st.markdown(SWING_TRADER)
    elif help_section=="Doppelganger":
        st.markdown("# Doppelganger Analysis")
        st.markdown(DOPPELGANGER)
    elif help_section=="Monte Carlo":
        st.markdown("# Monte Carlo Simulation")
        st.markdown(MONTE_CARLO)
    elif help_section=="PGI":
        st.markdown("# Potential Growth Indicator (PGI)")
        st.markdown(PGI)
    elif help_section=="Glossary":
        st.markdown("# Glossary of Terms")
        gloss_search=st.text_input("Search glossary",key="gloss_search",placeholder="e.g. PEG, ROE, RSI...")
        filtered=GLOSSARY
        if gloss_search:
            q=gloss_search.lower().strip()
            filtered=[g for g in GLOSSARY if q in g["term"].lower() or q in g["definition"].lower()]
        if not filtered:
            st.info("No matches. Try a different term.")
        else:
            st.caption(f"Showing {len(filtered)} of {len(GLOSSARY)} terms.")
            for g in filtered:
                st.markdown(f"**{g['term']}** -- {g['definition']}")
    elif help_section=="Data Sources":
        st.markdown("# Data Sources & Limitations")
        st.markdown(DATA_SOURCES)
    elif help_section=="Disclaimer":
        st.markdown("# Disclaimer")
        st.markdown(DISCLAIMER)

st.markdown("---")
st.caption(f"Quant Strategy Dashboard Pro v3.8.4 | AI: {'✓ '+get_provider_status()['provider'] if is_ai_available() else 'Not configured'} | Not financial advice")
