"""
Help, How-To, and Glossary Content
Centralized documentation rendered in the Help tab.
"""

GETTING_STARTED = """
**Welcome to Quant Strategy Dashboard Pro.** This tool combines fundamental factor analysis, technical setups, and AI-powered research to help you find and evaluate investment opportunities.

**Quick Start:**

1. **Home Tab** -- Get a market overview and your portfolio snapshot.
2. **Screener Tab** -- Browse the universe of scored stocks. Filter by sector, market cap, or rating.
3. **Stock Detail Tab** -- Deep-dive into any stock: fair value, buy point, earnings history, AI analysis.
4. **Portfolio Tab** -- Upload a Fidelity CSV or enter holdings manually. Save unlimited portfolios. Get prescriptive recommendations.
5. **Doppelganger Tab** -- See which historical stock setups your current picks resemble.
6. **Swing Trader Tab** -- Find short-term technical setups (3-10 day trades).

**Recommended workflow:**

- Start at Home for the daily snapshot.
- Use Screener or Advanced Screener to find candidates.
- Click into Stock Detail for any name you want to research.
- Use Portfolio tab to track and optimize your actual positions.
"""

PILLAR_METHODOLOGY = """
**The 5-Pillar Quant Score (0-12 scale)**

Every stock is evaluated across five fundamental pillars. Each pillar is graded A through F and contributes to a composite score. Default weights are equal at 20% each, customizable via the sidebar.

**1. Valuation (20%)**
How cheap is the stock relative to its earnings, sales, book value, and growth?
- Forward P/E, Trailing P/E, PEG Ratio
- Price/Sales, Price/Book, EV/EBITDA

**2. Growth (20%)**
How fast is the company expanding?
- Revenue growth (QoQ and YoY)
- Earnings growth (quarterly)
- Forward earnings expectations

**3. Profitability (20%)**
How efficient is the business at converting revenue to profit?
- Gross Margin, Operating Margin, Net Margin
- Return on Equity (ROE)
- Free Cash Flow margin

**4. Momentum (20%)**
How is the stock trending across multiple timeframes?
- 1-month, 3-month, 6-month, 12-month returns
- Risk-adjusted momentum scores

**5. EPS Revisions (20%)**
Are analysts raising or lowering estimates?
- Recent revision direction
- Analyst count and dispersion
- Surprise history

**Sector-Relative vs Absolute Scoring:**
- *Sector-Relative* (default): Stocks are graded against peers in their sector. A tech stock is compared only to other tech stocks. Useful for finding the best in each sector.
- *Absolute*: Stocks are graded against the entire universe. Useful for cross-sector comparison and identifying truly elite names.

Toggle in the sidebar to switch.
"""

RATING_SYSTEM = """
**Rating System**

Stocks are assigned an overall rating based on their composite score:

| Rating | Score | Interpretation |
|---|---|---|
| Strong Buy | 9.0+ | Top-tier across multiple pillars. High conviction. |
| Buy | 8.0-9.0 | Above-average across most pillars. Strong candidate. |
| Hold | 6.0-8.0 | Mixed signals. Wait for better entry or fundamentals. |
| Sell | 5.0-6.0 | Below-average. Consider exiting. |
| Strong Sell | <5.0 | Multiple weak pillars. Avoid or sell. |

**Important:** These are quantitative ratings based on backward-looking and current data. They do not account for unique catalysts, management changes, or upcoming events. Always combine with qualitative judgment.
"""

FAIR_VALUE = """
**Fair Value Analysis (v4 Methodology)**

The Stock Detail tab shows a composite Fair Value estimate combining four methods:

1. **PEG-Based (30% weight)** -- Fair P/E = Growth Rate. So a 25%-growth company should have a P/E of ~25.
2. **Quality-Adjusted Relative (25% weight)** -- Compares the stock's P/E to its sector peers, adjusted for quality (margins, ROE).
3. **Earnings-Based Cap (25% weight)** -- Caps fair value at a reasonable multiple of earnings to prevent unrealistic estimates for hyper-growth names.
4. **Analyst Target (20% weight)** -- Average of analyst price targets, capped at 30% premium to current price.

**Premium/Discount %**: How far above or below fair value the stock is trading. Negative = trading at a discount (potential value).

**Verdict:**
- *Deeply Undervalued*: 30%+ below fair value
- *Undervalued*: 10-30% below fair value
- *Fairly Valued*: Within 10%
- *Overvalued*: 10-30% above fair value
- *Significantly Overvalued*: 30%+ above fair value
"""

