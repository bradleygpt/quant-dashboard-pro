"""
Monthly PGI Update Script
Scrapes ICI's public money market fund total assets page and updates
the MONEY_MARKET_ASSETS_TRILLIONS constant in sentiment.py.

Source: https://www.ici.org/research/stats/mmf
ICI publishes weekly data; we sample at month-end.

Output: Updates sentiment.py in place if a new figure is found.
Exit code 0 if updated or no change; 1 on error.
"""

import re
import sys
import requests
from pathlib import Path


ICI_URL = "https://www.ici.org/research/stats/mmf"
SENTIMENT_PATH = Path("sentiment.py")
USER_AGENT = "Mozilla/5.0 (compatible; QuantDashboard PGI Updater)"


def fetch_ici_total_assets():
    """
    Fetch latest money market fund total assets from ICI.

    ICI publishes a table with "Total Money Market Funds" rows.
    Returns figure in trillions of dollars, or None if extraction fails.
    """
    try:
        resp = requests.get(ICI_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        html = resp.text

        # ICI publishes figures in millions. Look for patterns like:
        # "Total Money Market Funds" near a dollar figure
        # Example: "$7,123,456" (millions) -> $7.12 trillion

        # Strategy: Find numbers in millions that are large enough to be plausible
        # money market totals (>$5T = >$5,000,000 in millions)
        millions_pattern = re.compile(r'[\$]?\s*([\d,]{8,})\s*(?:million|M)?', re.IGNORECASE)

        # Look for the first table-like section mentioning total money market
        marker_idx = -1
        for marker in ["Total Money Market", "total money market", "Total Money Market Fund Assets"]:
            idx = html.find(marker)
            if idx > 0:
                marker_idx = idx
                break

        if marker_idx < 0:
            return None, "Could not find 'Total Money Market' marker on ICI page"

        # Look in the next 2000 chars after the marker for the figure
        snippet = html[marker_idx:marker_idx + 5000]
        matches = millions_pattern.findall(snippet)

        for match in matches:
            try:
                value_millions = int(match.replace(",", ""))
                # Plausibility: between $5T and $20T = 5,000,000 to 20,000,000 millions
                if 5_000_000 <= value_millions <= 20_000_000:
                    value_trillions = round(value_millions / 1_000_000, 2)
                    return value_trillions, None
            except ValueError:
                continue

        return None, "No plausible money market total found in expected range ($5T-$20T)"
    except Exception as e:
        return None, f"Fetch failed: {e}"


def update_sentiment_constant(new_value):
    """Update MONEY_MARKET_ASSETS_TRILLIONS in sentiment.py. Returns (changed, old_value)."""
    if not SENTIMENT_PATH.exists():
        raise FileNotFoundError("sentiment.py not found in current directory")

    content = SENTIMENT_PATH.read_text()

    # Match the constant assignment
    pattern = re.compile(r'^(MONEY_MARKET_ASSETS_TRILLIONS\s*=\s*)([\d.]+)', re.MULTILINE)
    match = pattern.search(content)
    if not match:
        raise ValueError("MONEY_MARKET_ASSETS_TRILLIONS constant not found in sentiment.py")

    old_value = float(match.group(2))
    if abs(old_value - new_value) < 0.05:
        return False, old_value  # No meaningful change

    new_content = pattern.sub(rf'\g<1>{new_value}', content)
    SENTIMENT_PATH.write_text(new_content)
    return True, old_value


def main():
    print(f"Fetching latest money market total from ICI...")
    value, error = fetch_ici_total_assets()
    if value is None:
        print(f"FAIL: {error}")
        print("Manual update needed. Visit https://www.ici.org/research/stats/mmf")
        return 1

    print(f"ICI reports: ${value}T")

    try:
        changed, old_value = update_sentiment_constant(value)
        if changed:
            print(f"UPDATED sentiment.py: ${old_value}T -> ${value}T")
        else:
            print(f"NO CHANGE: sentiment.py already shows ${old_value}T (within 0.05T tolerance)")
        return 0
    except Exception as e:
        print(f"ERROR updating sentiment.py: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
