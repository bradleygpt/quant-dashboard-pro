"""Test pit_scoring on the FULL universe at one checkpoint to see real distribution."""
import sys
sys.path.insert(0, ".")
from datetime import datetime
from pit_scoring import score_universe_pit
from build_quant_backtest import get_universe_tickers
from price_cache import get_listed_tickers_at

target_date = datetime(2014, 1, 15)
universe = get_universe_tickers()
print(f"Universe size: {len(universe)}")

listed = get_listed_tickers_at(target_date, universe)
print(f"Listed at {target_date.date()}: {len(listed)}")
print()
print(f"Scoring full universe (this will take 5-10 minutes)...")
print()

df = score_universe_pit(target_date, listed, verbose=False)

if df.empty:
    print("EMPTY result")
else:
    print(f"Got {len(df)} scored tickers")
    print()
    print("Rating distribution:")
    counts = df["overall_rating"].value_counts()
    for rating in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]:
        n = counts.get(rating, 0)
        pct = n / len(df) * 100
        print(f"  {rating:<12} {n:>5}  ({pct:>5.1f}%)")
    print()
    print(f"Score statistics:")
    s = df["composite_score"]
    print(f"  Min: {s.min():.2f}")
    print(f"  Max: {s.max():.2f}")
    print(f"  Mean: {s.mean():.2f}")
    print(f"  Median: {s.median():.2f}")
    print(f"  P90: {s.quantile(0.9):.2f}")
    print(f"  P95: {s.quantile(0.95):.2f}")
    print(f"  P99: {s.quantile(0.99):.2f}")
    print()
    print(f"Top 15 by score:")
    print(df[["composite_score", "overall_rating", "sector"]].head(15).to_string())
    print()
    print(f"Bottom 5 by score:")
    print(df[["composite_score", "overall_rating", "sector"]].tail(5).to_string())
