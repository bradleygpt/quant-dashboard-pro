"""
Quant Strategy Dashboard Pro - Data Refresh Orchestrator
=========================================================

Single entry point for refreshing all data in the dashboard. Different data has
different ideal cadences. Run this script with appropriate flags depending on
what you want to refresh.

USAGE
-----
Daily refresh (recommended weeknights at ~10pm ET, after market close):
    python refresh_data.py --daily

Weekly refresh (recommended Sundays):
    python refresh_data.py --weekly

Monthly refresh (recommended first weekend of month):
    python refresh_data.py --monthly

Full refresh (everything):
    python refresh_data.py --full

Specific component:
    python refresh_data.py --component cache
    python refresh_data.py --component correlations
    python refresh_data.py --component pgi

CADENCE GUIDE
-------------
| Data                      | Ideal Cadence       | Why                                 |
|---------------------------|---------------------|-------------------------------------|
| Fundamentals cache        | Daily (weeknights)  | Prices, momentum, valuations move   |
| Sector correlations       | Weekly              | Slow-moving structural relationship |
| PGI money market figure   | Monthly (after ICI) | ICI publishes monthly               |
| FRED macro indicators     | Auto (on-app-load)  | Cached at runtime, FRED is fast     |
| Doppelganger analogs      | Manual              | Historical, only edit when adding   |
| ETF cache (within main)   | Daily (with cache)  | Same yfinance call as stocks        |
| Quote data (Live Monitor) | Real-time           | yfinance call per refresh-click     |
| Earnings data (FH/EDGAR)  | 24hr cache (auto)   | Streamlit cache_data handles this   |
| Stock universe lists      | Quarterly           | Index reconstitution events         |

WHAT'S NOT REFRESHED HERE (and why):
- Live quotes/prices: Done at runtime, no caching needed
- AI responses: 24hr cache via @st.cache_data
- Supabase data: User-managed, persisted in cloud
- Sentiment indices: VIX/PCR/etc. fetched live each app session
"""

import sys
import argparse
import subprocess
from datetime import datetime
from pathlib import Path


# ══════════════════════════════════════════════════════════════════
# Component runners
# ══════════════════════════════════════════════════════════════════

