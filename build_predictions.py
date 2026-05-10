"""
Build Predictions Cache for New Dashboard

Reads fundamentals_cache.json (built by build_cache.py with quarterly_history
support), computes the 45 features the v2 model expects, runs XGBoost
to produce per-ticker predictions, and writes predictions_cache.json.

Workflow:
  python build_cache.py        # rebuild fundamentals (~50 min)
  python build_predictions.py  # compute predictions (~1-2 min)
  git add fundamentals_cache.json predictions_cache.json
  git commit -m "Daily refresh"
  git push

Inputs:
  fundamentals_cache.json   built by build_cache.py
  dashboard_model_v2.pkl    trained model bundle from quant-historical

Outputs:
  predictions_cache.json    per-ticker predictions for dashboard
  predictions_metadata.json regime context, run timestamp, etc.

The output structure mirrors fundamentals_cache.json:
  {
    "AAPL": {
      "ticker": "AAPL",
      "pred_return_12q": 0.34,
      "pred_rank": 247,
      "pred_pct": 81.2,
      "rating_v2": "Hold",
      "in_top10": False,
      "in_top25": False,
      "regime": "strong_bull",
      "feature_completeness": 0.95,
      "scored_at": "2026-05-10T12:34:00"
    },
    ...
  }
"""

from __future__ import annotations

import json
import pickle
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

CACHE_FILE = "fundamentals_cache.json"
MODEL_FILE = "dashboard_model_v2.pkl"
OUTPUT_FILE = "predictions_cache.json"
METADATA_FILE = "predictions_metadata.json"

# yfinance field name → our feature name mapping
# (cache stores yfinance field names; model expects our snake_case names)
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


def fetch_spy_regime() -> dict:
    """Compute SPY-derived regime features using fresh yfinance pull.
    All 6 regime features the model expects.
    Returns dict of feature_name → value."""
    try:
        spy = yf.Ticker("SPY").history(period="3y")
        if spy.empty or len(spy) < 252:
            print(f"WARN: insufficient SPY history ({len(spy)} rows); using neutral defaults")
            return {
                "spy_drawdown_pct": 0.0,
                "spy_trend_sma_ratio": 0.0,
                "spy_vol_realized": 0.15,
                "spy_vol_percentile": 0.5,
                "spy_return_3m": 0.0,
                "spy_return_12m": 0.0,
            }
        close = spy["Close"]
        latest = float(close.iloc[-1])

        # Drawdown vs trailing 252-day high
        high_252 = float(close.iloc[-252:].max())
        drawdown = latest / high_252 - 1.0

        # Trend: 50-day vs 200-day SMA
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])
        trend = sma50 / sma200 - 1.0

        # Realized vol (60-day annualized)
        log_returns = np.log(close / close.shift(1)).dropna()
        vol = float(log_returns.iloc[-60:].std() * np.sqrt(252))

        # Vol percentile vs trailing 504 days
        rolling_vol = log_returns.rolling(60).std() * np.sqrt(252)
        vol_history = rolling_vol.iloc[-504:].dropna()
        vol_pct = float((vol_history < vol).sum() / len(vol_history)) if len(vol_history) > 0 else 0.5

        # Returns
        ret_3m = float(close.iloc[-1] / close.iloc[-63] - 1.0) if len(close) >= 63 else 0.0
        ret_12m = float(close.iloc[-1] / close.iloc[-252] - 1.0) if len(close) >= 252 else 0.0

        return {
            "spy_drawdown_pct": drawdown,
            "spy_trend_sma_ratio": trend,
            "spy_vol_realized": vol,
            "spy_vol_percentile": vol_pct,
            "spy_return_3m": ret_3m,
            "spy_return_12m": ret_12m,
        }
    except Exception as e:
        print(f"WARN: SPY regime fetch failed ({e}); using neutral defaults")
        return {
            "spy_drawdown_pct": 0.0, "spy_trend_sma_ratio": 0.0,
            "spy_vol_realized": 0.15, "spy_vol_percentile": 0.5,
            "spy_return_3m": 0.0, "spy_return_12m": 0.0,
        }


