"""
QUANT BACKTEST - 10 STRATEGY VARIANTS

Tests 5 different entry/exit logic strategies, each in equal-weight AND score-weighted versions.

VARIANTS:
  1. Concentrated Quality - Strong Buy ONLY, sell when drops to Hold or below
  2. Diversified Buy-and-Above - Strong Buy + Buy, sell when drops to Sell or below
  3. Aggressive Exit - Strong Buy + Buy, sell on ANY downgrade (drops to Hold)
  4. Patient Holder - Strong Buy + Buy, sell only when Strong Sell
  5. Top-N Score - Top 20 by score regardless of rating, sell when drops out of top 30

  Each x2 weighting = 10 total variants.

ENGINE:
- Shared universe scoring per checkpoint (computed once, used by all variants)
- Each variant maintains its own portfolio state across checkpoints
- Position tracking: entries, exits, marked-to-market values

USAGE:
  python build_quant_variants_backtest.py
  Set LOCAL_RUN=1 for unattended overnight runs with intermediate saves.

OUTPUT:
  quant_variants_results.json with results for all 10 variants
"""
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# Reuse existing infrastructure
sys.path.insert(0, str(Path(__file__).parent))
from build_quant_backtest import (
    compute_quant_score_at_date,
    fetch_price_history,
    get_universe_tickers,
    get_first_of_months,
    START_YEAR,
    HOLD_DAYS_TRADING,
)
from price_cache import get_listed_tickers_at, get_prices

# Configuration
RESULTS_FILE = "quant_variants_results_c.json"
LOCAL_RUN = os.environ.get("LOCAL_RUN", "0") == "1"
INITIAL_CAPITAL = 100_000.00
MAX_UNIVERSE_SIZE = int(os.environ.get("MAX_UNIVERSE_SIZE", "2000"))
MIN_DATA_QUALITY = 20

# Rating thresholds (from config.py - matches dashboard 0-12 scale exactly)
RATING_MAP = {
    "Strong Buy": (9.0, 12.0),
    "Buy": (8.0, 9.0),
    "Hold": (6.0, 8.0),
    "Sell": (5.0, 6.0),
    "Strong Sell": (0.0, 5.0),
}


def score_to_rating(score):
    """Convert numeric composite score to rating tier."""
    if score is None or pd.isna(score):
        return "Hold"
    for rating, (low, high) in RATING_MAP.items():
        if low <= score <= high:
            return rating
    return "Hold"


def rating_rank(rating):
    """Convert rating to numeric rank (higher = better). Used for comparison."""
    return {"Strong Buy": 5, "Buy": 4, "Hold": 3, "Sell": 2, "Strong Sell": 1}.get(rating, 0)


# ============================================================================
# VARIANT DEFINITIONS
# ============================================================================
# Each variant has a name and two functions:
#   should_buy(rating, score, rank_in_universe) -> bool
#   should_sell(rating, score, rank_in_universe) -> bool
# rank_in_universe is the position when sorted by score descending (1 = highest)

VARIANTS = [
    {
        "name": "Concentrated Quality",
        "key": "v1_concentrated",
        "buy_eligible": lambda rating, score, rank: rating == "Strong Buy",
        "sell_trigger": lambda rating, score, rank: rating_rank(rating) <= 3,  # Hold or below
        "max_positions": 15,  # Strong Buys are rare, smaller portfolio
    },
    {
        "name": "Diversified Buy-and-Above",
        "key": "v2_diversified",
        "buy_eligible": lambda rating, score, rank: rating in ("Strong Buy", "Buy"),
        "sell_trigger": lambda rating, score, rank: rating_rank(rating) <= 2,  # Sell or below
        "max_positions": 25,
    },
    {
        "name": "Aggressive Exit",
        "key": "v3_aggressive_exit",
        "buy_eligible": lambda rating, score, rank: rating in ("Strong Buy", "Buy"),
        "sell_trigger": lambda rating, score, rank: rating_rank(rating) <= 3,  # Hold or below
        "max_positions": 25,
    },
    {
        "name": "Patient Holder",
        "key": "v4_patient",
        "buy_eligible": lambda rating, score, rank: rating in ("Strong Buy", "Buy"),
        "sell_trigger": lambda rating, score, rank: rating == "Strong Sell",
        "max_positions": 25,
    },
    {
        "name": "Top-N Score",
        "key": "v5_top_n",
        "buy_eligible": lambda rating, score, rank: rank is not None and rank <= 20,  # Top 20
        "sell_trigger": lambda rating, score, rank: rank is None or rank > 30,  # Out of top 30
        "max_positions": 20,
    },
]

