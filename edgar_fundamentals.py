"""
EDGAR XBRL Historical Fundamentals Fetcher
============================================

Fetches point-in-time historical fundamentals for any US public company
from SEC EDGAR's free XBRL data API.

Self-contained: doesn't require Streamlit context.
"""

import os
import json
import time
import requests
import sys
from datetime import datetime, date
from typing import Optional, Dict, List

# SEC requires User-Agent header identifying the requester
EDGAR_HEADERS = {
    "User-Agent": "QuantDashboardPro/1.0 contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}

# Local cache for companyfacts JSONs (large files, ~1-5MB each)
CACHE_DIR = "edgar_cache"

# Ticker-to-CIK mapping cache
_TICKER_CIK_MAP = None


def _load_ticker_cik_map():
    """Load SEC's company_tickers.json which maps tickers to CIKs.

    Self-contained version that doesn't depend on Streamlit caching.
    """
    global _TICKER_CIK_MAP
    if _TICKER_CIK_MAP is not None:
        return _TICKER_CIK_MAP

    cache_file = os.path.join(CACHE_DIR, "ticker_cik_map.json")

    # Try local cache first
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                _TICKER_CIK_MAP = json.load(f)
                return _TICKER_CIK_MAP
        except Exception:
            pass

    # Fetch from SEC
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        time.sleep(0.15)
        r = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
        if r.status_code == 200:
            data = r.json()
            mapping = {}
            for entry in data.values():
                ticker = entry.get("ticker", "").upper()
                cik = entry.get("cik_str")
                if ticker and cik:
                    mapping[ticker] = int(cik)

            _ensure_cache_dir()
            try:
                with open(cache_file, "w") as f:
                    json.dump(mapping, f)
            except Exception:
                pass
            _TICKER_CIK_MAP = mapping
            return mapping
    except Exception as e:
        print(f"  Failed to fetch ticker-CIK map: {e}", file=sys.stderr)
        return {}

    return {}


def get_cik_for_ticker(ticker):
    """Get CIK number for a ticker. Returns None if not found."""
    mapping = _load_ticker_cik_map()
    return mapping.get(ticker.upper())


# Concept mapping: maps logical metric names to ordered lists of XBRL tags
CONCEPT_MAPPING = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfServices",
    ],
    "total_debt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "DebtCurrent",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "total_assets": [
        "Assets",
    ],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ],
    "eps_basic": [
        "EarningsPerShareBasic",
    ],
    "eps_diluted": [
        "EarningsPerShareDiluted",
    ],
}


