"""
Quantitative Strategy Dashboard Pro v3.0
9 tabs: Screener, Watchlist, Stock Detail (with Fair Value), Compare,
Sector Overview, Portfolio, Monte Carlo, Thesis Engine, Market Sentiment
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
from sentiment import fetch_index_data, fetch_vix_data, compute_market_breadth, compute_fear_greed, COMING_SOON_INDICATORS

st.set_page_config(page_title="Quant Dashboard Pro", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
.main-header{font-size:1.8em;font-weight:800;background:linear-gradient(90deg,#00D4AA,#00A3FF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:0}
.sub-header{color:#888;font-size:0.95em;margin-top:-8px}
.suggestion-card{background:#1A1F2E;border-radius:10px;padding:14px;margin-bottom:10px}
.suggestion-warning{border-left:4px solid #FF5722}.suggestion-info{border-left:4px solid #FFC107}.suggestion-opportunity{border-left:4px solid #00C805}
.gauge-container{text-align:center;padding:10px}
</style>""", unsafe_allow_html=True)

for k,v in [("scored_df",None),("raw_data",None),("selected_ticker",None),("compare_tickers",[]),("weights",DEFAULT_PILLAR_WEIGHTS.copy()),("sector_relative",True),("portfolio_holdings",[])]:
    if k not in st.session_state: st.session_state[k]=v

def fmt_mcap(b): return f"${b/1000:.1f}T" if b>=1000 else f"${b:.1f}B"

def make_gauge(value, title, min_val=0, max_val=100, invert=False):
    """Create a plotly gauge chart. invert=True means lower=better (green on left)."""
    if invert:
        steps=[dict(range=[0,25],color="#00C805"),dict(range=[25,45],color="#8BC34A"),
               dict(range=[45,55],color="#FFC107"),dict(range=[55,75],color="#FF5722"),dict(range=[75,100],color="#D32F2F")]
    else:
        steps=[dict(range=[0,25],color="#D32F2F"),dict(range=[25,45],color="#FF5722"),
               dict(range=[45,55],color="#FFC107"),dict(range=[55,75],color="#8BC34A"),dict(range=[75,100],color="#00C805")]
    fig=go.Figure(go.Indicator(mode="gauge+number",value=value,title=dict(text=title,font=dict(size=14,color="#e0e0e0")),
        number=dict(font=dict(size=28,color="#e0e0e0")),
        gauge=dict(axis=dict(range=[min_val,max_val],tickcolor="#666"),bar=dict(color="#00D4AA",thickness=0.3),
            bgcolor="#1A1F2E",steps=steps,threshold=dict(line=dict(color="white",width=2),thickness=0.8,value=value))))
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

# Sidebar
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
        st.cache_data.clear();st.session_state.scored_df=None;st.session_state.raw_data=None
        import os
        try:
            f=os.path.join("data_cache","fundamentals_cache.json")
            if os.path.exists(f): os.utime(f,(0,0))
        except: pass
        st.rerun()

st.markdown('<p class="main-header">Quant Strategy Dashboard Pro</p>',unsafe_allow_html=True)
mode="Sector-Relative" if st.session_state.sector_relative else "Universe-Wide"
st.markdown(f'<p class="sub-header">{mode} scoring across 5 pillars</p>',unsafe_allow_html=True)

tab_screener,tab_watchlist,tab_detail,tab_compare,tab_sectors,tab_portfolio,tab_mc,tab_thesis,tab_sentiment=st.tabs(
    ["Screener","Watchlist","Stock Detail","Compare","Sector Overview","Portfolio","Monte Carlo","Thesis Engine","Market Sentiment"])

@st.cache_data(ttl=43200,show_spinner=False)
def load_and_score(mcap,wt,sr):
    w=dict(zip(DEFAULT_PILLAR_WEIGHTS.keys(),wt));tickers=get_broad_universe(mcap)
    progress=st.progress(0,text="Loading...");raw=fetch_universe_data(tickers,mcap,lambda p,m:progress.progress(p,text=m));progress.empty()
    scored=score_universe(raw,w,sector_relative=sr);ss=get_sector_stats(scored) if not scored.empty else {}
    return raw,scored,ss