WEIGHTING_SCHEMES = [
    {"name": "Equal Weight", "key": "equal", "compute": lambda candidates: equal_weight(candidates)},
    {"name": "Score Weighted", "key": "score_weighted", "compute": lambda candidates: score_weighted(candidates, power=2.0)},
]


def equal_weight(candidates):
    """Equal weight across all candidates."""
    n = len(candidates)
    if n == 0:
        return {}
    weight_pct = 1.0 / n
    return {c["ticker"]: weight_pct for c in candidates}


def score_weighted(candidates, power=2.0):
    """Score-weighted: weight = score^power, normalized to 1.0."""
    if not candidates:
        return {}
    raw = {c["ticker"]: c["score"] ** power for c in candidates}
    total = sum(raw.values())
    if total == 0:
        return equal_weight(candidates)
    return {t: w / total for t, w in raw.items()}


# ============================================================================
# PORTFOLIO STATE (one instance per variant)
# ============================================================================

class PortfolioState:
    def __init__(self, initial_capital):
        self.cash = initial_capital
        self.positions = {}  # ticker -> {"shares": float, "entry_price": float, "entry_date": date}
        self.history = []  # list of {"date": date, "total_value": float, "cash": float, "n_positions": int}
        self.trades = []  # list of {"ticker", "action", "date", "price", "shares", "value"}

    def get_total_value(self, prices_at_date):
        """Mark portfolio to market using current prices."""
        position_value = 0.0
        for ticker, pos in self.positions.items():
            price = prices_at_date.get(ticker)
            if price is None:
                # Position couldn't be priced - use entry price (conservative)
                price = pos["entry_price"]
            position_value += pos["shares"] * price
        return self.cash + position_value

    def sell(self, ticker, price, date):
        if ticker not in self.positions:
            return 0
        pos = self.positions[ticker]
        proceeds = pos["shares"] * price
        self.cash += proceeds
        self.trades.append({
            "ticker": ticker,
            "action": "SELL",
            "date": str(date),
            "price": round(price, 2),
            "shares": round(pos["shares"], 4),
            "value": round(proceeds, 2),
            "entry_price": round(pos["entry_price"], 2),
            "return_pct": round((price / pos["entry_price"] - 1) * 100, 2),
        })
        del self.positions[ticker]
        return proceeds

    def buy(self, ticker, dollars, price, date):
        if dollars < 100 or price <= 0:
            return 0  # Skip tiny positions or invalid prices
        shares = dollars / price
        self.cash -= dollars
        self.positions[ticker] = {
            "shares": shares,
            "entry_price": price,
            "entry_date": str(date),
        }
        self.trades.append({
            "ticker": ticker,
            "action": "BUY",
            "date": str(date),
            "price": round(price, 2),
            "shares": round(shares, 4),
            "value": round(dollars, 2),
        })
        return shares


# ============================================================================
# SHARED SCORING (one pass per checkpoint, used by all variants)
# ============================================================================

