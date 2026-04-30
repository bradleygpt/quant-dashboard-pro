"""
Convert iShares Holdings CSV to Python Ticker List
==================================================

Manual workflow (avoids broken iShares JSON API):

1. Visit one of these iShares pages in your browser:
   - IJR (S&P 600): https://www.ishares.com/us/products/239774/ishares-core-sp-smallcap-etf
   - IJH (S&P 400): https://www.ishares.com/us/products/239763/ishares-core-sp-midcap-etf
   - IVV (S&P 500): https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf

2. Click the "Holdings" tab

3. Click "Detailed Holdings and Analytics" or "Download Holdings" button (top right of holdings table)

4. Save the resulting CSV to: C:\\Users\\bmhar\\Downloads\\quant-dashboard-pro\\
   (Default filename is something like "iShares-Core-SP-SmallCap-ETF_fund.csv")

5. Run this script with the path:
   python csv_to_tickers.py iShares-Core-SP-SmallCap-ETF_fund.csv

This will produce universe_additions.txt with deduped new tickers ready to paste.
"""

import csv
import re
import sys


def get_current_universe():
    """Parse build_cache.py and extract all currently included stock + ETF tickers."""
    try:
        with open("build_cache.py") as f:
            content = f.read()
    except FileNotFoundError:
        print("ERROR: build_cache.py not found in current directory")
        sys.exit(1)

    def extract_list(name):
        pattern = re.compile(rf'^{name}\s*=\s*\[(.*?)^\]', re.MULTILINE | re.DOTALL)
        m = pattern.search(content)
        if not m:
            return []
        body = m.group(1)
        return re.findall(r'"([A-Z][A-Z0-9.\-]+)"', body)

    sp500 = extract_list("SP500")
    sp400 = extract_list("SP400_EXTRA")
    nasdaq_extra = ["APP", "ASML", "AZN", "CCEP", "GFS", "HON", "MRVL", "TEAM", "WDAY"]
    supplemental = extract_list("SUPPLEMENTAL")
    portfolio = ["CLS", "IREN", "ASTS", "RKLB", "BMNR", "ONDS"]
    etfs = extract_list("ETFS")

    return set(sp500) | set(sp400) | set(nasdaq_extra) | set(supplemental) | set(portfolio) | set(etfs)


def parse_ishares_csv(csv_path):
    """
    iShares CSVs have ~9 lines of metadata at the top, then the holdings table.

    Format example:
        Fund Holdings as of,"Apr 28, 2026",
        Inception Date,"May 22, 2000",
        Shares Outstanding,"118,250,000",
        Net Assets,"$95,127,532,950",
        ... metadata ...

        Ticker,Name,Sector,Asset Class,Market Value,Weight (%),...
        AAA,Some Company,Technology,Equity,...
        ...
    """
    tickers = []
    found_header = False

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                # Find the header row (starts with "Ticker")
                if not found_header:
                    if row[0].strip().lower() in ("ticker", "ticker symbol"):
                        found_header = True
                    continue
                # Now we're in the holdings table
                ticker = row[0].strip().upper()
                # Skip cash, currency hedges, derivatives
                if ticker in ("USD", "CASH", "-", ""):
                    continue
                if "FUTURES" in ticker or "CASH_USD" in ticker:
                    continue
                # Skip if not a clean ticker symbol
                if " " in ticker or len(ticker) > 8 or len(ticker) < 1:
                    continue
                # Some iShares CSVs use BRK.B format, others use BRK/B
                ticker = ticker.replace("/", ".")
                tickers.append(ticker)
    except FileNotFoundError:
        print(f"ERROR: CSV file not found: {csv_path}")
        return None
    except UnicodeDecodeError:
        # iShares sometimes uses Windows-1252 encoding
        try:
            with open(csv_path, "r", encoding="cp1252") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    if not found_header:
                        if row[0].strip().lower() in ("ticker", "ticker symbol"):
                            found_header = True
                        continue
                    ticker = row[0].strip().upper()
                    if ticker in ("USD", "CASH", "-", "") or "FUTURES" in ticker:
                        continue
                    if " " in ticker or len(ticker) > 8 or len(ticker) < 1:
                        continue
                    ticker = ticker.replace("/", ".")
                    tickers.append(ticker)
        except Exception as e:
            print(f"ERROR reading file: {e}")
            return None
    except Exception as e:
        print(f"ERROR parsing CSV: {e}")
        return None

    if not found_header:
        print(f"WARNING: Could not find 'Ticker' header in CSV. Format may have changed.")
        print(f"First few rows of file:")
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= 15:
                    break
                print(f"  {line.rstrip()}")

    return tickers


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    csv_path = sys.argv[1]
    print("=" * 60)
    print(f"PARSING: {csv_path}")
    print("=" * 60)

    tickers = parse_ishares_csv(csv_path)
    if tickers is None:
        return 1

    print(f"\n[1/2] Loaded {len(tickers)} tickers from CSV")
    if len(tickers) < 100:
        print("WARNING: Got fewer than 100 tickers. CSV format may be wrong.")
        print("First 10 tickers found:", tickers[:10])

    current = get_current_universe()
    print(f"[2/2] Current universe size: {len(current)}")

    new = sorted(set(tickers) - current)
    overlap = sorted(set(tickers) & current)

    print(f"\n=== ANALYSIS ===")
    print(f"Tickers in CSV: {len(set(tickers))}")
    print(f"Already in universe: {len(overlap)}")
    print(f"New to add: {len(new)}")
    print(f"Resulting universe: {len(current) + len(new)} total")

    output_file = "universe_additions.txt"
    with open(output_file, "w") as f:
        f.write(f"# New tickers from {csv_path}\n")
        f.write(f"# Count: {len(new)}\n")
        f.write(f"# Paste into build_cache.py as a new constant\n\n")
        f.write("SP600_EXTRA = [\n")
        for i in range(0, len(new), 10):
            chunk = new[i:i+10]
            line = "    " + ", ".join(f'"{t}"' for t in chunk) + ","
            f.write(line + "\n")
        f.write("]\n")

    print(f"\nWrote {len(new)} new tickers to {output_file}")
    print(f"Open the file, copy the SP600_EXTRA list, paste into build_cache.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
