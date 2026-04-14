"""
ETF Screener and Detail module.
Screens ETFs by momentum, category, expense ratio, and performance.
ETFs don't get 5-pillar factor grades but have their own metrics.
"""

import json
import os
import pandas as pd
import numpy as np


def load_etf_data() -> pd.DataFrame:
    """Load all ETFs from the fundamentals cache."""
    for path in ["fundamentals_cache.json", os.path.join("data_cache", "fundamentals_cache.json")]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)

                etfs = {}
                for ticker, info in data.items():
                    if info.get("type") == "etf" or info.get("sector") == "ETF":
                        etfs[ticker] = info

                if not etfs:
                    return pd.DataFrame()

                df = pd.DataFrame.from_dict(etfs, orient="index")
                df.index.name = "ticker"

                # Compute momentum score (simple average of available momentum metrics)
                mom_cols = ["momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m"]
                for col in mom_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")

                available_mom = [c for c in mom_cols if c in df.columns]
                if available_mom:
                    df["momentum_score"] = df[available_mom].mean(axis=1)
                else:
                    df["momentum_score"] = 0

                # Format columns
                if "currentPrice" in df.columns:
                    df["currentPrice"] = pd.to_numeric(df["currentPrice"], errors="coerce")
                if "totalAssets" in df.columns:
                    df["totalAssets"] = pd.to_numeric(df["totalAssets"], errors="coerce")
                    df["aum_b"] = (df["totalAssets"] / 1e9).round(1)
                else:
                    df["aum_b"] = 0

                return df.sort_values("momentum_score", ascending=False)

            except Exception:
                pass
    return pd.DataFrame()


def get_etf_categories(etf_df: pd.DataFrame) -> list[str]:
    """Get unique ETF categories/industries."""
    if etf_df.empty:
        return []
    categories = etf_df["industry"].dropna().unique().tolist()
    return sorted([c for c in categories if c and c != "Unknown" and c != "ETF"])


def filter_etfs(
    etf_df: pd.DataFrame,
    category: str = None,
    min_momentum_1m: float = None,
    max_expense_ratio: float = None,
    sort_by: str = "momentum_score",
) -> pd.DataFrame:
    """Filter ETFs by various criteria."""
    if etf_df.empty:
        return etf_df

    df = etf_df.copy()

    if category and category != "All":
        df = df[df["industry"] == category]

    if min_momentum_1m is not None and "momentum_1m" in df.columns:
        df = df[pd.to_numeric(df["momentum_1m"], errors="coerce") >= min_momentum_1m / 100]

    if max_expense_ratio is not None and "expenseRatio" in df.columns:
        er = pd.to_numeric(df["expenseRatio"], errors="coerce")
        df = df[(er <= max_expense_ratio / 100) | er.isna()]

    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=False)

    return df


def get_etf_detail(ticker: str, etf_df: pd.DataFrame) -> dict:
    """Get detailed info for a single ETF."""
    if etf_df.empty or ticker not in etf_df.index:
        return {}

    row = etf_df.loc[ticker]

    def safe_pct(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "N/A"
        return f"{float(val)*100:+.1f}%"

    return {
        "ticker": ticker,
        "name": row.get("shortName", ticker),
        "category": row.get("industry", "Unknown"),
        "price": row.get("currentPrice", 0),
        "aum_b": row.get("aum_b", 0),
        "expense_ratio": row.get("expenseRatio"),
        "nav": row.get("navPrice"),
        "ytd_return": row.get("ytdReturn"),
        "three_year_return": row.get("threeYearReturn"),
        "five_year_return": row.get("fiveYearReturn"),
        "momentum_1m": row.get("momentum_1m"),
        "momentum_3m": row.get("momentum_3m"),
        "momentum_6m": row.get("momentum_6m"),
        "momentum_12m": row.get("momentum_12m"),
        "vs_sma50": row.get("momentum_vs_sma50"),
        "vs_sma200": row.get("momentum_vs_sma200"),
        "momentum_summary": {
            "1 Month": safe_pct(row.get("momentum_1m")),
            "3 Month": safe_pct(row.get("momentum_3m")),
            "6 Month": safe_pct(row.get("momentum_6m")),
            "12 Month": safe_pct(row.get("momentum_12m")),
            "vs 50-SMA": safe_pct(row.get("momentum_vs_sma50")),
            "vs 200-SMA": safe_pct(row.get("momentum_vs_sma200")),
        },
    }