BUY_POINT = """
**Buy Point Analysis**

The Stock Detail tab shows a recommended Buy Point combining four signals:

1. **Bollinger Lower Band (30%)** -- Price tends to revert toward the mean from extremes.
2. **5% Below 50-SMA (25%)** -- A common technical entry zone for trend-following.
3. **Support Level (20%)** -- Recent local lows where buying interest has emerged.
4. **Fair Value Discount (25%)** -- Price-to-fair-value adjusted entry point.

The composite Buy Point gives you a level where multiple methodologies agree. **This is not a guaranteed bottom** -- it's where risk/reward turns favorable.
"""

SWING_TRADER = """
**IBD-Inspired Swing Trader**

Combines fundamental quality (the 5-pillar score) with technical setup quality to find short-term trade ideas (3-10 day holds).

**Six Components (Swing Score, 0-100):**

| Component | Weight | What it measures |
|---|---|---|
| 21-EMA Proximity | 25% | Best when price is at or just above the 21-day exponential MA |
| Trend Direction | 20% | 21-EMA must be sloping upward |
| Volume | 15% | Above-average volume + more up than down days |
| RSI | 15% | Sweet spot is 35-55 (oversold bounce zone) |
| Pullback + Bounce | 15% | Pulled back 3-8% then closing higher |
| Regression Channel | 10% | Best near lower band of 20-day channel |

**Combined Score:** 60% Swing Technical + 40% Quant Fundamental

Each candidate gets a full trade plan: entry, profit target (5-10% scaled by ATR), stop loss (3-5%), and risk/reward ratio.
"""

DOPPELGANGER = """
**Doppelganger Analysis**

Finds historical stock setups that resemble the current stock based on a fundamental fingerprint. Compares 30+ curated historical analogs across all sectors.

**Fingerprint Dimensions:**
- P/E ratio (15% weight)
- P/S ratio (15%)
- Revenue growth (20%)
- Profit margin (10%)
- Gross margin (10%)
- 12-month momentum (15%)
- Return on Equity (10%)
- Market cap (5%)

**How to use:**
1. Default: Same-sector matching (recommended).
2. Optional: Filter by theme tag (bubble-era, AI, platform-shift, etc.).
3. Each match shows context, narrative, what happened next, and the lesson.

**Important caveat:** History rhymes but doesn't repeat. Use these as perspective, not prophecy. The future of any stock depends on factors not captured in financial fingerprints.
"""

MONTE_CARLO = """
**Monte Carlo Simulation v2**

Projects portfolio outcomes over a chosen horizon using Geometric Brownian Motion with realistic constraints:

1. **Mean Reversion (60/40)** -- Blends 60% long-term equity premium with 40% trailing momentum. Prevents "this stock 5x'd last year so it'll 5x again" projections.
2. **Return Cap** -- Maximum 40% annualized return per holding. Stops outliers from dominating.
3. **Volatility Floors** -- Market-cap-tiered minimums. Micro-caps get 60% vol floor, large caps 20%.
4. **Scenario Selector** -- Bull (+8% drift), Base (neutral), Bear (-12%), or Blended (25/50/25 weighted).
5. **Log-Normal (GBM)** -- Proper geometric compounding with variance drag.

The simulation runs 1,000-10,000 paths and shows the distribution: 5th, 25th, 50th, 75th, 95th percentiles, plus probability of various outcomes.
"""

PGI = """
**Potential Growth Indicator (PGI)**

Inspired by Motley Fool's framework. Measures the ratio of money market fund assets to total US stock market cap.

**Formula:** Money Market Assets / Total US Stock Market Cap × 100

**Interpretation:**
- **Above 11.5%** -- High cash on sidelines. Investors are fearful. Contrarian bullish signal.
- **9.5% to 11.5%** -- Neutral range.
- **Below 9.5%** -- Low cash on sidelines. Investors are greedy. Be more selective.

Historical range: 8-20%. Spiked to 47% during the 2009 crisis.

**Note:** Money market figure is updated manually (~$6.7T as of early 2026). Update sentiment.py when ICI releases new data.
"""

