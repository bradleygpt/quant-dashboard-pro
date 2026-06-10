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

SP600_EXTRA = [
    "AAMI", "AAP", "AAT", "ABCB", "ABG", "ABM", "ABR", "ACA", "ACAD", "ACHC",
    "ACIW", "ACLS", "ACMR", "ACT", "ADAM", "ADEA", "ADMA", "ADNT", "ADT", "ADUS",
    "AEO", "AESI", "AGO", "AGX", "AGYS", "AHCO", "AIN", "AIR", "AKR", "ALG",
    "ALGT", "ALKS", "ALRM", "AMN", "AMPH", "AMR", "AMRX", "AMSF", "AMTM", "AMWD",
    "ANDE", "ANIP", "AORT", "AOSL", "APAM", "APLE", "APLS", "APOG", "ARCB", "ARI",
    "ARLO", "AROC", "ARR", "ASO", "ASTE", "ASTH", "ATEN", "ATMU", "AUB", "AVA",
    "AVNS", "AWI", "AWR", "AX", "AZTA", "AZZ", "BANC", "BANF", "BANR", "BCC",
    "BCPC", "BFH", "BFS", "BGC", "BHE", "BJRI", "BKE", "BKU", "BL", "BLFS",
    "BMI", "BNL", "BOH", "BOOT", "BOX", "BRC", "BTSG", "BTU", "BXMT", "CABO",
    "CAKE", "CALM", "CALX", "CARG", "CATY", "CBRL", "CBU", "CC", "CCOI", "CCS",
    "CENT", "CENTA", "CENX", "CERT", "CFFN", "CHCO", "CHEF", "CLB", "CLSK", "CNK",
    "CNMD", "CNR", "CNS", "CNXN", "COCO", "COHU", "COLL", "CON", "CORT", "CPF",
    "CPK", "CPRX", "CRC", "CRGY", "CRI", "CRK", "CRSR", "CRVL", "CSGS", "CSR",
    "CSW", "CTKB", "CTS", "CUBI", "CURB", "CVBF", "CVCO", "CVI", "CVSA", "CWEN",
    "CWEN-A", "CWK", "CWST", "CWT", "CXM", "CXW", "DAN", "DBD", "DCH", "DCOM",
    "DEA", "DEI", "DFH", "DFIN", "DGII", "DIOD", "DLX", "DNOW", "DORM", "DRH",
    "DV", "DXC", "DXPE", "EAT", "ECG", "ECPG", "EFC", "EGBN", "EIG", "EMBC",
    "ENOV", "ENR", "ENVA", "EPAC", "EPC", "ESE", "ETD", "EVTC", "EXPI", "EXTR",
    "EYE", "EZPW", "FBK", "FBNC", "FBP", "FBRT", "FCF", "FCPT", "FDP", "FELE",
    "FFBC", "FHB", "FIBK", "FIZZ", "FORM", "FOXF", "FRPT", "FTDR", "FTRE", "FUL",
    "FULT", "FUN", "FWRD", "GBX", "GDEN", "GDYN", "GEO", "GFF", "GIII", "GKOS",
    "GNL", "GNW", "GO", "GOGO", "GOLF", "GPI", "GRBK", "GSHD", "GTES", "GTM",
    "GTY", "GVA", "HAFC", "HASI", "HAYW", "HCC", "HCI", "HCSG", "HE", "HFWA",
    "HIW", "HLIT", "HLX", "HMN", "HNI", "HOPE", "HRMY", "HSTM", "HTH", "HTLD",
    "HTZ", "HUBG", "HWKN", "HZO", "IART", "IBP", "ICHR", "ICUI", "IIIN", "IIPR",
    "INDB", "INDV", "INSW", "INVA", "IOSP", "IPAR", "IRDM", "ITGR", "ITRI", "JBGS",
    "JBLU", "JBSS", "JJSF", "JOE", "JXN", "KAI", "KALU", "KFY", "KGS", "KLIC",
    "KMPR", "KMT", "KN", "KNTK", "KOP", "KRYS", "KSS", "KTB", "KW", "KWR",
    "LAUR", "LBRT", "LCII", "LEG", "LGIH", "LGND", "LIF", "LKFN", "LMAT", "LNN",
    "LPG", "LQDT", "LRN", "LTC", "LTH", "LUMN", "LXP", "LYFT", "LZ", "LZB",
    "MAC", "MAN", "MARA", "MATW", "MATX", "MBC", "MBIN", "MC", "MCRI", "MCW",
    "MCY", "MD", "MDU", "MGEE", "MGY", "MHO", "MIR", "MLKN", "MMI", "MMSI",
    "MNRO", "MPT", "MRCY", "MRP", "MRTN", "MSEX", "MSGS", "MTH", "MTRN", "MTUS",
    "MTX", "MWA", "MXL", "MYRG", "NABL", "NATL", "NAVI", "NBHC", "NBTB", "NE",
    "NEO", "NEOG", "NGVT", "NHC", "NMIH", "NOG", "NPK", "NPO", "NSIT", "NSP",
    "NSSC", "NTCT", "NVRI", "NWBI", "NWN", "NX", "NXRT", "OFG", "OI", "OII",
    "OMCL", "OSIS", "OSW", "OTTR", "OUT", "OXM", "PAHC", "PARR", "PATK", "PAYO",
    "PBH", "PBI", "PCRX", "PDFS", "PEB", "PECO", "PENG", "PENN", "PFBC", "PFS",
    "PGNY", "PHIN", "PI", "PIPR", "PJT", "PLAB", "PLMR", "PLUS", "PLXS", "PMT",
    "POWI", "POWL", "PRA", "PRAA", "PRDO", "PRG", "PRGO", "PRGS", "PRIM", "PRK",
    "PRKS", "PRLB", "PRSU", "PRVA", "PSMT", "PTCT", "PTEN", "PTGX", "PZZA", "QDEL",
    "QNST", "QTWO", "RAMP", "RCUS", "RDN", "RDNT", "RES", "REX", "REYN", "REZI",
    "RHP", "RITM", "RNG", "RNST", "ROCK", "ROG", "RRR", "RUN", "RUSHA", "RWT",
    "RXO", "SABR", "SAFE", "SAFT", "SAH", "SANM", "SBCF", "SBH", "SBSI", "SCHL",
    "SCL", "SCSC", "SDGR", "SEDG", "SEM", "SEZL", "SFBS", "SFNC", "SHAK", "SHEN",
    "SHO", "SHOO", "SIG", "SKT", "SKY", "SKYW", "SLG", "SLVM", "SM", "SMP",
    "SMPL", "SMTC", "SNCY", "SNDR", "SNEX", "SONO", "SPHR", "SPNT", "SPSC", "SRPT",
    "SSTK", "STAA", "STBA", "STC", "STEL", "STEP", "STRA", "SUPN", "SXI", "SXT",
    "TALO", "TBBK", "TDC", "TDS", "TDW", "TFIN", "TGTX", "THRM", "TILE", "TMDX",
    "TMP", "TNC", "TNDM", "TPH", "TR", "TRIP", "TRMK", "TRN", "TRNO", "TRST",
    "TRUP", "TWO", "UA", "UAA", "UCB", "UCTT", "UE", "UFCS", "UFPT", "UHT",
    "UNF", "UNFI", "UNIT", "UPBD", "UPWK", "URBN", "USPH", "UTL", "UVV", "VAC",
    "VCEL", "VCTR", "VCYT", "VECO", "VGNT", "VIAV", "VIR", "VIRT", "VITL", "VRE",
    "VRRM", "VRTS", "VSAT", "VSCO", "VSEC", "VSH", "VSNT", "VSTS", "VTOL", "VYX",
    "WABC", "WAFD", "WAY", "WD", "WDFC", "WERN", "WGO", "WHD", "WINA", "WKC",
    "WLY", "WOR", "WRLD", "WS", "WSFS", "WSR", "WT", "WU", "WWW", "XHR",
    "XNCR", "XPEL", "YELP", "YOU", "ZD",
]

