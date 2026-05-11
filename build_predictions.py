"""
Build Predictions Cache for New Dashboard - v2

Major changes from v1:
  - NaN-fill instead of 0-fill for missing features (XGBoost handles natively
    as it was trained to do)
  - Computes debt_to_equity and cash_to_market_cap from new cache fields
  - Dynamic threshold calibration: rating cutoffs derived from CURRENT
    prediction distribution, not historical training distribution
  - Trend features more robust (uses current TTM where quarterly_history
    insufficient)

Workflow:
  python build_cache.py        # rebuild fundamentals (~50-65 min)
  python build_predictions.py  # compute predictions (~1-2 min)
  git add fundamentals_cache.json predictions_cache.json
  git commit -m "Daily refresh"
  git push
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
    """Compute SPY-derived regime features."""
    try:
        spy = yf.Ticker("SPY").history(period="3y")
        if spy.empty or len(spy) < 252:
            print(f"WARN: insufficient SPY history; using neutral defaults")
            return _neutral_regime()
        close = spy["Close"]
        latest = float(close.iloc[-1])
        high_252 = float(close.iloc[-252:].max())
        drawdown = latest / high_252 - 1.0
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])
        trend = sma50 / sma200 - 1.0
        log_returns = np.log(close / close.shift(1)).dropna()
        vol = float(log_returns.iloc[-60:].std() * np.sqrt(252))
        rolling_vol = log_returns.rolling(60).std() * np.sqrt(252)
        vol_history = rolling_vol.iloc[-504:].dropna()
        vol_pct = float((vol_history < vol).sum() / len(vol_history)) if len(vol_history) > 0 else 0.5
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
        return _neutral_regime()


def _neutral_regime() -> dict:
    return {
        "spy_drawdown_pct": 0.0, "spy_trend_sma_ratio": 0.0,
        "spy_vol_realized": 0.15, "spy_vol_percentile": 0.5,
        "spy_return_3m": 0.0, "spy_return_12m": 0.0,
    }


def classify_regime(regime: dict) -> str:
    dd = regime["spy_drawdown_pct"]
    trend = regime["spy_trend_sma_ratio"]
    if dd < -0.10 or trend < -0.02:
        return "bear"
    if -0.10 <= dd < -0.05 and trend > 0:
        return "recovery"
    if dd > -0.05 and trend > 0.03:
        return "strong_bull"
    return "normal"


def compute_trend_features(quarterly_history: list, current_record: dict) -> dict:
    """Compute the 7 trend features.

    For each metric, the trend is current value minus 4-quarter-ago value.
    quarterly_history is most-recent-first (index 0 = current quarter).
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

    current = quarterly_history[0]
    past = quarterly_history[4]

    def diff(c, p):
        if c is None or p is None:
            return None
        return float(c - p)

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
    """Compute the 3 derived ratio features from cache record.

    Now uses totalDebt, stockholdersEquity, totalCash if present
    (added in build_cache.py patch v3).
    """
    out = {
        "debt_to_equity": None,
        "cash_to_market_cap": None,
        "net_income_margin_ttm": None,
    }

    debt = record.get("totalDebt")
    equity = record.get("stockholdersEquity")
    if debt is not None and equity is not None and equity > 0:
        try:
            out["debt_to_equity"] = float(debt) / float(equity)
        except (TypeError, ValueError):
            pass

    cash = record.get("totalCash")
    mcap = record.get("marketCap")
    if cash is not None and mcap is not None and mcap > 0:
        try:
            out["cash_to_market_cap"] = float(cash) / float(mcap)
        except (TypeError, ValueError):
            pass

    nm = record.get("profitMargins")
    if nm is not None:
        try:
            out["net_income_margin_ttm"] = float(nm)
        except (TypeError, ValueError):
            pass

    return out


def encode_sector(sector: str, sector_columns: list) -> dict:
    out = {col: 0 for col in sector_columns}
    if not sector or sector == "Unknown":
        return out
    target = "sector_" + sector.lower().replace(" ", "_")
    if target in out:
        out[target] = 1
    return out


