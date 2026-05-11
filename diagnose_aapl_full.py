"""
Comprehensive diagnostic to identify EXACTLY what's broken in EDGAR PIT extraction.

Tests:
1. What does our get_fundamentals_at_date actually return for AAPL at 2024-01-15?
2. Which revenue/COGS tag is _get_ttm_value picking?
3. What does the TTM aggregation look like with each tag?
4. What's the real revenue and COGS for AAPL in TTM ending Q3 2023?
5. What filings happened between 2023-08-04 and 2024-01-15 (any tag)?
6. Why isn't the 10-K filing being found?

This must complete cleanly. Each section runs independently.
"""
import sys
sys.path.insert(0, ".")
import json
from datetime import datetime, date
from edgar_fundamentals import (
    _load_ticker_cik_map, fetch_companyfacts, CONCEPT_MAPPING,
    get_fundamentals_at_date, _get_ttm_value
)

# Setup
cik_map = _load_ticker_cik_map()
cik = cik_map.get("AAPL")
print(f"AAPL CIK: {cik}")

facts = fetch_companyfacts("AAPL", cik)
us_gaap = facts.get("facts", {}).get("us-gaap", {})

target_date = datetime(2024, 1, 15)
target_dt_only = target_date.date()

print()
print("=" * 80)
print("PART 1: What does get_fundamentals_at_date ACTUALLY return?")
print("=" * 80)
result = get_fundamentals_at_date("AAPL", target_date, verbose=False)
print()
for key in sorted(result.keys()):
    val = result[key]
    if isinstance(val, (int, float)) and abs(val) > 1000:
        print(f"  {key}: ${val:,.0f}")
    else:
        print(f"  {key}: {val}")

# Helpers
def get_quarterly_entries(tag, target_dt):
    """Get all quarterly entries (80-100 day periods) for a tag, filed before target."""
    if tag not in us_gaap:
        return []
    units = us_gaap[tag].get("units", {})
    if "USD" not in units:
        return []
    entries = []
    for e in units["USD"]:
        try:
            end_str = e.get("end")
            start_str = e.get("start")
            filed_str = e.get("filed")
            if not all([end_str, start_str, filed_str]):
                continue
            end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
            filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()
            if filed_dt > target_dt:
                continue
            period = (end_dt - start_dt).days
            if 80 <= period <= 100:
                entries.append((end_dt, filed_dt, e.get("val"), period))
        except:
            continue
    return entries


def get_all_entries(tag, target_dt):
    """Get ALL entries (any period) filed before target."""
    if tag not in us_gaap:
        return []
    units = us_gaap[tag].get("units", {})
    if "USD" not in units:
        return []
    entries = []
    for e in units["USD"]:
        try:
            end_str = e.get("end")
            start_str = e.get("start")
            filed_str = e.get("filed")
            if not all([end_str, start_str, filed_str]):
                continue
            end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
            filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()
            if filed_dt > target_dt:
                continue
            period = (end_dt - start_dt).days
            entries.append((end_dt, filed_dt, e.get("val"), period))
        except:
            continue
    return entries


print()
print("=" * 80)
print("PART 2: Revenue tag analysis for AAPL")
print("=" * 80)
for i, tag in enumerate(CONCEPT_MAPPING["revenue"]):
    if tag in us_gaap:
        quarterly = sorted(get_quarterly_entries(tag, target_dt_only), reverse=True)
        all_e = sorted(get_all_entries(tag, target_dt_only), reverse=True)
        print(f"\n  [{i+1}] {tag}")
        print(f"      QUARTERLY (80-100d): {len(quarterly)} entries")
        if quarterly:
            print(f"      Top 4 quarterly (most recent):")
            for end_dt, filed_dt, val, period in quarterly[:4]:
                print(f"        end={end_dt} filed={filed_dt} val=${val:,.0f} period={period}d")
        print(f"      ALL PERIODS: {len(all_e)} entries")
        if all_e:
            print(f"      Top 4 by end date (any period):")
            for end_dt, filed_dt, val, period in all_e[:4]:
                print(f"        end={end_dt} filed={filed_dt} val=${val:,.0f} period={period}d")
    else:
        print(f"\n  [{i+1}] {tag}: NOT IN AAPL FACTS")

print()
print("=" * 80)
print("PART 3: What does _get_ttm_value RETURN for AAPL revenue?")
print("=" * 80)
ttm_rev_result = _get_ttm_value(facts, CONCEPT_MAPPING["revenue"], target_dt_only)
print(f"  _get_ttm_value(revenue) = {ttm_rev_result}")
if ttm_rev_result:
    print(f"  TTM revenue: ${ttm_rev_result[0]:,.0f}")
    print(f"  Latest end date: {ttm_rev_result[1]}")
print(f"  Real AAPL TTM revenue (Aug 2023 to Q3 2023): ~$383B")
print(f"  Real AAPL TTM revenue (Q3 2022 to Q3 2023): ~$394B")

print()
print("=" * 80)
print("PART 4: Cost of revenue analysis")
print("=" * 80)
ttm_cogs_result = _get_ttm_value(facts, CONCEPT_MAPPING["cost_of_revenue"], target_dt_only)
print(f"  _get_ttm_value(cost_of_revenue) = {ttm_cogs_result}")
if ttm_cogs_result:
    print(f"  TTM COGS: ${ttm_cogs_result[0]:,.0f}")
print(f"  Real AAPL TTM COGS: ~$212B")

print()
print("=" * 80)
print("PART 5: All filings between 2023-08-04 and 2024-01-15 (across ALL tags)")
print("=" * 80)
all_filings = {}  # date -> set of tags
for tag in us_gaap:
    units = us_gaap[tag].get("units", {})
    if "USD" not in units:
        continue
    for e in units["USD"]:
        try:
            filed_str = e.get("filed")
            if filed_str:
                filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()
                if date(2023, 8, 1) <= filed_dt <= target_dt_only:
                    all_filings.setdefault(filed_dt, set()).add(tag)
        except:
            continue

print()
for d in sorted(all_filings.keys(), reverse=True):
    n_tags = len(all_filings[d])
    print(f"  {d}: {n_tags} different tags filed")

print()
print("=" * 80)
print("PART 6: What tag would have the Q4 2023 10-K data?")
print("=" * 80)
# Q4 2023 fiscal year ends Sept 30. 10-K filed Nov 3, 2023.
# Look for entries filed 2023-11-03 with end dates around Sept 2023
print(f"  Looking for entries filed 2023-11-03 (the Q4 10-K):")
sample_count = 0
for tag in us_gaap:
    units = us_gaap[tag].get("units", {})
    if "USD" not in units:
        continue
    for e in units["USD"]:
        try:
            filed_str = e.get("filed")
            end_str = e.get("end")
            start_str = e.get("start")
            if filed_str == "2023-11-03" and end_str and start_str:
                end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
                start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
                period = (end_dt - start_dt).days
                if sample_count < 30:
                    val = e.get("val", "")
                    val_str = f"${val:,.0f}" if isinstance(val, (int, float)) and abs(val) > 1000 else str(val)
                    print(f"    {tag[:50]:<50} end={end_dt} period={period}d val={val_str}")
                    sample_count += 1
        except:
            continue
print(f"  ({sample_count} sample entries shown)")
