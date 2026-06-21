"""Refresh market_static.json macro_data + earnings_forecast from LIVE FRED (UNRATE, CPIAUCNS YoY),
mirroring the bake's macro block. Use when the bake's FRED fetch timed out and fell back to static.
Writes to the live dashboard. ISM stays manual (not on free FRED)."""
import urllib.request as U, json, time, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, r"C:\Users\bmhar\code\quant-dashboard-react")
import macro as M

def fred_rows(sid, retries=4):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    last = None
    for a in range(retries):
        try:
            rq = U.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; QuantDashboard/2.0)"})
            with U.urlopen(rq, timeout=30) as r:
                txt = r.read().decode()
            out = []
            for ln in txt.strip().split("\n")[1:]:
                p = ln.split(",")
                if len(p) < 2 or p[1] in ("", "."):
                    continue
                try: out.append((p[0], float(p[1])))
                except ValueError: pass
            if out: return out
        except Exception as e:
            last = e; time.sleep(1.5 * (a + 1))
    raise RuntimeError(f"FRED {sid} failed after {retries} tries: {last}")

def yoy(rows, back=0):
    """Date-aligned YoY at index -(1+back): value vs the same calendar month one year prior."""
    d = dict(rows)
    dt, val = rows[-(1 + back)]
    prior = d.get(f"{int(dt[:4]) - 1}-{dt[5:]}")
    if prior is None:  # gap month -> fall back to 12 filtered rows back
        prior = rows[-(13 + back)][1]
    return round((val / prior - 1) * 100, 1), dt

un = fred_rows("UNRATE"); cpi = fred_rows("CPIAUCNS")
unemp_cur, unemp_asof = un[-1][1], un[-1][0]; unemp_prior = un[-2][1]
cpi_cur, cpi_asof = yoy(cpi); cpi_prior, _ = yoy(cpi, back=1)

f = Path(r"C:\Users\bmhar\code\quant-dashboard-pro-v2\public\data\market_static.json")
ms = json.load(open(f)); md = ms["macro_data"]
md["unemployment_current"], md["unemployment_prior"], md["unemployment_asof"] = unemp_cur, unemp_prior, unemp_asof
md["unemployment_source"] = "FRED UNRATE (live)"
md["unemployment_trend"] = "rising" if unemp_cur > unemp_prior else "falling" if unemp_cur < unemp_prior else "stable"
md["cpi_current"], md["cpi_prior"], md["cpi_asof"] = cpi_cur, cpi_prior, cpi_asof
md["cpi_source"] = "FRED CPIAUCNS YoY (live)"
md["cpi_trend"] = "rising" if cpi_cur > cpi_prior else "falling" if cpi_cur < cpi_prior else "stable"
md["last_updated"] = date(2026, 6, 20).isoformat()
ms["earnings_forecast"] = M.compute_earnings_forecast(cpi_cur, unemp_cur, md["ism_composite"])
json.dump(ms, open(f, "w"), indent=2)
print(f"Unemp {unemp_cur}% (as-of {unemp_asof}, prior {unemp_prior}) | CPI YoY {cpi_cur}% (as-of {cpi_asof}, prior {cpi_prior})")
print(f"Earnings forecast: {ms['earnings_forecast']['sp500_earnings_growth']}% (was 8.1) | inputs {ms['earnings_forecast']['model_inputs']}")
