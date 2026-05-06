# Quant Strategy: Methodology & Engineering Journey

*Last updated: May 6, 2026*

This document walks through the full engineering journey behind the Quant Strategy 
backtest: what we tried, what failed, what worked, and why the result is trustworthy.

## TL;DR

**Result**: A 5-pillar quantitative scoring strategy applied to a 1,326-ticker universe, 
backtested with true point-in-time SEC EDGAR fundamentals over 86 quarterly checkpoints 
(2005-2026), produced:

- $100 → **$2,182** vs SPY $100 → **$572** (4.4x outperformance)
- 75% win rate at the quarterly level
- +5.08% average quarterly return vs SPY's +2.33%
- Max drawdown of -23.78% vs SPY's -23.32% (similar)

68 quarters had qualifying data (2009-2026). Pre-2009 had insufficient XBRL coverage 
for fundamentals-based scoring.

## Why This Was Hard

Building a real point-in-time backtest at zero ongoing cost is structurally difficult. 
Professional quant funds pay $50K+/year for Compustat or Refinitiv specifically because 
the data quality challenges are real.

Free data sources have known issues:
- **yfinance fundamentals**: Current snapshot only, baked-in lookahead bias
- **SEC companyfacts API**: Aggregated facts only, retains most recent restatement
- **Free fundamentals APIs**: Either expensive at scale or rate-limited to uselessness

We solved this by parsing the structure of the SEC companyfacts JSON correctly — 
finding that while it appears restated, each `(metric, period)` entry preserves its 
original `filed_date`. By filtering to `filed_date <= checkpoint_date`, we get true 
point-in-time data. This is the key insight that made the project feasible at zero cost.

## The Failed Path: Swing Trader (Discontinued)

Before validating the quant strategy, we extensively tested a swing trader strategy 
based on price-action signals (ATR-based entries/exits, multi-week holding). Six variants 
were tested:

| Variant | Description | Result |
|---|---|---|
| H1A | 1x ATR stop, 2x ATR target | Failed (rate-limited, bad data) |
| H1B | 2x ATR stop, 3x ATR target | $100 → $537 (vs $876 buy-and-hold) |
| H-Trail | Trailing stops | $100 → $207 |
| Regime-Aware | Bull/bear routing | $100 → $177 |
| PEAD | Post-Earnings Drift | -3.06% annualized vs SPY |
| Factor Rotation | Multi-factor AQR-style | Failed |

**Conclusion**: Price-action-only signals at retail data tier do not generate alpha. 
The swing trader system was eliminated. The bear-only variant was deferred (deferred 
until SPY confirms a bear regime).

This negative result is informative — it confirmed that the quant strategy's edge 
comes from fundamentals, not technical signals.

## What Worked: The 5-Pillar Quant System

### The Pillars

Each stock receives a score in five categories, then averaged into a composite 0-12 score:

1. **Momentum** (price-based)
   - Multi-timeframe price returns (1mo, 3mo, 6mo, 12mo)
   - Weighted by recency
   - Sector-relative ranking

2. **Valuation** (fundamentals)
   - P/E, P/B, EV/EBITDA
   - Compared to sector median
   - Lower is better

3. **Growth** (fundamentals)
   - TTM revenue growth
   - YoY earnings growth
   - Higher is better

4. **Profitability** (fundamentals)
   - Operating margin
   - ROE, ROA
   - Higher is better

5. **Financial Health** (fundamentals)
   - Debt/Equity ratio
   - Current ratio
   - Interest coverage
   - Stability is better

### Rating Tiers

| Composite Score | Rating | Approximate % of Universe |
|---|---|---|
| 9.0 - 12.0 | Strong Buy | Top 8-12% |
| 8.0 - 9.0 | Buy | Next 12-17% |
| 6.0 - 8.0 | Hold | Middle 45-55% |
| 5.0 - 6.0 | Sell | Next 12-17% |
| 0.0 - 5.0 | Strong Sell | Bottom 8-12% |

### The Backtest Protocol

1. Score the universe at every quarter-start
2. Take top 10 by composite score
3. Buy at close (1/10 of capital each, $10K each from $100K)
4. Hold 63 trading days (~one quarter)
5. Mark to market at end of hold period
6. Compare returns to SPY held over the same period

### Point-in-Time Discipline

Critical: At each checkpoint date `D`, fundamentals are filtered to entries with 
`filed_date <= D`. This means:
- A Q3 2018 fundamentals filing isn't visible for a backtest dated June 2018
- 2018-11 ASC 606 restatements of 2016 revenue aren't used for 2017 backtests
- Apple's 2020 10-K isn't available for 2019 scoring

This is the difference between a real backtest and snake oil.

## Engineering Journey: What Broke

The project hit several critical bugs before validation. Each is worth documenting 
because they're common pitfalls:

### Bug 1: TypeError silently zeroing fundamentals quality

