"""
Local Cache Builder for Quant Strategy Dashboard Pro
FAST + SAFE version: 0.3s base delay, batch progress saves, full error handling.
Target: ~12-18 minutes for 700+ tickers.
"""

import json
import time
import random
import os
import sys
import traceback
from datetime import datetime

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"ERROR: Missing library: {e}")
    print("Run: pip install numpy pandas yfinance")
    if sys.stdin and sys.stdin.isatty():
        input("Press Enter to close...")
    exit(1)

# ── Ticker Universe ────────────────────────────────────────────────

SP500 = [
    "AAPL","ABBV","ABT","ACN","ADBE","ADI","ADM","ADP","ADSK","AEE",
    "AEP","AES","AFL","AIG","AIZ","AJG","AKAM","ALB","ALGN","ALK",
    "ALL","ALLE","AMAT","AMCR","AMD","AME","AMGN","AMP","AMT","AMZN",
    "ANET","AON","AOS","APA","APD","APH","APTV","ARE","ATO",
    "AVB","AVGO","AVY","AWK","AXP","AZO","BA","BAC","BAX","BBWI",
    "BBY","BDX","BEN","BF-B","BG","BIIB","BIO","BK","BKNG","BKR",
    "BLK","BMY","BR","BRK-B","BRO","BSX","BWA","BXP","C","CAG",
    "CAH","CARR","CAT","CB","CBOE","CBRE","CCI","CCL","CDNS",
    "CDW","CE","CEG","CF","CFG","CHD","CHRW","CHTR","CI","CINF",
    "CL","CLX","CMCSA","CME","CMG","CMI","CMS","CNC","CNP",
    "COF","COO","COP","COST","CPB","CPRT","CPT","CRL","CRM","CSCO",
    "CSGP","CSX","CTAS","CTRA","CTSH","CTVA","CVS","CVX","CZR",
    "D","DAL","DD","DE","DG","DGX","DHI","DHR","DIS",
    "DLR","DLTR","DOV","DOW","DPZ","DRI","DTE","DUK","DVA","DVN",
    "DXCM","EA","EBAY","ECL","ED","EFX","EIX","EL","EMN","EMR",
    "ENPH","EOG","EPAM","EQIX","EQR","EQT","ES","ESS","ETN","ETR",
    "ETSY","EVRG","EW","EXC","EXPD","EXPE","EXR","F","FANG","FAST",
    "FCX","FDS","FDX","FE","FFIV","FIS","FISV","FITB",
    "FMC","FOX","FOXA","FRT","FTNT","FTV","GD","GE","GEHC","GEN",
    "GILD","GIS","GL","GLW","GM","GNRC","GOOG","GOOGL","GPC","GPN",
    "GRMN","GS","GWW","HAL","HAS","HBAN","HCA","HSIC","HST","HSY",
    "HUM","HWM","IBM","ICE","IDXX","IEX","IFF","ILMN","INCY","INTC",
    "INTU","INVH","IP","IQV","IR","IRM","ISRG","IT","ITW",
    "IVZ","J","JBHT","JCI","JKHY","JNJ","JPM","KDP",
    "KEY","KEYS","KHC","KIM","KLAC","KMB","KMI","KMX","KO","KR",
    "L","LDOS","LEN","LH","LHX","LIN","LKQ","LLY","LMT","LNC",
    "LNT","LOW","LRCX","LULU","LUV","LVS","LW","LYB","LYV","MA",
    "MAA","MAR","MAS","MCD","MCHP","MCK","MCO","MDLZ","MDT","MET",
    "META","MGM","MHK","MKC","MKTX","MLM","MMC","MMM","MNST","MO",
    "MOH","MOS","MPC","MPWR","MRK","MRNA","MS","MSCI","MSFT",
    "MSI","MTB","MTCH","MTD","MU","NCLH","NDAQ","NDSN","NEE","NEM",
    "NFLX","NI","NKE","NOC","NOW","NRG","NSC","NTAP","NTRS","NUE",
    "NVDA","NVR","NWL","NWS","NWSA","NXPI","O","ODFL","OGN","OKE",
    "OMC","ON","ORCL","ORLY","OTIS","OXY","PAYC","PAYX","PCAR",
    "PCG","PEG","PEP","PFE","PFG","PG","PGR","PH","PHM",
    "PKG","PLD","PM","PNC","PNR","PNW","POOL","PPG","PPL",
    "PRU","PSA","PSX","PTC","PVH","PWR","PYPL","QCOM","QRVO","RCL",
    "REG","REGN","RF","RHI","RJF","RL","RMD","ROK","ROL",
    "ROP","ROST","RSG","RTX","RVTY","SBAC","SBUX","SCHW","SEE","SHW",
    "SJM","SLB","SNA","SNPS","SO","SPG","SPGI","SRE","STE","STLD",
    "STT","STX","STZ","SWK","SWKS","SYF","SYK","SYY","T","TAP",
    "TDG","TDY","TECH","TEL","TER","TFC","TFX","TGT","TMO","TMUS",
    "TPR","TRGP","TRMB","TROW","TRV","TSCO","TSLA","TSN","TT","TTWO",
    "TXN","TXT","TYL","UAL","UDR","UHS","ULTA","UNH","UNP","UPS",
    "URI","USB","V","VFC","VICI","VLO","VMC","VRSK","VRSN","VRTX",
    "VTR","VTRS","VZ","WAB","WAT","WBD","WDC","WEC","WELL",
    "WFC","WHR","WM","WMB","WMT","WRB","WST","WTW","WY",
    "WYNN","XEL","XOM","XRAY","XYL","YUM","ZBH","ZBRA","ZION","ZTS",
    "COIN","PLTR","CRWD","DASH","DDOG","SNOW","NET","ZS","MDB",
    "TTD","PANW","ABNB","HOOD","RBLX","ARM","SMCI","VST",
    "DECK","AXON","FICO","GDDY","HUBB","TW","GEV","VLTO","KVUE",
    "SOLV","SW",
]