def run_fundamentals_cache():
    """Refresh fundamentals cache (~700 stocks + ETFs). Takes 25-40 minutes."""
    print(f"\n{'='*60}")
    print("[1/3] FUNDAMENTALS CACHE")
    print(f"{'='*60}")
    print("Refreshing fundamentals_cache.json...")
    print("Sources: yfinance for prices, fundamentals, momentum, ETFs")
    print("Coverage: ~700 stocks (S&P 500 + extras + ETFs)")
    print("Estimated time: 25-40 minutes\n")

    try:
        result = subprocess.run(
            [sys.executable, "build_cache.py"],
            capture_output=False,
            check=True,
        )
        print("\n✓ Fundamentals cache refreshed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ build_cache.py failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print("\n✗ build_cache.py not found in current directory")
        return False


def run_correlations():
    """Refresh sector correlation matrix. Takes 5-10 minutes."""
    print(f"\n{'='*60}")
    print("[2/3] SECTOR CORRELATIONS")
    print(f"{'='*60}")
    print("Refreshing sector_correlations.json...")
    print("Source: yfinance 1-year price history per sector ETF")
    print("Estimated time: 5-10 minutes\n")

    try:
        result = subprocess.run(
            [sys.executable, "build_correlations.py"],
            capture_output=False,
            check=True,
        )
        print("\n✓ Sector correlations refreshed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ build_correlations.py failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print("\n✗ build_correlations.py not found")
        return False


def update_pgi_figure():
    """
    Update the hardcoded money market fund figure in sentiment.py.
    Currently set to $6.7T as of early 2026. Real figure grows ~1-2% per month.

    Source: https://www.ici.org/research/stats/mmf

    This is MANUAL because ICI doesn't have a public API. You need to:
    1. Visit https://www.ici.org/research/stats/mmf
    2. Find the latest "Total Money Market Fund Assets" figure (in trillions)
    3. Update the constant in sentiment.py
    """
    print(f"\n{'='*60}")
    print("[3/3] PGI MONEY MARKET FIGURE")
    print(f"{'='*60}")
    sentiment_path = Path("sentiment.py")
    if not sentiment_path.exists():
        print("✗ sentiment.py not found")
        return False

    print("\nMANUAL UPDATE REQUIRED:")
    print("1. Open https://www.ici.org/research/stats/mmf")
    print("2. Find latest 'Total Money Market Fund Assets'")
    print("3. Open sentiment.py and find: MONEY_MARKET_ASSETS_TRILLIONS")
    print("4. Update to the new value (e.g., 7.3 if assets are $7.3T)")
    print("5. Save the file\n")

    # Show current value
    try:
        content = sentiment_path.read_text()
        for line in content.split("\n"):
            if "MONEY_MARKET_ASSETS_TRILLIONS" in line and "=" in line:
                print(f"Current line in sentiment.py: {line.strip()}")
                break
    except Exception:
        pass
    print("\n(This component is informational only - no code change made.)")
    return True


# ══════════════════════════════════════════════════════════════════
# Cadence presets
# ══════════════════════════════════════════════════════════════════

def run_daily():
    """Daily refresh (weeknights at 10pm ET recommended)."""
    print(f"\n{'#'*60}")
    print(f"# DAILY REFRESH - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")
    success = run_fundamentals_cache()
    if success:
        print("\n✓ DAILY REFRESH COMPLETE")
    return success


def run_weekly():
    """Weekly refresh (Sunday recommended)."""
    print(f"\n{'#'*60}")
    print(f"# WEEKLY REFRESH - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")
    s1 = run_fundamentals_cache()
    s2 = run_correlations()
    if s1 and s2:
        print("\n✓ WEEKLY REFRESH COMPLETE")
    return s1 and s2


def run_monthly():
    """Monthly refresh (first weekend of month recommended)."""
    print(f"\n{'#'*60}")
    print(f"# MONTHLY REFRESH - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")
    s1 = run_fundamentals_cache()
    s2 = run_correlations()
    s3 = update_pgi_figure()
    if all([s1, s2, s3]):
        print("\n✓ MONTHLY REFRESH COMPLETE")
    return all([s1, s2, s3])


def run_full():
    """Full refresh - same as monthly currently."""
    return run_monthly()


def run_component(name):
    """Run a specific component by name."""
    components = {
        "cache": run_fundamentals_cache,
        "fundamentals": run_fundamentals_cache,
        "correlations": run_correlations,
        "pgi": update_pgi_figure,
    }
    func = components.get(name.lower())
    if not func:
        print(f"Unknown component: {name}")
        print(f"Available: {', '.join(components.keys())}")
        return False
    return func()


# ══════════════════════════════════════════════════════════════════
# CLI entry
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Refresh dashboard data with appropriate cadence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Cadence Guide:
  --daily    : Refresh fundamentals cache (~30 min)
  --weekly   : Daily + sector correlations (~40 min)
  --monthly  : Weekly + PGI reminder (~40 min + manual step)
  --full     : Same as --monthly
  --component <name>: Run one component only
                      (cache | correlations | pgi)
        """
    )
    parser.add_argument("--daily", action="store_true", help="Daily refresh")
    parser.add_argument("--weekly", action="store_true", help="Weekly refresh")
    parser.add_argument("--monthly", action="store_true", help="Monthly refresh")
    parser.add_argument("--full", action="store_true", help="Full refresh")
    parser.add_argument("--component", type=str, help="Run specific component (cache|correlations|pgi)")

    args = parser.parse_args()

    # Default if no flags
    if not any([args.daily, args.weekly, args.monthly, args.full, args.component]):
        print("No flag specified. Showing help:\n")
        parser.print_help()
        return 1

    success = True
    if args.daily:
        success = run_daily()
    elif args.weekly:
        success = run_weekly()
    elif args.monthly:
        success = run_monthly()
    elif args.full:
        success = run_full()
    elif args.component:
        success = run_component(args.component)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
