"""
SimFin v3 API test + Python bulk-download approach.

The /api/v2 endpoints SimFin previously used are gone (404).
Try /api/v3 endpoints from their 2023+ documentation.
Also confirm we can use simfin Python package for bulk download.
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

print(f"SimFin key: {SIMFIN_KEY[:6]}...{SIMFIN_KEY[-4:]}")
print()


def test_v3_general():
    """v3 companies/general endpoint."""
    print("=" * 80)
    print("TEST 1: SimFin v3 - companies/general for AAPL")
    print("=" * 80)

    url = "https://backend.simfin.com/api/v3/companies/general/compact"
    params = {"ticker": "AAPL"}
    headers = {"Authorization": f"api-key {SIMFIN_KEY}"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=30)
        print(f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                print(f"Got {len(data)} companies")
                first = data[0]
                if isinstance(first, dict):
                    print(f"Fields: {list(first.keys())[:8]}")
                    print(f"Name: {first.get('name', first.get('companyName'))}")
                    print(f"ID: {first.get('id', first.get('SimFinId'))}")
                else:
                    print(f"First item: {first}")
            elif isinstance(data, dict):
                print(f"Dict response: {json.dumps(data)[:400]}")
        else:
            print(f"Response: {r.text[:500]}")
    except Exception as e:
        print(f"Exception: {e}")
    print()


def test_v3_alt_url():
    """Try alternative v3 URL patterns."""
    print("=" * 80)
    print("TEST 2: Try various SimFin URL patterns")
    print("=" * 80)

    urls_to_try = [
        ("backend api/v3 general", "https://backend.simfin.com/api/v3/companies/general/compact?ticker=AAPL"),
        ("api/v3 general", "https://simfin.com/api/v3/companies/general/compact?ticker=AAPL"),
        ("backend api/v3 statements", "https://backend.simfin.com/api/v3/companies/statements/compact?ticker=AAPL&statements=PL"),
        ("backend v3 with auth header", "https://backend.simfin.com/api/v3/companies/general?ticker=AAPL"),
    ]

    for label, url in urls_to_try:
        # Try header auth
        h = {"Authorization": f"api-key {SIMFIN_KEY}"}
        try:
            r = requests.get(url, headers=h, timeout=15)
            status = r.status_code
            if status == 200:
                try:
                    data = r.json()
                    if isinstance(data, list):
                        print(f"  [{status}] {label}: list[{len(data)}]")
                    elif isinstance(data, dict):
                        print(f"  [{status}] {label}: dict({list(data.keys())[:5]})")
                except:
                    print(f"  [{status}] {label}: non-json response")
            else:
                msg = r.text[:120].replace('\n', ' ')
                print(f"  [{status}] {label}: {msg}")
        except Exception as e:
            print(f"  [ERR] {label}: {str(e)[:80]}")
        time.sleep(0.5)
    print()


def test_python_package_install():
    """Suggest installing the simfin Python package for bulk download."""
    print("=" * 80)
    print("TEST 3: SimFin Python package (RECOMMENDED for bulk download)")
    print("=" * 80)

    try:
        import simfin as sf
        print(f"simfin package installed: version {sf.__version__ if hasattr(sf, '__version__') else 'unknown'}")
        print("Can use sf.load_income(variant='annual', market='us') for full bulk dataset")
    except ImportError:
        print("simfin package NOT installed.")
        print()
        print("Install with:")
        print("  pip install simfin")
        print()
        print("Then this code will give us full free bulk dataset:")
        print("""
import simfin as sf
from simfin.names import *

sf.set_api_key('YOUR_KEY')
sf.set_data_dir('./simfin_data/')

# Annual income statements for ALL US companies
df_income = sf.load_income(variant='annual', market='us')
print(f"Total rows: {len(df_income)}")
print(f"Date range: {df_income.index.get_level_values('Report Date').min()} to {df_income.index.get_level_values('Report Date').max()}")

# Get AAPL data
aapl = df_income.loc['AAPL']
print(aapl[[REVENUE, NET_INCOME]])
""")


# Run all
test_v3_general()
time.sleep(1)
test_v3_alt_url()
time.sleep(1)
test_python_package_install()

print("=" * 80)
print("CONCLUSION:")
print("=" * 80)
print("If v3 REST endpoints work above, we know how to query SimFin programmatically.")
print("If they all 404, simfin Python package is the path - it bulk-downloads CSV files.")
print("Bulk download = one-time fetch, all data on disk, no rate limits.")