def classify_regime(regime_features: dict) -> str:
    """Classify current regime from SPY signals."""
    dd = regime_features["spy_drawdown_pct"]
    trend = regime_features["spy_trend_sma_ratio"]
    if dd < -0.10 or trend < -0.02:
        return "bear"
    if -0.10 <= dd < -0.05 and trend > 0:
        return "recovery"
    if dd > -0.05 and trend > 0.03:
        return "strong_bull"
    return "normal"


def compute_trend_features(quarterly_history: list) -> dict:
    """Compute the 7 trend features from quarterly history.

    For each metric, the trend is current value minus value 4 quarters ago.
    Returns dict; values are None if insufficient history.
    """
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

    # quarterly_history is most-recent first, so [0] is current and [4] is 4Q ago
    current = quarterly_history[0]
    past = quarterly_history[4]

    def diff(curr, prev):
        if curr is None or prev is None:
            return None
        return float(curr - prev)

    out["gross_margin_yoy_change"] = diff(
        current.get("grossMargins"), past.get("grossMargins"))
    out["operating_margin_yoy_change"] = diff(
        current.get("operatingMargins"), past.get("operatingMargins"))
    out["net_margin_yoy_change"] = diff(
        current.get("netMargins"), past.get("netMargins"))
    out["roe_yoy_change"] = diff(
        current.get("returnOnEquity"), past.get("returnOnEquity"))
    out["roa_yoy_change"] = diff(
        current.get("returnOnAssets"), past.get("returnOnAssets"))
    out["revenue_growth_yoy_yoy_change"] = diff(
        current.get("revenueGrowth"), past.get("revenueGrowth"))
    out["earnings_growth_yoy_yoy_change"] = diff(
        current.get("earningsGrowth"), past.get("earningsGrowth"))

    return out


def compute_ratio_features(record: dict) -> dict:
    """Compute the 3 derived ratio features from cache record."""
    out = {
        "debt_to_equity": None,
        "cash_to_market_cap": None,
        "net_income_margin_ttm": None,
    }
    # debt_to_equity not directly in cache; build_cache doesn't store totalDebt/equity
    # Leave None — model handles it.

    # cash_to_market_cap: same — totalCash not in cache
    # Leave None.

    # net_income_margin_ttm: profitMargins is essentially this (TTM NI / TTM revenue)
    nm = record.get("profitMargins")
    if nm is not None:
        out["net_income_margin_ttm"] = float(nm)
    return out


def encode_sector(sector: str, sector_columns: list) -> dict:
    """One-hot encode the sector into the model's expected columns."""
    out = {col: 0 for col in sector_columns}
    if not sector or sector == "Unknown":
        return out
    # Sector column format: sector_consumer_cyclical
    target_col = "sector_" + sector.lower().replace(" ", "_")
    if target_col in out:
        out[target_col] = 1
    return out


def build_feature_row(
    ticker: str, record: dict, regime_features: dict, bundle: dict,
) -> tuple[dict, float]:
    """Build a complete feature dict for one ticker.
    Returns (feature_dict, completeness_pct)."""
    row = {}

    # Core features
    n_observed = 0
    for cache_key, model_key in FIELD_MAP.items():
        v = record.get(cache_key)
        if v is not None:
            try:
                row[model_key] = float(v)
                n_observed += 1
            except (TypeError, ValueError):
                row[model_key] = None
        else:
            row[model_key] = None

    n_core_features = len(FIELD_MAP)
    completeness = n_observed / n_core_features if n_core_features > 0 else 0.0

    # Trend features
    trend = compute_trend_features(record.get("quarterly_history", []))
    row.update(trend)

    # Ratio features
    ratios = compute_ratio_features(record)
    row.update(ratios)

    # Regime features (same for all tickers)
    row.update(regime_features)

    # Sector encoding
    sector = record.get("sector", "Unknown")
    sector_encoded = encode_sector(sector, bundle["sector_columns"])
    row.update(sector_encoded)

    return row, completeness


