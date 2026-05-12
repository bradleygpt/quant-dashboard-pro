# Quant Dashboard Pro — Strategic Architecture

**Last updated:** 2026-05-12
**Status:** Living document, iterate as architecture evolves

---

## The Three-Layer Vision

The dashboard is evolving from a single deterministic quant model into a three-layer predictive system. Each layer addresses a different question.

```
┌──────────────────────────────────────────────────────────────┐
│  LAYER 3: RACP                                                │
│  Regime Aware Bayesian Forward Guidance                       │
│  Question: "What's likely to happen, given current state?"    │
│                                                                │
│  Combines Quant + BH signals with regime context.             │
│  Outputs probability-weighted forward decisions.              │
└──────────────────────────────────────────────────────────────┘
        ▲                                          ▲
        │                                          │
┌───────────────────────────┐         ┌────────────────────────┐
│  LAYER 1: QUANT MODEL     │         │  LAYER 2: BH           │
│  Question: "What is true  │         │  Question: "What       │
│   now?"                   │         │   could surprise?"     │
│                           │         │                        │
│  TOP25 by composite       │         │  Multi-horizon return  │
│  score. Deterministic.    │         │  curves (1Q-4Q).       │
│  Historically validated.  │         │  Catches pre-momentum  │
│                           │         │  quality.              │
│  STATUS: Shipping         │         │  STATUS: Architected,  │
│                           │         │   not built            │
└───────────────────────────┘         └────────────────────────┘
```

---

## Layer 1: Quant Model (Shipping)

The deterministic engine. Picks TOP25 stocks by weighted composite score, rebalances quarterly.

### What's validated

| Universe | Best CAGR | Strategy | Sharpe | MaxDD |
|----------|-----------|----------|--------|-------|
| No floor (full universe) | +30.12% | m_heavy weights | 1.30 | -32.04% |
| $1B+ | +16.63% | mature_bull weights | 1.02 | -34.86% |
| $10B+ | +12.51% | equal weight | 0.86 | -32.26% |

**Source:** 1996-2026 historical backtest, 121 quarterly rebalances, point-in-time SEC EDGAR data.

### Validated design decisions

- **TOP25 is optimal across all tested universes.** Not TOP10 (worse drawdown) or TOP50 (lower CAGR).
- **1Q reselection dominates** HOLD_UNTIL_HOLD and 4Q hold strategies.
- **Equal-weight allocation** within TOP25 for momentum-tilted schemes (m_heavy). Concentration hurts: -1.38% CAGR delta with 2x Strong Buy weighting.
- **2x Strong Buy concentration** adds +0.5-0.6% CAGR for stable signals (equal_weight, mature_bull). The conviction tilt rewards persistent quality.
- **HELD positions outperform NEW entries** in TOP25 by 1-2% CAGR. Persistence is positive signal, not noise.
- **Score-weighted allocation** within TOP25 adds zero alpha (+0.06% delta). Tier-based concentration matters; continuous score weighting does not.

### What we ruled out

- **Algorithmic regime weighting via SMA crossovers.** Lagging and unreliable. The "regime adaptive" preset lost to equal-weight.
- **RAQP v1 (probabilistic relabeling of quant signals).** XGBoost regressor produced BH-shaped picks. Isotonic calibration collapsed to step functions. Sigmoid calibration was overconfident at the high end. Conclusion: relabeling certainty as probability adds nothing — you need new information, not new framing.

---

## Layer 2: Breakout Hunter (Architected, Not Built)

The asymmetric upside engine. Identifies beaten-down quality stocks *before* momentum kicks in. Independent of the Quant Model's ratings.

### The signal we've identified

From the m_heavy Strong Sell diagnostic (1996-2026 full history):
- 51,416 Strong Sell observations under m_heavy weights
- 1,093 cases of Strong Sells delivering 100%+ returns in the following 4 quarters
- Notable examples: AXON +4,649%, SBRA +2,655%, SM +1,374%, AKAM +1,054%, MTUS +400%
- The pattern: high V+G scores, low M score. Quality fundamentals, beaten-down price.

### Key architectural decisions

