import json
p = json.load(open('predictions_cache.json'))
print(f'Predictions: {len(p):,}')
print('Top 5:')
top5 = sorted(p.values(), key=lambda x: x['pred_rank'])[:5]
for r in top5:
    print(f"  #{r['pred_rank']:>2} {r['ticker']:<8} pred={r['pred_return_12q']*100:+6.1f}%  {r['rating_v2']}")