GLOSSARY = [
    {"term": "Composite Score", "definition": "Weighted average of 5 pillar scores. Range 0-12. Higher is better."},
    {"term": "Pillar", "definition": "A category of fundamental metrics (Valuation, Growth, Profitability, Momentum, EPS Revisions)."},
    {"term": "Fair Value", "definition": "Estimated intrinsic value combining 4 methodologies. Compared to current price gives Premium/Discount %."},
    {"term": "Buy Point", "definition": "Recommended entry price where multiple technical and valuation signals align."},
    {"term": "PEG Ratio", "definition": "P/E divided by earnings growth rate. PEG of 1.0 means fairly priced for growth. <1.0 = potentially undervalued."},
    {"term": "PEG", "definition": "Same as PEG Ratio."},
    {"term": "P/E", "definition": "Price-to-Earnings ratio. Stock price divided by earnings per share. Lower can indicate value, higher can indicate growth expectations."},
    {"term": "P/S", "definition": "Price-to-Sales ratio. Useful for unprofitable companies where P/E is meaningless."},
    {"term": "P/B", "definition": "Price-to-Book ratio. Stock price relative to net asset value per share. Used for banks, insurance, real estate."},
    {"term": "EV/EBITDA", "definition": "Enterprise Value to EBITDA. A capital-structure-neutral valuation metric."},
    {"term": "ROE", "definition": "Return on Equity. Net income / shareholder equity. Measures profitability efficiency."},
    {"term": "ROA", "definition": "Return on Assets. Net income / total assets. Measures asset utilization."},
    {"term": "FCF", "definition": "Free Cash Flow. Operating cash flow minus capital expenditures. The 'real' cash available to shareholders."},
    {"term": "Gross Margin", "definition": "Revenue minus cost of goods sold, divided by revenue. Pricing power indicator."},
    {"term": "Operating Margin", "definition": "Operating income divided by revenue. Core business profitability."},
    {"term": "Net Margin", "definition": "Net income divided by revenue. Bottom-line profitability after all expenses."},
    {"term": "Momentum", "definition": "Recent price performance across multiple timeframes (1M, 3M, 6M, 12M). Used to identify trends."},
    {"term": "EPS", "definition": "Earnings Per Share. Net income divided by shares outstanding."},
    {"term": "EPS Revisions", "definition": "Changes in analyst earnings estimates. Upward revisions = bullish, downward = bearish."},
    {"term": "Beat / Miss", "definition": "Whether reported EPS exceeded (beat) or fell short of (missed) consensus analyst estimates."},
    {"term": "Surprise %", "definition": "(Reported EPS - Estimated EPS) / Estimated EPS × 100. Positive = beat, negative = miss."},
    {"term": "Strong Buy / Buy / Hold / Sell / Strong Sell", "definition": "Rating tiers based on composite score thresholds. See Rating System above."},
    {"term": "Sector-Relative Scoring", "definition": "Grading stocks within their sector peer group. Default mode."},
    {"term": "Absolute Scoring", "definition": "Grading stocks against the entire universe. Useful for cross-sector comparisons."},
    {"term": "Composite Fair Value", "definition": "Weighted average of 4 fair value methodologies (PEG, relative, earnings cap, analyst target)."},
    {"term": "21-EMA", "definition": "21-day Exponential Moving Average. Primary trend line used by IBD swing traders."},
    {"term": "50-SMA / 200-SMA", "definition": "50-day and 200-day Simple Moving Averages. Standard medium and long-term trend indicators."},
    {"term": "RSI", "definition": "Relative Strength Index. Oscillator between 0-100. Above 70 = overbought, below 30 = oversold."},
    {"term": "ATR", "definition": "Average True Range. Volatility measure used to size stops and targets."},
    {"term": "Bollinger Bands", "definition": "Price channels at 2 standard deviations from a moving average. Mean reversion signal at extremes."},
    {"term": "Regression Channel", "definition": "Linear trend line with parallel boundaries at 2 std dev. Identifies normal trading range."},
    {"term": "Buffett Indicator", "definition": "Total market cap divided by GDP. Above 100% historically suggests overvalued market. Currently elevated."},
    {"term": "Fear & Greed Index", "definition": "Composite sentiment indicator (0-100). Below 25 = extreme fear (contrarian buy), above 75 = extreme greed (contrarian sell)."},
    {"term": "VIX", "definition": "Volatility Index based on S&P 500 options. Above 30 = high fear, below 15 = complacency."},
    {"term": "Yield Curve", "definition": "Difference between long-term and short-term Treasury yields. Inversion (negative) historically precedes recessions."},
    {"term": "PGI", "definition": "Potential Growth Indicator. Money market assets / US market cap. Higher = more cash on sidelines = contrarian bullish."},
    {"term": "Drawdown", "definition": "Decline from peak to trough. Maximum drawdown is the worst loss over a period."},
    {"term": "Sharpe Ratio", "definition": "Risk-adjusted return. (Return - Risk-free rate) / volatility. Higher is better."},
    {"term": "Beta", "definition": "Stock's volatility relative to the market. Beta of 1.0 = market, >1 = more volatile, <1 = less volatile."},
    {"term": "Concentration / HHI", "definition": "Herfindahl-Hirschman Index. Sum of squared sector weights. <0.15 = diversified, 0.15-0.25 = moderate, >0.25 = concentrated."},
    {"term": "Doppelganger", "definition": "Historical stock situation that resembles a current stock based on fundamental fingerprint."},
    {"term": "Mean Reversion", "definition": "Tendency of metrics to return to long-term averages over time. Used in Monte Carlo to dampen extreme projections."},
    {"term": "GBM (Geometric Brownian Motion)", "definition": "Stochastic process used in financial modeling to project price paths with realistic compounding."},
    {"term": "Tax Loss Harvesting", "definition": "Selling losing positions to offset gains for tax purposes. Wash sale rule prevents repurchase within 30 days."},
    {"term": "Wash Sale", "definition": "IRS rule prohibiting claiming a tax loss if you buy back the same security within 30 days."},
]


