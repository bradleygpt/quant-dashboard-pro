"""
Correlation Builder - 20-Year Lookback
Computes historical return correlations between every stock and macro factors.

Run locally:
    python build_correlations.py

Output:
    correlations_cache.json (upload to quant-dashboard-pro repo)
"""

import json
import time
import os
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf


MACRO_FACTORS = {
    "oil": {"ticker": "CL=F", "name": "WTI Crude Oil"},
    "rates_10y": {"ticker": "^TNX", "name": "10-Year Treasury Yield"},
    "dollar": {"ticker": "DX-Y.NYB", "name": "US Dollar Index"},
    "vix": {"ticker": "^VIX", "name": "VIX Volatility Index"},
    "gold": {"ticker": "GC=F", "name": "Gold"},
    "bitcoin": {"ticker": "BTC-USD", "name": "Bitcoin"},
    "natgas": {"ticker": "NG=F", "name": "Natural Gas"},
    "sp500": {"ticker": "^GSPC", "name": "S&P 500"},
}

ALL_TICKERS = sorted(set([
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
    "DECK","AXON","FICO","GDDY","HUBB","TW","GEV","VLTO","KVUE","SOLV","SW",
    "CLS","IREN","ASTS","RKLB","BMNR","ONDS",
    "APP","ASML","AZN","CCEP","GFS","HON","MRVL","TEAM","WDAY",
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
    "SAM","SAIA","SBRA","SCI","SFM","SSD","ST",
    "TNET","TOST","TPG","TPL","TREX","TWLO","UHAL","UTHR",
    "VEEV","VOYA","VVV","WAL","WBS","WCC","WEN","WEX","WH",
    "WMS","WSC","WSM","WPC","YETI","ZWS",
    "TSM","BABA","JD","PDD","BIDU","NIO","LI","XPEV",
    "SHOP","TD","RY","CNQ","SU","BN","BAM","SE","MELI","NU","GRAB",
    "BX","KKR","APO","OWL","SPOT","SQ","MSTR","CELH","CAVA",
    "RIVN","LCID","JOBY","BILL","PATH","SNAP","U","PINS",
]))


def main():
    print("=" * 60)
    print("CORRELATION BUILDER (20-Year Lookback)")
    print("=" * 60)
    print(f"Tickers: {len(ALL_TICKERS)}")
    print(f"Factors: {', '.join(MACRO_FACTORS.keys())}")
    print()

    # Step 1: Download factor prices
    print("Downloading macro factor prices (20 years)...")
    factor_tickers = [f["ticker"] for f in MACRO_FACTORS.values()]
    factor_data = yf.download(factor_tickers, period="20y", auto_adjust=True, progress=False)

    if isinstance(factor_data.columns, pd.MultiIndex):
        factor_prices = factor_data["Close"]
    else:
        factor_prices = factor_data

    ticker_to_key = {f["ticker"]: k for k, f in MACRO_FACTORS.items()}
    factor_prices = factor_prices.rename(columns=ticker_to_key)

    print(f"  Got {len(factor_prices)} days of factor data")
    for col in factor_prices.columns:
        valid = factor_prices[col].dropna()
        print(f"    {col}: {len(valid)} days")

    # Step 2: Download stock prices
    print(f"\nDownloading stock prices for {len(ALL_TICKERS)} tickers (20 years)...")
    all_stock_prices = pd.DataFrame()
    chunk_size = 50

    for i in range(0, len(ALL_TICKERS), chunk_size):
        chunk = ALL_TICKERS[i:i + chunk_size]
        pct = (i + len(chunk)) / len(ALL_TICKERS) * 100
        print(f"  [{pct:5.1f}%] Chunk {i // chunk_size + 1}...")

        try:
            data = yf.download(chunk, period="20y", auto_adjust=True, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                chunk_prices = data["Close"]
            else:
                chunk_prices = data
            all_stock_prices = pd.concat([all_stock_prices, chunk_prices], axis=1)
        except Exception as e:
            print(f"    Error: {e}")

        time.sleep(3)

    all_stock_prices = all_stock_prices.loc[:, ~all_stock_prices.columns.duplicated()]
    print(f"  Got prices for {len(all_stock_prices.columns)} tickers")

    # Step 3: Compute correlations
    print("\nComputing correlations (full available history per ticker)...")
    stock_returns = all_stock_prices.pct_change().dropna(how="all")
    factor_returns = factor_prices.pct_change().dropna(how="all")

    common_dates = stock_returns.index.intersection(factor_returns.index)
    stock_returns = stock_returns.loc[common_dates]
    factor_returns = factor_returns.loc[common_dates]

    print(f"  {len(stock_returns)} total trading days available")

    results = {}
    total = len(stock_returns.columns)
    min_days = 60

    for i, ticker in enumerate(stock_returns.columns):
        if (i + 1) % 100 == 0 or i == total - 1:
            print(f"  [{(i+1)/total*100:5.1f}%] {i+1}/{total} | {len(results)} computed")

        stock_ret = stock_returns[ticker].dropna()
        if len(stock_ret) < min_days:
            continue

        ticker_corrs = {}
        for factor_key in factor_returns.columns:
            factor_ret = factor_returns[factor_key].dropna()
            common = stock_ret.index.intersection(factor_ret.index)
            if len(common) < min_days:
                continue

            s = stock_ret.loc[common]
            f = factor_ret.loc[common]

            mask = np.isfinite(s) & np.isfinite(f)
            s = s[mask]
            f = f[mask]

            if len(s) < min_days:
                continue

            corr = s.corr(f)
            cov = s.cov(f)
            var_f = f.var()
            beta = cov / var_f if var_f > 0 else 0
            r_squared = corr ** 2 if not np.isnan(corr) else 0

            if not np.isnan(corr):
                ticker_corrs[factor_key] = {
                    "correlation": round(float(corr), 4),
                    "beta": round(float(beta), 4),
                    "r_squared": round(float(r_squared), 4),
                    "days_used": int(len(s)),
                }

        if ticker_corrs:
            results[ticker] = ticker_corrs

    # Step 4: Save
    output = {
        "metadata": {
            "computed_at": datetime.now().isoformat(),
            "lookback": "20 years (full available history per ticker)",
            "window_days": "all available",
            "num_tickers": len(results),
            "factors": {k: v["name"] for k, v in MACRO_FACTORS.items()},
        },
        "correlations": results,
    }

    output_file = "correlations_cache.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)

    file_size = os.path.getsize(output_file) / 1024 / 1024

    print(f"\n{'='*60}")
    print(f"DONE!")
    print(f"  Tickers: {len(results)}")
    print(f"  File: {output_file} ({file_size:.1f} MB)")
    print(f"{'='*60}")

    # Sample output
    def show_top(factor_key, name, n=10):
        print(f"\nTop correlated to {name}:")
        corrs = [(t, d[factor_key]["correlation"]) for t, d in results.items() if factor_key in d]
        corrs.sort(key=lambda x: x[1], reverse=True)
        print(f"  POSITIVE: {', '.join(f'{t} ({c:+.3f})' for t, c in corrs[:n])}")
        print(f"  NEGATIVE: {', '.join(f'{t} ({c:+.3f})' for t, c in corrs[-n:])}")

    show_top("oil", "Oil")
    show_top("rates_10y", "10Y Rates")
    show_top("gold", "Gold")
    show_top("sp500", "S&P 500 Beta")
    show_top("vix", "VIX")
    show_top("bitcoin", "Bitcoin")

    print(f"\nUpload {output_file} to quant-dashboard-pro repo.")


if __name__ == "__main__":
    main()
