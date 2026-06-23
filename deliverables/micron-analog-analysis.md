# Micron (MU) Analog "What Happens Next" Simulation

_Generated 2026-06-22 from `daily_panel_CLEAN.parquet` (2011-01-03 -> 2026-06-17, 1210 tickers). Earnings dates from EDGAR 10-K/10-Q filing calendar._

## MU current run

- As of **2026-06-17**, MU adj close = **$1043.19**.
- **Trailing-252-trading-day (52-week) total return = 773%** (price 252 sessions ago = $119.55).
- This is consistent with external research (~+880% over 52wk); the exact 252-session window gives +773%. MU sits in the **>=+500%** bucket and the tight **+600% to +1000%** band below.
- Liquidity: MU 20-day median dollar volume is ~$49.3B/day (far above the $5M floor) -- a highly liquid mega-cap, unlike many small-cap moonshots in the cohort.

## Method

- For every (ticker, date) in the panel, trailing-252d total return computed on adjusted close.
- Liquidity filter: adj close > $5 AND 20-day median dollar volume >= $5M (volume from `stage4_output/prices_long.parquet`).
- De-overlap: at most one observation per ticker per ~quarter (63 trading days) so a single moonshot can't dominate a bucket.
- Forward total returns at +21/+63/+126/+252 trading days, strictly forward (no look-ahead). Max forward drawdown measured over the next 252 sessions vs running peak.
- Next-earnings reaction: first EDGAR 10-K/10-Q filing date strictly after the observation date; earn-day return and ret[-1,+1] around that print.

## Forward outcomes by bucket

Each cell = **median / mean / % positive**.

| Trailing-252d bucket | N | Fwd +21d (1mo) | Fwd +63d (3mo) | Fwd +126d (6mo) | Fwd +252d (12mo) |
|---|---|---|---|---|---|
| >=+100% | 5110 | 1.2% / 2.2% / 54.3% | 3.1% / 5.4% / 56.2% | 4.6% / 10.1% / 57.1% | 3.5% / 17.5% / 53.8% |
| >=+150% | 2218 | 1.3% / 3.1% / 54.1% | 3.0% / 7.8% / 55.5% | 5.6% / 13.4% / 57.4% | 3.7% / 22.9% / 53.7% |
| >=+200% | 1247 | 0.7% / 3.2% / 51.6% | 3.2% / 8.7% / 56.5% | 5.5% / 15.4% / 57.1% | 4.0% / 27.8% / 52.9% |
| >=+300% | 536 | 0.8% / 3.5% / 52.4% | 3.4% / 9.3% / 56.2% | 8.6% / 19.8% / 58.2% | 8.0% / 37.0% / 55.1% |
| >=+500% | 181 | -1.9% / 2.9% / 45.9% | 2.3% / 11.5% / 54.7% | 14.0% / 24.7% / 62.3% | 18.4% / 46.3% / 57.1% |
| BAND +600..1000% (MU-like) | 118 | -1.8% / 4.3% / 45.8% | 2.4% / 13.3% / 51.8% | 14.4% / 26.1% / 63.6% | 29.0% / 50.5% / 60.2% |

### Forward downside (next 252 sessions)

| Bucket | N | Median maxDD | Worst maxDD | % with >20% DD | % with >40% DD |
|---|---|---|---|---|---|
| >=+100% | 5110 | -34.9% | -94.3% | 87.0% | 38.3% |
| >=+150% | 2218 | -39.0% | -93.0% | 91.8% | 47.7% |
| >=+200% | 1247 | -41.4% | -93.0% | 94.3% | 52.8% |
| >=+300% | 536 | -42.8% | -93.0% | 95.7% | 57.1% |
| >=+500% | 181 | -46.4% | -93.0% | 96.7% | 70.2% |
| BAND +600..1000% | 118 | -44.5% | -93.0% | 97.5% | 70.3% |

