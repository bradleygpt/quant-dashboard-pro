"""
Universe Expansion Tool
=======================

Fetches the FULL S&P 600 constituent list from the iShares IJR ETF holdings JSON
(publicly accessible, no auth, always current as of T-1).

Run: python expand_universe.py

Output:
- Prints stats on current vs proposed universe
- Generates universe_additions.txt with new tickers
- These tickers can then be added to build_cache.py manually or via apply_additions.py
"""

import json
import re
import sys
import requests


# iShares JSON endpoints (publicly accessible, no auth required)
# These are the data feeds iShares uses to populate their public website.
ISHARES_ENDPOINTS = {
    "IJR": "https://www.ishares.com/us/products/239774/ishares-core-sp-smallcap-etf/1467271812596.ajax?fileType=json&fileName=IJR_holdings",
    "IJH": "https://www.ishares.com/us/products/239763/ishares-core-sp-midcap-etf/1467271812596.ajax?fileType=json&fileName=IJH_holdings",
}


def fetch_holdings(etf_ticker, url):
    """Fetch ETF holdings JSON. Returns list of stock tickers."""
    print(f"Fetching {etf_ticker} holdings from iShares...")
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; QuantDashboard Universe Expander)",
        "Accept": "application/json,text/plain,*/*",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()

        # iShares wraps response - sometimes raw JSON, sometimes JSONP-ish
        text = resp.text.strip()
        if text.startswith("{") or text.startswith("["):
            data = json.loads(text)
        else:
            # Try to extract JSON from wrapped response
            match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
            if not match:
                print(f"  ERROR: Could not parse iShares response for {etf_ticker}")
                return []
            data = json.loads(match.group(1))

        # iShares format: {"aaData": [[ticker, name, sector, ...], ...]}
        rows = data.get("aaData", []) if isinstance(data, dict) else data
        if not rows:
            print(f"  ERROR: No holdings rows in {etf_ticker} response")
            return []

        tickers = []
        for row in rows:
            if isinstance(row, list) and len(row) > 0:
                ticker = row[0] if isinstance(row[0], str) else str(row[0])
                ticker = ticker.strip().upper()
                # Skip cash positions and bond holdings
                if ticker in ("USD", "CASH", "USD COLLATERAL", "-"):
                    continue
                # Skip if ticker contains spaces or is too long (likely not a stock symbol)
                if " " in ticker or len(ticker) > 8:
                    continue
                tickers.append(ticker)
            elif isinstance(row, dict):
                ticker = row.get("ticker") or row.get("symbol") or ""
                if ticker and ticker not in ("USD", "CASH", "-"):
                    tickers.append(ticker.upper().strip())

        print(f"  Got {len(tickers)} tickers from {etf_ticker}")
        return tickers
    except Exception as e:
        print(f"  ERROR fetching {etf_ticker}: {str(e)[:200]}")
        return []


def get_current_universe():
    """Parse build_cache.py and extract all currently included stock tickers."""
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

    all_stocks = set(sp500) | set(sp400) | set(nasdaq_extra) | set(supplemental) | set(portfolio)
    all_etfs = set(etfs)
    return all_stocks, all_etfs


def main():
    print("=" * 60)
    print("UNIVERSE EXPANSION TOOL")
    print("=" * 60)

    # Get current universe
    current_stocks, current_etfs = get_current_universe()
    print(f"\nCurrent universe: {len(current_stocks)} stocks, {len(current_etfs)} ETFs")

    # Fetch IJR holdings (S&P 600 small cap)
    ijr_tickers = fetch_holdings("IJR", ISHARES_ENDPOINTS["IJR"])
    if not ijr_tickers:
        print("\nFailed to fetch IJR holdings. Possible alternatives:")
        print("  1. Try downloading the CSV directly from")
        print("     https://www.ishares.com/us/products/239774/ishares-core-sp-smallcap-etf")
        print("  2. Click 'Holdings' tab > 'Download All Holdings' (CSV)")
        print("  3. Extract ticker column manually")
        return 1

    # Compute additions
    ijr_set = set(ijr_tickers)
    new_tickers = sorted(ijr_set - current_stocks - current_etfs)
    overlap = sorted(ijr_set & (current_stocks | current_etfs))

    print(f"\n=== ANALYSIS ===")
    print(f"IJR total holdings: {len(ijr_set)}")
    print(f"Already in our universe: {len(overlap)}")
    print(f"New tickers to add: {len(new_tickers)}")
    print(f"Resulting universe size: {len(current_stocks) + len(new_tickers)} stocks + {len(current_etfs)} ETFs = {len(current_stocks) + len(new_tickers) + len(current_etfs)} total")
    print(f"Estimated cache build time: {(len(current_stocks) + len(new_tickers)) * 4 / 60:.0f}-{(len(current_stocks) + len(new_tickers)) * 6 / 60:.0f} minutes")

    # Write the new tickers to a file
    output_file = "universe_additions.txt"
    with open(output_file, "w") as f:
        f.write(f"# S&P 600 (IJR) tickers not currently in build_cache.py\n")
        f.write(f"# Generated: {len(new_tickers)} new tickers\n")
        f.write(f"# Paste into build_cache.py as a new SP600_EXTRA section\n\n")
        f.write("SP600_EXTRA = [\n")
        for i in range(0, len(new_tickers), 10):
            chunk = new_tickers[i:i+10]
            line = "    " + ", ".join(f'"{t}"' for t in chunk) + ","
            f.write(line + "\n")
        f.write("]\n")

    print(f"\nWrote {len(new_tickers)} new tickers to {output_file}")
    print(f"Next step: open {output_file}, copy the SP600_EXTRA list, paste into build_cache.py")
    print(f"Then run: python build_cache.py (or trigger the GitHub Action)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