def winsorize_value(value, bounds):
    """Clip a value to bounds. None passes through."""
    if value is None:
        return None
    lo, hi = bounds
    return max(lo, min(hi, value))


def assign_rating(pred: float, thresholds: dict) -> str:
    if pred >= thresholds["strong_buy"]:
        return "Strong Buy"
    if pred >= thresholds["buy"]:
        return "Buy"
    if pred >= thresholds["sell"]:
        return "Hold"
    if pred >= thresholds["strong_sell"]:
        return "Sell"
    return "Strong Sell"


def main() -> int:
    print("=" * 70)
    print("BUILD PREDICTIONS CACHE")
    print("=" * 70)

    # ── Load model bundle ──
    if not Path(MODEL_FILE).exists():
        print(f"ERROR: {MODEL_FILE} not found")
        print(f"  Copy from quant-historical: copy ..\\quant-historical\\stage5_output\\{MODEL_FILE} .")
        return 1
    print(f"\n1. Loading model bundle...")
    with open(MODEL_FILE, "rb") as f:
        bundle = pickle.load(f)
    print(f"   Model: {bundle['metadata']['model_type']}, "
          f"trained {bundle['metadata']['trained_at'][:10]}")
    print(f"   Features: {len(bundle['feature_cols'])}")

    # ── Load cache ──
    if not Path(CACHE_FILE).exists():
        print(f"ERROR: {CACHE_FILE} not found. Run build_cache.py first.")
        return 1
    print(f"\n2. Loading fundamentals cache...")
    with open(CACHE_FILE, "r") as f:
        cache = json.load(f)
    print(f"   {len(cache):,} tickers in cache")

    # Filter to stocks (skip ETFs)
    stocks = {k: v for k, v in cache.items() if v.get("type") == "stock"}
    print(f"   {len(stocks):,} stocks (ETFs excluded)")

    # Check quarterly_history coverage
    with_qh = sum(1 for v in stocks.values()
                  if v.get("quarterly_history") and len(v["quarterly_history"]) >= 5)
    print(f"   {with_qh:,} stocks have ≥5 quarters of history "
          f"({with_qh/len(stocks)*100:.1f}%)")
    if with_qh < len(stocks) * 0.5:
        print(f"   WARN: less than 50% of stocks have sufficient quarterly history")
        print(f"         model accuracy will be reduced for affected tickers")

    # ── Compute SPY regime ──
    print(f"\n3. Computing SPY regime features...")
    regime = fetch_spy_regime()
    regime_class = classify_regime(regime)
    print(f"   Regime detected: {regime_class}")
    print(f"   Drawdown: {regime['spy_drawdown_pct']*100:+.2f}%")
    print(f"   Trend (SMA50/200): {regime['spy_trend_sma_ratio']*100:+.2f}%")
    print(f"   Vol percentile: {regime['spy_vol_percentile']:.2f}")
    print(f"   3m return: {regime['spy_return_3m']*100:+.2f}%")
    print(f"   12m return: {regime['spy_return_12m']*100:+.2f}%")

    # ── Build feature matrix ──
    print(f"\n4. Building feature matrix for {len(stocks):,} stocks...")
    feature_cols = bundle["feature_cols"]
    winsor_bounds = bundle["winsorization_bounds"]

    feature_rows = []
    completeness_scores = []
    tickers_in_order = []

    for ticker, record in stocks.items():
        row, completeness = build_feature_row(ticker, record, regime, bundle)

        # Winsorize
        for col, bounds in winsor_bounds.items():
            if col in row:
                row[col] = winsorize_value(row[col], bounds)

        feature_rows.append(row)
        completeness_scores.append(completeness)
        tickers_in_order.append(ticker)

    df = pd.DataFrame(feature_rows)
    # Reorder to match the model's expected feature order
    for col in feature_cols:
        if col not in df.columns:
            df[col] = None
    df = df[feature_cols]

    # Fill remaining NaN with 0 (XGBoost tolerates but we standardize)
    df = df.fillna(0.0)
    print(f"   Built {len(df):,} feature rows × {df.shape[1]} columns")
    print(f"   Mean feature completeness: {np.mean(completeness_scores)*100:.1f}%")

    # ── Predict ──
    print(f"\n5. Running model...")
    model = bundle["xgb_model"]
    X = df.values
    preds = model.predict(X)
    print(f"   Generated {len(preds):,} predictions")
    print(f"   Pred range: [{preds.min():+.4f}, {preds.max():+.4f}]")
    print(f"   Pred median: {np.median(preds):+.4f}")

    # ── Build ranks ──
    pred_series = pd.Series(preds, index=tickers_in_order)
    rank_series = pred_series.rank(method="first", ascending=False).astype(int)
    pct_series = pred_series.rank(pct=True, ascending=True) * 100

    # ── Assign ratings ──
    print(f"\n6. Assigning ratings...")
    thresholds = bundle["rating_thresholds"]
    rating_counts = {}
    predictions_out = {}
    scored_at = datetime.now().isoformat()

    for i, ticker in enumerate(tickers_in_order):
        pred = float(preds[i])
        rating = assign_rating(pred, thresholds)
        rank = int(rank_series[ticker])
        pct = float(pct_series[ticker])

        rating_counts[rating] = rating_counts.get(rating, 0) + 1

        predictions_out[ticker] = {
            "ticker": ticker,
            "pred_return_12q": round(pred, 4),
            "pred_rank": rank,
            "pred_pct": round(pct, 1),
            "rating_v2": rating,
            "in_top10": rank <= 10,
            "in_top25": rank <= 25,
            "in_top50": rank <= 50,
            "regime": regime_class,
            "feature_completeness": round(completeness_scores[i], 2),
            "scored_at": scored_at,
        }

    print(f"   Rating distribution:")
    for r in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]:
        n = rating_counts.get(r, 0)
        pct = n / len(predictions_out) * 100
        print(f"     {r:<12} {n:>5,} ({pct:>5.1f}%)")

    # ── TOP10 ──
    top10 = sorted(predictions_out.values(), key=lambda r: r["pred_rank"])[:10]
    print(f"\n7. Current TOP10 (by predicted 12Q return):")
    for r in top10:
        sector = stocks[r["ticker"]].get("sector", "?")
        name = stocks[r["ticker"]].get("shortName", r["ticker"])[:30]
        print(f"   #{r['pred_rank']:>2} {r['ticker']:<8} pred={r['pred_return_12q']*100:+6.1f}%  "
              f"{r['rating_v2']:<12} [{sector[:18]:<18}]  {name}")

    # ── Save ──
    print(f"\n8. Saving outputs...")
    with open(OUTPUT_FILE, "w") as f:
        json.dump(predictions_out, f, default=str)
    print(f"   {OUTPUT_FILE} ({Path(OUTPUT_FILE).stat().st_size / 1024:.1f} KB)")

    metadata = {
        "scored_at": scored_at,
        "model_version": bundle["metadata"]["version"],
        "model_trained_at": bundle["metadata"]["trained_at"],
        "n_tickers_scored": len(predictions_out),
        "n_tickers_in_cache": len(cache),
        "regime": regime_class,
        "regime_features": regime,
        "rating_thresholds": thresholds,
        "rating_distribution": rating_counts,
        "feature_completeness_mean": float(np.mean(completeness_scores)),
        "feature_completeness_min": float(np.min(completeness_scores)),
    }
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"   {METADATA_FILE}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print(f"\nNext step: commit and push")
    print(f"  git add {CACHE_FILE} {OUTPUT_FILE} {METADATA_FILE}")
    print(f'  git commit -m "Refresh predictions cache (regime={regime_class})"')
    print(f"  git push")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
