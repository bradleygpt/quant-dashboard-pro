"""
Local Cache Builder for Quant Strategy Dashboard
Run this on your home computer to build the full ticker universe cache.
Then upload the output file to your GitHub repo.

Usage:
    python build_cache.py

Output:
    fundamentals_cache.json (upload this to your GitHub repo root)
"""

import json
import time
import random
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf


# ── Full Ticker Universe ───────────────────────────────────────────

SP500 = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE",
    "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN", "ALK",
    "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP", "AMT", "AMZN",
    "ANET", "AON", "AOS", "APA", "APD", "APH", "APTV", "ARE", "ATO",
    "AVB", "AVGO", "AVY", "AWK", "AXP", "AZO", "BA", "BAC", "BAX", "BBWI",
    "BBY", "BDX", "BEN", "BF-B", "BG", "BIIB", "BIO", "BK", "BKNG", "BKR",
    "BLK", "BMY", "BR", "BRK-B", "BRO", "BSX", "BWA", "BXP", "C", "CAG",
    "CAH", "CARR", "CAT", "CB", "CBOE", "CBRE", "CCI", "CCL", "CDNS",
    "CDW", "CE", "CEG", "CF", "CFG", "CHD", "CHRW", "CHTR", "CI", "CINF",
    "CL", "CLX", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC", "CNP",
    "COF", "COO", "COP", "COST", "CPB", "CPRT", "CPT", "CRL", "CRM", "CSCO",
    "CSGP", "CSX", "CTAS", "CTRA", "CTSH", "CTVA", "CVS", "CVX", "CZR",
    "D", "DAL", "DD", "DE", "DG", "DGX", "DHI", "DHR", "DIS",
    "DLR", "DLTR", "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK", "DVA", "DVN",
    "DXCM", "EA", "EBAY", "ECL", "ED", "EFX", "EIX", "EL", "EMN", "EMR",
    "ENPH", "EOG", "EPAM", "EQIX", "EQR", "EQT", "ES", "ESS", "ETN", "ETR",
    "ETSY", "EVRG", "EW", "EXC", "EXPD", "EXPE", "EXR", "F", "FANG", "FAST",
    "FCX", "FDS", "FDX", "FE", "FFIV", "FIS", "FISV", "FITB",
    "FMC", "FOX", "FOXA", "FRT", "FTNT", "FTV", "GD", "GE", "GEHC", "GEN",
    "GILD", "GIS", "GL", "GLW", "GM", "GNRC", "GOOG", "GOOGL", "GPC", "GPN",
    "GRMN", "GS", "GWW", "HAL", "HAS", "HBAN", "HCA", "HSIC", "HST", "HSY",
    "HUM", "HWM", "IBM", "ICE", "IDXX", "IEX", "IFF", "ILMN", "INCY", "INTC",
    "INTU", "INVH", "IP", "IQV", "IR", "IRM", "ISRG", "IT", "ITW",
    "IVZ", "J", "JBHT", "JCI", "JKHY", "JNJ", "JPM", "KDP",
    "KEY", "KEYS", "KHC", "KIM", "KLAC", "KMB", "KMI", "KMX", "KO", "KR",
    "L", "LDOS", "LEN", "LH", "LHX", "LIN", "LKQ", "LLY", "LMT", "LNC",
    "LNT", "LOW", "LRCX", "LULU", "LUV", "LVS", "LW", "LYB", "LYV", "MA",
    "MAA", "MAR", "MAS", "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT", "MET",
    "META", "MGM", "MHK", "MKC", "MKTX", "MLM", "MMC", "MMM", "MNST", "MO",
    "MOH", "MOS", "MPC", "MPWR", "MRK", "MRNA", "MS", "MSCI", "MSFT",
    "MSI", "MTB", "MTCH", "MTD", "MU", "NCLH", "NDAQ", "NDSN", "NEE", "NEM",
    "NFLX", "NI", "NKE", "NOC", "NOW", "NRG", "NSC", "NTAP", "NTRS", "NUE",
    "NVDA", "NVR", "NWL", "NWS", "NWSA", "NXPI", "O", "ODFL", "OGN", "OKE",
    "OMC", "ON", "ORCL", "ORLY", "OTIS", "OXY", "PAYC", "PAYX", "PCAR",
    "PCG", "PEG", "PEP", "PFE", "PFG", "PG", "PGR", "PH", "PHM",
    "PKG", "PLD", "PM", "PNC", "PNR", "PNW", "POOL", "PPG", "PPL",
    "PRU", "PSA", "PSX", "PTC", "PVH", "PWR", "PYPL", "QCOM", "QRVO", "RCL",
    "REG", "REGN", "RF", "RHI", "RJF", "RL", "RMD", "ROK", "ROL",
    "ROP", "ROST", "RSG", "RTX", "RVTY", "SBAC", "SBUX", "SCHW", "SEE", "SHW",
    "SJM", "SLB", "SNA", "SNPS", "SO", "SPG", "SPGI", "SRE", "STE", "STLD",
    "STT", "STX", "STZ", "SWK", "SWKS", "SYF", "SYK", "SYY", "T", "TAP",
    "TDG", "TDY", "TECH", "TEL", "TER", "TFC", "TFX", "TGT", "TMO", "TMUS",
    "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN", "TT", "TTWO",
    "TXN", "TXT", "TYL", "UAL", "UDR", "UHS", "ULTA", "UNH", "UNP", "UPS",
    "URI", "USB", "V", "VFC", "VICI", "VLO", "VMC", "VRSK", "VRSN", "VRTX",
    "VTR", "VTRS", "VZ", "WAB", "WAT", "WBD", "WDC", "WEC", "WELL",
    "WFC", "WHR", "WM", "WMB", "WMT", "WRB", "WST", "WTW", "WY",
    "WYNN", "XEL", "XOM", "XRAY", "XYL", "YUM", "ZBH", "ZBRA", "ZION", "ZTS",
    "COIN", "PLTR", "CRWD", "DASH", "DDOG", "SNOW", "NET", "ZS", "MDB",
    "TTD", "PANW", "ABNB", "HOOD", "RBLX", "ARM", "SMCI", "VST",
    "DECK", "AXON", "FICO", "GDDY", "HUBB", "TW", "GEV", "VLTO", "KVUE",
    "SOLV", "SW",
]

