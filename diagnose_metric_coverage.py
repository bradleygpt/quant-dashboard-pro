"""Compare PIT metric coverage 2010 vs 2014 to find what's broken."""
import sys
sys.path.insert(0, ".")
from datetime import datetime
from pit_scoring_c import compute_pit_metrics_for_ticker
from build_quant_backtest import get_universe_tickers
from price_cache import get_listed_tickers_at

universe = get_universe_tickers()

for date_label, target_date in [("2010-01-15", datetime(2010, 1, 15)), ("2014-01-15", datetime(2014, 1, 15))]:
    listed = get_listed_tickers_at(target_date, universe)
    print(f"\n{'='*70}")
    print(f"Date: {date_label}, Listed: {len(listed)}")
    print(f"{'='*70}")

    # Sample first 100 tickers, check metric coverage
    metric_counts = {}
    metric_total = 0
    for ticker in listed[:200]:
        m = compute_pit_metrics_for_ticker(ticker, target_date)
        if m is None:
            continue
        metric_total += 1
        for k, v in m.items():
            if k.startswith("_") or k == "ticker" or k == "sector":
                continue
            if v is not None and not (isinstance(v, float) and v != v):  # not NaN
                metric_counts[k] = metric_counts.get(k, 0) + 1

    print(f"\nSampled {metric_total} tickers (out of first 200 listed)")
    print(f"\nMetric coverage (% of sampled tickers with valid value):")
    for k in sorted(metric_counts.keys()):
        pct = metric_counts[k] / metric_total * 100 if metric_total > 0 else 0
        print(f"  {k:<35} {metric_counts[k]:>4}/{metric_total} ({pct:>5.1f}%)")
