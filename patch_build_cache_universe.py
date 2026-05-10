"""
Patch build_cache.py to expand SUPPLEMENTAL with 35 additional tickers.

Adds recent IPOs (2022-2025), spinoffs, and meaningful growth/thematic
names not currently in any of SP500/NASDAQ100_EXTRA/SP400_EXTRA/SP600_EXTRA.

Categories (kept in single SUPPLEMENTAL list, with comments for clarity):
  - Recent re-IPOs and 2024 IPOs (8)
  - 2023 IPOs (3)
  - Pre-2022 missing names (3)
  - Crypto/digital mining (4)
  - AI infrastructure / growth (2)
  - Nuclear / SMR thesis (5)
  - Fintech (4)
  - Biotech / gene editing (6)

Total: 35 new tickers.

After running this patch, regenerate fundamentals_cache.json by running
build_cache.py. The new tickers will be fetched via yfinance.

Run from the dashboard repo (where build_cache.py lives).

Original is backed up to build_cache.py.bak before modification.
"""

from pathlib import Path
import shutil
import sys

TARGET = Path("./build_cache.py")

# Current SUPPLEMENTAL block as-is in the file
OLD_BLOCK = '''SUPPLEMENTAL = [
    "TSM","BABA","JD","PDD","BIDU","NIO","LI","XPEV",
    "SHOP","TD","RY","CNQ","SU","BN","BAM","SE","MELI","NU","GRAB",
    "BX","KKR","APO","OWL","SPOT","XYZ","MSTR","CELH","CAVA",
    "RIVN","LCID","JOBY","BILL","PATH","SNAP","U","PINS",
]'''

# New SUPPLEMENTAL with categorized comments + additions
NEW_BLOCK = '''SUPPLEMENTAL = [
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
]'''


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found in current directory")
        print(f"  Run this from the dashboard repo where build_cache.py lives.")
        return 1

    text = TARGET.read_text(encoding="utf-8")

    if OLD_BLOCK not in text:
        # Check if already patched
        if '"SNDK"' in text and "Recent re-IPOs" in text:
            print("File already patched (SNDK and category comments present).")
            print("Nothing to do.")
            return 0
        print("ERROR: expected SUPPLEMENTAL block not found exactly as expected.")
        print("File may have been modified. Aborting to avoid breaking it.")
        print("\nExpected block (39 tickers, no comments):")
        print(OLD_BLOCK[:200] + "...")
        return 1

    # Backup
    backup = TARGET.with_suffix(".py.bak")
    shutil.copy(TARGET, backup)
    print(f"Backup saved to {backup}")

    # Patch
    new_text = text.replace(OLD_BLOCK, NEW_BLOCK)
    TARGET.write_text(new_text, encoding="utf-8")

    # Verify
    verify = TARGET.read_text(encoding="utf-8")
    if "SNDK" not in verify or "Recent re-IPOs" not in verify:
        print("ERROR: patch did not take effect")
        return 1

    # Count what's there now
    import re
    new_supp_match = re.search(r"^SUPPLEMENTAL\s*=\s*\[(.*?)^\]",
                                verify, re.MULTILINE | re.DOTALL)
    if new_supp_match:
        ticker_count = len(re.findall(r'"[A-Z][A-Z0-9.\-]*"',
                                       new_supp_match.group(1)))
        print(f"\nPatched successfully.")
        print(f"  SUPPLEMENTAL now has {ticker_count} tickers (was 36, added 35).")
        print(f"  All tickers categorized with comments for clarity.")
        print(f"\nNext step:")
        print(f"  Run: python build_cache.py")
        print(f"  Estimated time: ~30-45 sec for 35 new tickers @ ~0.8s each")
        print(f"  Then commit fundamentals_cache.json and push.")
    else:
        print("Patched but couldn't verify count.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
