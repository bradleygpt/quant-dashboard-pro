"""
Quantitative Strategy Dashboard Pro v3.3
12 tabs: Macro Economics added, Fair Value & Buy Point in screeners
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
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
from thesis import get_thesis_results, is_correlation_data_available
from fairvalue import compute_fair_value
from sentiment import fetch_index_data, fetch_vix_data, fetch_buffett_indicator, compute_market_breadth, compute_fear_greed, COMING_SOON_INDICATORS
from advanced_screener import apply_advanced_filters, compute_fair_values_batch, PRESET_SCREENS, FILTERABLE_METRICS
from etf_screener import load_etf_data, get_etf_categories, filter_etfs, get_etf_detail
from buy_point import compute_buy_point, compute_buy_points_batch
from macro import get_macro_summary, get_fed_rate_outlook, fetch_economic_calendar, fetch_yield_curve

st.set_page_config(page_title="Quant Dashboard Pro", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.main-header{font-size:1.8em;font-weight:800;background:linear-gradient(90deg,#00D4AA,#00A3FF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:0}
.sub-header{color:#888;font-size:0.95em;margin-top:-8px}
</style>""", unsafe_allow_html=True)

for k,v in [("scored_df",None),("raw_data",None),("selected_ticker",None),("compare_tickers",[]),("weights",DEFAULT_PILLAR_WEIGHTS.copy()),("sector_relative",True),("portfolio_holdings",[])]:
    if k not in st.session_state: st.session_state[k]=v

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

tabs=st.tabs(["Macro Economy","Market Sentiment","Screener","Advanced Screener","Sector Overview","Stock Detail","Portfolio","Monte Carlo","Thesis Engine","ETF Screener","Watchlist","Compare"])
tab_macro,tab_sentiment,tab_screener,tab_advanced,tab_sectors,tab_detail,tab_portfolio,tab_mc,tab_thesis,tab_etfs,tab_watchlist,tab_compare=tabs

@st.cache_data(ttl=43200,show_spinner=False)
def load_and_score(mcap,wt,sr):
    w=dict(zip(DEFAULT_PILLAR_WEIGHTS.keys(),wt));tickers=get_broad_universe(mcap)
    progress=st.progress(0,text="Loading...");raw=fetch_universe_data(tickers,mcap,lambda p,m:progress.progress(p,text=m));progress.empty()
    scored=score_universe(raw,w,sector_relative=sr);ss=get_sector_stats(scored) if not scored.empty else {}
    return raw,scored,ss

try: raw_data,scored_df,sector_stats=load_and_score(market_cap_floor,tuple(st.session_state.weights.values()),st.session_state.sector_relative)
except Exception as e: st.error(f"Error: {e}");st.stop()
if scored_df is None or scored_df.empty: st.warning("No data.");st.stop()

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
    if index_data:
        idf=pd.DataFrame(index_data);dc=["name","current_price","all_time_high","distance_from_ath_pct","change_1d_pct","change_5d_pct","change_1m_pct","change_ytd_pct"]
        st.dataframe(idf[dc].rename(columns={"name":"Asset","current_price":"Price","all_time_high":"ATH","distance_from_ath_pct":"From ATH %","change_1d_pct":"1D%","change_5d_pct":"5D%","change_1m_pct":"1M%","change_ytd_pct":"YTD%"}),use_container_width=True,hide_index=True)
    with st.expander("Coming Soon"):
        for ind in COMING_SOON_INDICATORS:
            st.markdown(f"**{ind['name']}** -- *{ind.get('status','Planned')}*");st.caption(ind["description"])

# ═══ TAB 3: SCREENER ══════════════════════════════════════════════
with tab_screener:
    c1,c2,c3=st.columns(3)
    with c1: sel_sec=st.selectbox("Sector",["All"]+sorted(scored_df["sector"].dropna().unique().tolist()))
    with c2: sel_rat=st.selectbox("Rating",["All","Strong Buy","Buy","Hold","Sell","Strong Sell"])
    with c3: top_n=st.selectbox("Show Top",[50,100,250,500],index=3)
    filtered=get_top_stocks(scored_df,top_n,sel_sec,sel_rat)
    if not filtered.empty:
        s1,s2,s3,s4,s5,s6=st.columns(6)
        with s1: st.metric("Universe",f"{len(scored_df):,}")
        with s2: st.metric("Strong Buys",len(scored_df[scored_df["overall_rating"]=="Strong Buy"]))
        with s3: st.metric("Buys",len(scored_df[scored_df["overall_rating"]=="Buy"]))
        with s4: st.metric("Holds",len(scored_df[scored_df["overall_rating"]=="Hold"]))
        with s5: st.metric("Sells",len(scored_df[scored_df["overall_rating"]=="Sell"]))
        with s6: st.metric("Strong Sells",len(scored_df[scored_df["overall_rating"]=="Strong Sell"]))
        dc=["shortName","sector","marketCapB","currentPrice"]
        for p in PILLAR_METRICS: dc.append(f"{p}_grade")
        dc+=["composite_score","overall_rating"]
        dd=filtered[dc].copy();dd.columns=["Company","Sector","Mkt Cap ($B)","Price","Valuation","Growth","Profit","Momentum","EPS Rev","Score","Rating"]
        st.dataframe(dd,use_container_width=True,height=700)