NASDAQ100 = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "APP", "ARM", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR",
    "CCEP", "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COIN", "COST", "CPRT", "CRWD",
    "CSCO", "CSGP", "CTAS", "CTSH", "DASH", "DDOG", "DLTR", "DXCM", "EA", "EXC",
    "FANG", "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX",
    "ILMN", "INTC", "INTU", "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "LULU",
    "MAR", "MCHP", "MDB", "MDLZ", "MELI", "META", "MNST", "MRVL", "MSFT", "MU",
    "NFLX", "NVDA", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX", "PCAR", "PDD",
    "PEP", "PLTR", "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SMCI", "SNPS",
    "TEAM", "TMUS", "TSLA", "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY",
    "ZS",
]

SP400_MIDCAP = [
    "ACGL", "ACM", "ACI", "AFRM", "AFG", "AGCO", "ALNY", "ALLY",
    "ARMK", "ARES", "ARW", "ATR", "AVTR",
    "BFAM", "BJ", "BLD", "BMRN", "BROS", "BURL",
    "CART", "CAVA", "CBSH", "CCK", "CHDN", "CHE", "CG", "CGNX",
    "CLH", "COHR", "COKE", "COOP", "CRUS",
    "CVNA", "CW", "CYBR",
    "DAR", "DINO", "DKS", "DOCU", "DOX", "DT", "DUOL",
    "ENTG", "ENSG", "EPRT", "ESI", "ESTC", "EVR", "EWBC",
    "EXP", "EXAS",
    "FIVE", "FIX", "FNB", "FND", "FNF", "FSLR", "FSS", "FTI",
    "GATX", "GBCI", "GLPI", "GMS", "GPK",
    "H", "HALO", "HGV", "HLI", "HOLX", "HP", "HQY", "HRB",
    "IAC", "IBKR", "ICL", "ICLR", "IDCC", "IDA",
    "INSP", "IOT", "IRTC", "ITT",
    "JEF", "JLL",
    "KNSL", "KNX",
    "LAMR", "LBRDA", "LBRDK", "LEA", "LFUS", "LNTH", "LSCC",
    "MANH", "MASI", "MEDP", "MIDD", "MKSI",
    "MORN", "MTDR", "MTN", "MTZ",
    "NBIX", "NEU", "NNN", "NOV", "NVT",
    "OLED", "OLN", "ORI", "OVV", "PCOR", "PCTY", "PEN", "PII",
    "PLNT", "PNFP", "PPC", "PSTG", "PRI",
    "RBA", "RBC", "RGA", "RGLD", "RNR",
    "SAM", "SAIA", "SBRA", "SCI", "SFM", "SKX", "SMAR", "SNV",
    "SSD", "ST", "SWN",
    "TNET", "TOST", "TPG", "TPL", "TREX", "TWLO",
    "UHAL", "UTHR",
    "VEEV", "VOYA", "VVV",
    "WAL", "WBS", "WCC", "WEN", "WEX", "WH", "WMS",
    "WSC", "WSM", "WPC",
    "YETI",
    "ZWS",
]

