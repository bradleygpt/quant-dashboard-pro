"""Diagnose what score scale compute_quant_score_at_date returns."""
import sys
sys.path.insert(0, ".")
from build_quant_backtest import compute_quant_score_at_date
from datetime import datetime

# Test on 5 well-known tickers at a recent date with confirmed good data
test_date = datetime(2024, 1, 15)
test_tickers = ["AAPL", "MSFT", "NVDA", "JPM", "JNJ"]

print(f"Testing scores at {test_date.date()}")
print("-" * 70)

for ticker in test_tickers:
    result = compute_quant_score_at_date(ticker, test_date)
    if result is None:
        print(f"{ticker}: NULL")
        continue
    score = result.get("composite_score")
    quality = result.get("data_quality_score", 0)
    print(f"{ticker}: composite_score={score}, data_quality={quality}")

print()
print("Expected scale: 0-12 (where 9.0+ = Strong Buy)")
print("If actual scores are 0-100 or 0-10, that explains why variants 1-4 never trigger buys")