def score_universe_at_date(checkpoint_date, universe):
    """
    Score all listed tickers at this date using DASHBOARD-COMPATIBLE methodology.

    Output is on 0-12 scale, with proper Strong Buy / Buy / Hold / Sell ratings
    matching the live dashboard.
    """
    print(f"  Scoring universe at {checkpoint_date.strftime('%Y-%m-%d')} (dashboard methodology)...", flush=True)

    sample = universe[:MAX_UNIVERSE_SIZE]
    listed = get_listed_tickers_at(checkpoint_date, sample)
    if len(listed) < len(sample):
        print(f"  Filtered to {len(listed)} listed tickers (skipped {len(sample) - len(listed)} pre-IPO)", flush=True)

    # Use the new PIT scoring (Version C: 4-pillar, drops EPS Revisions pillar)
    from pit_scoring_c import score_universe_pit
    df = score_universe_pit(checkpoint_date, listed, verbose=False)

    if df.empty:
        print(f"  Scored 0 tickers (no data)", flush=True)
        return []

    # Convert DataFrame to list of dicts (preserving sort order: highest score first)
    scored = []
    for rank, (ticker, row) in enumerate(df.iterrows(), 1):
        scored.append({
            "ticker": ticker,
            "score": float(row["composite_score"]),  # 0-12 scale now
            "rating": row["overall_rating"],         # Strong Buy / Buy / Hold / Sell / Strong Sell
            "data_quality": float(row.get("_data_quality", 0)),
            "rank": rank,
            "sector": row.get("sector", "Unknown"),
        })

    print(f"  Scored {len(scored)} tickers ({df['overall_rating'].value_counts().to_dict()})", flush=True)
    return scored


def get_prices_at_date(tickers, target_date):
    """Get most recent close price at or before target_date for each ticker."""
    prices = {}
    start = target_date - timedelta(days=10)
    for ticker in tickers:
        try:
            hist = fetch_price_history(ticker, start.strftime("%Y-%m-%d"), (target_date + timedelta(days=1)).strftime("%Y-%m-%d"))
            if hist is not None and not hist.empty:
                prices[ticker] = float(hist["Close"].iloc[-1])
        except Exception:
            pass
    return prices


# ============================================================================
# REBALANCE LOGIC
# ============================================================================

def rebalance_portfolio(portfolio, scored_universe, variant, weighting, checkpoint_date, prices):
    """
    Apply variant's buy/sell rules to portfolio.

    prices: dict of ticker -> price, pre-fetched for ALL relevant tickers this checkpoint
    """
    # Build scored lookup
    scored_by_ticker = {s["ticker"]: s for s in scored_universe}

    # Step 1: SELL based on variant rules
    positions_to_sell = []
    for ticker, pos in portfolio.positions.items():
        scored = scored_by_ticker.get(ticker)
        if scored is None:
            # Ticker dropped out of scored universe entirely -> sell
            positions_to_sell.append(ticker)
            continue
        if variant["sell_trigger"](scored["rating"], scored["score"], scored["rank"]):
            positions_to_sell.append(ticker)

    for ticker in positions_to_sell:
        price = prices.get(ticker, portfolio.positions[ticker]["entry_price"])
        portfolio.sell(ticker, price, checkpoint_date)

    # Step 2: Identify eligible buy candidates
    buy_eligible = [
        s for s in scored_universe
        if variant["buy_eligible"](s["rating"], s["score"], s["rank"])
        and s["ticker"] not in portfolio.positions
        and s["ticker"] in prices
        and prices[s["ticker"]] > 0
    ]
    # Cap at max_positions slots (factoring in existing positions)
    available_slots = variant["max_positions"] - len(portfolio.positions)
    if available_slots <= 0:
        return  # Already full
    buy_eligible = buy_eligible[:available_slots]

    if not buy_eligible:
        return

    # Step 3: Compute target weights using weighting scheme
    weights = weighting["compute"](buy_eligible)

    # Step 4: BUY based on available cash and target weights
    available_cash = portfolio.cash
    if available_cash < 200:
        return

    for candidate in buy_eligible:
        ticker = candidate["ticker"]
        weight = weights.get(ticker, 0)
        if weight == 0:
            continue
        dollars = available_cash * weight
        price = prices[ticker]
        portfolio.buy(ticker, dollars, price, checkpoint_date)


# ============================================================================
# METRICS
# ============================================================================