def build_feature_row(
    ticker: str, record: dict, regime: dict, bundle: dict,
) -> tuple[dict, float]:
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

    completeness = n_observed / len(FIELD_MAP) if FIELD_MAP else 0.0

    row.update(compute_trend_features(record.get("quarterly_history", []), record))
    row.update(compute_ratio_features(record))
    row.update(regime)
    row.update(encode_sector(record.get("sector", "Unknown"), bundle["sector_columns"]))

    return row, completeness


def winsorize_value(value, bounds):
    if value is None or pd.isna(value):
        return value  # preserve None/NaN
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
    print("BUILD PREDICTIONS CACHE v2")
    print("  - NaN-fill for missing features")
    print("  - Computed ratios from new cache fields")
    print("  - Dynamic threshold calibration")
    print("=" * 70)

    if not Path(MODEL_FILE).exists():
        print(f"ERROR: {MODEL_FILE} not found")
        return 1

    print(f"\n1. Loading model bundle...")
    with open(MODEL_FILE, "rb") as f:
        bundle = pickle.load(f)
    print(f"   Model: {bundle['metadata']['model_type']}")
    print(f"   Features: {len(bundle['feature_cols'])}")

    if not Path(CACHE_FILE).exists():
        print(f"ERROR: {CACHE_FILE} not found")
        return 1
    print(f"\n2. Loading fundamentals cache...")
    with open(CACHE_FILE, "r") as f:
        cache = json.load(f)
    print(f"   {len(cache):,} entries in cache")

    stocks = {k: v for k, v in cache.items() if v.get("type") == "stock"}
    print(f"   {len(stocks):,} stocks (ETFs excluded)")

    with_qh = sum(1 for v in stocks.values()
                  if v.get("quarterly_history") and len(v["quarterly_history"]) >= 5)
    print(f"   {with_qh:,} stocks have ≥5 quarters of history "
          f"({with_qh/len(stocks)*100:.1f}%)")

    with_balance = sum(1 for v in stocks.values()
                       if v.get("totalDebt") is not None or v.get("totalCash") is not None)
    print(f"   {with_balance:,} stocks have balance sheet fields "
          f"({with_balance/len(stocks)*100:.1f}%)")

    print(f"\n3. Computing SPY regime features...")
    regime = fetch_spy_regime()
    regime_class = classify_regime(regime)
    print(f"   Regime: {regime_class}")
    print(f"   Drawdown: {regime['spy_drawdown_pct']*100:+.2f}%")
    print(f"   Trend: {regime['spy_trend_sma_ratio']*100:+.2f}%")
    print(f"   Vol pct: {regime['spy_vol_percentile']:.2f}")
    print(f"   12m return: {regime['spy_return_12m']*100:+.2f}%")

    print(f"\n4. Building feature matrix for {len(stocks):,} stocks...")
    feature_cols = bundle["feature_cols"]
    winsor_bounds = bundle["winsorization_bounds"]

    feature_rows = []
    completeness_scores = []
    tickers_in_order = []

    for ticker, record in stocks.items():
        row, completeness = build_feature_row(ticker, record, regime, bundle)
        for col, bounds in winsor_bounds.items():
            if col in row:
                row[col] = winsorize_value(row[col], bounds)
        feature_rows.append(row)
        completeness_scores.append(completeness)
        tickers_in_order.append(ticker)

    df = pd.DataFrame(feature_rows)
    for col in feature_cols:
        if col not in df.columns:
            df[col] = None
    df = df[feature_cols]

    n_missing_per_feature = df.isna().sum()
    n_full_features = (n_missing_per_feature == 0).sum()
    print(f"   Built {len(df):,} feature rows × {df.shape[1]} columns")
    print(f"   Features with 0% missing: {n_full_features}/{len(feature_cols)}")
    print(f"   Mean feature completeness: {np.mean(completeness_scores)*100:.1f}%")

    # CRITICAL: don't fillna here. Pass NaN through to XGBoost.
    print(f"\n5. Running model (NaN-fill, native XGBoost handling)...")
    model = bundle["xgb_model"]
    X = df.values.astype(np.float32)  # numpy preserves NaN
    preds = model.predict(X)
    print(f"   Generated {len(preds):,} predictions")
    print(f"   min={preds.min():+.4f}  q05={np.quantile(preds, 0.05):+.4f}  "
          f"median={np.median(preds):+.4f}  "
          f"q95={np.quantile(preds, 0.95):+.4f}  max={preds.max():+.4f}")

    # ── DYNAMIC THRESHOLD CALIBRATION ──
    print(f"\n6. Dynamic threshold calibration...")
    print(f"   Computing rating thresholds from CURRENT prediction distribution")
    print(f"   (5/15/60/15/5 split — same shape as training, but dynamic levels)")

    thresholds_dynamic = {
        "strong_buy": float(np.quantile(preds, 0.95)),
        "buy": float(np.quantile(preds, 0.80)),
        "sell": float(np.quantile(preds, 0.20)),
        "strong_sell": float(np.quantile(preds, 0.05)),
    }
    thresholds_static = bundle["rating_thresholds"]

    print(f"   Dynamic thresholds (used for ratings):")
    print(f"     Strong Buy   >= {thresholds_dynamic['strong_buy']:+.4f}")
    print(f"     Buy          >= {thresholds_dynamic['buy']:+.4f}")
    print(f"     Sell          < {thresholds_dynamic['sell']:+.4f}")
    print(f"     Strong Sell   < {thresholds_dynamic['strong_sell']:+.4f}")
    print(f"   Static (training) thresholds (for reference):")
    print(f"     Strong Buy   >= {thresholds_static['strong_buy']:+.4f}")
    print(f"     Buy          >= {thresholds_static['buy']:+.4f}")
    print(f"     Sell          < {thresholds_static['sell']:+.4f}")
    print(f"     Strong Sell   < {thresholds_static['strong_sell']:+.4f}")

    # Use dynamic thresholds for ratings
    thresholds = thresholds_dynamic

    pred_series = pd.Series(preds, index=tickers_in_order)
    rank_series = pred_series.rank(method="first", ascending=False).astype(int)
    pct_series = pred_series.rank(pct=True, ascending=True) * 100

    print(f"\n7. Assigning ratings...")
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

    print(f"\n8. Current TOP10:")
    top10 = sorted(predictions_out.values(), key=lambda r: r["pred_rank"])[:10]
    for r in top10:
        sector = stocks[r["ticker"]].get("sector", "?")
        name = stocks[r["ticker"]].get("shortName", r["ticker"])[:30]
        print(f"   #{r['pred_rank']:>2} {r['ticker']:<8} pred={r['pred_return_12q']*100:+6.1f}%  "
              f"{r['rating_v2']:<12} [{sector[:18]:<18}]  {name}")

    print(f"\n9. Bottom 10 (Strong Sell candidates):")
    bottom10 = sorted(predictions_out.values(), key=lambda r: r["pred_rank"])[-10:]
    for r in bottom10:
        sector = stocks[r["ticker"]].get("sector", "?")
        name = stocks[r["ticker"]].get("shortName", r["ticker"])[:30]
        print(f"   #{r['pred_rank']:>4} {r['ticker']:<8} pred={r['pred_return_12q']*100:+6.1f}%  "
              f"{r['rating_v2']:<12} [{sector[:18]:<18}]  {name}")

    print(f"\n10. Saving outputs...")
    with open(OUTPUT_FILE, "w") as f:
        json.dump(predictions_out, f, default=str)
    print(f"    {OUTPUT_FILE} ({Path(OUTPUT_FILE).stat().st_size / 1024:.1f} KB)")

    metadata = {
        "scored_at": scored_at,
        "model_version": bundle["metadata"]["version"],
        "model_trained_at": bundle["metadata"]["trained_at"],
        "n_tickers_scored": len(predictions_out),
        "n_tickers_in_cache": len(cache),
        "regime": regime_class,
        "regime_features": regime,
        "rating_thresholds_dynamic": thresholds_dynamic,
        "rating_thresholds_static": thresholds_static,
        "rating_distribution": rating_counts,
        "feature_completeness_mean": float(np.mean(completeness_scores)),
        "feature_completeness_min": float(np.min(completeness_scores)),
        "prediction_distribution": {
            "min": float(preds.min()),
            "q05": float(np.quantile(preds, 0.05)),
            "q20": float(np.quantile(preds, 0.20)),
            "median": float(np.median(preds)),
            "q80": float(np.quantile(preds, 0.80)),
            "q95": float(np.quantile(preds, 0.95)),
            "max": float(preds.max()),
        },
    }
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"    {METADATA_FILE}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