1. **BH includes current TOP25.** Persistence in TOP25 is a positive signal (HELD outperforms NEW). BH is not "the inverse of Quant" — it's an independent scoring of upside potential and confidence.

2. **Multi-horizon return curves.** BH predicts 1Q / 2Q / 3Q / 4Q forward returns per stock. The SHAPE of the curve indicates the opportunity type:
   - **Linear:** steady predicted compounder
   - **Front-loaded:** momentum already started, ride for 1-2Q
   - **Accelerating:** building momentum, position for 4Q
   - **Flat/declining:** exit signal

3. **m_heavy is NOT the BH model.** m_heavy catches stocks already trending up (late mover). BH catches beaten-down quality before momentum kicks in (early mover). They're different points in the lifecycle.

4. **BH allocation:** 0-25% of portfolio, user-discretionary, separate from core TOP25.

### Prerequisites before building

1. **Add 2Q and 3Q forward returns to the historical parquet.** Currently has 1Q, 4Q, 12Q. Need 2Q and 3Q to test multi-horizon curve shapes.

2. **Verify the parquet has the raw price data needed.** If pipeline kept only the pre-computed returns, we need to backfill from raw prices.

3. **Define the BH winner criterion empirically.** Is it 50%+ in 1Q? 100%+ in 4Q? Risk-adjusted threshold? Needs to be derived from data, not chosen.

4. **Feature engineering for the classifier.** Pillar scores, sector, regime, time-since-prior-rating, etc. Which features predict which curve shapes?

### Open questions for the BH build

- Is the 1Q→4Q return shape predictable at all? Linear vs non-linear test required before model building.
- Do certain pillar profiles (V+G high, M low) reliably predict accelerating curves?
- What's the realistic false-positive rate? Many beaten-down stocks stay beaten down. Need conviction calibration.
- Should the BH classifier output a single score, or four (one per horizon)?

---

## Layer 3: RACP — Regime Aware Bayesian Forward Guidance

**The synthesis layer.** Combines Quant Model output and BH signal with current regime context to produce probability-weighted forward guidance.

### The premise

The Quant Model says what's true *now* (current composite scores, current ratings). BH says what *could* surprise (asymmetric upside candidates). Neither knows about the *regime* — the broader market state that conditions how these signals translate into outcomes.

RACP adds the third dimension: given the current regime, what's the Bayesian probability that each Quant pick continues to outperform? That each BH candidate actually breaks out?

### What RACP would need

#### 1. A regime detector that actually works

Not SMA crossovers (already ruled out). Probably a multi-factor regime classifier combining:

- **Cross-sectional dispersion.** High = stock-pickers' market (Quant + BH should outperform). Low = beta market (passive wins).
- **Sector correlation.** High = risk-on/risk-off binary (regime is dominant). Low = idiosyncratic stories (regime is secondary).
- **Volatility regime.** VIX percentile vs trailing year, term structure.
- **Yield curve shape.** Steepening / inverted / flat as separate regime states.
- **Credit spread state.** IG and HY spreads vs historical distribution.
- **Market breadth.** New highs vs new lows, % above 50-day SMA.

The output isn't "bull/bear" — it's a regime fingerprint that gets matched against historical analogs.

#### 2. Bayesian framework per stock

For each stock in TOP25 + BH watchlist:

- **Prior:** historical forward-return distribution for stocks with similar pillar profiles in similar regimes.
- **Likelihood:** current pillar scores given that prior (how well does this stock match the profile?).
- **Posterior:** updated probability distribution over forward outperformance.

Updates with each new quarterly observation — new data refines next quarter's prior. This is genuinely Bayesian, not just probabilistic relabeling.

#### 3. Synthesis logic

Combines Quant signal + BH signal + regime context into a forward-looking decision:

| Quant | BH | Regime | Decision |
|-------|-----|--------|----------|
| BUY (Strong Buy) | BREAKOUT | RISK-ON | Maximum conviction, full allocation |
| BUY (Buy) | NEUTRAL | LATE-CYCLE | Standard core allocation |
| HOLD | BREAKOUT | RECOVERY | Trim Quant, add to BH bucket |
| SELL | BREAKOUT | RECOVERY | Speculation candidate (BH only) |
| SELL | NEUTRAL | ANY | Avoid |

