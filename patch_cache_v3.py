"""
Patch 2: build_cache.py improvements for full feature coverage.

Two changes:

1. Fetch 12 quarters instead of 8 in fetch_quarterly_history.
   - This is needed because trend features compare quarter[0] to quarter[4],
     and YoY growth on quarter[4] requires quarter[8] for the comparison.
   - Without this, revenue_growth_yoy_yoy_change and
     earnings_growth_yoy_yoy_change are always None.

2. Add 3 fields to fetch_stock return dict from yfinance info:
   - totalDebt
   - totalCash
   - stockholdersEquity
   These enable debt_to_equity and cash_to_market_cap ratio computation
   in the scoring pipeline.

Run from the dashboard repo. Backs up to build_cache.py.bak3.
"""

from pathlib import Path
import shutil
import sys

TARGET = Path("./build_cache.py")

# Patch 1: max_quarters=8 → max_quarters=12
OLD_QUARTERS = "def fetch_quarterly_history(t, max_quarters=8):"
NEW_QUARTERS = "def fetch_quarterly_history(t, max_quarters=12):"

# Patch 2: Add 3 fields just before quarterly_history in fetch_stock return
OLD_RETURN = '''            "analyst_count": info.get("numberOfAnalystOpinions", 0),
            "quarterly_history": fetch_quarterly_history(t),'''

NEW_RETURN = '''            "analyst_count": info.get("numberOfAnalystOpinions", 0),
            "totalDebt": info.get("totalDebt"),
            "totalCash": info.get("totalCash"),
            "stockholdersEquity": info.get("stockholdersEquity"),
            "quarterly_history": fetch_quarterly_history(t),'''

# Update est. time
OLD_TIME = 'print(f"  Est. time: 40-55 minutes (with quarterly history)")'
NEW_TIME = 'print(f"  Est. time: 50-65 minutes (12 quarters + balance sheet fields)")'


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found")
        return 1

    text = TARGET.read_text(encoding="utf-8")

    # Idempotency check
    if "max_quarters=12" in text and '"totalDebt": info.get("totalDebt")' in text:
        print("Already patched.")
        return 0

    # Validate
    issues = []
    if OLD_QUARTERS not in text:
        issues.append("could not find max_quarters=8 signature")
    if OLD_RETURN not in text:
        issues.append("could not find return dict pattern with quarterly_history")
    if issues:
        print("ERROR: cannot apply patch:")
        for i in issues:
            print(f"  - {i}")
        return 1

    # Backup
    backup = Path("build_cache.py.bak3")
    shutil.copy(TARGET, backup)
    print(f"Backup: {backup}")

    # Apply
    text = text.replace(OLD_QUARTERS, NEW_QUARTERS)
    text = text.replace(OLD_RETURN, NEW_RETURN)
    if OLD_TIME in text:
        text = text.replace(OLD_TIME, NEW_TIME)

    TARGET.write_text(text, encoding="utf-8")

    # Validate result
    import ast
    try:
        ast.parse(TARGET.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"ERROR: syntax broken: {e}")
        shutil.copy(backup, TARGET)
        return 1

    print("Patched successfully:")
    print("  - fetch_quarterly_history now fetches 12 quarters")
    print("  - fetch_stock now stores totalDebt, totalCash, stockholdersEquity")
    print("  - Time estimate updated")
    print()
    print("Next: python build_cache.py  (~50-65 min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
