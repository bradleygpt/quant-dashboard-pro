import json
import pickle

# Load predictions
p = json.load(open('predictions_cache.json'))
preds = [r['pred_return_12q'] for r in p.values()]

import numpy as np
print(f'Current scoring (n={len(preds):,})')
print(f'  min:    {min(preds):+.4f}')
print(f'  q05:    {np.quantile(preds, 0.05):+.4f}')
print(f'  q20:    {np.quantile(preds, 0.20):+.4f}')
print(f'  median: {np.median(preds):+.4f}')
print(f'  q80:    {np.quantile(preds, 0.80):+.4f}')
print(f'  q95:    {np.quantile(preds, 0.95):+.4f}')
print(f'  max:    {max(preds):+.4f}')
print()

# Load model thresholds (these were derived from training distribution)
b = pickle.load(open('dashboard_model_v2.pkl', 'rb'))
t = b['rating_thresholds']
print('Training thresholds (what we apply for ratings):')
print(f'  Strong Sell:  < {t["strong_sell"]:+.4f}')
print(f'  Sell:         < {t["sell"]:+.4f}')
print(f'  Buy:          >= {t["buy"]:+.4f}')
print(f'  Strong Buy:   >= {t["strong_buy"]:+.4f}')