def compute_metrics(portfolio_history, initial_capital):
    """Compute aggregate metrics from portfolio history."""
    if not portfolio_history:
        return {}

    final_value = portfolio_history[-1]["total_value"]
    total_return_pct = (final_value / initial_capital - 1) * 100

    # Quarterly returns (between checkpoints)
    quarterly_returns = []
    for i in range(1, len(portfolio_history)):
        prev = portfolio_history[i - 1]["total_value"]
        curr = portfolio_history[i]["total_value"]
        if prev > 0:
            quarterly_returns.append((curr / prev - 1) * 100)

    if not quarterly_returns:
        return {"final_value": final_value, "total_return_pct": total_return_pct}

    wins = [r for r in quarterly_returns if r > 0]
    losses = [r for r in quarterly_returns if r <= 0]

    # Max drawdown
    peak = portfolio_history[0]["total_value"]
    max_dd = 0
    for h in portfolio_history:
        if h["total_value"] > peak:
            peak = h["total_value"]
        dd = (peak - h["total_value"]) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    return {
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return_pct, 2),
        "n_periods": len(quarterly_returns),
        "win_rate_pct": round(len(wins) / len(quarterly_returns) * 100, 2) if quarterly_returns else 0,
        "avg_return_pct": round(sum(quarterly_returns) / len(quarterly_returns), 2),
        "avg_win_pct": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss_pct": round(sum(losses) / len(losses), 2) if losses else 0,
        "best_period_pct": round(max(quarterly_returns), 2),
        "worst_period_pct": round(min(quarterly_returns), 2),
        "max_drawdown_pct": round(max_dd, 2),
    }


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

