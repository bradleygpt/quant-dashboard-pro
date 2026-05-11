"""Check if 2009 fundamentals exist in EDGAR for sample tickers - is data MISSING or just NOT FETCHED?"""
import sys
sys.path.insert(0, ".")
import json
import os
from datetime import datetime
from edgar_fundamentals import _load_ticker_cik_map, fetch_companyfacts, _get_ttm_value, CONCEPT_MAPPING, get_fundamentals_at_date

cik_map = _load_ticker_cik_map()

# Test on tickers we KNOW existed in 2009 with public earnings
test_tickers = ["AAPL", "MSFT", "JPM", "GE", "WMT", "JNJ", "PG", "KO", "XOM", "CVX"]
target_2010 = datetime(2010, 1, 15)
target_2009 = datetime(2009, 1, 15)

print("=" * 90)
print(f"Testing fundamentals availability at {target_2009.date()} (1 year before 2010-01-15)")
print("=" * 90)

for ticker in test_tickers:
    cik = cik_map.get(ticker)
    if not cik:
        print(f"\n{ticker}: NO CIK")
        continue

    facts = fetch_companyfacts(ticker, cik)
    if not facts:
        print(f"\n{ticker}: NO COMPANYFACTS DATA")
        continue

    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    # Check if revenue exists at any date <= 2009-01-15
    found_2009 = False
    earliest_revenue_date = None
    for tag in CONCEPT_MAPPING["revenue"]:
        if tag in us_gaap:
            for entry in us_gaap[tag].get("units", {}).get("USD", []):
                try:
                    filed_str = entry.get("filed")
                    end_str = entry.get("end")
                    if not (filed_str and end_str):
                        continue
                    filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()
                    end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
                    if filed_dt <= target_2009.date():
                        found_2009 = True
                        if earliest_revenue_date is None or filed_dt < earliest_revenue_date:
                            earliest_revenue_date = filed_dt
                except:
                    continue

    # Check what get_fundamentals_at_date returns for 2009
    f_2009 = get_fundamentals_at_date(ticker, target_2009)
    f_2010 = get_fundamentals_at_date(ticker, target_2010)

    rev_2009 = f_2009.get("ttm_revenue") if f_2009 else None
    rev_2010 = f_2010.get("ttm_revenue") if f_2010 else None
    growth = None
    if rev_2010 and f_2010.get("revenue_growth_yoy") is not None:
        growth = f_2010.get("revenue_growth_yoy")

    print(f"\n{ticker}:")
    print(f"  EDGAR has data filed before 2009-01-15: {found_2009} (earliest: {earliest_revenue_date})")
    print(f"  TTM Revenue at 2009-01-15: ${rev_2009:,.0f}" if rev_2009 else f"  TTM Revenue at 2009-01-15: MISSING")
    print(f"  TTM Revenue at 2010-01-15: ${rev_2010:,.0f}" if rev_2010 else f"  TTM Revenue at 2010-01-15: MISSING")
    print(f"  Computed revenue_growth_yoy: {growth}%" if growth is not None else f"  Computed revenue_growth_yoy: MISSING")
