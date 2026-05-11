"""Run the SAME scoring path the variants script uses to verify rating output."""
import sys
sys.path.insert(0, ".")
from datetime import datetime
from build_quant_backtest import get_universe_tickers
from price_cache import get_listed_tickers_at
from pit_scoring import score_universe_pit

# Mimic what build_quant_variants_backtest.score_universe_at_date does
target_date = datetime(2014, 1, 15)
MAX_UNIVERSE_SIZE = 2000

universe = get_universe_tickers()
sample = universe[:MAX_UNIVERSE_SIZE]
listed = get_listed_tickers_at(target_date, sample)
print(f"Listed tickers: {len(listed)}")

df = score_universe_pit(target_date, listed, verbose=False)
print(f"Scored {len(df)} tickers")
print()

if df.empty:
    print("EMPTY")
else:
    # Convert exactly like variants script does
    scored = []
    for rank, (ticker, row) in enumerate(df.iterrows(), 1):
        scored.append({
            "ticker": ticker,
            "score": float(row["composite_score"]),
            "rating": row["overall_rating"],
            "data_quality": float(row.get("_data_quality", 0)),
            "rank": rank,
            "sector": row.get("sector", "Unknown"),
        })

    # Apply variant 2 (Diversified Buy-and-Above) logic
    buy_eligible = [s for s in scored if s["rating"] in ("Strong Buy", "Buy")]
    print(f"Variant 2 'Diversified' would buy: {len(buy_eligible)} tickers")
    print()
    print("First 10 buy-eligible:")
    for s in buy_eligible[:10]:
        print(f"  {s['ticker']:<8} score={s['score']:.2f} rating={s['rating']:<12} sector={s['sector']}")

    # Apply variant 1 (Concentrated Quality) logic
    sb_only = [s for s in scored if s["rating"] == "Strong Buy"]
    print()
    print(f"Variant 1 'Concentrated' would buy: {len(sb_only)} Strong Buy tickers")
    print()
    print("Counts by rating:")
    from collections import Counter
    rating_counts = Counter(s["rating"] for s in scored)
    for r, c in rating_counts.most_common():
        print(f"  {r}: {c}")