NASDAQ100_EXTRA = ["APP","ASML","AZN","CCEP","GFS","HON","MRVL","TEAM","WDAY"]

SP400_EXTRA = [
    "ACGL","ACM","ACI","AFRM","AFG","AGCO","ALNY","ALLY",
    "ARMK","ARES","ARW","ATR","AVTR","BFAM","BJ","BLD","BMRN",
    "BROS","BURL","CART","CAVA","CBSH","CCK","CHDN","CHE","CG",
    "CGNX","CLH","COHR","COKE","CRUS","CVNA","CW","CYBR",
    "DAR","DINO","DKS","DOCU","DOX","DT","DUOL","ENTG","ENSG",
    "EPRT","ESI","ESTC","EVR","EWBC","EXP","EXAS","FIVE","FIX",
    "FNB","FND","FNF","FSLR","FSS","FTI","GATX","GBCI","GLPI",
    "GPK","H","HALO","HGV","HLI","HOLX","HP","HQY","HRB",
    "IAC","IBKR","ICL","ICLR","IDCC","IDA","INSP","IOT","IRTC",
    "ITT","JEF","JLL","KNSL","KNX","LAMR","LBRDA","LBRDK","LEA",
    "LFUS","LNTH","LSCC","MANH","MASI","MEDP","MIDD","MKSI",
    "MORN","MTDR","MTN","MTZ","NBIX","NEU","NNN","NOV","NVT",
    "OLED","OLN","ORI","OVV","PCOR","PCTY","PEN","PII","PLNT",
    "PNFP","PPC","PSTG","PRI","RBA","RBC","RGA","RGLD","RNR",
    "SAM","SAIA","SBRA","SCI","SFM","SKX","SMAR","SSD","ST",
    "TNET","TOST","TPG","TPL","TREX","TWLO","UHAL","UTHR",
    "VEEV","VOYA","VVV","WAL","WBS","WCC","WEN","WEX","WH",
    "WMS","WSC","WSM","WPC","YETI","ZWS",
]

SUPPLEMENTAL = [
    "TSM","BABA","JD","PDD","BIDU","NIO","LI","XPEV",
    "SHOP","TD","RY","CNQ","SU","BN","BAM","SE","MELI","NU","GRAB",
    "BX","KKR","APO","OWL","SPOT","SQ","MSTR","CELH","CAVA",
    "RIVN","LCID","JOBY","BILL","PATH","SNAP","U","PINS",
]

PORTFOLIO_STOCKS = ["CLS","IREN","ASTS","RKLB","BMNR","ONDS"]