SUPPLEMENTAL = [
    "TSM", "BABA", "JD", "PDD", "BIDU", "NIO", "LI", "XPEV",
    "SHOP", "TD", "RY", "CNQ", "SU", "BN", "BAM", "SE", "MELI", "NU", "GRAB",
    "BX", "KKR", "APO", "ARES", "OWL",
    "SPOT", "SQ", "MSTR", "CELH", "DUOL", "CAVA",
    "RIVN", "LCID", "JOBY", "BILL", "PATH", "SNAP", "U", "PINS",
]

ALL_TICKERS = sorted(set(SP500 + NASDAQ100 + SP400_MIDCAP + SUPPLEMENTAL))


# ── Fetch Logic ────────────────────────────────────────────────────


def fetch_ticker(ticker):
    """Fetch everything for one ticker."""
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

        # Momentum
        def pct_ret(days):
            if len(close) >= days + 1:
                past = float(close.iloc[-(days + 1)])
                if past > 0:
                    return round((price - past) / past, 4)
            return None

        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        # Earnings surprise
        surprise = None
        try:
            cal = t.earnings_dates
            if cal is not None and not cal.empty and "Surprise(%)" in cal.columns:
                recent = cal.dropna(subset=["Surprise(%)"])
                if not recent.empty:
                    surprise = float(recent["Surprise(%)"].iloc[0])
                    if not np.isfinite(surprise):
                        surprise = None
        except Exception:
            pass

        # Analyst
        target = info.get("targetMeanPrice")
        cur = info.get("currentPrice") or info.get("previousClose")
        upside = round((target - cur) / cur, 4) if target and cur and cur > 0 else None

        return {
            "ticker": ticker,
            "shortName": info.get("shortName", ticker),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "marketCap": info.get("marketCap", 0),
            "currentPrice": round(price, 2),
            "currency": info.get("currency", "USD"),
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


# ── Main ───────────────────────────────────────────────────────────


def main():
    total = len(ALL_TICKERS)
    print(f"Fetching {total} tickers...")
    print(f"This will take approximately 15-25 minutes.\n")

    results = {}
    failures = []
    consecutive_fails = 0

    for i, ticker in enumerate(ALL_TICKERS):
        data = fetch_ticker(ticker)

        if data:
            results[ticker] = data
            consecutive_fails = 0
            status = "OK"
        else:
            failures.append(ticker)
            consecutive_fails += 1
            status = "SKIP"

        # Progress
        if (i + 1) % 10 == 0 or i == total - 1:
            pct = (i + 1) / total * 100
            print(f"  [{pct:5.1f}%] {i + 1}/{total}  |  {len(results)} success  |  {len(failures)} failed  |  Last: {ticker} ({status})")

        # Save progress every 50 tickers
        if (i + 1) % 50 == 0:
            with open("fundamentals_cache.json", "w") as f:
                json.dump(results, f, default=str)

        # If 10+ consecutive failures, back off
        if consecutive_fails >= 10:
            print(f"  ** Rate limited. Pausing 30 seconds...")
            time.sleep(30)
            consecutive_fails = 0
        else:
            # Normal delay
            time.sleep(0.6 + random.uniform(0, 0.4))

    # Final save
    output_file = "fundamentals_cache.json"
    with open(output_file, "w") as f:
        json.dump(results, f, default=str)

    print(f"\n{'='*60}")
    print(f"DONE!")
    print(f"  Total tickers attempted: {total}")
    print(f"  Successfully fetched:    {len(results)}")
    print(f"  Failed:                  {len(failures)}")
    print(f"  Output file:             {output_file}")
    print(f"  File size:               {os.path.getsize(output_file) / 1024 / 1024:.1f} MB")
    print(f"{'='*60}")
    print(f"\nNext steps:")
    print(f"  1. Go to your GitHub repo: github.com/bradleygpt/quant-dashboard")
    print(f"  2. Click 'Add file' > 'Upload files'")
    print(f"  3. Upload {output_file}")
    print(f"  4. Commit the change")
    print(f"  5. The dashboard will use this data immediately")

    if failures:
        print(f"\nFailed tickers (likely delisted or ticker changed):")
        print(f"  {', '.join(sorted(failures))}")


import os
if __name__ == "__main__":
    main()
