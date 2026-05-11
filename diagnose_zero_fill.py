"""
Diagnostic: 0-Fill vs NaN-Fill for Missing Features

Tests the hypothesis that filling missing features with 0 (current behavior
in build_predictions.py) is biasing predictions upward.

Approach: score the same tickers two ways and compare distributions.
  Method A: 0-fill missing features (current behavior)
  Method B: NaN-fill (let XGBoost handle natively)

If Method B produces meaningfully different predictions (especially
lower ones), the 0-fill is a real bug. If predictions are similar,
the issue is elsewhere (genuine distribution shift).

Also tests:
  - How many features are missing per ticker (worst offenders)
  - Which features specifically are most often 0/NaN
  - Whether quarterly_history-derived trend features are populated

Run from quant-dashboard-pro repo (where the cache and model live).
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_FILE = "fundamentals_cache.json"
MODEL_FILE = "dashboard_model_v2.pkl"

# Same mapping as build_predictions.py
FIELD_MAP = {
    "trailingPE": "trailing_pe",
    "priceToBook": "price_to_book",
    "priceToSalesTrailing12Months": "price_to_sales",
    "grossMargins": "gross_margin",
    "operatingMargins": "operating_margin",
    "profitMargins": "net_margin",
    "returnOnEquity": "roe",
    "returnOnAssets": "roa",
    "revenueQuarterlyGrowth": "revenue_growth_qoq",
    "revenueGrowth": "revenue_growth_yoy",
    "earningsQuarterlyGrowth": "earnings_growth_qoq",
    "earningsGrowth": "earnings_growth_yoy",
    "momentum_1m": "momentum_1m",
    "momentum_3m": "momentum_3m",
    "momentum_6m": "momentum_6m",
    "momentum_12m": "momentum_12m",
    "momentum_vs_sma50": "momentum_vs_sma50",
    "momentum_vs_sma200": "momentum_vs_sma200",
}


def compute_trend_features(quarterly_history):
    out = {
        "gross_margin_yoy_change": None,
        "operating_margin_yoy_change": None,
        "net_margin_yoy_change": None,
        "roe_yoy_change": None,
        "roa_yoy_change": None,
        "revenue_growth_yoy_yoy_change": None,
        "earnings_growth_yoy_yoy_change": None,
    }
    if not quarterly_history or len(quarterly_history) < 5:
        return out
    current = quarterly_history[0]
    past = quarterly_history[4]

    def diff(c, p):
        if c is None or p is None:
            return None
        return float(c - p)

    out["gross_margin_yoy_change"] = diff(current.get("grossMargins"), past.get("grossMargins"))
    out["operating_margin_yoy_change"] = diff(current.get("operatingMargins"), past.get("operatingMargins"))
    out["net_margin_yoy_change"] = diff(current.get("netMargins"), past.get("netMargins"))
    out["roe_yoy_change"] = diff(current.get("returnOnEquity"), past.get("returnOnEquity"))
    out["roa_yoy_change"] = diff(current.get("returnOnAssets"), past.get("returnOnAssets"))
    out["revenue_growth_yoy_yoy_change"] = diff(current.get("revenueGrowth"), past.get("revenueGrowth"))
    out["earnings_growth_yoy_yoy_change"] = diff(current.get("earningsGrowth"), past.get("earningsGrowth"))
    return out


def encode_sector(sector, sector_columns):
    out = {col: 0 for col in sector_columns}
    if not sector or sector == "Unknown":
        return out
    target = "sector_" + sector.lower().replace(" ", "_")
    if target in out:
        out[target] = 1
    return out


def build_features(record, regime_features, sector_columns):
    """Build feature dict — values may be None for missing features."""
    row = {}
    for cache_key, model_key in FIELD_MAP.items():
        v = record.get(cache_key)
        if v is not None:
            try:
                row[model_key] = float(v)
            except (TypeError, ValueError):
                row[model_key] = None
        else:
            row[model_key] = None

    row.update(compute_trend_features(record.get("quarterly_history", [])))

    # Ratio features — debt_to_equity & cash_to_market_cap aren't in cache
    row["debt_to_equity"] = None
    row["cash_to_market_cap"] = None
    nm = record.get("profitMargins")
    row["net_income_margin_ttm"] = float(nm) if nm is not None else None

    row.update(regime_features)
    row.update(encode_sector(record.get("sector", "Unknown"), sector_columns))
    return row


def main():
    print("=" * 70)
    print("DIAGNOSTIC: 0-fill vs NaN-fill comparison")
    print("=" * 70)

    print("\n1. Loading model and cache...")
    with open(MODEL_FILE, "rb") as f:
        bundle = pickle.load(f)
    with open(CACHE_FILE, "r") as f:
        cache = json.load(f)
    stocks = {k: v for k, v in cache.items() if v.get("type") == "stock"}
    print(f"   {len(stocks):,} stocks loaded")

    feature_cols = bundle["feature_cols"]
    sector_cols = bundle["sector_columns"]
    winsor = bundle["winsorization_bounds"]
    model = bundle["xgb_model"]
    thresholds = bundle["rating_thresholds"]

    # Use neutral regime features for this test
    regime = {
        "spy_drawdown_pct": 0.0,
        "spy_trend_sma_ratio": 0.02,
        "spy_vol_realized": 0.15,
        "spy_vol_percentile": 0.5,
        "spy_return_3m": 0.05,
        "spy_return_12m": 0.20,
    }

    print("\n2. Building features (with None for missing)...")
    rows = []
    tickers = []
    for ticker, record in stocks.items():
        row = build_features(record, regime, sector_cols)
        rows.append(row)
        tickers.append(ticker)

    df = pd.DataFrame(rows)
    for col in feature_cols:
        if col not in df.columns:
            df[col] = None
    df = df[feature_cols]

    # Apply winsorization (None passes through)
    for col, (lo, hi) in winsor.items():
        if col in df.columns:
            df[col] = df[col].apply(lambda v: max(lo, min(hi, v)) if v is not None else None)

    print(f"\n3. Missingness diagnosis...")
    missing_count = df.isna().sum().sort_values(ascending=False)
    print(f"   Top 15 features by missingness:")
    for col, n in missing_count.head(15).items():
        pct = n / len(df) * 100
        print(f"     {col:<35} {n:>5,} missing ({pct:>5.1f}%)")

    rows_with_full_features = (df.notna().sum(axis=1) == len(feature_cols)).sum()
    print(f"\n   Rows with all features populated:  {rows_with_full_features:,} / {len(df):,}")
    avg_missing_per_row = df.isna().sum(axis=1).mean()
    print(f"   Average missing features per row:  {avg_missing_per_row:.1f}")

    print("\n4. Method A: score with 0-fill (current behavior)...")
    X_zero = df.fillna(0.0).values.astype(np.float32)
    preds_zero = model.predict(X_zero)
    print(f"   Distribution:")
    print(f"     min:    {preds_zero.min():+.4f}")
    print(f"     q05:    {np.quantile(preds_zero, 0.05):+.4f}")
    print(f"     q20:    {np.quantile(preds_zero, 0.20):+.4f}")
    print(f"     median: {np.median(preds_zero):+.4f}")
    print(f"     q80:    {np.quantile(preds_zero, 0.80):+.4f}")
    print(f"     q95:    {np.quantile(preds_zero, 0.95):+.4f}")
    print(f"     max:    {preds_zero.max():+.4f}")

    print("\n5. Method B: score with NaN-fill (XGBoost native handling)...")
    X_nan = df.values.astype(np.float32)  # numpy preserves NaN through this
    preds_nan = model.predict(X_nan)
    print(f"   Distribution:")
    print(f"     min:    {preds_nan.min():+.4f}")
    print(f"     q05:    {np.quantile(preds_nan, 0.05):+.4f}")
    print(f"     q20:    {np.quantile(preds_nan, 0.20):+.4f}")
    print(f"     median: {np.median(preds_nan):+.4f}")
    print(f"     q80:    {np.quantile(preds_nan, 0.80):+.4f}")
    print(f"     q95:    {np.quantile(preds_nan, 0.95):+.4f}")
    print(f"     max:    {preds_nan.max():+.4f}")

    print("\n6. Per-ticker comparison...")
    diff = preds_nan - preds_zero
    print(f"   Mean shift (NaN minus 0-fill):  {diff.mean():+.4f}")
    print(f"   Stocks moved DOWN by NaN-fill:   {(diff < 0).sum():,}")
    print(f"   Stocks moved UP by NaN-fill:     {(diff > 0).sum():,}")
    print(f"   Stocks unchanged:                {(diff == 0).sum():,}")

    # Show top movers
    cmp_df = pd.DataFrame({
        "ticker": tickers,
        "pred_zero": preds_zero,
        "pred_nan": preds_nan,
        "shift": diff,
    }).sort_values("shift")

    print(f"\n   Top 10 stocks pushed DOWN most by NaN-fill (current 0-fill makes these look better than they are):")
    for _, r in cmp_df.head(10).iterrows():
        print(f"     {r['ticker']:<8} 0-fill={r['pred_zero']:+.4f}  NaN-fill={r['pred_nan']:+.4f}  diff={r['shift']:+.4f}")

    print(f"\n   Top 10 stocks pushed UP most by NaN-fill:")
    for _, r in cmp_df.tail(10).iterrows():
        print(f"     {r['ticker']:<8} 0-fill={r['pred_zero']:+.4f}  NaN-fill={r['pred_nan']:+.4f}  diff={r['shift']:+.4f}")

    # Re-score with NaN and check rating distribution
    print("\n7. Rating distribution under NaN-fill...")
    def rate(p):
        if p >= thresholds["strong_buy"]: return "Strong Buy"
        if p >= thresholds["buy"]: return "Buy"
        if p >= thresholds["sell"]: return "Hold"
        if p >= thresholds["strong_sell"]: return "Sell"
        return "Strong Sell"
    ratings_nan = [rate(p) for p in preds_nan]
    counts_nan = pd.Series(ratings_nan).value_counts().reindex(
        ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"], fill_value=0
    )
    print(f"   {'rating':<15}{'count':>8}{'%':>8}")
    for r, n in counts_nan.items():
        pct = n / len(preds_nan) * 100
        print(f"   {r:<15}{n:>8,}{pct:>7.1f}%")

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    abs_diff = np.abs(diff).mean()
    if abs_diff < 0.01:
        print("\n   0-fill and NaN-fill produce nearly identical predictions.")
        print("   The bias is NOT caused by missing-feature handling.")
        print("   The issue is genuine distribution shift between training data and current data.")
        print("   FIX: dynamic threshold calibration (Option A).")
    elif diff.mean() < -0.05:
        print(f"\n   NaN-fill systematically lowers predictions (mean shift {diff.mean():+.4f}).")
        print("   The 0-fill IS biasing predictions upward.")
        print(f"   FIX: switch build_predictions.py to use NaN-fill instead of 0-fill.")
    else:
        print(f"\n   Predictions move both directions (mean shift {diff.mean():+.4f}, abs {abs_diff:.4f}).")
        print(f"   0-fill has SOME effect but it's not the primary driver of inflated predictions.")
        print(f"   Likely: combination of 0-fill bias + genuine distribution shift.")
        print(f"   FIX: NaN-fill first, then dynamic threshold calibration if still problematic.")


if __name__ == "__main__":
    main()