The table is illustrative — actual logic emerges from Bayesian inference, not hardcoded rules.

#### 4. Forward guidance output

For each decision:
- Probability of outperformance over 1Q / 4Q given current state
- Confidence interval (not a point estimate)
- Explicit reasoning trace: "Quant rates BUY (composite 9.2). BH curve is accelerating (4Q expected +24%). Regime: late-cycle. Bayesian posterior: 68% probability of outperforming benchmark over 4Q with 90% CI of [-12%, +52%]."

### What we've ruled out for RACP

- **Naive probabilistic restatement** (RAQP v1). Doesn't add information.
- **Regime detection by SMA crossovers.** Lagging, unreliable.
- **Direct ML on composite scores → forward returns.** Tested via XGBoost regressor. Overfits to BH-shaped picks. Information leakage between composite construction and return prediction.

### Prerequisites before building

1. **BH must exist first.** RACP is a synthesis layer — pointless to synthesize before the second signal exists.
2. **Working regime detector.** Multi-factor, validated against historical regimes.
3. **Historical regime labeling** of the 1996-2026 backtest. Each quarter needs a regime tag so the Bayesian priors have data to build from.
4. **2Q/3Q/4Q forward return data in parquet.** Same prerequisite as BH.

---

## Zero-Cost Expansion Opportunities

The dashboard operates as a **zero-marginal-cost model** — no paid data subscriptions, no paid API fees beyond free tiers. Every feature must be implementable with free data sources and free LLM access (Gemini free tier, Anthropic starter credits).

