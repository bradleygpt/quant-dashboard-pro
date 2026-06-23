# Akribeia Quant Dashboard — Operating Guide
*Complete app + data + command reference · as of 2026-06-22*

This covers **what every screen is, how to read it, and how to use it**, the **quant engine** behind the scores, the **data pipeline**, and at the end a **complete PowerShell command library** (scheduled/automated first, then the local refresh pipeline, then one-time/informational).

Repos:
- **`quant-dashboard-pro-v2`** — the live React/Vite app (deploys to Vercel on push to `main`). The frontend + its baked data (`public/data/*.json`).
- **`quant-dashboard-react`** (remote `quant-dashboard-pro`) — the Python "backend": the **bake** (`bake/bake.py`), scoring engine, caches, AI generators, and all the scheduled CI workflows. Has a nested `web/` checkout (a second copy of the frontend the bake writes into).
- **`quant-historical`** — *local-only* research repo (no remote): the price panel, strategy builders, and the ETF/index/AI-theme builders. Its scripts run locally and write data into the two frontends.

---

# PART 1 — THE QUANT ENGINE (read this first; every screen builds on it)

**The universe:** ~1,289 US stocks + ~70 ETFs (`universe_floor0.json`), scored daily.

**The 5 pillars** (each graded A+ → F): **Valuation · Growth · Profitability · Momentum · EPS Revisions**. They roll into a single **composite score** (higher = better). Grades are *sector-relative* (an "A" in Tech is judged against Tech).

**Ratings** (the colored badge): the top names by composite become **Strong Buy+ / Strong Buy / Buy** (tiered by how far below fair value they trade); the rest fall to **Hold / Sell / Strong Sell**. ETFs are rated on a separate score-band (no Buy tiers).

**Three price anchors on every name:**
- **Fair Value (FV)** + **premium/discount** + **verdict** (Deeply Undervalued → Significantly Overvalued) — the model's intrinsic value vs the current price.
- **Quant Buy Point (QBP)** — the price the model would start buying, with a **BP distance** and **BP signal** (Approaching / At Buy / Far from).
- **FCF quality flag** — free-cash-flow yield *after* expensing stock comp (SBC). "Clean", "SBC-flagged", "OCF<0", or "—".

**Index membership badges** — small **S&P** / **NDX** chips next to a ticker mean it's in the S&P 500 / Nasdaq-100 (sourced from SPY holdings ∪ Wikipedia — authoritative).

---

# PART 2 — EVERY SCREEN

### 🏠 Home
The landing/splash page. Click **"enter dashboard →"** to reach the app. Not analytical — it's the front door.

### 📊 Overview
The universe at a glance, and the daily starting point.
- **Rating-distribution cards** (Universe / Strong Buy+ / Strong Buy / Buy / Hold / Sell / Strong Sell) — the shape of the whole market today.
- **AI Market Summary** — "the market in a paragraph": posture (risk-on/neutral/cautious), valuation backdrop, where strength sits. *(AI; numbers-only-fed.)*
- **AI Anomaly Watch** — names whose pillars most *diverge* (e.g. strong Momentum + weak Valuation = "is this sustainable?"), each with the risk to watch. *(AI.)*
- **Stock Screener mini-table** — the top names, sortable, with S&P/NDX badges.
- **How to use:** scan the distribution + read the AI summary for the day's tone, then click the highest-conviction tickers into Stock Detail.

### 📊 Market Regime
The macro "weather" for risk appetite.
- **Fear & Greed** composite (VIX, breadth, S&P-vs-ATH, Buffett, **HY-OAS credit stress** folded in).
- **Metrics row:** VIX · real **10Y Treasury** & **10Y–2Y curve** (true `T10Y2Y`, "Inverted ⚠" when negative) · **HY Credit OAS** (Calm/Elevated/Stress) · S&P vs ATH · Dollar (DXY) · Buffett Indicator.
- **Macro Health** composite (ISM, jobs, GDP, CPI, real yield curve, + HY credit) → Strong Expansion → Recession.
- **How to read:** inverted curve + widening credit OAS + falling Macro Health = lean defensive. Tight credit + positive curve = risk-on.

### 🌐 Macro Outlook
Top-down forecasts and what they imply.
- **Forecast Consensus** — a cross-institution table (GDP / CPI / Unemployment / Fed Funds / S&P target for the next ~3 years). **Live feeds**: Fed SEP, World Bank, IMF (green dot). **Curated bank house-views** (9 forecasters: WFII, Fannie Mae, KPMG, Guggenheim, UBS, Goldman, Morgan Stanley, Yardeni, Vanguard — dated snapshots). *The value is the **spread** between forecasters — nobody publishes this comparison.*
- **FOMC dot plot** · **Macro Signals** (T10Y2Y, HY OAS, breakevens, jobless claims — live FRED) · **Forward Earnings Path**.
- **Risk Radar** — what institutions are collectively watching right now (Gemini, web-grounded).
- **AI Sector Rotation** — which sectors the current macro setup favors / pressures. *(AI.)*
- **How to use:** read the consensus spread for the macro debate; use Sector Rotation + Risk Radar for top-down sector tilts.