BEST_PRACTICES = """
**Best Practices**

**Daily routine (5-10 minutes):**
1. Check the Home tab for market sentiment and your portfolio snapshot.
2. Review the top 3 actionable recommendations for your portfolio.
3. Scan the Sector Quality Distribution to see where opportunities are concentrated.

**Weekly research (30-60 minutes):**
1. Run the Screener with your preferred preset (e.g., Foundational Stocks, Momentum Leaders).
2. Click into 3-5 candidates in Stock Detail.
3. Run the AI Research Note on the top 1-2 to get a written thesis.
4. Check Doppelganger matches for historical context.
5. Run the Swing Trader scan to find short-term setups.

**Before any trade:**
1. Check Fair Value -- am I paying a reasonable price?
2. Check Buy Point -- is this a good entry zone?
3. Check Doppelganger -- are there any historical analogs that should give me pause?
4. Run AI Research Note for a final sanity check.
5. Size the position relative to existing portfolio (no single position above 15%).

**Portfolio management:**
1. Save your portfolio after every trade.
2. Run Monte Carlo monthly to see updated probability distributions.
3. Review Prescriptive Recommendations weekly.
4. Use AI Portfolio Advisor monthly for strategic rebalancing.

**What this tool is NOT:**
- A trading signal service. It does not tell you when to buy or sell precisely.
- Financial advice. All decisions are yours.
- Predictive. Quant scores reflect current and past data only.
- A substitute for understanding the businesses you own.

**Risk reminders:**
- Concentration risk: No single position should exceed 15-20% of portfolio.
- Sector risk: No single sector should exceed 40-50% of portfolio.
- Beware momentum traps -- high recent returns don't predict future returns.
- Beware value traps -- cheap stocks can stay cheap or get cheaper.
- The market can stay irrational longer than you can stay solvent.
"""

DATA_SOURCES = """
**Data Sources & Limitations**

**Primary source:** Yahoo Finance via `yfinance` library.
- Free, no API key required.
- Updated daily during market hours.
- Some data fields can be incomplete or delayed for smaller stocks.
- Rate limits apply; cache rebuilds take 12-18 minutes for the full universe.

**Macro data:** Static values updated manually in `macro.py` (CPI, unemployment, ISM PMI, GDP, Fed funds rate).

**Money Market data (PGI):** Manually updated. Source: ICI weekly reports.

**Sentiment data:** Computed from market data (VIX, breadth, indices, Buffett Indicator).

**Historical Doppelganger database:** Hand-curated, 30+ entries.

**Known limitations:**
- yfinance can be rate-limited or temporarily unavailable.
- Some international stocks have incomplete fundamentals.
- Earnings history limited to ~5 quarters from primary source; older periods are approximated from annual data.
- ETF data is partial (not all ETF metrics available).
- Macro indicators require manual periodic updates.

**For better data quality (paid options):**
- Polygon ($29-200/mo): Real-time data, full options chain, 5+ years of fundamentals.
- Alpha Vantage ($50/mo): Better macro, fundamentals, earnings calendar.
- IEX Cloud / Finnhub: Mid-tier alternatives.
- FactSet / Bloomberg: Institutional grade (very expensive).
"""

DISCLAIMER = """
**Important Disclaimers**

This tool is provided for **informational and educational purposes only**. It does not constitute investment advice, financial advice, trading advice, or any other sort of advice.

**You should:**
- Not rely solely on this tool for investment decisions.
- Conduct your own due diligence before any trade.
- Consult with a licensed financial advisor for personalized advice.
- Understand that past performance does not predict future results.
- Recognize that all investments carry risk of loss.

**The creators and operators of this tool:**
- Make no warranties about the accuracy, completeness, or timeliness of data.
- Are not registered investment advisors.
- Will not be liable for any losses arising from use of this tool.
- May hold positions in stocks discussed.

**By using this tool, you acknowledge that you are responsible for your own investment decisions.**
"""