def main():
    print(f"[{datetime.now().isoformat()}] QUANT VARIANTS BACKTEST", flush=True)
    print(f"Variants: {len(VARIANTS)} logic x {len(WEIGHTING_SCHEMES)} weightings = {len(VARIANTS) * len(WEIGHTING_SCHEMES)} total", flush=True)
    print(f"Initial capital per variant: ${INITIAL_CAPITAL:,.0f}", flush=True)

    universe = get_universe_tickers()
    if not universe:
        print("ERROR: No universe found", file=sys.stderr)
        sys.exit(1)
    print(f"Universe size: {len(universe)} tickers", flush=True)

    # Use quarterly checkpoints
    os.environ["CHECKPOINT_FREQ"] = "quarterly"
    # Version C: 4-pillar (no EPS Revisions/PEAD), can start 2009 since Growth pillar
    # is the only one needing prior-year data (and most companies have at least 1 year by 2010)
    checkpoint_dates = get_first_of_months(start_year=2009)
    print(f"Backtesting {len(checkpoint_dates)} quarterly checkpoints (Version C: 4-pillar, 2009 start)", flush=True)
    if LOCAL_RUN:
        print(f"LOCAL_RUN=1: saving every 5 checkpoints", flush=True)

    # Initialize portfolio for each variant + weighting combo
    portfolios = {}
    for variant in VARIANTS:
        for weighting in WEIGHTING_SCHEMES:
            key = f"{variant['key']}_{weighting['key']}"
            portfolios[key] = PortfolioState(INITIAL_CAPITAL)

    print(f"Initialized {len(portfolios)} portfolio combos", flush=True)

    # SPY benchmark portfolio (buy and hold)
    spy_history = []
    spy_initial_price = None
    skip_until = 0  # Skip this many checkpoints (resume support)

    # Resume from saved state
    if LOCAL_RUN and os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE) as f:
                existing = json.load(f)
            n_existing = existing.get("n_checkpoints_completed", 0)
            if n_existing > 0 and existing.get("variants", {}).get("v1_concentrated_equal", {}).get("_state_cash") is not None:
                # Has new format with state - resume!
                portfolios, spy_history, skip_until, spy_initial_price = restore_portfolios_from_save(existing)
                print(f"RESUMED: Restored state from {skip_until} completed checkpoints", flush=True)
                print(f"  SPY history: {len(spy_history)} entries", flush=True)
                # Health check on a sample portfolio
                sample = portfolios["v1_concentrated_equal"]
                print(f"  Sample (v1 equal): cash=${sample.cash:,.0f}, positions={len(sample.positions)}, history_pts={len(sample.history)}", flush=True)
            elif n_existing > 0:
                # Old format without state - cannot resume
                print(f"Found old-format save with {n_existing} checkpoints but no state data - cannot resume, starting fresh", flush=True)
        except Exception as e:
            print(f"Could not load existing results: {e} - starting fresh", flush=True)

    start_time = time.time()

    for i, checkpoint_date in enumerate(checkpoint_dates):
        # Skip already-completed checkpoints (resume support)
        if i < skip_until:
            continue
        try:
            # Score universe ONCE per checkpoint (shared across all variants)
            scored = score_universe_at_date(checkpoint_date, universe)

            if not scored:
                print(f"[{i+1}/{len(checkpoint_dates)}] {checkpoint_date.strftime('%Y-%m')}: no scored tickers - skipping", flush=True)
                continue

            # Fetch ALL prices needed this checkpoint (once, shared across variants)
            # Tickers needed: union of all variants' max_positions * 3 (for weighting flexibility) + all current positions
            tickers_needed = set()
            for variant in VARIANTS:
                top_n = variant["max_positions"] * 3
                tickers_needed.update(s["ticker"] for s in scored[:top_n])
            for variant in VARIANTS:
                for weighting in WEIGHTING_SCHEMES:
                    key = f"{variant['key']}_{weighting['key']}"
                    tickers_needed.update(portfolios[key].positions.keys())

            print(f"  Fetching prices for {len(tickers_needed)} tickers...", flush=True)
            prices = get_prices_at_date(list(tickers_needed), checkpoint_date)

            # Get SPY price for benchmark
            spy_price = prices.get("SPY")
            if spy_price is None:
                try:
                    spy_hist = fetch_price_history("SPY", (checkpoint_date - timedelta(days=10)).strftime("%Y-%m-%d"), (checkpoint_date + timedelta(days=1)).strftime("%Y-%m-%d"))
                    if spy_hist is not None and not spy_hist.empty:
                        spy_price = float(spy_hist["Close"].iloc[-1])
                except Exception:
                    pass

            if spy_price:
                if spy_initial_price is None:
                    spy_initial_price = spy_price
                spy_value = INITIAL_CAPITAL * (spy_price / spy_initial_price)
                spy_history.append({"date": str(checkpoint_date), "spy_value": round(spy_value, 2)})

            # Rebalance each variant + weighting combo (using shared prices)
            for variant in VARIANTS:
                for weighting in WEIGHTING_SCHEMES:
                    key = f"{variant['key']}_{weighting['key']}"
                    portfolio = portfolios[key]

                    rebalance_portfolio(portfolio, scored, variant, weighting, checkpoint_date, prices)

                    # Mark to market using shared prices
                    total_value = portfolio.get_total_value(prices)
                    portfolio.history.append({
                        "date": str(checkpoint_date),
                        "total_value": round(total_value, 2),
                        "cash": round(portfolio.cash, 2),
                        "n_positions": len(portfolio.positions),
                    })

            # Progress update
            elapsed = time.time() - start_time
            avg_per = elapsed / (i + 1)
            eta = avg_per * (len(checkpoint_dates) - i - 1)

            # Show one variant's value as quick health check (concentrated equal weight)
            sample_key = "v1_concentrated_equal"
            sample_val = portfolios[sample_key].history[-1]["total_value"] if portfolios[sample_key].history else 0
            spy_val = spy_history[-1]["spy_value"] if spy_history else 0

            print(
                f"[{i+1}/{len(checkpoint_dates)}] {checkpoint_date.strftime('%Y-%m')}: "
                f"v1_eq=${sample_val:,.0f} spy=${spy_val:,.0f} "
                f"(elapsed: {elapsed/60:.1f}min, eta: {eta/60:.1f}min)",
                flush=True
            )

            # Intermediate save every 5 checkpoints
            if LOCAL_RUN and (i + 1) % 5 == 0:
                save_results(portfolios, spy_history, i + 1, spy_initial_price)
                print(f"  [Saved intermediate results: {i+1} checkpoints]", flush=True)

        except KeyboardInterrupt:
            print(f"\n[INTERRUPTED] Saving partial results...", flush=True)
            save_results(portfolios, spy_history, i, spy_initial_price)
            print(f"Saved with full state. Rerun script to resume from checkpoint {i+1}.", flush=True)
            sys.exit(0)
        except Exception as e:
            print(f"[{i+1}] FAILED for {checkpoint_date}: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            continue

    # Final save
    save_results(portfolios, spy_history, len(checkpoint_dates), spy_initial_price)

    # Print summary
    print(f"\n[{datetime.now().isoformat()}] BACKTEST COMPLETE", flush=True)
    print(f"\n=== VARIANT RESULTS ===", flush=True)
    print(f"{'Variant':<35} {'Final':>12} {'Return':>10} {'WinRate':>10} {'MaxDD':>10}", flush=True)
    print(f"{'-' * 85}", flush=True)

    for variant in VARIANTS:
        for weighting in WEIGHTING_SCHEMES:
            key = f"{variant['key']}_{weighting['key']}"
            portfolio = portfolios[key]
            metrics = compute_metrics(portfolio.history, INITIAL_CAPITAL)
            label = f"{variant['name']} ({weighting['name']})"
            print(f"{label:<35} ${metrics.get('final_value', 0):>10,.0f} "
                  f"{metrics.get('total_return_pct', 0):>9.1f}% "
                  f"{metrics.get('win_rate_pct', 0):>9.1f}% "
                  f"{metrics.get('max_drawdown_pct', 0):>9.1f}%", flush=True)

    if spy_history:
        spy_final = spy_history[-1]["spy_value"]
        spy_return = (spy_final / INITIAL_CAPITAL - 1) * 100
        print(f"{'-' * 85}", flush=True)
        print(f"{'SPY Buy-and-Hold':<35} ${spy_final:>10,.0f} {spy_return:>9.1f}%", flush=True)


def save_results(portfolios, spy_history, n_completed, spy_initial_price=None):
    """Save full state for resume capability."""
    output = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "n_checkpoints_completed": n_completed,
        "initial_capital": INITIAL_CAPITAL,
        "spy_initial_price": spy_initial_price,
        "variants": {},
        "spy_benchmark": {
            "history": spy_history,
            "final_value": spy_history[-1]["spy_value"] if spy_history else INITIAL_CAPITAL,
            "return_pct": round((spy_history[-1]["spy_value"] / INITIAL_CAPITAL - 1) * 100, 2) if spy_history else 0,
        },
    }

    for variant in VARIANTS:
        for weighting in WEIGHTING_SCHEMES:
            key = f"{variant['key']}_{weighting['key']}"
            portfolio = portfolios[key]
            metrics = compute_metrics(portfolio.history, INITIAL_CAPITAL)
            output["variants"][key] = {
                "name": f"{variant['name']} ({weighting['name']})",
                "logic": variant["name"],
                "weighting": weighting["name"],
                "max_positions": variant["max_positions"],
                "metrics": metrics,
                "history": portfolio.history,
                "n_trades": len(portfolio.trades),
                # FULL STATE FOR RESUME:
                "_state_cash": portfolio.cash,
                "_state_positions": {
                    ticker: {
                        "shares": pos["shares"],
                        "entry_price": pos["entry_price"],
                        "entry_date": str(pos["entry_date"]),
                    }
                    for ticker, pos in portfolio.positions.items()
                },
                "_state_trades": portfolio.trades,  # Save all trades (could be large)
            }

    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)