ETFS = [
    # Broad market
    "IVV","QQQ","VOO","VTI","SPY",
    # ARK Innovation
    "ARKK","ARKX",
    # Crypto / Digital
    "BITQ","IBIT","XOVR",
    # AI / Thematic
    "IVES","BAI","QTUM",
    # Commodities / Specialty
    "COPX","UFO","NLR","MAGS","GLD","IAU",
    # Sector SPDRs
    "XLE","XLF","XLK","XLV","XLI","XLP","XLU","XLB","XLY","XLRE",
    # Fixed Income
    "TLT","SHY","BND","AGG",
    # International
    "EEM","EFA","VWO",
    # Other Indices
    "DIA","IWM","MDY",
    # ── Motley Fool Ranked ETFs (March 2026) ──
    "IJR",   # iShares S&P 600 Small-Cap
    "SCHF",  # Schwab International Equity
    "VO",    # Vanguard Mid-Cap
    "VTV",   # Vanguard Value
    "VYM",   # Vanguard High Dividend Yield
    "VSS",   # Vanguard FTSE All-World ex-US Small-Cap
    "VUG",   # Vanguard Growth
    "VNQ",   # Vanguard Real Estate
    # ── Motley Fool Substitution Chart ──
    "SCHB",  # Schwab U.S. Broad Market
    "ITOT",  # iShares Core S&P Total US
    "SPTM",  # SPDR Portfolio S&P 1500
    "SCHX",  # Schwab U.S. Large-Cap
    "SPLG",  # SPDR Portfolio S&P 500 (alt ticker for SPYM)
    "SCHV",  # Schwab U.S. Large-Cap Value
    "SPYV",  # SPDR Portfolio S&P 500 Value
    "VIG",   # Vanguard Dividend Appreciation
    "SCHG",  # Schwab U.S. Large-Cap Growth
    "SPYG",  # SPDR Portfolio S&P 500 Growth
    "SCHM",  # Schwab U.S. Mid-Cap
    "IJH",   # iShares Core S&P Mid-Cap
    "IMCV",  # iShares Morningstar Mid-Cap Value
    "VOT",   # Vanguard Mid-Cap Growth
    "VB",    # Vanguard Small-Cap
    "SCHA",  # Schwab U.S. Small-Cap
    "ISCV",  # iShares Morningstar Small-Cap Value
    "VBK",   # Vanguard Small-Cap Growth
    "VXUS",  # Vanguard Total International Stock
    "VEA",   # Vanguard FTSE Developed Markets
    "IDEV",  # iShares Core MSCI Intl Developed
    "IEMG",  # iShares Core MSCI Emerging Markets
    "SCHC",  # Schwab International Small-Cap Equity
]

SECTOR_OVERRIDES = {
    "FISV": {"sector": "Technology", "industry": "Information Technology Services"},
    "FIS": {"sector": "Technology", "industry": "Information Technology Services"},
    "GPN": {"sector": "Technology", "industry": "Information Technology Services"},
    "JKHY": {"sector": "Technology", "industry": "Information Technology Services"},
}

ALL_STOCKS = sorted(set(SP500 + NASDAQ100_EXTRA + SP400_EXTRA + SUPPLEMENTAL + PORTFOLIO_STOCKS))
ALL_ETFS = sorted(set(ETFS))


# ── Fetch Logic ────────────────────────────────────────────────────

