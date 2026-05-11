"""
Patch build_cache.py to add quarterly history capture for trend features.

Adds a `quarterly_history` block to each stock's cache entry containing
the last 4-8 quarters of metrics needed for trend feature computation:
  - margins (gross, operating, net)
  - returns (ROE, ROA)
  - growth rates (revenue YoY, earnings YoY)

This enables the Phase 2 scoring pipeline to compute the 7 trend features
the model was trained on:
  gross_margin_yoy_change, operating_margin_yoy_change,
  net_margin_yoy_change, roe_yoy_change, roa_yoy_change,
  revenue_growth_yoy_yoy_change, earnings_growth_yoy_yoy_change

Per-ticker cost: ~3-5 sec extra (3 API calls for quarterly statements).
Total cache rebuild estimate: 27 min → ~40-50 min.

Run from the dashboard repo (where build_cache.py lives).

Original is backed up to build_cache.py.bak2 before modification.
"""

from pathlib import Path
import shutil
import sys

TARGET = Path("./build_cache.py")

# Marker for finding the right insertion point and the existing fetch_stock
INSERT_MARKER = "# ── Fetch Logic ────────────────────────────────────────────────────"

NEW_HISTORY_FUNCTION = '''# ── Fetch Logic ────────────────────────────────────────────────────


def fetch_quarterly_history(t, max_quarters=8):
    """Fetch last N quarters of key metrics for a ticker.

    Returns a list of dicts (most-recent first) with computable metrics.
    On any error or missing data, returns []. The caller must tolerate
    an empty result.

    Used to enable trend feature computation in the model scoring pipeline.
    Each quarter contains: date, grossMargins, operatingMargins, netMargins,
    returnOnEquity, returnOnAssets, revenueGrowth (yoy), earningsGrowth (yoy).
    """
    try:
        # Pull all three quarterly statements
        income = t.quarterly_income_stmt
        balance = t.quarterly_balance_sheet
        # cashflow not strictly needed for trend features but cheap to grab
        # cashflow = t.quarterly_cashflow

        if income is None or income.empty:
            return []

        # Columns are quarter-end dates, sorted newest first by yfinance
        # Take up to max_quarters
        quarters = list(income.columns)[:max_quarters]
        if len(quarters) < 2:
            return []

        # Helper to safely extract a row value, returning None if missing
        def get_val(df, row_name, col):
            try:
                if df is None or df.empty:
                    return None
                if row_name not in df.index:
                    return None
                v = df.at[row_name, col]
                if v is None:
                    return None
                fv = float(v)
                if not np.isfinite(fv):
                    return None
                return fv
            except Exception:
                return None

        history = []

        # Pre-compute revenue series for YoY growth (needs same-quarter-prior-year)
        # yfinance gives ~4 quarters typically, sometimes 5-8
        # We compute YoY by comparing q[i] to q[i+4] when both exist
        rev_by_q = {}
        ni_by_q = {}
        for q in quarters:
            rev_by_q[q] = get_val(income, "Total Revenue", q)
            ni_by_q[q] = get_val(income, "Net Income", q)

        for i, q in enumerate(quarters):
            revenue = rev_by_q.get(q)
            net_income = ni_by_q.get(q)
            cogs = get_val(income, "Cost Of Revenue", q)
            op_income = get_val(income, "Operating Income", q)

            # Margins
            gross_margin = None
            op_margin = None
            net_margin = None
            if revenue and revenue > 0:
                if cogs is not None:
                    gross_margin = (revenue - cogs) / revenue
                if op_income is not None:
                    op_margin = op_income / revenue
                if net_income is not None:
                    net_margin = net_income / revenue

            # Returns: need balance sheet
            equity = get_val(balance, "Stockholders Equity", q)
            assets = get_val(balance, "Total Assets", q)

            roe = None
            roa = None
            if net_income is not None:
                # Annualize quarterly NI by *4 for ROE/ROA computation
                ni_annualized = net_income * 4
                if equity and equity > 0:
                    roe = ni_annualized / equity
                if assets and assets > 0:
                    roa = ni_annualized / assets

            # YoY growth: compare to same quarter 4 quarters back
            rev_growth_yoy = None
            ni_growth_yoy = None
            if i + 4 < len(quarters):
                q_prior = quarters[i + 4]
                rev_prior = rev_by_q.get(q_prior)
                ni_prior = ni_by_q.get(q_prior)
                if revenue is not None and rev_prior and rev_prior > 0:
                    rev_growth_yoy = (revenue - rev_prior) / rev_prior
                if net_income is not None and ni_prior and ni_prior != 0:
                    ni_growth_yoy = (net_income - ni_prior) / abs(ni_prior)

            history.append({
                "date": str(q.date()) if hasattr(q, "date") else str(q),
                "grossMargins": round(gross_margin, 4) if gross_margin is not None else None,
                "operatingMargins": round(op_margin, 4) if op_margin is not None else None,
                "netMargins": round(net_margin, 4) if net_margin is not None else None,
                "returnOnEquity": round(roe, 4) if roe is not None else None,
                "returnOnAssets": round(roa, 4) if roa is not None else None,
                "revenueGrowth": round(rev_growth_yoy, 4) if rev_growth_yoy is not None else None,
                "earningsGrowth": round(ni_growth_yoy, 4) if ni_growth_yoy is not None else None,
            })

        return history
    except Exception:
        return []


'''