def restore_portfolios_from_save(saved_data):
    """Rebuild portfolio state from saved JSON. Returns (portfolios, spy_history, last_completed_idx, spy_initial_price)."""
    portfolios = {}
    spy_history = saved_data.get("spy_benchmark", {}).get("history", [])
    n_completed = saved_data.get("n_checkpoints_completed", 0)
    spy_initial_price = saved_data.get("spy_initial_price")

    saved_variants = saved_data.get("variants", {})

    for variant in VARIANTS:
        for weighting in WEIGHTING_SCHEMES:
            key = f"{variant['key']}_{weighting['key']}"
            portfolio = PortfolioState(INITIAL_CAPITAL)

            saved = saved_variants.get(key, {})

            # Restore cash
            portfolio.cash = saved.get("_state_cash", INITIAL_CAPITAL)

            # Restore positions
            saved_positions = saved.get("_state_positions", {})
            for ticker, pos_data in saved_positions.items():
                portfolio.positions[ticker] = {
                    "shares": pos_data["shares"],
                    "entry_price": pos_data["entry_price"],
                    "entry_date": pos_data["entry_date"],
                }

            # Restore history
            portfolio.history = saved.get("history", [])

            # Restore trades
            portfolio.trades = saved.get("_state_trades", [])

            portfolios[key] = portfolio

    return portfolios, spy_history, n_completed, spy_initial_price


if __name__ == "__main__":
    main()