**Symptom**: Every ticker showed `data_quality_score: 0` despite the EDGAR cache having 
real data.

**Cause**: `get_fundamentals_at_date` accepted both `datetime` and `date` objects but 
internal comparisons (`filed_dt > target_dt`) raised `TypeError` when comparing them. 
The exception was caught silently in a generic `except` block and treated as "no data".

**Fix**: Force `target_dt` to be a pure `date` object on entry to all comparison functions.

**Lesson**: Generic except blocks hide real bugs. When backtest results look implausibly 
bad, suspect the error handler before suspecting the data.

### Bug 2: Pre-IPO ticker noise

**Symptom**: Backtest hit yfinance fallback for ABBV, ABNB, AFRM, etc. in 2010 with 
"possibly delisted" errors. Slow and noisy.

**Cause**: Universe contained 1,326 tickers existing today, many of which IPO'd 
post-2010. The backtest tried to score them at 2009-2010 dates where they had no data.

**Fix**: Pre-compute each ticker's first-available date from the parquet price cache. 
Filter universe to listed tickers BEFORE scoring at each checkpoint. Skip pre-IPO 
tickers silently rather than falling through to yfinance.

**Result**: Per-checkpoint scoring time dropped from ~10 minutes to ~5 minutes.

### Bug 3: GitHub Actions 6-hour timeout

**Symptom**: Workflow auto-bailed at 5h30m, completing only 6 of 86 checkpoints.

**Cause**: 70+ checkpoints × 5 minutes each = 5.8 hours of compute. GitHub's 6-hour 
limit on free runners is hard.

**Fix**: Move execution to local machine with no timeout. Add intermediate saves every 
5 checkpoints. Single 6.5-hour overnight run completed all 86 checkpoints.

**Lesson**: GitHub Actions is for CI/CD, not multi-hour scientific computing.

### Bug 4: LFS bandwidth exhaustion

**Symptom**: After 4 workflow runs, LFS pulls started failing.

**Cause**: 270 MB EDGAR cache via Git-LFS = 1.08 GB across 4 runs, hitting free tier's 
1 GB/month limit.

**Resolution**: Local execution avoids LFS entirely. Workflow approach is now reserved 
for occasional verification runs.

## Why The Result Is Trustworthy

### Methodological strengths

1. **True point-in-time data** — Every fundamental is filtered by `filed_date <= checkpoint`
2. **No look-ahead bias** — Restatements aren't used retroactively
3. **Universe filtering by IPO date** — Don't score stocks that didn't exist
4. **86 checkpoints over 21 years** — Not a single year cherry-pick
5. **Multiple market regimes** — 2008 recovery, 2020 COVID, 2022 inflation, 2025 bull

### Acknowledged limitations

1. **Survivorship bias** — Universe = today's tickers. Excludes bankrupt/delisted companies. 
   Likely inflates 21-year returns by 1-3pp annualized.
2. **Pre-2009 sparse data** — XBRL adoption was limited. 14 quarters had qualified=0.
3. **No transaction costs** — Real-world friction estimated at 0.1-0.3% per quarter.
4. **No risk overlay** — System buys top 10 every quarter regardless of conditions.
5. **Equal-weight implementation** — Doesn't model fractional shares or intra-quarter rebalancing.

### Statistical confidence

68 quarterly returns is meaningful but not definitive. Different starting periods 
or rebalance frequencies could shift results 5-15pp. The strategy variants project 
(in progress) tests this by varying entry/exit logic and weighting schemes.

## What's Next

### Strategy Variants (In Progress)

Currently running an extended backtest with 5 logic variants × 2 weighting schemes:

1. **Concentrated Quality** — Strong Buy only, sell on Hold or below
2. **Diversified Buy-and-Above** — Strong Buy + Buy, sell on Sell or below
3. **Aggressive Exit** — Strong Buy + Buy, sell on any downgrade to Hold
4. **Patient Holder** — Strong Buy + Buy, sell only on Strong Sell
5. **Top-N Score** — Top 20 by raw score, sell when out of top 30

Each variant runs in equal-weight AND score-weighted versions.

### Future Work

- **Forward validation** — Monthly cron running strategy on current data, tracking 
  out-of-sample performance over 6-12 months
- **Risk overlay** — Test adding regime detection (above/below 200-day MA) to halt 
  trading in confirmed bear markets
- **Transaction cost model** — Add realistic slippage assumptions
- **Sector neutrality** — Test forcing equal sector weights to remove sector concentration risk

## References

- SEC EDGAR API: https://www.sec.gov/edgar/sec-api-documentation
- yfinance library (price data): https://github.com/ranaroussi/yfinance
- Streamlit Community Cloud (deployment): https://streamlit.io/cloud
- Repository: github.com/bradleygpt/quant-dashboard-pro

---

*Bradley Hartnett | bradleygpt/quant-dashboard-pro*