SUPPLEMENTAL = [
    # International / ADRs
    "TSM","BABA","JD","PDD","BIDU","NIO","LI","XPEV",
    "SHOP","TD","RY","CNQ","SU","BN","BAM","SE","MELI","NU","GRAB",
    # Private equity / asset managers / financial services
    "BX","KKR","APO","OWL","SPOT","XYZ",
    # Crypto/digital treasury
    "MSTR",
    # Consumer growth
    "CELH","CAVA",
    # EV / mobility
    "RIVN","LCID","JOBY",
    # Software / fintech
    "BILL","PATH","SNAP","U","PINS",
    # ── Recent re-IPOs and 2024 IPOs ──
    "SNDK",   # SanDisk re-IPO from Western Digital (Feb 2025)
    "RDDT",   # Reddit (Mar 2024)
    "RBRK",   # Rubrik (Apr 2024)
    "ALAB",   # Astera Labs (Mar 2024, AI infrastructure)
    "BIRK",   # Birkenstock (Oct 2023)
    "ODD",    # Oddity Tech (Jul 2023, AI beauty)
    "NXT",    # Nextracker (Feb 2023, solar trackers)
    "MBLY",   # Mobileye (Intel spinoff, Oct 2022)
    # ── 2023 IPOs ──
    "KVYO",   # Klaviyo (Sep 2023)
    "VFS",    # VinFast (Aug 2023, Vietnamese EV)
    "TBPH",   # Theravance Biopharma
    # ── Pre-2022 missing names ──
    "BE",     # Bloom Energy
    "CHWY",   # Chewy
    "ROKU",   # Roku
    # ── Crypto/digital mining ──
    "RIOT",   # Riot Platforms
    "CIFR",   # Cipher Mining
    "WULF",   # TeraWulf
    "HUT",    # Hut 8
    # ── AI infrastructure / growth ──
    "CRWV",   # CoreWeave (Mar 2025, AI cloud)
    "VRT",    # Vertiv (data center power)
    # ── Nuclear / SMR thesis ──
    "SMR",    # NuScale Power
    "OKLO",   # Oklo Inc
    "CCJ",    # Cameco (uranium miner)
    "UEC",    # Uranium Energy
    "NRGV",   # Energy Vault
    # ── Fintech ──
    "HIMS",   # Hims & Hers Health
    "SOFI",   # SoFi Technologies
    "UPST",   # Upstart Holdings
    "OPEN",   # Opendoor
    # ── Biotech / gene editing ──
    "GH",     # Guardant Health
    "NTRA",   # Natera
    "CRSP",   # CRISPR Therapeutics
    "EDIT",   # Editas Medicine
    "BEAM",   # Beam Therapeutics
    "NVAX",   # Novavax
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

ALL_STOCKS = sorted(set(SP500 + NASDAQ100_EXTRA + SP400_EXTRA + SP600_EXTRA + SUPPLEMENTAL + PORTFOLIO_STOCKS))
ALL_ETFS = sorted(set(ETFS))


# ── Fetch Logic ────────────────────────────────────────────────────


def fetch_quarterly_history(t, max_quarters=12):
    """Fetch last N quarters of key metrics for a ticker.

    Returns a list of dicts (most-recent first) with computable metrics.
    On any error or missing data, returns []. The caller must tolerate
    an empty result.

    Used to enable trend feature computation in the model scoring pipeline.
    Each quarter contains: date, grossMargins, operatingMargins, netMargins,
    returnOnEquity, returnOnAssets, revenueGrowth (yoy), earningsGrowth (yoy).
    """
    try:
        # Pull all three quarterly statements
        income = t.quarterly_income_stmt
        balance = t.quarterly_balance_sheet
        # cashflow not strictly needed for trend features but cheap to grab
        # cashflow = t.quarterly_cashflow

        if income is None or income.empty:
            return []

        # Columns are quarter-end dates, sorted newest first by yfinance
        # Take up to max_quarters
        quarters = list(income.columns)[:max_quarters]
        if len(quarters) < 2:
            return []

        # Helper to safely extract a row value, returning None if missing
        def get_val(df, row_name, col):
            try:
                if df is None or df.empty:
                    return None
                if row_name not in df.index:
                    return None
                v = df.at[row_name, col]
                if v is None:
                    return None
                fv = float(v)
                if not np.isfinite(fv):
                    return None
                return fv
            except Exception:
                return None

        history = []

        # Pre-compute revenue series for YoY growth (needs same-quarter-prior-year)
        # yfinance gives ~4 quarters typically, sometimes 5-8
        # We compute YoY by comparing q[i] to q[i+4] when both exist
        rev_by_q = {}
        ni_by_q = {}
        for q in quarters:
            rev_by_q[q] = get_val(income, "Total Revenue", q)
            ni_by_q[q] = get_val(income, "Net Income", q)

        for i, q in enumerate(quarters):
            revenue = rev_by_q.get(q)
            net_income = ni_by_q.get(q)
            cogs = get_val(income, "Cost Of Revenue", q)
            op_income = get_val(income, "Operating Income", q)

            # Margins
            gross_margin = None
            op_margin = None
            net_margin = None
            if revenue and revenue > 0:
                if cogs is not None:
                    gross_margin = (revenue - cogs) / revenue
                if op_income is not None:
                    op_margin = op_income / revenue
                if net_income is not None:
                    net_margin = net_income / revenue

            # Returns: need balance sheet
            equity = get_val(balance, "Stockholders Equity", q)
            assets = get_val(balance, "Total Assets", q)

            roe = None
            roa = None
            if net_income is not None:
                # Annualize quarterly NI by *4 for ROE/ROA computation
                ni_annualized = net_income * 4
                if equity and equity > 0:
                    roe = ni_annualized / equity
                if assets and assets > 0:
                    roa = ni_annualized / assets

            # YoY growth: compare to same quarter 4 quarters back
            rev_growth_yoy = None
            ni_growth_yoy = None
            if i + 4 < len(quarters):
                q_prior = quarters[i + 4]
                rev_prior = rev_by_q.get(q_prior)
                ni_prior = ni_by_q.get(q_prior)
                if revenue is not None and rev_prior and rev_prior > 0:
                    rev_growth_yoy = (revenue - rev_prior) / rev_prior
                if net_income is not None and ni_prior and ni_prior != 0:
                    ni_growth_yoy = (net_income - ni_prior) / abs(ni_prior)

            history.append({
                "date": str(q.date()) if hasattr(q, "date") else str(q),
                "grossMargins": round(gross_margin, 4) if gross_margin is not None else None,
                "operatingMargins": round(op_margin, 4) if op_margin is not None else None,
                "netMargins": round(net_margin, 4) if net_margin is not None else None,
                "returnOnEquity": round(roe, 4) if roe is not None else None,
                "returnOnAssets": round(roa, 4) if roa is not None else None,
                "revenueGrowth": round(rev_growth_yoy, 4) if rev_growth_yoy is not None else None,
                "earningsGrowth": round(ni_growth_yoy, 4) if ni_growth_yoy is not None else None,
            })

        return history
    except Exception:
        return []


def _retry(fn, tries=3, base_delay=1.5):
    """Retry a yfinance call through transient rate-limit/session failures.
    Reduces wholesale drops when Yahoo throttles a batch (a recurring cause of
    near-empty cache builds). Re-raises after the final attempt."""
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(base_delay * (i + 1) + random.random())


def fetch_stock(ticker):
    try:
        t = yf.Ticker(ticker)
        info = _retry(lambda: t.info) or {}
        if not info.get("marketCap"):
            return None
        hist = _retry(lambda: t.history(period="1y"))
        if hist is None or hist.empty or len(hist) < 20:
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
            "totalDebt": info.get("totalDebt"),
            "totalCash": info.get("totalCash"),
            "stockholdersEquity": info.get("stockholdersEquity"),
            "quarterly_history": fetch_quarterly_history(t),
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
    print(f"  Est. time: 50-65 minutes (12 quarters + balance sheet fields)")
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