## Next-earnings reaction after a MU-like run

Distribution of **ret[-1,+1]** around the first earnings print after the run (day-before close -> day-after close).

| Bucket | N | Median | Mean | % positive | 10th pct | 90th pct |
|---|---|---|---|---|---|---|
| >=+100% | 4995 | 0.3% | 0.6% | 52.8% | -8.3% | 10.0% |
| >=+150% | 2151 | 0.1% | 0.8% | 51.2% | -8.9% | 11.4% |
| >=+200% | 1206 | 0.0% | 0.9% | 50.2% | -9.8% | 12.7% |
| >=+300% | 503 | -0.2% | 1.4% | 49.3% | -10.2% | 15.0% |
| >=+500% | 162 | -0.1% | 2.2% | 50.0% | -11.6% | 18.3% |
| BAND +600..1000% | 108 | -0.5% | 0.7% | 49.1% | -13.6% | 15.8% |

## Interpretation & verdict

**MU's +773% trailing-52wk run is an extreme historical analog.** Using the most comparable cohort (N=118):
- Forward **1mo**: median -1.8%, 45.8% positive.
- Forward **3mo**: median 2.4%, 51.8% positive.
- Forward **6mo**: median 14.4%, 63.6% positive.
- Forward **12mo**: median 29.0%, mean 50.5%, 60.2% positive.
- Downside: median forward maxDD -44.5%; 97.5% of analogs suffered a >20% drawdown and 70.3% a >40% drawdown within 12 months.
- **Next earnings**: ret[-1,+1] median -0.5%, mean 0.7%, 49.1% positive (10th/90th pct -13.6% / 15.8%).

### Verdict: HOLD the core, but expect a wild ride — and don't add into the print

The analog evidence does **not** say "sell" — it says "hold a position you can stomach drawing down 40%+." Three findings drive this:

1. **Drift is still positive, not mean-reverting.** Even at the most extreme +500% / +600-1000% cohorts, forward 6mo and 12mo medians are *higher* than the milder buckets (+14% / +18-29% at 12mo, 57-60% positive). Momentum does **not** flip to mean-reversion after a parabolic 52-week run; the central tendency stays up and to the right. This is the opposite of the "it's run too far, it must revert" thesis.

2. **But the near term is a coin flip and the path is brutal.** At MU-like magnitudes the forward **1-month median is negative** (-1.8%), only ~46% of cases are up after a month, and the 3mo median is barely positive. The 12-month *mean* (+50%) sits far above the *median* (+29%), meaning the positive expectancy is carried by a right tail of continued moonshots — the typical outcome is more muted. Critically, **97% of these analogs drew down more than 20% and 70% drew down more than 40%** within the following year (median trough -44%, worst -93%). A MU-like name almost always gives back a large chunk at some point even when it ends the year higher.

3. **The next print is a non-edge, fat-tailed event.** After a MU-sized run, the very next earnings reaction (ret[-1,+1]) is a **coin flip** (median ≈ 0%, ~49-50% positive) with **fat tails that widen as the run gets more extreme** (10th/90th pct -14% / +16% in the MU-like band; the >=+500% bucket reaches +18% on the upside). There is no systematic post-run earnings *edge* in either direction — but the dispersion is large, so a single print can move MU ±15% with roughly even odds.

**Bottom line for Wednesday and beyond:** The history of stocks that ran like MU favors **holding the core position** (forward drift is positive, mean-reversion does not dominate), but it gives **no edge for holding *extra* through the print** — the earnings reaction is symmetric and fat-tailed. The prudent play the analogs support is: keep the core, **trim any oversized/leveraged exposure before the print** to survive the ~±14% earnings tail and the near-certain (>40% probability) >40% drawdown somewhere in the next 12 months, and treat post-print weakness as noise rather than a thesis-breaker unless fundamentals change. Hold — but size for a 40% drawdown, and don't press the bet into Wednesday.
