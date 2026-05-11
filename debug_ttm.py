import json
import datetime
from edgar_fundamentals import _get_ttm_value, CONCEPT_MAPPING

f = json.load(open('edgar_cache/AAPL_facts.json'))
target = datetime.date(2018, 6, 15)

print(f"Target date: {target}")
print()

# Try each revenue tag manually
for tag in CONCEPT_MAPPING['revenue']:
    print(f"Trying tag: {tag}")
    us_gaap = f['facts']['us-gaap']
    if tag not in us_gaap:
        print("  Tag not in us-gaap")
        continue
    units = us_gaap[tag].get('units', {})
    if 'USD' not in units:
        print("  No USD units")
        continue
    entries = units['USD']
    valid = []
    for e in entries:
        try:
            end_dt = datetime.datetime.strptime(e['end'], '%Y-%m-%d').date()
            start_dt = datetime.datetime.strptime(e['start'], '%Y-%m-%d').date()
            filed_dt = datetime.datetime.strptime(e['filed'], '%Y-%m-%d').date()
            period_days = (end_dt - start_dt).days
            if 80 <= period_days <= 100 and filed_dt <= target:
                valid.append((end_dt, filed_dt, e['val']))
        except Exception as ex:
            print(f"  Parse error: {ex}")
    print(f"  Valid quarterly entries filed before target: {len(valid)}")
    if valid:
        valid.sort(key=lambda x: x[0], reverse=True)
        print(f"  Most recent 4 quarters:")
        for end, filed, val in valid[:4]:
            print(f"    end={end}, filed={filed}, val=${val:,.0f}")

print()
print("Calling _get_ttm_value directly...")
result = _get_ttm_value(f, CONCEPT_MAPPING['revenue'], target)
print(f"Final result: {result}")