def _ensure_cache_dir():
    """Create cache directory if needed."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)


def fetch_companyfacts(ticker, cik, verbose=False):
    """
    Fetch and cache the full companyfacts JSON for a ticker.

    Returns the parsed JSON dict, or None on failure.
    """
    _ensure_cache_dir()
    cache_file = os.path.join(CACHE_DIR, f"{ticker.upper()}_facts.json")

    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                return json.load(f)
        except Exception:
            pass

    try:
        cik_int = int(str(cik).lstrip("0") or "0")
    except (ValueError, TypeError):
        if verbose:
            print(f"  Invalid CIK: {cik}", file=sys.stderr)
        return None

    if cik_int == 0:
        if verbose:
            print(f"  CIK is 0", file=sys.stderr)
        return None

    cik_padded = str(cik_int).zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"

    if verbose:
        print(f"  Fetching: {url}", file=sys.stderr)

    try:
        time.sleep(0.15)
        r = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
        if verbose:
            print(f"  HTTP status: {r.status_code}", file=sys.stderr)
        if r.status_code == 200:
            data = r.json()
            try:
                with open(cache_file, "w") as f:
                    json.dump(data, f)
            except Exception:
                pass
            return data
        elif r.status_code == 404:
            if verbose:
                print(f"  404 - not in EDGAR", file=sys.stderr)
            return None
        else:
            if verbose:
                print(f"  Unexpected status {r.status_code}", file=sys.stderr)
            return None
    except Exception as e:
        if verbose:
            print(f"  Request error: {e}", file=sys.stderr)
        return None


def _get_concept_value_at_date(facts_dict, concept_tags, target_date):
    """
    Find the most recent reported value for any of `concept_tags`
    that was filed BEFORE target_date.

    Tries ALL tags and picks the one with the most recent end_date.
    This handles cases where ticker uses different tags over time.

    Returns (value, end_date_of_period, filing_date) or None.
    """
    if not facts_dict:
        return None

    us_gaap = facts_dict.get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None

    target_dt = target_date.date() if isinstance(target_date, datetime) else target_date

    best_value = None
    best_end_date = None
    best_filed_date = None

    # Try ALL tags, keep the entry with the most recent end_date
    for tag in concept_tags:
        if tag not in us_gaap:
            continue

        units = us_gaap[tag].get("units", {})
        for unit_name in ["USD", "shares", "USD/shares", "pure"]:
            if unit_name not in units:
                continue

            entries = units[unit_name]
            for entry in entries:
                try:
                    end_str = entry.get("end")
                    filed_str = entry.get("filed")
                    if not end_str or not filed_str:
                        continue

                    end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
                    filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()

                    if filed_dt > target_dt:
                        continue

                    # Pick most recent end_date; tiebreak with latest filed_date (latest restatement)
                    is_better = False
                    if best_end_date is None:
                        is_better = True
                    elif end_dt > best_end_date:
                        is_better = True
                    elif end_dt == best_end_date and filed_dt > best_filed_date:
                        is_better = True

                    if is_better:
                        val = entry.get("val")
                        if val is not None:
                            best_value = val
                            best_end_date = end_dt
                            best_filed_date = filed_dt
                except (ValueError, TypeError, KeyError):
                    continue

    if best_value is None:
        return None

    return (best_value, best_end_date, best_filed_date)


def _get_ttm_value(facts_dict, concept_tags, target_date):
    """
    Get trailing-twelve-month sum for a concept at target_date.

    Logic:
    1. Collect ALL entries from ALL provided tags (filed before target_date)
    2. Prefer the most recent annual entry (350-380 day period)
    3. Otherwise, sum the 4 most recent quarterly entries (80-100 day periods)
    4. Pick whichever option has the most recent end_date

    This handles tickers like AAPL where:
    - Q4 fiscal data appears as 370-day annual entries (10-K filings), not 90-day
    - Multiple revenue tags exist with data spanning different periods
    - First-tag-wins logic would miss the most recent data

    Returns (ttm_value, latest_end_date) or None.
    """
    if not facts_dict:
        return None

    us_gaap = facts_dict.get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None

    target_dt = target_date.date() if isinstance(target_date, datetime) else target_date

    # Collect entries across ALL tags
    all_quarterly = []  # (end_dt, filed_dt, val, period_days, tag)
    all_annual = []     # same shape

    for tag in concept_tags:
        if tag not in us_gaap:
            continue

        units = us_gaap[tag].get("units", {})
        if "USD" not in units:
            continue

        for entry in units["USD"]:
            try:
                end_str = entry.get("end")
                start_str = entry.get("start")
                filed_str = entry.get("filed")
                if not all([end_str, start_str, filed_str]):
                    continue

                end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
                start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
                filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()

                # Skip future filings (point-in-time discipline)
                if filed_dt > target_dt:
                    continue

                period_days = (end_dt - start_dt).days
                val = entry.get("val")
                if val is None:
                    continue

                if 80 <= period_days <= 100:
                    all_quarterly.append((end_dt, filed_dt, val, period_days, tag))
                elif 350 <= period_days <= 380:
                    all_annual.append((end_dt, filed_dt, val, period_days, tag))
            except (ValueError, TypeError, KeyError):
                continue

    # Find best annual candidate (most recent end_date, latest filed_date as tiebreaker)
    annual_candidate = None
    if all_annual:
        all_annual.sort(key=lambda x: (x[0], x[1]), reverse=True)
        # Dedupe by end_dt (keep latest filed)
        seen = set()
        deduped_annual = []
        for end_dt, filed_dt, val, period, tag in all_annual:
            if end_dt not in seen:
                seen.add(end_dt)
                deduped_annual.append((end_dt, filed_dt, val, period, tag))
        if deduped_annual:
            best = deduped_annual[0]
            annual_candidate = (best[2], best[0])  # (val, end_dt)

    # Find best quarterly TTM candidate
    quarterly_candidate = None
    if all_quarterly:
        # Dedupe by end_dt (keep latest filed)
        all_quarterly.sort(key=lambda x: (x[0], x[1]), reverse=True)
        seen = set()
        deduped_q = []
        for end_dt, filed_dt, val, period, tag in all_quarterly:
            if end_dt not in seen:
                seen.add(end_dt)
                deduped_q.append((end_dt, filed_dt, val, period, tag))

        # Need 4 quarters for TTM
        if len(deduped_q) >= 4:
            top_4 = deduped_q[:4]
            ttm_sum = sum(v for _, _, v, _, _ in top_4)
            latest_end = top_4[0][0]
            quarterly_candidate = (ttm_sum, latest_end)

    # Pick whichever candidate has the most recent end_date
    if annual_candidate and quarterly_candidate:
        if annual_candidate[1] >= quarterly_candidate[1]:
            return annual_candidate
        else:
            return quarterly_candidate
    elif annual_candidate:
        return annual_candidate
    elif quarterly_candidate:
        return quarterly_candidate
    else:
        return None


def get_latest_earnings_filing_date(ticker, target_date):
    """
    Find the most recent earnings filing date BEFORE target_date.
    Returns date object or None.

    Used by PEAD computation: PEAD = stock return in 30 trading days post-filing,
    minus SPY return over same period.

    Accepts both 10-Q (quarterly, 80-100 day periods) and 10-K (annual, 350-380 day) filings.
    """
    cik_map = _load_ticker_cik_map()
    cik = cik_map.get(ticker.upper())
    if cik is None:
        return None

    facts_dict = fetch_companyfacts(ticker, cik)
    if not facts_dict:
        return None

    target_dt = target_date.date() if isinstance(target_date, datetime) else target_date
    us_gaap = facts_dict.get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None

    # Use revenue or net_income as proxy for earnings filings (10-Q / 10-K)
    latest_filed = None
    for concept_tags in [CONCEPT_MAPPING["revenue"], CONCEPT_MAPPING["net_income"]]:
        for tag in concept_tags:
            if tag not in us_gaap:
                continue
            units = us_gaap[tag].get("units", {})
            if "USD" not in units:
                continue
            for entry in units["USD"]:
                try:
                    filed_str = entry.get("filed")
                    if not filed_str:
                        continue
                    filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").date()
                    if filed_dt > target_dt:
                        continue
                    # Accept both quarterly (80-100d) and annual (350-380d)
                    end_str = entry.get("end")
                    start_str = entry.get("start")
                    if not (end_str and start_str):
                        continue
                    end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
                    start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
                    period_days = (end_dt - start_dt).days
                    if not ((80 <= period_days <= 100) or (350 <= period_days <= 380)):
                        continue
                    if latest_filed is None or filed_dt > latest_filed:
                        latest_filed = filed_dt
                except (ValueError, TypeError, KeyError):
                    continue

    return latest_filed


def get_fundamentals_at_date(ticker, target_date, verbose=False):
    """
    Get point-in-time fundamentals for a ticker as of target_date.

    Returns dict with available metrics, plus data_quality_score (0-100),
    or None on total failure.
    """
    result = {
        "ticker": ticker,
        "as_of_date": target_date.strftime("%Y-%m-%d") if hasattr(target_date, 'strftime') else str(target_date),
        "data_quality_score": 0,
        "_source": "edgar_xbrl",
    }

    cik = get_cik_for_ticker(ticker)
    if not cik:
        if verbose:
            print(f"  No CIK found for {ticker}", file=sys.stderr)
        return result

    if verbose:
        print(f"  CIK: {cik}", file=sys.stderr)

    facts = fetch_companyfacts(ticker, cik, verbose=verbose)
    if not facts:
        if verbose:
            print(f"  No companyfacts data", file=sys.stderr)
        return result

    target_dt = target_date.date() if isinstance(target_date, datetime) else target_date

    if verbose:
        # Show what tags ARE available
        us_gaap_tags = list(facts.get("facts", {}).get("us-gaap", {}).keys())
        print(f"  Available us-gaap tags: {len(us_gaap_tags)} total", file=sys.stderr)
        revenue_tags = [t for t in us_gaap_tags if "revenue" in t.lower() or "sales" in t.lower()]
        print(f"  Revenue-related tags: {revenue_tags[:5]}", file=sys.stderr)

    # TTM Revenue
    ttm_rev = _get_ttm_value(facts, CONCEPT_MAPPING["revenue"], target_dt)
    if ttm_rev:
        result["ttm_revenue"] = ttm_rev[0]
        result["data_quality_score"] += 20
        if verbose:
            print(f"  TTM Revenue: ${ttm_rev[0]:,.0f}", file=sys.stderr)

    # TTM Net Income
    ttm_ni = _get_ttm_value(facts, CONCEPT_MAPPING["net_income"], target_dt)
    if ttm_ni:
        result["ttm_net_income"] = ttm_ni[0]
        result["data_quality_score"] += 15
        if verbose:
            print(f"  TTM Net Income: ${ttm_ni[0]:,.0f}", file=sys.stderr)

    # YoY Revenue Growth
    if ttm_rev:
        prior_year_dt = date(target_dt.year - 1, target_dt.month, max(1, min(target_dt.day, 28)))
        prior_ttm = _get_ttm_value(facts, CONCEPT_MAPPING["revenue"], prior_year_dt)
        if prior_ttm and prior_ttm[0] > 0:
            growth = ((ttm_rev[0] / prior_ttm[0]) - 1) * 100
            result["revenue_growth_yoy"] = growth
            result["data_quality_score"] += 15
            if verbose:
                print(f"  Revenue Growth YoY: {growth:.1f}%", file=sys.stderr)

    # Operating Income (TTM, for consistency with TTM revenue)
    ttm_op_inc = _get_ttm_value(facts, CONCEPT_MAPPING["operating_income"], target_dt)
    if ttm_op_inc and ttm_rev and ttm_rev[0] > 0:
        op_inc_value = ttm_op_inc[0]
        margin = (op_inc_value / ttm_rev[0]) * 100
        result["ttm_operating_income"] = op_inc_value
        result["operating_margin"] = margin
        result["data_quality_score"] += 10
        if verbose:
            print(f"  Operating Margin: {margin:.1f}%", file=sys.stderr)

    # TTM Cost of Revenue (for Gross Margin)
    ttm_cogs = _get_ttm_value(facts, CONCEPT_MAPPING["cost_of_revenue"], target_dt)
    if ttm_cogs and ttm_rev and ttm_rev[0] > 0:
        cogs_value = ttm_cogs[0]
        gross_profit = ttm_rev[0] - cogs_value
        gross_margin_pct = (gross_profit / ttm_rev[0]) * 100
        result["ttm_cost_of_revenue"] = cogs_value
        result["gross_margin"] = gross_margin_pct
        result["data_quality_score"] += 10
        if verbose:
            print(f"  Gross Margin: {gross_margin_pct:.1f}%", file=sys.stderr)

    # Balance sheet items
    debt_data = _get_concept_value_at_date(facts, CONCEPT_MAPPING["total_debt"], target_dt)
    equity_data = _get_concept_value_at_date(facts, CONCEPT_MAPPING["stockholders_equity"], target_dt)

    if debt_data:
        result["total_debt"] = debt_data[0]
        result["data_quality_score"] += 5

    if equity_data:
        result["stockholders_equity"] = equity_data[0]
        result["data_quality_score"] += 5

    if debt_data and equity_data and equity_data[0] > 0:
        result["debt_to_equity"] = debt_data[0] / equity_data[0]
        result["data_quality_score"] += 10
        if verbose:
            print(f"  Debt/Equity: {result['debt_to_equity']:.2f}", file=sys.stderr)

    cash_data = _get_concept_value_at_date(facts, CONCEPT_MAPPING["cash"], target_dt)
    if cash_data:
        result["cash"] = cash_data[0]
        result["data_quality_score"] += 5

    shares_data = _get_concept_value_at_date(facts, CONCEPT_MAPPING["shares_outstanding"], target_dt)
    if shares_data:
        result["shares_outstanding"] = shares_data[0]
        if ttm_ni and shares_data[0] > 0:
            result["ttm_eps"] = ttm_ni[0] / shares_data[0]
            result["data_quality_score"] += 5

    if verbose:
        print(f"  Final data quality score: {result['data_quality_score']}", file=sys.stderr)

    return result


# CLI test with verbose mode
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python edgar_fundamentals.py <TICKER> <YYYY-MM-DD>")
        print("Example: python edgar_fundamentals.py AAPL 2018-06-15")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    date_str = sys.argv[2]
    test_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    print(f"Fetching {ticker} fundamentals as of {date_str}...", file=sys.stderr)
    result = get_fundamentals_at_date(ticker, test_date, verbose=True)
    print()
    print(json.dumps(result, indent=2, default=str))
