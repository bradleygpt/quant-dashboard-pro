"""Quick analyzer for partial variant results."""
import json
import os

if not os.path.exists("quant_variants_results.json"):
    print("ERROR: quant_variants_results.json not found")
    exit(1)

with open("quant_variants_results.json") as f:
    d = json.load(f)

n_completed = d.get("n_checkpoints_completed", 0)
print(f"Checkpoints completed: {n_completed}/86")
print(f"Last save: {d.get('last_run_utc', 'unknown')}")
print()

variants = d.get("variants", {})
spy = d.get("spy_benchmark", {})
spy_return = spy.get("return_pct", 0)

# Build sortable list
results = []
for key, var_data in variants.items():
    metrics = var_data.get("metrics", {})
    results.append({
        "name": var_data.get("name", key),
        "final_value": metrics.get("final_value", 0),
        "total_return": metrics.get("total_return_pct", 0),
        "win_rate": metrics.get("win_rate_pct", 0),
        "max_dd": metrics.get("max_drawdown_pct", 0),
        "n_periods": metrics.get("n_periods", 0),
    })

# Sort by total return descending
results.sort(key=lambda x: x["total_return"], reverse=True)

print(f"{'Variant':<40} {'Final':>12} {'Return':>10} {'Win%':>7} {'MaxDD':>7} {'vs SPY':>8}")
print("-" * 95)
for r in results:
    edge = r["total_return"] - spy_return
    edge_str = f"{edge:+.1f}%"
    final = f"${r['final_value']:,.0f}"
    print(f"{r['name'][:38]:<40} {final:>12} {r['total_return']:>9.1f}% {r['win_rate']:>6.1f}% {r['max_dd']:>6.1f}% {edge_str:>8}")

print("-" * 95)
print(f"{'SPY Buy-and-Hold':<40} {'$' + format(spy.get('final_value', 0), ',.0f'):>12} {spy_return:>9.1f}% {'—':>7} {'—':>7} {'—':>8}")
