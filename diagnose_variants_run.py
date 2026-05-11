"""Diagnose the variants run to understand what scored and what got bought."""
import json

with open("quant_variants_results.json") as f:
    d = json.load(f)

print(f"Checkpoints completed: {d.get('n_checkpoints_completed', 0)}/86")
print()

# Top-N stats
print("=" * 70)
print("Top-N Score (Equal Weight) - the variant that worked")
print("=" * 70)
v5 = d["variants"]["v5_top_n_equal"]
trades = v5.get("_state_trades", [])
buys = [t for t in trades if t["action"] == "BUY"]
sells = [t for t in trades if t["action"] == "SELL"]
print(f"Total trades: {len(trades)} ({len(buys)} buys, {len(sells)} sells)")
print(f"Final value: ${v5['metrics']['final_value']:,.0f}")
print(f"Final positions: {len(v5.get('_state_positions', {}))}")
print()
print("First 5 buys:")
for t in buys[:5]:
    print(f"  {t['date']} {t['ticker']} @ ${t['price']:.2f}")

# Check if other variants did anything at all
print()
print("=" * 70)
print("Diversified Buy-and-Above - SHOULD have triggered if any Buys/Strong Buys existed")
print("=" * 70)
v2 = d["variants"]["v2_diversified_equal"]
trades2 = v2.get("_state_trades", [])
print(f"Total trades: {len(trades2)}")
print(f"Final value: ${v2['metrics']['final_value']:,.0f}")
print(f"Final cash: ${v2.get('_state_cash', 0):,.0f}")
print(f"Final positions: {len(v2.get('_state_positions', {}))}")
if trades2:
    print(f"First 5 trades:")
    for t in trades2[:5]:
        print(f"  {t['date']} {t['action']} {t['ticker']} @ ${t['price']:.2f}")
else:
    print("ZERO TRADES across 67 checkpoints - means no ticker ever rated Buy or Strong Buy")

print()
print("=" * 70)
print("Sample Top-N portfolio history (trajectory)")
print("=" * 70)
hist = v5.get("history", [])
# Show every 10th checkpoint
for i in range(0, len(hist), 10):
    h = hist[i]
    print(f"  {h.get('date')}: ${h.get('total_value', 0):,.0f} ({h.get('n_positions', 0)} positions, ${h.get('cash', 0):,.0f} cash)")
