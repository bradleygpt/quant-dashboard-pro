"""Verify both Version B and C produce healthy rating distributions at scale."""
import sys
sys.path.insert(0, ".")
from datetime import datetime
from build_quant_backtest import get_universe_tickers
from price_cache import get_listed_tickers_at

universe = get_universe_tickers()

# Test at 2014-01-15 (full data available for both)
target = datetime(2014, 1, 15)
listed = get_listed_tickers_at(target, universe)
print(f"Universe: {len(listed)} listed at {target.date()}")
print()

print("=" * 70)
print("Version B (5-pillar with PEAD neutral fill)")
print("=" * 70)
from pit_scoring_b import score_universe_pit as score_b
df_b = score_b(target, listed, verbose=False)
print(f"Scored: {len(df_b)} tickers")
counts_b = df_b["overall_rating"].value_counts()
for rating in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]:
    n = counts_b.get(rating, 0)
    pct = n / len(df_b) * 100 if len(df_b) > 0 else 0
    print(f"  {rating:<12} {n:>5}  ({pct:>5.1f}%)")
print(f"Score range: {df_b['composite_score'].min():.2f} to {df_b['composite_score'].max():.2f}")
print()

print("=" * 70)
print("Version C (4-pillar, no PEAD)")
print("=" * 70)
from pit_scoring_c import score_universe_pit as score_c
df_c = score_c(target, listed, verbose=False)
print(f"Scored: {len(df_c)} tickers")
counts_c = df_c["overall_rating"].value_counts()
for rating in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]:
    n = counts_c.get(rating, 0)
    pct = n / len(df_c) * 100 if len(df_c) > 0 else 0
    print(f"  {rating:<12} {n:>5}  ({pct:>5.1f}%)")
print(f"Score range: {df_c['composite_score'].min():.2f} to {df_c['composite_score'].max():.2f}")
print()

# Also test 2011-Q1 for Version B (its start point)
print("=" * 70)
print("Version B at 2011-01-15 (its actual start checkpoint)")
print("=" * 70)
target2 = datetime(2011, 1, 15)
listed2 = get_listed_tickers_at(target2, universe)
print(f"Listed: {len(listed2)}")
df_b2 = score_b(target2, listed2, verbose=False)
print(f"Scored: {len(df_b2)} tickers")
if len(df_b2) > 0:
    counts_b2 = df_b2["overall_rating"].value_counts()
    for rating in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]:
        n = counts_b2.get(rating, 0)
        pct = n / len(df_b2) * 100
        print(f"  {rating:<12} {n:>5}  ({pct:>5.1f}%)")