def fetch_stock(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        if not info.get("marketCap"):
            return None
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 20:
            return None
        close = hist["Close"]
        price = float(close.iloc[-1])

        def pct_ret(days):
            try:
                if len(close) >= days + 1:
                    past = float(close.iloc[-(days + 1)])
                    if past > 0: return round((price - past) / past, 4)
            except: pass
            return None

        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        surprise = None
        try:
            cal = t.earnings_dates
            if cal is not None and not cal.empty and "Surprise(%)" in cal.columns:
                recent = cal.dropna(subset=["Surprise(%)"])
                if not recent.empty:
                    surprise = float(recent["Surprise(%)"].iloc[0])
                    if not np.isfinite(surprise): surprise = None
        except: pass

        try:
            target = info.get("targetMeanPrice")
            cur = info.get("currentPrice") or info.get("previousClose")
            upside = round((target - cur) / cur, 4) if target and cur and cur > 0 else None
        except: upside = None

        return {
            "ticker": ticker,
            "shortName": str(info.get("shortName", ticker))[:100],
            "sector": str(info.get("sector", "Unknown")),
            "industry": str(info.get("industry", "Unknown")),
            "marketCap": info.get("marketCap", 0),
            "currentPrice": round(price, 2),
            "currency": info.get("currency", "USD"),
            "type": "stock",
            "forwardPE": info.get("forwardPE"),
            "trailingPE": info.get("trailingPE"),
            "pegRatio": info.get("pegRatio"),
            "priceToBook": info.get("priceToBook"),
            "priceToSalesTrailing12Months": info.get("priceToSalesTrailing12Months"),
            "enterpriseToEbitda": info.get("enterpriseToEbitda"),
            "enterpriseToRevenue": info.get("enterpriseToRevenue"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "revenueQuarterlyGrowth": info.get("revenueQuarterlyGrowth"),
            "earningsQuarterlyGrowth": info.get("earningsQuarterlyGrowth"),
            "grossMargins": info.get("grossMargins"),
            "operatingMargins": info.get("operatingMargins"),
            "profitMargins": info.get("profitMargins"),
            "returnOnEquity": info.get("returnOnEquity"),
            "returnOnAssets": info.get("returnOnAssets"),
            "momentum_1m": pct_ret(21),
            "momentum_3m": pct_ret(63),
            "momentum_6m": pct_ret(126),
            "momentum_12m": pct_ret(252) if len(close) >= 253 else pct_ret(max(len(close) - 2, 1)),
            "momentum_vs_sma50": round((price - sma50) / sma50, 4) if sma50 and sma50 > 0 else None,
            "momentum_vs_sma200": round((price - sma200) / sma200, 4) if sma200 and sma200 > 0 else None,
            "analyst_mean_target_upside": upside,
            "analyst_recommendation_score": info.get("recommendationMean"),
            "earnings_surprise_pct": surprise,
            "analyst_count": info.get("numberOfAnalystOpinions", 0),
            "lastUpdated": datetime.now().isoformat(),
        }
    except Exception as e:
        return None


def fetch_etf(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 20: return None
        close = hist["Close"]
        price = float(close.iloc[-1])

        def pct_ret(days):
            try:
                if len(close) >= days + 1:
                    past = float(close.iloc[-(days + 1)])
                    if past > 0: return round((price - past) / past, 4)
            except: pass
            return None

        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        return {
            "ticker": ticker,
            "shortName": str(info.get("shortName", ticker))[:100],
            "sector": "ETF", "industry": str(info.get("category", "Unknown") or "Unknown"),
            "marketCap": info.get("totalAssets", 0) or 0,
            "currentPrice": round(price, 2),
            "currency": info.get("currency", "USD"), "type": "etf",
            "expenseRatio": info.get("annualReportExpenseRatio"),
            "totalAssets": info.get("totalAssets", 0) or 0,
            "navPrice": info.get("navPrice", price),
            "ytdReturn": info.get("ytdReturn"),
            "threeYearReturn": info.get("threeYearAverageReturn"),
            "fiveYearReturn": info.get("fiveYearAverageReturn"),
            "momentum_1m": pct_ret(21), "momentum_3m": pct_ret(63),
            "momentum_6m": pct_ret(126),
            "momentum_12m": pct_ret(252) if len(close) >= 253 else pct_ret(max(len(close) - 2, 1)),
            "momentum_vs_sma50": round((price - sma50) / sma50, 4) if sma50 and sma50 > 0 else None,
            "momentum_vs_sma200": round((price - sma200) / sma200, 4) if sma200 and sma200 > 0 else None,
            "forwardPE": None, "trailingPE": None, "pegRatio": None,
            "priceToBook": None, "priceToSalesTrailing12Months": None,
            "enterpriseToEbitda": None, "enterpriseToRevenue": None,
            "revenueGrowth": None, "earningsGrowth": None,
            "revenueQuarterlyGrowth": None, "earningsQuarterlyGrowth": None,
            "grossMargins": None, "operatingMargins": None, "profitMargins": None,
            "returnOnEquity": None, "returnOnAssets": None,
            "analyst_mean_target_upside": None, "analyst_recommendation_score": None,
            "earnings_surprise_pct": None, "analyst_count": 0,
            "lastUpdated": datetime.now().isoformat(),
        }
    except: return None


# ── Main ───────────────────────────────────────────────────────────

def main():
    total_stocks = len(ALL_STOCKS)
    total_etfs = len(ALL_ETFS)
    start_time = time.time()

    print(f"{'='*60}")
    print(f"CACHE BUILDER v3 (fast + safe)")
    print(f"{'='*60}")
    print(f"  Stocks: {total_stocks}  |  ETFs: {total_etfs}")
    print(f"  Started: {datetime.now().strftime('%H:%M:%S')}")
    print(f"  Est. time: 12-18 minutes")
    print()

    results = {}
    failures = []
    consecutive_fails = 0

    # ── PHASE 1: Stocks ────────────────────────────────────────────
    print("PHASE 1: Fetching stocks...")
    for i, ticker in enumerate(ALL_STOCKS):
        try:
            data = fetch_stock(ticker)
            if data:
                results[ticker] = data
                consecutive_fails = 0
                status = "OK"
            else:
                failures.append(ticker)
                consecutive_fails += 1
                status = "SKIP"
        except Exception as e:
            failures.append(ticker)
            consecutive_fails += 1
            status = "ERR"

        if (i + 1) % 20 == 0 or i == total_stocks - 1:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (total_stocks - i - 1) / rate / 60 if rate > 0 else 0
            pct = (i + 1) / total_stocks * 100
            print(f"  [{pct:5.1f}%] {i+1}/{total_stocks} | {len(results)} ok | ~{remaining:.0f}m left | Last: {ticker} ({status})")

        # Save every 100
        if (i + 1) % 100 == 0:
            try:
                with open("fundamentals_cache.json", "w") as f:
                    json.dump(results, f, default=str)
            except: pass

        # Rate limit handling
        if consecutive_fails >= 10:
            print(f"  ** Rate limited. Pausing 15s...")
            time.sleep(15)
            consecutive_fails = 0
        else:
            # Fast delay: 0.3s base + small random jitter
            time.sleep(0.3 + random.uniform(0, 0.2))

    stock_count = len(results)
    print(f"\n  Stocks: {stock_count} fetched in {(time.time()-start_time)/60:.1f} min")

    # ── PHASE 2: ETFs ──────────────────────────────────────────────
    print(f"\nPHASE 2: Fetching ETFs...")
    etf_start = time.time()
    etf_ok = 0
    for i, ticker in enumerate(ALL_ETFS):
        try:
            data = fetch_etf(ticker)
            if data: results[ticker] = data; etf_ok += 1
            else: failures.append(ticker)
        except: failures.append(ticker)

        if (i + 1) % 10 == 0 or i == total_etfs - 1:
            print(f"  [{(i+1)/total_etfs*100:5.1f}%] {i+1}/{total_etfs} | {etf_ok} ok")

        time.sleep(0.4 + random.uniform(0, 0.2))

    print(f"  ETFs: {etf_ok} fetched in {(time.time()-etf_start)/60:.1f} min")

    # ── PHASE 3: Sector Overrides ──────────────────────────────────
    for ticker, overrides in SECTOR_OVERRIDES.items():
        if ticker in results:
            results[ticker].update(overrides)
            print(f"  Fixed {ticker} -> {overrides['sector']}")

    # ── PHASE 4: Save ──────────────────────────────────────────────
    output_file = "fundamentals_cache.json"
    try:
        with open(output_file, "w") as f:
            json.dump(results, f, default=str)
        file_size = os.path.getsize(output_file) / 1024 / 1024
    except Exception as e:
        print(f"  !! SAVE ERROR: {e}")
        file_size = 0

    total_time = (time.time() - start_time) / 60

    print(f"\n{'='*60}")
    print(f"DONE! Total time: {total_time:.1f} minutes")
    print(f"{'='*60}")
    print(f"  Stocks: {stock_count}  |  ETFs: {etf_ok}  |  Total: {len(results)}")
    print(f"  Failed: {len(failures)}  |  File: {file_size:.1f} MB")
    print(f"{'='*60}")
    print(f"\nNext steps:")
    print(f"  cd quant-dashboard-pro")
    print(f"  copy ..\\fundamentals_cache.json .")
    print(f"  git add fundamentals_cache.json")
    print(f'  git commit -m "Daily refresh"')
    print(f"  git push --force")

    if failures:
        print(f"\nFailed ({len(failures)}):")
        for j in range(0, len(failures), 15):
            print(f"  {', '.join(sorted(set(failures))[j:j+15])}")

    if sys.stdin and sys.stdin.isatty():
        input("\nPress Enter to close...")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        if sys.stdin and sys.stdin.isatty():
            input("\nPress Enter to close...")
