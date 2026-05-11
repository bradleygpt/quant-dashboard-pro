"""Diagnose AAPL EDGAR data to understand gross margin + filing date issues."""
import sys
sys.path.insert(0, ".")
import json
import os
from datetime import datetime, date
from edgar_fundamentals import _load_ticker_cik_map, fetch_companyfacts, CONCEPT_MAPPING

cik_map = _load_ticker_cik_map()
cik = cik_map.get("AAPL")
print(f"AAPL CIK: {cik}")

facts = fetch_companyfacts("AAPL", cik)
us_gaap = facts.get("facts", {}).get("us-gaap", {})

target_date = date(2024, 1, 15)

print()
print("=" * 70)
print("Issue 1: What cost_of_revenue tags exist for AAPL?")
print("=" * 70)
for tag in CONCEPT_MAPPING["cost_of_revenue"]:
    if tag in us_gaap:
        units = us_gaap[tag].get("units", {})
        if "USD" in units:
            entries = units["USD"]
            # Recent quarterly entries before target_date
            recent_quarterly = []
            for e in entries:
                try:
                    end_str = e.get("end")
                    start_str = e.get("start")
                    filed_str = e.get("filed")
                    if not all([end_str, start_str, filed_str]):
                        continue
                    end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
                    start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
                    filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()
                    if filed_dt > target_date:
                        continue
                    period_days = (end_dt - start_dt).days
                    if 80 <= period_days <= 100:
                        recent_quarterly.append((end_dt, filed_dt, e.get("val"), period_days))
                except:
                    continue
            recent_quarterly.sort(reverse=True)
            print(f"\n  {tag}: {len(recent_quarterly)} quarterly entries, top 6:")
            for end_dt, filed_dt, val, days in recent_quarterly[:6]:
                print(f"    end={end_dt} filed={filed_dt} val=${val:>15,.0f} period={days}d")
    else:
        print(f"  {tag}: NOT IN AAPL FACTS")

print()
print("=" * 70)
print("Issue 1 cont: What about Revenue for comparison?")
print("=" * 70)
for tag in CONCEPT_MAPPING["revenue"]:
    if tag in us_gaap:
        units = us_gaap[tag].get("units", {})
        if "USD" in units:
            entries = units["USD"]
            recent_quarterly = []
            for e in entries:
                try:
                    end_str = e.get("end")
                    start_str = e.get("start")
                    filed_str = e.get("filed")
                    if not all([end_str, start_str, filed_str]):
                        continue
                    end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
                    start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
                    filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()
                    if filed_dt > target_date:
                        continue
                    period_days = (end_dt - start_dt).days
                    if 80 <= period_days <= 100:
                        recent_quarterly.append((end_dt, filed_dt, e.get("val"), period_days))
                except:
                    continue
            recent_quarterly.sort(reverse=True)
            print(f"\n  {tag}: {len(recent_quarterly)} quarterly entries, top 6:")
            for end_dt, filed_dt, val, days in recent_quarterly[:6]:
                print(f"    end={end_dt} filed={filed_dt} val=${val:>15,.0f} period={days}d")
            break  # Just first found revenue tag

print()
print("=" * 70)
print("Issue 2: What earnings filing dates exist after 2023-08-04?")
print("=" * 70)
all_filing_dates = set()
for tag_list in [CONCEPT_MAPPING["revenue"], CONCEPT_MAPPING["net_income"]]:
    for tag in tag_list:
        if tag in us_gaap:
            for e in us_gaap[tag].get("units", {}).get("USD", []):
                try:
                    filed_str = e.get("filed")
                    if filed_str:
                        filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()
                        if date(2023, 8, 1) <= filed_dt <= target_date:
                            all_filing_dates.add(filed_dt)
                except:
                    continue

print(f"\n  All filing dates between 2023-08-01 and {target_date}:")
for d in sorted(all_filing_dates, reverse=True):
    print(f"    {d}")

print()
print("=" * 70)
print("Issue 2 cont: What's in AAPL's submissions for 10-K filings?")
print("=" * 70)
print("(Would need to fetch submissions endpoint — skipping for now)")