This rules out the paid MCP ecosystem (Daloopa, Morningstar, S&P Global, FactSet, Moody's, MT Newswires, LSEG, PitchBook, Chronograph, Egnyte, Aiera). Those are enterprise data products requiring subscriptions.

What remains accessible at zero cost:

### Free data sources (untapped or partially used)

| Source | What it provides | Current usage | Opportunity |
|--------|------------------|---------------|-------------|
| **yfinance** | Equity prices, fundamentals, basic ratios | Primary data source | Already integrated |
| **SEC EDGAR (XBRL)** | Filings, financials, point-in-time data | Used for backtest parquet | Underused for real-time alerts |
| **SEC EDGAR (full-text search)** | Search across all filings for keywords | Not integrated | NEW: keyword-based research |
| **SEC EDGAR (Form 4)** | Insider trading transactions | Not integrated | NEW: insider activity signal |
| **FRED API** | 800k+ economic time series, Treasury yields | Not integrated | NEW: macro context enhancement |
| **Treasury Direct** | Treasury auction results, yield curves | Not integrated | Already covered by FRED |
| **Finnhub free tier** | Earnings data | Used in earnings_data.py | Already integrated |
| **Gemini API free tier** | LLM access, 1500 requests/day | Used in ai_assistant.py | Underused for workflows |
| **Anthropic API starter credits** | Claude access | Not integrated | Could enable specific high-value prompts |

### Inspiration from anthropics/financial-services repo

The repo's MCP connectors are paywalled and out of scope. The repo's **patterns** are free and valuable:

1. **Skill-as-markdown organization** — pull existing AI prompts (Doppelganger narratives, AI Pundit, M&A analysis) from Python files into structured markdown files with frontmatter. Easier to iterate prompts without code changes.

2. **Slash command UX pattern** — `/comps`, `/earnings`, `/screen` as a unified command palette. Power-user efficiency, mobile-friendly future.

3. **Agent workflow patterns** — Earnings Reviewer, Thesis Tracker, Morning Note. These are LLM-driven workflows applied to existing data, not new data sources.

### Proposed zero-cost features (ranked by ROI)

#### Tier A: Quick wins (2-4 hours each)

**AI Earnings Reviewer** *(2-3 hours)*
- Replaces the currently broken Forward Outlook section
- Read EDGAR 8-K via existing integration, send to free Gemini for summary
- Output: "What changed at last earnings and why it matters"
- Cost: Gemini free tier handles this comfortably

**FRED macro integration** *(3-4 hours)*
- Pull Treasury yields, employment, inflation, credit spreads from FRED
- Enhance existing Macro tab with real economic time series
- Enable regime detection inputs for future RACP build
- Cost: $0 (FRED API is free)

**Skill-as-markdown refactor** *(3-4 hours)*
- Extract AI prompts from Python files into structured markdown
- Architecture cleanup, no user-facing change
- Unlocks easier prompt iteration for all future AI features

#### Tier B: Mid-effort high-value (4-7 hours each)

**Slash command interface** *(4-5 hours)*
- Streamlit text input + command parser
- Initial commands: `/screen`, `/comps TICKER`, `/earnings TICKER`, `/thesis TICKER`, `/regime`, `/rebal`
- Centralizes dashboard navigation, sets up mobile UX path

**AI Investment Thesis Builder** *(4-6 hours)*
- Per-stock bull case / bear case / risks / catalysts
- Save to Supabase, track thesis evolution quarterly
- Enforces investment discipline — explicit reasoning before commitment

**EDGAR Form 4 insider trading signal** *(5-7 hours)*
- Free structured data on every insider buy/sell since 2003
- New column in Quant Screener: "recent insider activity"
- Could be a real alternative-data signal

**Morning Note generator** *(5-7 hours)*
- Daily summary combining portfolio + watchlist + screener changes + AI narrative
- GitHub Actions scheduling (free)
- Best ROI feature but most valuable AFTER BH model exists to surface BH signals

#### Tier C: Lower priority (4-6 hours each)

**SEC EDGAR full-text search** *(4-6 hours)*
- Keyword search across all filings
- Use case: "find all stocks mentioning AI capex in latest 10-K"
- Niche but powerful for specific research workflows

**IC Memo generator** *(6-8 hours)*
- Formal one-page investment memo per stock
- PDF export
- Useful for compounders, less so for tactical positions

### Constraints these features must honor

- **No paid subscriptions.** Ever.
- **Free LLM tier only.** Gemini free tier is 1500 req/day — enough for personal use but not multi-user. If usage grows beyond that, find another free tier rather than pay.
- **No vendor lock-in to specific LLMs.** Code should abstract over LLM provider so Gemini, Anthropic, or local models can be swapped.
- **Caching aggressively.** LLM responses to deterministic prompts (e.g., "summarize this 8-K") should cache to disk and reuse. No reason to regenerate the same summary twice.
- **Background jobs over real-time.** Morning Notes generated overnight cost nothing; on-demand LLM calls compete for the free tier rate limit. Default to scheduled generation.

---

## Order of Operations

```
PHASE 1 (immediate):       Quant Model polish
├── ✅ TOP25 dynamic threshold (SB+B=25)
├── ✅ Preset-aware allocation logic
├── ✅ Validated MC floor buttons + alpha display
├── 🟡 Verify SB+B=25 at all universes on live data
└── ⏳ Tab reorder + jump-to-section anchors

PHASE 2 (next):            BH model build
├── ⏳ Add 2Q, 3Q forward returns to parquet
├── ⏳ Test 1Q→4Q return curve linearity
├── ⏳ Feature engineering for BH classifier
├── ⏳ Train + validate classifier out-of-sample
├── ⏳ BH Watch tier in Quant Screener
└── ⏳ BH allocation in Quant Portfolio (0-25%)

PHASE 3 (after BH):        Regime investigation
├── ⏳ Cross-sectional dispersion as regime signal
├── ⏳ Sector correlation as regime signal
├── ⏳ Multi-factor regime classifier
└── ⏳ Historical regime labeling (1996-2026)

PHASE 4 (synthesis):       RACP build
├── ⏳ Bayesian priors framework
├── ⏳ Quant + BH + regime synthesis logic
├── ⏳ Forward guidance UI
└── ⏳ Confidence interval display

PHASE 5 (continuous):      Validation
├── ⏳ Real-money paper trading log
├── ⏳ Out-of-sample test on 2026+ data
└── ⏳ Regime detector calibration

PHASE 6 (parallel track): Zero-cost AI feature layer
├── ⏳ AI Earnings Reviewer (replaces broken Forward Outlook)
├── ⏳ FRED macro integration (feeds RACP regime detection)
├── ⏳ Skill-as-markdown refactor (architecture cleanup)
├── ⏳ Slash command interface
├── ⏳ AI Investment Thesis Builder + tracker
├── ⏳ EDGAR Form 4 insider trading signal
├── ⏳ Morning Note generator (best ROI, post-BH)
└── ⏳ SEC EDGAR full-text search
```

---

## Constraints and Principles

### Things to remember

1. **TOP25 is the validated portfolio size.** Don't deviate without strong empirical reason. The number is non-negotiable.

2. **The no-MC-floor backtest is the validated universe.** $10B+ delivers only +3.17% alpha vs SPY — marginal. $1B+ delivers +5.13% alpha — meaningful. No floor delivers +12.84% — best, but harder to implement live.

3. **Concentration helps stable signals, hurts momentum signals.** Equal-weight m_heavy. 2x SB equal and mature_bull.

4. **HELD beats NEW.** Persistence in TOP25 is positive signal. Don't filter out current TOP25 from BH consideration.

5. **m_heavy is NOT BH.** They catch different points in a stock's lifecycle.

6. **Cliff detection for SB/Buy split.** Top 25 = SB+Buy combined. Within those 25, the largest gap (≥0.5 absolute AND ≥2x avg gap) separates Strong Buy (above) from Buy (below). If no clear cliff, all 25 = Buy. This is correct behavior — compressed score regimes have no clear elite tier.

7. **Historical validation isn't live performance.** Survivorship bias is real, especially below $1B. Transaction costs (~1.2%/yr at quarterly rebalance) and tax drag (1-3%/yr for short-term gains) reduce realized alpha by 2-4%/yr below the backtest number.

### Things to avoid

- **Algorithmic regime detection by SMA crossover.** Doesn't work, already tested.
- **Continuous score weighting.** Adds zero alpha. Tier-based concentration is what matters.
- **Excluding current TOP25 from BH.** Removes the persistence signal.
- **Probabilistic relabeling without new information.** RAQP v1 failure mode.
- **Mid-cap floor between $1B and $10B without testing.** The data only validates the three tested levels (no floor, $1B, $10B). Untested values shouldn't appear in production UI.

---

## Open Strategic Questions

1. **What's the practical MC floor for live trading?** The no-floor backtest includes names too illiquid to actually trade. Probably $500M-$1B is the realistic floor for retail execution. Worth testing $500M as a fourth validated tier.

2. **How does BH allocation interact with Quant Portfolio?** Is BH a separate sleeve (75% Quant / 25% BH) or an overlay that adjusts Quant weights? The cleaner architecture is separate sleeves, but overlap (a stock that's both TOP25 and BH-flagged) needs explicit handling.

3. **Should the dashboard support multiple parallel strategies?** Currently one set of weights → one TOP25. Could support 50% equal-weight + 50% m_heavy as a blended portfolio. Not validated as superior to single-preset, but might reduce drawdown variance.

4. **Exit strategy reverse engineering.** For historical winners, did rating drop BEFORE price peak, AFTER, or coincident? Determines whether HOLD_UNTIL_HOLD captures gains or gives them back. Open question.

5. **Sector-relative scoring.** Currently optional toggle. Never separately backtested vs universe-wide scoring. Could be a free +1-2% CAGR if it helps, or noise.

6. **Real-time vs end-of-quarter rebalancing.** Backtest assumes Q1/Q2/Q3/Q4 boundary rebalancing. Live trading could rebalance on any day. Does mid-quarter information warrant intra-quarter adjustment, or is the quarterly cadence the whole strategy?

---

## Living Document Note

This roadmap captures architectural intent at this snapshot. Update as:
- Backtests rule things in or out
- Live performance diverges from validated expectations
- New free data sources become available (FRED endpoints, EDGAR coverage improvements, etc.)
- Practical execution constraints emerge
- Free LLM tier limits change (Gemini, Anthropic, others)

**The dashboard is a zero-cost personal tool.** No feature added here should require ongoing paid subscriptions. Paid MCP connectors, premium data feeds, and paid LLM tiers are explicitly out of scope. If a feature would require ongoing spend, it's not in scope unless explicitly approved as a separate paid tier.

The goal is not to predict the final shape of the system but to keep the major architectural decisions traceable. Future-Bradley should be able to read this and understand WHY the architecture is what it is, not just WHAT it is.