# ═══ TAB 4: ADVANCED SCREENER ═════════════════════════════════════
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

# ═══ TAB 5: SECTOR OVERVIEW ═══════════════════════════════════════
with tab_sectors:
    st.markdown("### Sector Overview")
    overview=get_sector_overview(scored_df)
    if not overview.empty:
        rc=["Rank","Sector","Stocks","composite_avg","Strong Buy","Buy","Hold","Sell","Strong Sell"]
        for p in PILLAR_METRICS: rc.append(f"{p}_grade")
        rc+=["best_stock","worst_stock"];ac=[c for c in rc if c in overview.columns]
        rn2={"composite_avg":"Avg Score","best_stock":"Best","worst_stock":"Worst"}
        for p in PILLAR_METRICS: rn2[f"{p}_grade"]={"Valuation":"Val","Growth":"Grw","Profitability":"Prof","Momentum":"Mom","EPS Revisions":"EPS"}.get(p,p)
        st.dataframe(overview[ac].rename(columns=rn2),use_container_width=True,hide_index=True)
        fig_s=px.bar(overview,x="Sector",y="composite_avg",color="composite_avg",color_continuous_scale=["#D32F2F","#FFC107","#00C805"],range_color=[4,9])
        fig_s.update_layout(yaxis=dict(range=[0,12],title="Avg Score"),height=400,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),coloraxis_showscale=False)
        st.plotly_chart(fig_s,use_container_width=True,key="sec_bar")
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

# ═══ TAB 7: PORTFOLIO ═════════════════════════════════════════════
with tab_portfolio:
    st.markdown("### Portfolio Analyzer")
    inp=st.radio("Input",["Manual Entry","CSV Upload (Fidelity)"],horizontal=True)
    if inp=="CSV Upload (Fidelity)":
        up=st.file_uploader("Upload CSV",type=["csv"])
        if up:
            parsed=parse_fidelity_csv(up.read().decode("utf-8"))
            if parsed: st.session_state.portfolio_holdings=parsed;st.success(f"Parsed {len(parsed)}")
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
        if st.button("Analyze",key="ab"): st.session_state.portfolio_holdings=holdings
    if st.session_state.portfolio_holdings:
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
            sugs=generate_suggestions(analysis,scored_df)
            if sugs:
                for sg in sugs:
                    icon={"warning":"⚠️","info":"ℹ️","opportunity":"✅"}[sg["type"]]
                    st.markdown(f"{icon} **{sg['title']}**");st.caption(sg["detail"])