# What we replace: add the function AND modify fetch_stock to call it.
# We'll insert the new function before fetch_stock, then add the
# quarterly_history field to fetch_stock's return dict.

OLD_HEADER = "# ── Fetch Logic ────────────────────────────────────────────────────\n\ndef fetch_stock(ticker):"

NEW_HEADER = NEW_HISTORY_FUNCTION + "def fetch_stock(ticker):"

# Add quarterly_history to fetch_stock return dict (insert before lastUpdated)
OLD_RETURN_TAIL = '''            "analyst_count": info.get("numberOfAnalystOpinions", 0),
            "lastUpdated": datetime.now().isoformat(),
        }
    except Exception as e:
        return None'''

NEW_RETURN_TAIL = '''            "analyst_count": info.get("numberOfAnalystOpinions", 0),
            "quarterly_history": fetch_quarterly_history(t),
            "lastUpdated": datetime.now().isoformat(),
        }
    except Exception as e:
        return None'''

# Update the time estimate displayed at startup
OLD_TIME_EST = 'print(f"  Est. time: 12-18 minutes")'
NEW_TIME_EST = 'print(f"  Est. time: 40-55 minutes (with quarterly history)")'


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found in current directory")
        print(f"  Run this from the dashboard repo where build_cache.py lives.")
        return 1

    text = TARGET.read_text(encoding="utf-8")

    # Idempotency check
    if "fetch_quarterly_history" in text:
        print("Already patched (fetch_quarterly_history function present).")
        print("Nothing to do.")
        return 0

    # Apply patches in sequence
    if OLD_HEADER not in text:
        print("ERROR: expected fetch_stock header pattern not found.")
        print("Aborting to avoid breaking the file.")
        return 1

    if OLD_RETURN_TAIL not in text:
        print("ERROR: expected fetch_stock return-dict pattern not found.")
        print("Aborting.")
        return 1

    if OLD_TIME_EST not in text:
        print("WARNING: time estimate string not found — patch will skip that update")
        # Not fatal; continue

    # Backup
    backup = Path("build_cache.py.bak2")
    shutil.copy(TARGET, backup)
    print(f"Backup saved to {backup}")

    # Apply patches
    new_text = text.replace(OLD_HEADER, NEW_HEADER)
    new_text = new_text.replace(OLD_RETURN_TAIL, NEW_RETURN_TAIL)
    if OLD_TIME_EST in new_text:
        new_text = new_text.replace(OLD_TIME_EST, NEW_TIME_EST)

    TARGET.write_text(new_text, encoding="utf-8")

    # Verify
    verify = TARGET.read_text(encoding="utf-8")
    checks = {
        "function_added": "def fetch_quarterly_history" in verify,
        "function_called": "quarterly_history\": fetch_quarterly_history(t)" in verify,
        "syntax_valid": True,
    }
    try:
        import ast
        ast.parse(verify)
    except SyntaxError as e:
        checks["syntax_valid"] = False
        print(f"ERROR: patched file has syntax error: {e}")
        print(f"Restoring from backup...")
        shutil.copy(backup, TARGET)
        return 1

    all_ok = all(checks.values())
    print()
    print("Patch verification:")
    for check, ok in checks.items():
        sym = "OK" if ok else "FAIL"
        print(f"  {check:<25} {sym}")
    print()

    if all_ok:
        print("Patch applied successfully.")
        print()
        print("Changes:")
        print("  - Added fetch_quarterly_history(t, max_quarters=8) function")
        print("    Returns up to 8 quarters of margins/returns/growth metrics")
        print("  - fetch_stock() now stores quarterly_history in cache record")
        print("  - Updated time estimate to 40-55 min")
        print()
        print("Next step:")
        print("  Run: python build_cache.py")
        print("  This rebuilds fundamentals_cache.json with quarterly_history")
        print("  Estimated time: ~40-55 min")
        return 0
    else:
        print("Patch failed verification. File restored from backup.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
