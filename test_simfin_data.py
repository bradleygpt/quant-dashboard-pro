"""
SimFin v3 actual data extraction - confirm depth of coverage.
"""
import os
import sys
import json
import time

import requests

SIMFIN_KEY = os.environ.get("SIMFIN_API_KEY")
if not SIMFIN_KEY:
    print("ERROR: SIMFIN_API_KEY not set")
    sys.exit(1)

BASE_URL = "https://backend.simfin.com/api/v3"
HEADERS = {"Authorization": f"api-key {SIMFIN_KEY}"}


def get_aapl_id():
    """Get SimFin's internal ID for AAPL."""
    url = f"{BASE_URL}/companies/general/compact"
    params = {"ticker": "AAPL"}
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    if r.status_code == 200:
        data = r.json()
        # Response structure: {"columns": [...], "data": [[...]]}
        if "data" in data and data["data"]:
            cols = data["columns"]
            row = data["data"][0]
            return dict(zip(cols, row))
    return None


def get_statements(ticker, statement_type="PL", period="FY"):
    """Get statements for ticker.

    statement_type: PL (income), BS (balance sheet), CF (cash flow), DERIVED
    period: FY (full year), Q1, Q2, Q3, Q4, H1, H2, 9M
    """
    url = f"{BASE_URL}/companies/statements/compact"
    params = {
        "ticker": ticker,
        "statements": statement_type,
        # "period": period  # try without period filter to see all
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    return r


print("=" * 80)
print("STEP 1: Get AAPL company info from SimFin v3")
print("=" * 80)

aapl = get_aapl_id()
if aapl:
    print(f"AAPL found: id={aapl.get('id')}, ticker={aapl.get('ticker')}")
    print(f"Industry: {aapl.get('industryName')}")
    print(f"Sector: {aapl.get('sectorName')}")
    print(f"End fiscal year month: {aapl.get('endFy')}")
else:
    print("Could not get AAPL info")
    sys.exit(1)
print()


print("=" * 80)
print("STEP 2: Get AAPL annual income statements (P&L)")
print("=" * 80)

r = get_statements("AAPL", "PL", "FY")
print(f"HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json()
    if isinstance(data, list) and data:
        # Each item likely has structure with statements
        first = data[0]
        print(f"Top-level keys: {list(first.keys())[:10] if isinstance(first, dict) else 'not dict'}")
        print()

        # Inspect structure - usually has "statements" or "data" array
        if isinstance(first, dict):
            for k, v in first.items():
                if isinstance(v, list) and v:
                    print(f"  {k}: list of {len(v)} items")
                    if isinstance(v[0], dict):
                        print(f"    Sample keys: {list(v[0].keys())[:15]}")
                elif isinstance(v, dict):
                    print(f"  {k}: dict with {len(v)} keys")
                else:
                    print(f"  {k}: {str(v)[:80]}")

            # Look for the actual statements array
            statements = None
            for k in ["statements", "data", "values"]:
                if k in first and isinstance(first[k], list):
                    statements = first[k]
                    print(f"\n  Using '{k}' array with {len(statements)} statements")
                    break

            if statements:
                # Find date and revenue fields
                print(f"\n  All keys in first statement: {list(statements[0].keys())}")
                print()

                # Look for typical field names
                date_field = None
                revenue_field = None
                period_field = None

                possible_date_keys = ["reportDate", "Report Date", "report_date", "publicationDate", "endDate", "end_date", "fiscalPeriod"]
                possible_revenue_keys = ["revenue", "Revenue", "totalRevenue", "Total Revenue", "sales", "Sales"]

                for key in statements[0].keys():
                    if key in possible_date_keys:
                        date_field = key
                    if key in possible_revenue_keys:
                        revenue_field = key

                print(f"Date field detected: {date_field}")
                print(f"Revenue field detected: {revenue_field}")

                # Sort by date if possible
                if date_field:
                    sortable = [(s.get(date_field), s.get(revenue_field), s.get('fiscalYear'), s.get('fiscalPeriod')) for s in statements]
                    sortable = [s for s in sortable if s[0]]
                    sortable.sort(key=lambda x: x[0])

                    print()
                    print(f"Total statements: {len(sortable)}")
                    print(f"\nEarliest 5:")
                    for d, rev, fy, fp in sortable[:5]:
                        rev_str = f"${rev:,.0f}" if isinstance(rev, (int, float)) else str(rev)
                        print(f"  {d}: FY{fy} {fp} - Rev={rev_str}")
                    print(f"\nLatest 5:")
                    for d, rev, fy, fp in sortable[-5:]:
                        rev_str = f"${rev:,.0f}" if isinstance(rev, (int, float)) else str(rev)
                        print(f"  {d}: FY{fy} {fp} - Rev={rev_str}")
            else:
                print("Could not find statements list - dumping raw structure:")
                print(json.dumps(first, indent=2, default=str)[:1500])
    elif isinstance(data, dict):
        print(f"Got dict instead of list: {json.dumps(data, default=str)[:600]}")
    else:
        print(f"Empty data")
else:
    print(f"Error: {r.text[:500]}")

print()


print("=" * 80)
print("STEP 3: Get AAPL quarterly income statements")
print("=" * 80)

r = get_statements("AAPL", "PL", None)  # all periods
print(f"HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json()
    if isinstance(data, list) and data and isinstance(data[0], dict):
        statements = None
        for k in ["statements", "data", "values"]:
            if k in data[0] and isinstance(data[0][k], list):
                statements = data[0][k]
                break

        if statements:
            date_field = "reportDate" if "reportDate" in statements[0] else None
            if not date_field:
                for k in statements[0].keys():
                    if "date" in k.lower():
                        date_field = k
                        break

            if date_field:
                dates = sorted([s.get(date_field) for s in statements if s.get(date_field)])
                print(f"Total statements (all periods): {len(statements)}")
                if dates:
                    print(f"Earliest: {dates[0]}")
                    print(f"Latest: {dates[-1]}")

                # Count by period
                from collections import Counter
                periods = Counter(s.get('fiscalPeriod') or 'unknown' for s in statements)
                print(f"By period: {dict(periods)}")
print()


print("=" * 80)
print("STEP 4: Get GE annual P&L (long-history company)")
print("=" * 80)

r = get_statements("GE", "PL", "FY")
print(f"HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json()
    if isinstance(data, list) and data and isinstance(data[0], dict):
        statements = None
        for k in ["statements", "data", "values"]:
            if k in data[0] and isinstance(data[0][k], list):
                statements = data[0][k]
                break

        if statements:
            date_field = next((k for k in statements[0].keys() if "date" in k.lower()), None)
            if date_field:
                dates = sorted([s.get(date_field) for s in statements if s.get(date_field)])
                print(f"GE annual statements: {len(statements)}")
                if dates:
                    print(f"Earliest: {dates[0]}")
                    print(f"Latest: {dates[-1]}")
print()


print("=" * 80)
print("STEP 5: Get AAPL annual balance sheet")
print("=" * 80)

r = get_statements("AAPL", "BS", "FY")
print(f"HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json()
    if isinstance(data, list) and data and isinstance(data[0], dict):
        statements = None
        for k in ["statements", "data", "values"]:
            if k in data[0] and isinstance(data[0][k], list):
                statements = data[0][k]
                break

        if statements:
            date_field = next((k for k in statements[0].keys() if "date" in k.lower()), None)
            print(f"AAPL annual balance sheets: {len(statements)}")
            if date_field:
                dates = sorted([s.get(date_field) for s in statements if s.get(date_field)])
                if dates:
                    print(f"Earliest: {dates[0]}")
                    print(f"Latest: {dates[-1]}")
            print(f"Available fields: {list(statements[0].keys())}")