# ═══ TAB 8: MONTE CARLO ══════════════════════════════════════════
with tab_mc:
    st.markdown("### Monte Carlo Simulation")
    if not st.session_state.portfolio_holdings: st.info("Enter holdings in Portfolio tab first.")
    else:
        analysis=analyze_portfolio(st.session_state.portfolio_holdings,scored_df,sector_stats)
        if "error" not in analysis and analysis:
            mc1,mc2=st.columns(2)
            with mc1: ns=st.selectbox("Sims",[1000,5000,10000],index=1)
            with mc2: nd=st.selectbox("Horizon",[63,126,252],index=2,format_func=lambda x:{63:"3Mo",126:"6Mo",252:"1Yr"}[x])
            if st.button("Run",key="mcr"):
                hdf=analysis.get("holdings_df",pd.DataFrame())
                with st.spinner("Simulating..."):
                    mc=run_monte_carlo(hdf,scored_df,n_simulations=ns,n_days=nd)
                if mc:
                    r1,r2,r3,r4=st.columns(4)
                    with r1: st.metric("Return",f"{mc['expected_annual_return']}%")
                    with r2: st.metric("Vol",f"{mc['estimated_annual_vol']}%")
                    with r3: st.metric("P(Gain)",f"{mc['prob_positive']}%")
                    with r4: st.metric("P(Loss>20%)",f"{mc['prob_loss_20']}%")
                    paths=mc["path_percentiles"];days=list(range(1,nd+1))
                    fig_f=go.Figure()
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p95"].tolist(),mode="lines",line=dict(width=0),showlegend=False))
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p5"].tolist(),mode="lines",line=dict(width=0),fill="tonexty",fillcolor="rgba(0,212,170,0.1)",name="5-95th"))
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p75"].tolist(),mode="lines",line=dict(width=0),showlegend=False))
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p25"].tolist(),mode="lines",line=dict(width=0),fill="tonexty",fillcolor="rgba(0,212,170,0.25)",name="25-75th"))
                    fig_f.add_trace(go.Scatter(x=days,y=paths["p50"].tolist(),mode="lines",line=dict(color="#00D4AA",width=2),name="Median"))
                    fig_f.add_hline(y=mc["total_value"],line_dash="dash",line_color="#666")
                    fig_f.update_layout(yaxis=dict(title="Value ($)",tickformat="$,.0f"),height=450,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"))
                    st.plotly_chart(fig_f,use_container_width=True,key="mcf")

# ═══ TAB 9: THESIS ENGINE ════════════════════════════════════════
with tab_thesis:
    st.markdown("### Investment Thesis Engine")
    if not is_correlation_data_available():
        st.warning("Correlation data not found. Run build_correlations.py locally.")
    else:
        from thesis import get_factor_documentation, analyze_portfolio_impact
        with st.expander("Factor Guide"):
            docs=get_factor_documentation()
            for doc in docs:
                st.markdown(f"**{doc['name']}**");st.caption(doc["description"])
                st.markdown(f"Try: *\"{doc['examples'][0]}\"*");st.markdown("---")
        thesis_input=st.text_area("Your thesis",placeholder="e.g., I think oil prices will increase by 20%",height=100,key="thesis_input")
        if thesis_input:
            results=get_thesis_results(thesis_input,scored_df)
            if not results["matched"]: st.warning(results.get("message","No match."))
            else:
                st.info(f"**{results['factor_name']}** going **{results['direction']}**")
                if st.session_state.portfolio_holdings:
                    impact=analyze_portfolio_impact(results["factor_key"],results["direction"],st.session_state.portfolio_holdings,scored_df)
                    if impact:
                        st.markdown("### Portfolio Impact")
                        for h in impact:
                            c1,c2,c3,c4,c5=st.columns([1.2,2.5,1.2,1,1.5])
                            with c1: st.markdown(f"**{h['ticker']}**")
                            with c2: st.markdown(h["name"])
                            with c3: st.markdown(f"${h['market_value']:,.0f}")
                            with c4: st.markdown(f"{h['correlation']:+.3f}" if h["correlation"] else "N/A")
                            with c5: st.markdown(f'<span style="color:{h["impact_color"]};font-weight:700;">{h["impact"]}</span>',unsafe_allow_html=True)
                if not results["bullish_top_rated"].empty:
                    st.markdown("### Highest Conviction")
                    tc=["shortName","sector","correlation","composite_score","overall_rating"];ac2=[c for c in tc if c in results["bullish_top_rated"].columns]
                    st.dataframe(results["bullish_top_rated"][ac2].rename(columns={"shortName":"Company","correlation":"Corr","composite_score":"Score","overall_rating":"Rating"}),use_container_width=True)
                st.markdown(f"### Positively Correlated ({len(results['bullish_all'])})")
                if not results["bullish_all"].empty:
                    bc=["shortName","sector","correlation","composite_score","overall_rating"];ac3=[c for c in bc if c in results["bullish_all"].columns]
                    st.dataframe(results["bullish_all"][ac3].rename(columns={"shortName":"Company","correlation":"Corr","composite_score":"Score","overall_rating":"Rating"}),use_container_width=True,height=400)

# ═══ TAB 10: ETF SCREENER ════════════════════════════════════════
with tab_etfs:
    st.markdown("### ETF Screener")
    etf_df=load_etf_data()
    if etf_df.empty: st.info("No ETF data. Re-run build_cache.py.")
    else:
        st.metric("ETFs",len(etf_df))
        ec1,ec2,ec3=st.columns(3)
        with ec1: etf_cat=st.selectbox("Category",["All"]+get_etf_categories(etf_df),key="etf_cat")
        with ec2: etf_sort=st.selectbox("Sort",["momentum_score","momentum_1m","momentum_3m","momentum_12m"],key="etf_sort",format_func=lambda x:{"momentum_score":"Score","momentum_1m":"1M","momentum_3m":"3M","momentum_12m":"12M"}.get(x,x))
        with ec3: max_er=st.slider("Max Expense %",0.0,2.0,2.0,0.05,key="etf_er")
        fe=filter_etfs(etf_df,category=etf_cat if etf_cat!="All" else None,max_expense_ratio=max_er,sort_by=etf_sort)
        if not fe.empty:
            dcols=["shortName","industry","currentPrice","aum_b","momentum_1m","momentum_3m","momentum_6m","momentum_12m"]
            avail=[c for c in dcols if c in fe.columns];ed=fe[avail].copy()
            for mc in ["momentum_1m","momentum_3m","momentum_6m","momentum_12m"]:
                if mc in ed.columns: ed[mc]=pd.to_numeric(ed[mc],errors="coerce").apply(lambda x:f"{x*100:+.1f}%" if pd.notna(x) else "N/A")
            ed=ed.rename(columns={"shortName":"Name","industry":"Category","currentPrice":"Price","aum_b":"AUM ($B)","momentum_1m":"1M","momentum_3m":"3M","momentum_6m":"6M","momentum_12m":"12M"})
            st.dataframe(ed,use_container_width=True,height=500)
        st.markdown("---")
        if not etf_df.empty:
            etf_sel=st.selectbox("ETF Detail",etf_df.index.tolist(),format_func=lambda x:f"{x} -- {etf_df.loc[x,'shortName']}" if x in etf_df.index else x,key="etf_det")
            if etf_sel:
                edt=get_etf_detail(etf_sel,etf_df)
                if edt:
                    e1,e2,e3,e4=st.columns(4)
                    with e1: st.metric("Price",f"${edt['price']:.2f}" if edt['price'] else "N/A")
                    with e2: st.metric("AUM",f"${edt['aum_b']:.1f}B" if edt['aum_b'] else "N/A")
                    with e3: st.metric("Expense",f"{edt['expense_ratio']*100:.2f}%" if edt['expense_ratio'] else "N/A")
                    with e4: st.markdown(f"**{edt['category']}**")
                    mom=edt["momentum_summary"];mc1,mc2,mc3,mc4,mc5,mc6=st.columns(6)
                    with mc1: st.metric("1M",mom["1 Month"])
                    with mc2: st.metric("3M",mom["3 Month"])
                    with mc3: st.metric("6M",mom["6 Month"])
                    with mc4: st.metric("12M",mom["12 Month"])
                    with mc5: st.metric("vs 50-SMA",mom["vs 50-SMA"])
                    with mc6: st.metric("vs 200-SMA",mom["vs 200-SMA"])

# ═══ TAB 11: WATCHLIST ════════════════════════════════════════════
with tab_watchlist:
    wl=load_watchlist()
    if not wl: st.info("Watchlist empty.")
    else:
        st.markdown(f"### Watchlist ({len(wl)})")
        for entry in wl:
            t3=entry["ticker"]
            if t3 in scored_df.index:
                r=scored_df.loc[t3];rat=r.get("overall_rating","N/A");rc=RATING_COLORS.get(rat,"#666")
                c1,c2,c3,c4,c5=st.columns([1.5,2.5,1.5,1.5,0.8])
                with c1: st.markdown(f"**{t3}**")
                with c2: st.markdown(r.get("shortName",""))
                with c3: st.markdown(f'<span style="background:{rc};padding:2px 10px;border-radius:4px;font-weight:700;color:#111;">{rat}</span>',unsafe_allow_html=True)
                with c4: st.markdown(f"Score: **{r.get('composite_score',0):.1f}**")
                with c5:
                    if st.button("X",key=f"wl_{t3}"): remove_from_watchlist(t3);st.rerun()
            st.markdown("---")

# ═══ TAB 12: COMPARE ══════════════════════════════════════════════
with tab_compare:
    sel_cmp=st.multiselect("Select 2-5",sorted(scored_df.index.tolist()),default=st.session_state.compare_tickers[:5],max_selections=5,format_func=lambda x:f"{x} -- {scored_df.loc[x,'shortName']}" if x in scored_df.index else x,key="cmp_ms")
    st.session_state.compare_tickers=sel_cmp
    if len(sel_cmp)>=2:
        td={};
        for t4 in sel_cmp:
            d=get_pillar_detail(t4,scored_df,sector_stats)
            if d: td[t4]={p:v["pillar_score"] for p,v in d.items()}
        if td: st.plotly_chart(multi_radar(td),use_container_width=True,key="cmp_radar")
        rows=[]
        for t4 in sel_cmp:
            if t4 in scored_df.index:
                r=scored_df.loc[t4];rd={"Ticker":t4,"Company":r.get("shortName","")}
                for p in PILLAR_METRICS: rd[p]=f"{r.get(f'{p}_grade','N/A')} ({r.get(f'{p}_score',0):.1f})"
                rd["Composite"]=f"{r.get('composite_score',0):.1f}";rd["Rating"]=r.get("overall_rating","N/A");rows.append(rd)
        if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

st.markdown("---")
st.caption("Quant Strategy Dashboard Pro v3.3 | Not financial advice")