try: raw_data,scored_df,sector_stats=load_and_score(market_cap_floor,tuple(st.session_state.weights.values()),st.session_state.sector_relative)
except Exception as e: st.error(f"Error: {e}");st.stop()
if scored_df is None or scored_df.empty: st.warning("No data.");st.stop()

# ═══════════════════════════════════════════════════════════════════
# TAB 1: SCREENER
# ═══════════════════════════════════════════════════════════════════
with tab_screener:
    c1,c2,c3=st.columns(3)
    with c1: sel_sec=st.selectbox("Sector",["All"]+sorted(scored_df["sector"].dropna().unique().tolist()))
    with c2: sel_rat=st.selectbox("Rating",["All","Strong Buy","Buy","Hold","Sell","Strong Sell"])
    with c3: top_n=st.selectbox("Show Top",[50,100,250,500],index=3)
    filtered=get_top_stocks(scored_df,top_n,sel_sec,sel_rat)
    if not filtered.empty:
        s1,s2,s3,s4=st.columns(4)
        with s1: st.metric("Universe",f"{len(scored_df):,}")
        with s2: st.metric("Strong Buys",len(scored_df[scored_df["overall_rating"]=="Strong Buy"]))
        with s3: st.metric("Avg Score",f"{scored_df['composite_score'].mean():.1f}")
        with s4: st.metric("Showing",f"{len(filtered):,}")
        dc=["shortName","sector","marketCapB","currentPrice"]
        for p in PILLAR_METRICS: dc.append(f"{p}_grade")
        dc+=["composite_score","overall_rating"]
        dd=filtered[dc].copy();dd.columns=["Company","Sector","Mkt Cap ($B)","Price","Valuation","Growth","Profit","Momentum","EPS Rev","Score","Rating"]
        st.dataframe(dd,use_container_width=True,height=700)

# ═══════════════════════════════════════════════════════════════════
# TAB 2: WATCHLIST
# ═══════════════════════════════════════════════════════════════════
with tab_watchlist:
    wl=load_watchlist()
    if not wl: st.info("Watchlist empty.")
    else:
        st.markdown(f"### Watchlist ({len(wl)})")
        for entry in wl:
            t=entry["ticker"]
            if t in scored_df.index:
                r=scored_df.loc[t];rat=r.get("overall_rating","N/A");rc=RATING_COLORS.get(rat,"#666")
                c1,c2,c3,c4,c5=st.columns([1.5,2.5,1.5,1.5,0.8])
                with c1: st.markdown(f"**{t}**")
                with c2: st.markdown(r.get("shortName",""))
                with c3: st.markdown(f'<span style="background:{rc};padding:2px 10px;border-radius:4px;font-weight:700;color:#111;">{rat}</span>',unsafe_allow_html=True)
                with c4: st.markdown(f"Score: **{r.get('composite_score',0):.1f}**")
                with c5:
                    if st.button("X",key=f"wl_{t}"): remove_from_watchlist(t);st.rerun()
            st.markdown("---")

