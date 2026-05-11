"""
FMP and SimFin coverage test - FMP capped at 5 records on free tier.
Focus: confirm SimFin gives us full historical depth.
"""
import os
import sys
import json
import time

import requests

FMP_KEY = os.environ.get("FMP_API_KEY")
SIMFIN_KEY = os.environ.get("SIMFIN_API_KEY")

if not FMP_KEY or not SIMFIN_KEY:
    print("ERROR: API keys not set")
    sys.exit(1)

print(f"FMP key: {FMP_KEY[:6]}...{FMP_KEY[-4:]}")
print(f"SimFin key: {SIMFIN_KEY[:6]}...{SIMFIN_KEY[-4:]}")
print()


def test_fmp_5year_limit():
    """FMP free tier - confirm what 5 years actually gives us."""
    print("=" * 80)
    print("TEST 1: FMP free tier - max 5 records (annual)")
    print("=" * 80)

    url = "https://financialmodelingprep.com/stable/income-statement"
    params = {"symbol": "AAPL", "period": "annual", "limit": 5, "apikey": FMP_KEY}

    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                print(f"Got {len(data)} records")
                for d in data:
                    rev = d.get('revenue', 0)
                    rev_str = f"${rev:,.0f}" if isinstance(rev, (int, float)) else str(rev)
                    print(f"  {d.get('date')} - revenue={rev_str}")
            else:
                print(f"Unexpected: {str(data)[:200]}")
        else:
            print(f"HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"Exception: {e}")
    print()


def test_simfin_company():
    """Confirm SimFin API works."""
    print("=" * 80)
    print("TEST 2: SimFin company lookup AAPL")
    print("=" * 80)

    url = "https://simfin.com/api/v2/companies/general"
    params = {"ticker": "AAPL", "api-key": SIMFIN_KEY}

    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                print(f"Response is list[{len(data)}], first: {str(data[0])[:300]}")
            elif isinstance(data, dict):
                print(f"Response is dict: {str(data)[:400]}")
        else:
            print(f"Response: {r.text[:500]}")
    except Exception as e:
        print(f"Exception: {e}")
    print()


def test_simfin_annual():
    """SimFin annual income statements - full history."""
    print("=" * 80)
    print("TEST 3: SimFin AAPL annual income statements")
    print("=" * 80)

    url = "https://simfin.com/api/v2/companies/statements"
    params = {
        "ticker": "AAPL",
        "statement": "pl",
        "period": "fy",
        "fyear": "all",
        "api-key": SIMFIN_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                first = data[0]
                if "data" in first and first["data"]:
                    cols = first["columns"]
                    rows = first["data"]
                    print(f"Got {len(rows)} annual statements")
                    print(f"Columns ({len(cols)} total): {cols[:8]}")

                    rev_idx = next((i for i, c in enumerate(cols) if c == "Revenue"), None)
                    date_idx = next((i for i, c in enumerate(cols) if c == "Report Date"), None)
                    fy_idx = next((i for i, c in enumerate(cols) if c == "Fiscal Year"), None)

                    if date_idx is not None:
                        dated_rows = [(r[date_idx], r[fy_idx] if fy_idx is not None else None,
                                      r[rev_idx] if rev_idx is not None else None) for r in rows]
                        dated_rows.sort(key=lambda x: x[0] if x[0] else "")

                        print(f"\nEarliest 5:")
                        for d, fy, rev in dated_rows[:5]:
                            rev_str = f"${rev:,.0f}" if isinstance(rev, (int, float)) else str(rev)
                            print(f"  {d} (FY{fy}): Rev={rev_str}")
                        print(f"\nLatest 5:")
                        for d, fy, rev in dated_rows[-5:]:
                            rev_str = f"${rev:,.0f}" if isinstance(rev, (int, float)) else str(rev)
                            print(f"  {d} (FY{fy}): Rev={rev_str}")
                else:
                    print(f"No data in first dataset: {str(first)[:300]}")
            else:
                print(f"Unexpected: {str(data)[:400]}")
        else:
            print(f"Error: {r.text[:500]}")
    except Exception as e:
        print(f"Exception: {e}")
    print()


def test_simfin_quarterly():
    """SimFin quarterly income statements."""
    print("=" * 80)
    print("TEST 4: SimFin AAPL quarterly income statements")
    print("=" * 80)

    url = "https://simfin.com/api/v2/companies/statements"
    params = {
        "ticker": "AAPL",
        "statement": "pl",
        "period": "quarters",
        "fyear": "all",
        "api-key": SIMFIN_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                first = data[0]
                if "data" in first and first["data"]:
                    rows = first["data"]
                    cols = first["columns"]
                    date_idx = next((i for i, c in enumerate(cols) if c == "Report Date"), None)
                    print(f"Got {len(rows)} quarterly statements")
                    if date_idx is not None:
                        dates = sorted([r[date_idx] for r in rows if r[date_idx]])
                        if dates:
                            print(f"Earliest: {dates[0]}")
                            print(f"Latest: {dates[-1]}")
        else:
            print(f"Error: {r.text[:500]}")
    except Exception as e:
        print(f"Exception: {e}")
    print()


def test_simfin_balance_sheet():
    """Confirm balance sheet also works."""
    print("=" * 80)
    print("TEST 5: SimFin AAPL annual balance sheet")
    print("=" * 80)

    url = "https://simfin.com/api/v2/companies/statements"
    params = {
        "ticker": "AAPL",
        "statement": "bs",  # balance sheet
        "period": "fy",
        "fyear": "all",
        "api-key": SIMFIN_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                first = data[0]
                if "data" in first and first["data"]:
                    rows = first["data"]
                    cols = first["columns"]
                    date_idx = next((i for i, c in enumerate(cols) if c == "Report Date"), None)
                    print(f"Got {len(rows)} annual balance sheets")
                    print(f"Sample columns: {cols[:8]}")
                    if date_idx is not None:
                        dates = sorted([r[date_idx] for r in rows if r[date_idx]])
                        if dates:
                            print(f"Earliest: {dates[0]}")
                            print(f"Latest: {dates[-1]}")
        else:
            print(f"Error: {r.text[:500]}")
    except Exception as e:
        print(f"Exception: {e}")
    print()


def test_simfin_old_company():
    """Test with a company that's been around longer than AAPL went public.
    AAPL IPO'd 1980 so has long history. Try GE which has been public since 1962."""
    print("=" * 80)
    print("TEST 6: SimFin - check coverage on long-history company (GE)")
    print("=" * 80)

    url = "https://simfin.com/api/v2/companies/statements"
    params = {
        "ticker": "GE",
        "statement": "pl",
        "period": "fy",
        "fyear": "all",
        "api-key": SIMFIN_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                first = data[0]
                if "data" in first and first["data"]:
                    rows = first["data"]
                    cols = first["columns"]
                    date_idx = next((i for i, c in enumerate(cols) if c == "Report Date"), None)
                    print(f"GE: {len(rows)} annual statements")
                    if date_idx is not None:
                        dates = sorted([r[date_idx] for r in rows if r[date_idx]])
                        if dates:
                            print(f"Earliest: {dates[0]}")
                            print(f"Latest: {dates[-1]}")
        else:
            print(f"Error: {r.text[:500]}")
    except Exception as e:
        print(f"Exception: {e}")
    print()


# Run
test_fmp_5year_limit()
time.sleep(1)
test_simfin_company()
time.sleep(1)
test_simfin_annual()
time.sleep(1)
test_simfin_quarterly()
time.sleep(1)
test_simfin_balance_sheet()
time.sleep(1)
test_simfin_old_company()

print("=" * 80)
print("ASSESSMENT:")
print("=" * 80)
print("- FMP free tier: 5 records max - useless for historical backtest")
print("- SimFin: shows actual coverage range, deciding factor")
