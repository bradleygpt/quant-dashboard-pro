"""
SimFin v3 - properly parse the nested {statements: [{columns, data}]} structure.
"""
import os
import sys
import json

import requests

SIMFIN_KEY = os.environ.get("SIMFIN_API_KEY")
if not SIMFIN_KEY:
    print("ERROR: SIMFIN_API_KEY not set")
    sys.exit(1)

BASE_URL = "https://backend.simfin.com/api/v3"
HEADERS = {"Authorization": f"api-key {SIMFIN_KEY}"}


def parse_statements(response_json, ticker):
    """
    Parse SimFin v3 statements response.
    Structure: [{"statements": [{"statement": "PL", "columns": [...], "data": [[row], [row]]}]}]
    """
    if not isinstance(response_json, list) or not response_json:
        return None
    company = response_json[0]
    if "statements" not in company or not company["statements"]:
        return None

    # Each item in statements is one statement type (PL, BS, CF)
    parsed = {}
    for stmt in company["statements"]:
        stmt_type = stmt.get("statement", "?")
        cols = stmt.get("columns", [])
        rows = stmt.get("data", [])

        # Convert rows of values into list of dicts
        records = [dict(zip(cols, row)) for row in rows]
        parsed[stmt_type] = {"columns": cols, "records": records}
    return parsed


def get_full_statements(ticker, statement_types="PL,BS,CF"):
    """Get all statement types for ticker."""
    url = f"{BASE_URL}/companies/statements/compact"
    params = {"ticker": ticker, "statements": statement_types}
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    return r


def show_coverage(ticker, statement_types="PL"):
    print(f"\n{'='*80}")
    print(f"{ticker} - statements: {statement_types}")
    print(f"{'='*80}")

    r = get_full_statements(ticker, statement_types)
    if r.status_code != 200:
        print(f"HTTP {r.status_code}: {r.text[:300]}")
        return

    parsed = parse_statements(r.json(), ticker)
    if not parsed:
        print("Could not parse response")
        return

    for stmt_type, content in parsed.items():
        cols = content["columns"]
        records = content["records"]
        print(f"\n  {stmt_type}: {len(records)} records, {len(cols)} columns")

        # Find date and revenue/key fields
        date_field = None
        for c in cols:
            if c in ["Report Date", "reportDate", "End Date"]:
                date_field = c
                break
        if not date_field:
            # Try anything with "date" in it
            for c in cols:
                if "date" in c.lower():
                    date_field = c
                    break

        rev_field = None
        for c in cols:
            if c in ["Revenue", "revenue", "Sales", "Total Revenue"]:
                rev_field = c
                break

        period_field = next((c for c in cols if c in ["Fiscal Period", "fiscalPeriod"]), None)
        fy_field = next((c for c in cols if c in ["Fiscal Year", "fiscalYear"]), None)

        print(f"  Sample columns: {cols[:12]}")
        print(f"  Date field: {date_field}, Revenue field: {rev_field}")

        if date_field and records:
            sortable = []
            for rec in records:
                d = rec.get(date_field)
                if d:
                    rev = rec.get(rev_field) if rev_field else None
                    fy = rec.get(fy_field) if fy_field else None
                    fp = rec.get(period_field) if period_field else None
                    sortable.append((d, fy, fp, rev))
            sortable.sort(key=lambda x: x[0])

            print(f"\n  Earliest 5:")
            for d, fy, fp, rev in sortable[:5]:
                rev_str = f"${rev:,.0f}" if isinstance(rev, (int, float)) else str(rev)
                print(f"    {d}: FY{fy} {fp} - {rev_str}")
            print(f"\n  Latest 5:")
            for d, fy, fp, rev in sortable[-5:]:
                rev_str = f"${rev:,.0f}" if isinstance(rev, (int, float)) else str(rev)
                print(f"    {d}: FY{fy} {fp} - {rev_str}")


# Run
print("SimFin v3 data coverage assessment\n")

show_coverage("AAPL", "PL")
show_coverage("AAPL", "BS")
show_coverage("GE", "PL")
show_coverage("MSFT", "PL")
show_coverage("KO", "PL")  # Coca-Cola - very old company

print("\n" + "=" * 80)
print("ASSESSMENT NEEDED:")
print("=" * 80)
print("Look at the EARLIEST date for each ticker above.")
print("- If 1985-1990: Full historical depth available")
print("- If 2000-2003: Dot-com tail captured but no GFC pre-data")
print("- If 2009-2014: Same data wall as EDGAR, no improvement")