### 💼 Your Portfolio
Your personal book (paste a Fidelity-style CSV or add manually; **stored only in your browser's localStorage — never uploaded**).
- **Holdings** table with live quant ratings · **Factor tilts vs the universe** · **Sector allocation** · **Monte Carlo** scenario simulation.
- **AI Portfolio Advisor** — plain-English rebalance reasoning: where you're over/under-exposed and which uncorrelated, strong-quant sectors would diversify. *(AI runtime.)*
- **Actionable Recommendations** — prescriptive flags (concentration, dead weight, tax-loss, momentum exits).
- **How to use:** load your real holdings → read the tilts + advisor → act on the recommendations.

### 💎 Quant Portfolio
The model-built "optimal" portfolio — what the quant itself would hold, with its backtest. Read it as the reference book vs your own.

### 🔍 Stock Detail
The deep-dive on one name.
- **Header:** ticker + S&P/NDX badges + rating + watch toggle.
- **Scores:** composite + the 5 pillar grades; **Fair Value** (+ premium/discount + verdict); **Quant Buy Point** (+ BP distance/signal); **FCF Quality**.
- **Quarterly history** (revenue/earnings/margins) + price chart.
- **AI block:** **Research Note** (4-paragraph analyst note), **AI Earnings Review** (thesis-check vs the latest 8-K, with a **Quality: High/Med/Low** badge), and an **AI correlation read** (what this name's factor correlations mean). *(AI runtime via Gemini; the earnings reviews are pre-baked.)*
- **How to read:** the 5 grades tell you the character; FV verdict + QBP tell you the entry; FCF flag warns on stock-comp distortion.

### ✨ Doppelganger
Find a stock's closest **historical analogues** by fundamental fingerprint (valuation/growth/momentum), and **what happened next** (aggregate forward returns across eras).
- **AI analogue read** — central tendency + dispersion of the analogues, and what split winners from losers. *(AI runtime.)*
- **How to use:** "setups that looked like this historically returned X, with this much downside risk."

### 📋 Quant Screener
The full power-tool over the universe (ETFs excluded).
- **🗣️ Ask the Screener** — type a plain-English screen ("cheap profitable industrials with momentum") → AI maps it to filters, applied live. *(AI runtime.)*
- **🧠 Thematic Explorer** — the **"AI buildout"** theme: stocks ranked by return-correlation to an AI-compute proxy basket — surfaces the **picks-and-shovels** (MPWR, ETN/Eaton, semi-equipment) over the megacaps — with an AI layer-map (compute → power → cooling → networking).
- **The dense table** — every metric (score, rating, FV, QBP, pillar grades, market cap, FCF, SBC/OCF), all sortable, with quick-screens + custom filters. *(Wide — scroll horizontally; the ticker column is frozen.)*
- **How to use:** ask in plain English, or filter manually, or explore the AI theme; click any ticker to Stock Detail.

### Project Prolepsis (ML Predictions)
The machine-learning **12-month price predictions** (the MLPred streams) — forecast returns per name, with the horizon term structure. Company names + ticker links to Stock Detail. Feeds the Pronoia strategy and the FV model.

### 📈 Strategies
The consolidated quant book — **5 strategies run as one pooled portfolio**:
- **Katalepsis** (ML posterior · c78q), **Aristeia** (event/PEAD), **Pronoia** (ML 12-month foresight) = the **3 distinct, decorrelated bets**.
- **Auxo** + **Prosodos** = the surviving quant factors.
- Shows per-strategy CAGR/Sharpe/holdings, the **total basket** (≈28.5% backtest CAGR, with a "deployable" figure that goes to cash in >10% SPY drawdowns), an **AI Strategy Read** (why each book holds what it holds), and the holdings treemap + correlation-network viz.
- **How to use:** this is the **live deployment** (the 7/1 book). The allocator command (Part 4-C) turns current holdings into dollar targets.

### Sector Overview
Sector-level aggregates: market cap & earnings, aggregate P/E, average score, rating distribution, pillar grades, and best/worst name per sector — plus an **AI Sector Read** (a narrative per sector). *(AI.)* Use for sector rotation.

### ₿ Crypto
Crypto-asset view (prices/momentum and crypto-equity context).

### 🫧 AI Bubble Watch
An AI-bubble indicator — tracks froth in the AI complex.

### ETF Center
Six sections:
- **🧭 Find your ETF** — enter 1–10+ tickers (or "Load 7/1 basket") → the ETFs most relevant to that set, ranked, with an **orthogonal-set novelty banner** (fires when no ETF replicates your names — a non-consensus signal). Fresh holdings (issuer CSV / yfinance, today's data).
- **📈 Index-Add** — likely **S&P 500 / Nasdaq-100 additions** + the estimated **passive-buy impact** (indexed AUM × new weight) and **days-of-ADV** (higher = bigger price pop). The "book" badge flags names you already hold.
- **📊 Portfolio Builder** (model ETF portfolios) · **🔍 ETF Comparison** · **🗺️ Sector & Theme Map** · **📋 ETF Universe** (scored ETFs; ⓘ = AI description).

### 🎤 Pundit Views
Curated market-commentator views (Gemini-grounded, refreshed daily).

### 📖 Help
In-app explanations of the metrics and tabs.

---

# PART 3 — HOW DATA FLOWS

1. **Caches** (fundamentals, prices) are refreshed — nightly by CI (`build_cache.py`) and from the price panel in `quant-historical`.
2. **The bake** (`bake/bake.py`) reads those caches + the universe, runs the real scoring engine, and writes all the frontend JSON (`universe_floor0.json`, `market_static.json`, `macro_forecasts.json`, `earnings_reviews.json`, etc.) into `quant-dashboard-react/web/public/data` **and mirrors to** `quant-dashboard-pro-v2/public/data`.
3. **Post-bake builders** (AI generators, ETF/index, correlations) read the baked universe and write their own JSON into both frontends.
4. **Commit + push** `quant-dashboard-pro-v2` → **Vercel deploys**.

**Two AI engines:**
- **Local Ollama** (`qwen2.5:7b`) — free, unlimited, runs the bake-time generators (narratives, earnings reviews). *Never sees the internet; only narrates pre-computed numbers.*
- **Gemini** (via the Vercel `/api/ai` edge function + the CI web-grounded jobs) — the runtime AI (Research Note, Earnings Review, Portfolio Advisor, Doppelganger, Ask-the-Screener, correlation read) and the web-grounded jobs (pundits, risk radar, house-views). Needs `GEMINI_API_KEY` (a Vercel env var + a CI secret).
- **Integrity rule everywhere:** the LLM only narrates numbers we pre-compute — it never calculates prices/metrics or invents figures.

---

# PART 4 — POWERSHELL COMMAND LIBRARY

## A) Scheduled / Automated — *these run themselves; no PowerShell needed*

All live in `quant-dashboard-react/.github/workflows/` and run on GitHub Actions cron. To run one **on demand**, use GitHub → **Actions → (pick workflow) → "Run workflow"** (every one supports manual dispatch). The Gemini jobs use the `GEMINI_API_KEY` repo secret.

| Workflow | Schedule (UTC) | What it does |
|---|---|---|
| `refresh-daily.yml` | `0 3 * * 1-6` (~11pm ET, after each close) | Evening fundamentals cache (`build_cache.py`) |
| `refresh-daily-morning.yml` | `0 14 * * 1-5` (~10am ET) | Morning fundamentals refresh |
| `refresh-weekly.yml` | `0 4 * * 0` (Sun) | Weekly cache refresh |
| `refresh-indicator-snapshots.yml` | `0 22 * * 1-5` | Market-indicator snapshots |
| `refresh-monthly-pgi.yml` | `0 5 1 * *` (1st) | PGI money-market "dry powder" figure |
| `refresh-manual-macro.yml` | `0 14 5 * *` (5th) | **ISM + money-market** via grounded Gemini |
| `check-house-views-freshness.yml` | `0 9 1,15 * *` (1st + 15th) | **Bank house-views staleness watchdog** → opens a GitHub issue + drafts candidate figures when an outlook is stale |
| `refresh-pundits-daily.yml` | `0 10 * * 1-5` (~6am ET) | **Pundit Views + Risk Radar** (Gemini, web-grounded) |
| `refresh-backtest.yml` | `0 5 * * 0` (Sun) | Backtest refresh |
| `refresh-quant-backtest.yml` | `0 11 * * 0` (Sun) | Quant backtest refresh |
| `backtest-*`, `quant-backtest-dual/quarterly` | manual only | On-demand backtest variants (Actions UI) |

> Note: the **bake itself is not in CI** — it runs locally (Part B). The CI jobs refresh *inputs* (caches) and the web-grounded narratives; you bake + deploy locally.

---

## B) The local refresh + deploy pipeline — *run periodically to push fresh data + AI*

**One-time setup** (only needed once on this machine):
```powershell
# Local LLM for all bake-time AI (free, unlimited)
# Install Ollama from https://ollama.com, then:
ollama pull qwen2.5:7b
```

**The full refresh, in order.** Set the Ollama env once; it persists for the PowerShell window:
```powershell
$env:AI_PROVIDER="ollama"; $env:OLLAMA_MODEL="qwen2.5:7b"

# 1) Bake the dashboard (scores the universe, writes all frontend JSON to both frontends)
cd C:\Users\bmhar\code\quant-dashboard-react
python bake/bake.py

# 2) Bake-time AI generators (quant-dashboard-react)
python build_sector_narratives.py      # AI Sector Read
python build_strategy_rationale.py     # AI Strategy Read
python build_anomalies.py              # AI Anomaly Watch
python build_macro_rotation.py         # AI Sector Rotation
python build_universe_summary.py       # AI Market Summary
python build_earnings_quality.py       # Earnings-quality badges (free, deterministic)

# 3) ETF / index / theme builders (quant-historical)
cd ..\quant-historical
python refresh_etf_data.py             # membership -> holdings/reverse -> index-add candidates
python build_ai_theme.py               # Thematic Explorer ("AI buildout")
python build_etf_descriptions.py       # ETF ⓘ descriptions

# 4) Commit the regenerated data + push  (frontend = deploy trigger)
cd ..\quant-dashboard-pro-v2
git add public/data/
git commit -m "data: refresh bake + AI + ETF/index"
git push origin main                   # -> Vercel deploys
git -C ..\quant-dashboard-react push origin main
```

**If a push is rejected** (a CI refresh raced you — common):
```powershell
git fetch origin; git rebase origin/main; git push origin main
# if a generated file conflicts (e.g. macro_forecasts.json), keep your local copy:
#   git checkout --theirs public/data/<file>; git add public/data/<file>; git rebase --continue
```

**Earnings reviews** (the big one — only when you want fresh 8-K reviews; ~2s/name on Ollama):
```powershell
cd C:\Users\bmhar\code\quant-dashboard-react
$env:AI_PROVIDER="ollama"; $env:OLLAMA_MODEL="qwen2.5:7b"
python build_earnings_reviews.py --holdings   # just your strategy book (fast, ~15 names)
python build_earnings_reviews.py              # the whole universe (long; resumes if interrupted)
# then re-bake (step 1 above) so earnings_reviews.json is rebuilt, then commit/push
```

---

## C) One-time / informational — *run as needed*

**Rebalance allocator** — turns the 5 strategies' current holdings into dollar targets (run on rebalance eve, e.g. 6/30 for the 7/1 book):
```powershell
cd C:\Users\bmhar\code\quant-historical
python allocate.py                 # defaults: total $21,350, cash $1,350 ($4k/strategy)
python allocate.py 21350 1350      # custom total, cash reserve
python allocate.py 21350 1350 2000 # + optional single-name cap (excess -> cash)
# Check the printed "sleeve as-of" dates are current before placing orders.
```

**Find-your-ETF (CLI)** — which ETFs hold a set of names:
```powershell
cd C:\Users\bmhar\code\quant-historical
python etf_finder.py MU NVDA AMD AVGO     # any tickers
python etf_finder.py                      # no args = the 7/1 strategy basket (the novelty check)
```

**Factor correlations** — powers the Stock-Detail "AI correlation read" (#9). Slow (20-year, ~508 tickers). Optional:
```powershell
cd C:\Users\bmhar\code\quant-dashboard-react
python build_correlations.py
# it writes correlations_cache.json to this repo; copy it into the frontend for the app:
copy correlations_cache.json ..\quant-dashboard-pro-v2\public\data\
```

**Fundamentals cache (manual)** — normally CI does this nightly; run locally only to force-refresh before a bake:
```powershell
cd C:\Users\bmhar\code\quant-dashboard-react
python build_cache.py
```

**Run a scheduled job on demand** — don't run these locally; trigger in **GitHub → Actions → (workflow) → Run workflow** (e.g. to regenerate the Risk Radar or fire the house-views watchdog now).

---

## Quick mental model
- **CI keeps the *inputs* fresh** (fundamentals, pundits, risk radar, ISM/PGI, house-views watchdog) — automatically.
- **You bake + run the AI generators + push** when you want the dashboard itself updated and deployed (Part B).
- **Ollama = free local AI** for everything baked; **Gemini = runtime AI** on the deployed app (needs the Vercel key).
- **`quant-historical` is local-only** — its builders run on your machine and write data into the frontends; nothing there is pushed to GitHub.