# ═══════════════════════════════════════════════════════════════════
# TAB 3: STOCK DETAIL (with Fair Value + Historical Chart)
# ═══════════════════════════════════════════════════════════════════
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
        with h4:
            rat=row.get("overall_rating","Hold");st.metric("Score",f"{row.get('composite_score',0):.1f}/12")
            st.markdown(f'<span style="background:{RATING_COLORS.get(rat,"#666")};padding:4px 14px;border-radius:6px;font-weight:700;color:#111;">{rat}</span>',unsafe_allow_html=True)
        st.markdown(f"**Sector:** {row.get('sector','N/A')} | **Industry:** {row.get('industry','N/A')}")

        # ── Fair Value Section ─────────────────────────────────
        st.markdown("---")
        st.markdown("### Fair Value Analysis")
        fv=compute_fair_value(sel,scored_df)
        if "error" not in fv:
            fv1,fv2,fv3,fv4=st.columns(4)
            with fv1: st.metric("Current Price",f"${fv['current_price']:.2f}")
            with fv2: st.metric("Fair Value Estimate",f"${fv['composite_fair_value']:.2f}")
            with fv3: st.metric("Premium/Discount",f"{fv['premium_discount_pct']:+.1f}%")
            with fv4:
                st.markdown(f'<span style="background:{fv["verdict_color"]};padding:4px 14px;border-radius:6px;font-weight:700;color:#111;">{fv["verdict"]}</span>',unsafe_allow_html=True)
                if fv["margin_of_safety"]>0: st.caption(f"Margin of Safety: {fv['margin_of_safety']:.1f}%")

            # Fair value bar chart
            method_names=list(fv["methods"].keys())
            method_values=[fv["methods"][m]["fair_value"] for m in method_names]
            fig_fv=go.Figure()
            fig_fv.add_trace(go.Bar(x=method_names,y=method_values,marker_color="#4ECDC4",name="Fair Value"))
            fig_fv.add_hline(y=fv["current_price"],line_dash="dash",line_color="#FF6B6B",annotation_text=f"Current: ${fv['current_price']}")
            fig_fv.add_hline(y=fv["composite_fair_value"],line_dash="dash",line_color="#00D4AA",annotation_text=f"Composite: ${fv['composite_fair_value']:.0f}")
            fig_fv.update_layout(yaxis=dict(title="Price ($)",tickformat="$,.0f"),height=350,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"))
            st.plotly_chart(fig_fv,use_container_width=True,key="fv_bar")

            with st.expander("View method details"):
                for mname,mdata in fv["methods"].items():
                    st.markdown(f"**{mname}**: ${mdata['fair_value']:.2f} ({mdata['premium_discount_pct']:+.1f}%)")
                    if "assumptions" in mdata:
                        for ak,av in mdata["assumptions"].items():
                            st.caption(f"  {ak}: {av}")
                    st.markdown("---")
        else:
            st.caption(fv.get("error","Insufficient data for fair value."))

        # ── Pillar Breakdown ───────────────────────────────────
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
                        with mc3: g=m["grade"];gc=GRADE_COLORS.get(g,"#666");st.markdown(f'<span style="background:{gc};padding:2px 8px;border-radius:4px;font-weight:700;color:#111;">{g}</span>',unsafe_allow_html=True)
                        with mc4: st.markdown(m["percentile"])
                        with mc5: st.markdown(m["sector_avg"])
                        with mc6: st.markdown(f'**{m["a_threshold"]}**')

# ═══════════════════════════════════════════════════════════════════
# TAB 4: COMPARE
# ═══════════════════════════════════════════════════════════════════
with tab_compare:
    sel_cmp=st.multiselect("Select 2-5",sorted(scored_df.index.tolist()),default=st.session_state.compare_tickers[:5],max_selections=5,format_func=lambda x:f"{x} -- {scored_df.loc[x,'shortName']}" if x in scored_df.index else x,key="cmp_ms")
    st.session_state.compare_tickers=sel_cmp
    if len(sel_cmp)>=2:
        td={};
        for t in sel_cmp:
            d=get_pillar_detail(t,scored_df,sector_stats)
            if d: td[t]={p:v["pillar_score"] for p,v in d.items()}
        if td: st.plotly_chart(multi_radar(td),use_container_width=True,key="cmp_radar")
        rows=[]
        for t in sel_cmp:
            if t in scored_df.index:
                r=scored_df.loc[t];rd={"Ticker":t,"Company":r.get("shortName","")}
                for p in PILLAR_METRICS: rd[p]=f"{r.get(f'{p}_grade','N/A')} ({r.get(f'{p}_score',0):.1f})"
                rd["Composite"]=f"{r.get('composite_score',0):.1f}";rd["Rating"]=r.get("overall_rating","N/A");rows.append(rd)
        if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 5: SECTOR OVERVIEW
# ═══════════════════════════════════════════════════════════════════
with tab_sectors:
    st.markdown("### Sector Overview")
    overview=get_sector_overview(scored_df)
    if not overview.empty:
        rc=["Rank","Sector","Stocks","composite_avg","Strong Buy","Buy","Hold","Sell","Strong Sell"]
        for p in PILLAR_METRICS: rc.append(f"{p}_grade")
        rc+=["best_stock","worst_stock"]
        ac=[c for c in rc if c in overview.columns];rdf=overview[ac].copy()
        rn={"composite_avg":"Avg Score","best_stock":"Best","worst_stock":"Worst"}
        for p in PILLAR_METRICS: rn[f"{p}_grade"]={"Valuation":"Val","Growth":"Grw","Profitability":"Prof","Momentum":"Mom","EPS Revisions":"EPS"}.get(p,p)
        rdf=rdf.rename(columns=rn);st.dataframe(rdf,use_container_width=True,hide_index=True)

        fig_s=px.bar(overview,x="Sector",y="composite_avg",color="composite_avg",color_continuous_scale=["#D32F2F","#FFC107","#00C805"],range_color=[4,9])
        fig_s.update_layout(yaxis=dict(range=[0,12],title="Avg Score"),height=400,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"),coloraxis_showscale=False)
        st.plotly_chart(fig_s,use_container_width=True,key="sec_bar")

        st.markdown("#### Sector Deep Dive")
        ss=st.selectbox("Select sector",overview["Sector"].tolist(),key="sec_drill")
        if ss:
            sd=get_sector_detail(ss,scored_df)
            if sd:
                m1,m2,m3=st.columns(3)
                with m1: st.metric("Stocks",sd["num_stocks"])
                with m2: st.metric("Avg Score",f"{sd['composite_avg']:.1f}")
                with m3: st.metric("Median",f"{sd['composite_median']:.1f}")
                sdf=sd["stocks_df"].copy()
                cm={"shortName":"Company","currentPrice":"Price","marketCapB":"Mkt Cap","composite_score":"Score","overall_rating":"Rating"}
                for p in PILLAR_METRICS: cm[f"{p}_grade"]={"Valuation":"Val","Growth":"Grw","Profitability":"Prof","Momentum":"Mom","EPS Revisions":"EPS"}.get(p,p)
                sdf=sdf.rename(columns={c:cm.get(c,c) for c in sdf.columns})
                st.dataframe(sdf,use_container_width=True,height=500)

# ═══════════════════════════════════════════════════════════════════
# TAB 6: PORTFOLIO ANALYZER
# ═══════════════════════════════════════════════════════════════════
with tab_portfolio:
    st.markdown("### Portfolio Analyzer")
    inp=st.radio("Input",["Manual Entry","CSV Upload (Fidelity)"],horizontal=True)
    if inp=="CSV Upload (Fidelity)":
        up=st.file_uploader("Upload CSV",type=["csv"])
        if up:
            parsed=parse_fidelity_csv(up.read().decode("utf-8"))
            if parsed: st.session_state.portfolio_holdings=parsed;st.success(f"Parsed {len(parsed)}")
            else: st.error("Could not parse.")
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
            st.markdown("---")
            m1,m2,m3,m4,m5=st.columns(5)
            with m1: st.metric("Value",f"${analysis['total_value']:,.0f}")
            with m2: st.metric("Holdings",analysis["num_holdings"])
            with m3: st.metric("Rating",analysis["weighted_rating"])
            with m4: st.metric("Score",f"{analysis['weighted_composite']:.1f}/12")
            with m5: st.metric("Concentration",analysis["concentration_level"])
            if analysis.get("num_etfs",0)>0: st.caption(f"Stocks: {analysis.get('stock_weight',0):.0f}% | ETFs: {analysis.get('etf_weight',0):.0f}%")
            if analysis["num_unmatched"]>0: st.caption(f"Unmatched: {', '.join(analysis['unmatched_tickers'])}")
            td2=[];
            for p,t in analysis["factor_tilts"].items(): td2.append({"Pillar":p,"Portfolio":t["portfolio"],"Universe":t["universe"]})
            fig_t=go.Figure();tdf=pd.DataFrame(td2)
            fig_t.add_trace(go.Bar(name="Portfolio",x=tdf["Pillar"],y=tdf["Portfolio"],marker_color="#00D4AA"))
            fig_t.add_trace(go.Bar(name="Universe",x=tdf["Pillar"],y=tdf["Universe"],marker_color="#555"))
            fig_t.update_layout(barmode="group",yaxis=dict(range=[0,12]),height=350,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color="#e0e0e0"))
            st.plotly_chart(fig_t,use_container_width=True,key="pt")
            sugs=generate_suggestions(analysis,scored_df)
            if sugs:
                st.markdown("### Suggestions")
                for sg in sugs:
                    css=f"suggestion-{sg['type']}";icon={"warning":"!!","info":"i","opportunity":"++"}[sg["type"]]
                    st.markdown(f'<div class="suggestion-card {css}"><strong>{icon} {sg["title"]}</strong><br><span style="color:#aaa;">{sg["detail"]}</span></div>',unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# TAB 7: MONTE CARLO
# ═══════════════════════════════════════════════════════════════════
with tab_mc:
    st.markdown("### Monte Carlo Simulation")
    if not st.session_state.portfolio_holdings: st.info("Enter holdings in Portfolio tab first.")
    else:
        analysis=analyze_portfolio(st.session_state.portfolio_holdings,scored_df,sector_stats)
        if "error" not in analysis and analysis:
            hdf=analysis.get("holdings_df",pd.DataFrame())
            mc1,mc2=st.columns(2)
            with mc1: ns=st.selectbox("Sims",[1000,5000,10000],index=1)
            with mc2: nd=st.selectbox("Horizon",[63,126,252],index=2,format_func=lambda x:{63:"3Mo",126:"6Mo",252:"1Yr"}[x])
            if st.button("Run",key="mcr"):
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

# ═══════════════════════════════════════════════════════════════════
# TAB 8: THESIS ENGINE
# ═══════════════════════════════════════════════════════════════════
with tab_thesis:
    st.markdown("### Investment Thesis Engine")
    if not is_correlation_data_available():
        st.warning("Correlation data not found. Run build_correlations.py locally and upload correlations_cache.json.")
        st.markdown("**Factors available once deployed:** Oil, Interest Rates, US Dollar, VIX, Gold, Bitcoin, Natural Gas, S&P 500 Beta")
    else:
        st.caption("Powered by 20-year historical return correlations.")
        thesis_input=st.text_area("Your thesis",placeholder="e.g., I think oil prices will increase by 20%",height=100,key="thesis_input")
        if thesis_input:
            results=get_thesis_results(thesis_input,scored_df)
            if not results["matched"]:
                st.warning(results.get("message","No match."))
            else:
                st.info(results["thesis_summary"])
                if not results["bullish_top_rated"].empty:
                    st.markdown("### Highest Conviction (Buy/Strong Buy + Correlated)")
                    tc=["shortName","sector","correlation","beta","r_squared","composite_score","overall_rating"]
                    ac=[c for c in tc if c in results["bullish_top_rated"].columns]
                    st.dataframe(results["bullish_top_rated"][ac].rename(columns={"shortName":"Company","sector":"Sector","correlation":"Corr","beta":"Beta","r_squared":"R2","composite_score":"Score","overall_rating":"Rating"}),use_container_width=True)
                st.markdown(f"### All Positively Correlated ({len(results['bullish_all'])})")
                if not results["bullish_all"].empty:
                    bc=["shortName","sector","correlation","beta","composite_score","overall_rating"]
                    ac2=[c for c in bc if c in results["bullish_all"].columns]
                    st.dataframe(results["bullish_all"][ac2].rename(columns={"shortName":"Company","sector":"Sector","correlation":"Corr","beta":"Beta","composite_score":"Score","overall_rating":"Rating"}),use_container_width=True,height=400)
                st.markdown(f"### Negatively Correlated ({len(results['bearish_all'])})")
                if not results["bearish_all"].empty:
                    bc2=["shortName","sector","correlation","beta","composite_score","overall_rating"]
                    ac3=[c for c in bc2 if c in results["bearish_all"].columns]
                    st.dataframe(results["bearish_all"][ac3].rename(columns={"shortName":"Company","sector":"Sector","correlation":"Corr","beta":"Beta","composite_score":"Score","overall_rating":"Rating"}),use_container_width=True,height=400)

# ═══════════════════════════════════════════════════════════════════
# TAB 9: MARKET SENTIMENT
# ═══════════════════════════════════════════════════════════════════
with tab_sentiment:
    st.markdown("### Market Sentiment Dashboard")
    st.caption("When to buy: favorable sentiment (gauges right). What to buy: use the Screener and Portfolio tabs.")

    # Load live data
    with st.spinner("Fetching live market data..."):
        index_data=fetch_index_data()
        vix_data=fetch_vix_data()
        breadth_data=compute_market_breadth(scored_df)
        fear_greed=compute_fear_greed(vix_data,breadth_data,index_data)

    # ── Composite Fear/Greed Gauge ─────────────────────────────
    st.markdown("---")
    st.markdown("### Composite Fear & Greed Score")
    fg_col1,fg_col2=st.columns([1,1])
    with fg_col1:
        st.plotly_chart(make_gauge(fear_greed["score"],"Fear & Greed",0,100),use_container_width=True,key="fg_gauge")
    with fg_col2:
        st.markdown(f'### <span style="color:{fear_greed["color"]}">{fear_greed["classification"]}</span>',unsafe_allow_html=True)
        st.markdown(f"**Score: {fear_greed['score']:.0f}/100**")
        st.caption("0 = Extreme Fear (buy signal) | 100 = Extreme Greed (caution)")
        st.markdown("---")
        st.markdown("**Components:**")
        for comp in fear_greed["components"]:
            bar_color="#00C805" if comp["score"]>60 else "#FFC107" if comp["score"]>40 else "#FF5722"
            st.markdown(f"**{comp['name']}**: {comp['value']} ({comp['interpretation']})")
            st.progress(comp["score"]/100)

    # ── Individual Sentiment Gauges ────────────────────────────
    st.markdown("---")
    st.markdown("### Sentiment Indicators")

    g1,g2,g3=st.columns(3)
    with g1:
        if vix_data:
            # VIX: inverted gauge (lower VIX = more favorable)
            st.plotly_chart(make_gauge(vix_data["score"],f"VIX: {vix_data['current']}",0,100),use_container_width=True,key="vix_gauge")
            st.caption(f"{vix_data['level']} | 1Y Range: {vix_data['low_1y']}-{vix_data['high_1y']}")
    with g2:
        if breadth_data:
            st.plotly_chart(make_gauge(breadth_data["pct_above_50sma"],f"Above 50-SMA: {breadth_data['pct_above_50sma']:.0f}%",0,100),use_container_width=True,key="sma50_gauge")
            st.caption("% of universe stocks trading above their 50-day moving average")
    with g3:
        if breadth_data:
            st.plotly_chart(make_gauge(breadth_data["pct_above_200sma"],f"Above 200-SMA: {breadth_data['pct_above_200sma']:.0f}%",0,100),use_container_width=True,key="sma200_gauge")
            st.caption("% of universe stocks trading above their 200-day moving average")

    g4,g5,g6=st.columns(3)
    with g4:
        if breadth_data:
            st.plotly_chart(make_gauge(breadth_data["pct_positive_1m"],"1-Month Momentum Breadth",0,100),use_container_width=True,key="mom1m_gauge")
            st.caption("% of stocks with positive 1-month returns")
    with g5:
        if breadth_data:
            st.plotly_chart(make_gauge(breadth_data["buy_pct"],"Quant Buy %",0,100),use_container_width=True,key="buy_gauge")
            st.caption("% of universe rated Strong Buy or Buy by our model")
    with g6:
        sp_dist=0
        for idx in index_data:
            if idx["name"]=="S&P 500": sp_dist=idx["distance_from_ath_pct"];break
        sp_score=max(0,min(100,100+(sp_dist*3.33)))
        st.plotly_chart(make_gauge(sp_score,f"S&P 500 vs ATH: {sp_dist:+.1f}%",0,100),use_container_width=True,key="sp_gauge")
        st.caption("Distance from all-time high (0% = at ATH)")

    # ── Major Indexes Table ────────────────────────────────────
    st.markdown("---")
    st.markdown("### Major Indexes & Assets")
    if index_data:
        idx_df=pd.DataFrame(index_data)
        display_cols=["name","current_price","all_time_high","distance_from_ath_pct","change_1d_pct","change_5d_pct","change_1m_pct","change_ytd_pct"]
        idx_display=idx_df[display_cols].copy()
        idx_display.columns=["Asset","Price","All-Time High","From ATH %","1D %","5D %","1M %","YTD %"]
        st.dataframe(idx_display,use_container_width=True,hide_index=True)

    # ── Coming Soon ────────────────────────────────────────────
    st.markdown("---")
    with st.expander("Coming Soon: Additional Indicators"):
        for ind in COMING_SOON_INDICATORS:
            st.markdown(f"**{ind['name']}** ({ind['source']})")
            st.caption(ind["description"])

# Footer
st.markdown("---")
st.caption("Quant Strategy Dashboard Pro v3.0 | Not financial advice")
