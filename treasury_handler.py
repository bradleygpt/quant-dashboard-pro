"""
Treasury Holdings Handler.

Detects and processes US Treasury securities (T-bills, T-notes, T-bonds) from
Fidelity CSV exports. Treasury CUSIPs follow the pattern: starts with 91, total
9 characters, alphanumeric.

Holdings schema for Treasuries:
{
  "ticker": str,        # CUSIP (e.g., "91282CMN8")
  "shares": float,      # Quantity (face value units)
  "cost_basis": float,  # Avg cost basis per unit
  "type": "treasury",   # Distinguishes from stock entries
  "current_value": float,  # Current market value (manual update)
  "description": str,   # e.g., "UNITED STATES TREAS SER AK-2028 4.250% Feb-15-2028"
}

Stock entries lack the "type" field (defaults to stock) or have type="stock".
"""

from __future__ import annotations
import re
import csv
import io
from typing import Optional

# US Treasury CUSIP pattern: starts with 91, 9 chars total, alphanumeric.
# Examples: 91282CMN8 (T-Note 2028), 912828YK0, 9128286Z8
TREASURY_CUSIP_PATTERN = re.compile(r"^91[0-9A-Z]{7}$")


def is_treasury_cusip(symbol: str) -> bool:
    """Return True if the symbol matches the US Treasury CUSIP format."""
    if not symbol:
        return False
    return bool(TREASURY_CUSIP_PATTERN.match(symbol.strip().upper()))


def _parse_money(value: str) -> Optional[float]:
    """Parse a money string like '$7,042.14' or '+$51.92' or '--' to float."""
    if value is None:
        return None
    s = str(value).strip().replace("$", "").replace(",", "").replace("+", "")
    if s in ("", "--", "n/a", "N/A", "None"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_number(value: str) -> Optional[float]:
    """Parse a plain number string like '7,000' or '100.602' to float."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s in ("", "--", "n/a", "N/A", "None"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_treasury_row(row: dict) -> Optional[dict]:
    """Parse a Fidelity CSV row representing a Treasury security.

    Expected column names (Fidelity export format, case-insensitive matching):
      - Symbol / Account
      - Description
      - Quantity
      - Average Cost Basis (or Avg Cost Basis)
      - Current Value
      - Cost Basis Total

    Returns dict with the Treasury schema, or None if parsing fails or this
    row isn't a Treasury.
    """
    # Lookup keys are case-insensitive
    lc_row = {k.lower().strip(): v for k, v in row.items()}

    symbol = lc_row.get("symbol") or lc_row.get("account") or ""
    symbol = str(symbol).strip().upper()

    if not is_treasury_cusip(symbol):
        return None

    qty = _parse_number(lc_row.get("quantity"))
    if qty is None or qty <= 0:
        return None

    # Cost basis can be in either "Average Cost Basis" or "Avg Cost Basis"
    cost_basis = (
        _parse_money(lc_row.get("average cost basis"))
        or _parse_money(lc_row.get("avg cost basis"))
        or _parse_money(lc_row.get("cost basis per share"))
    )

    current_value = (
        _parse_money(lc_row.get("current value"))
        or _parse_money(lc_row.get("market value"))
        or _parse_money(lc_row.get("value"))
    )

    description = (
        lc_row.get("description")
        or lc_row.get("security description")
        or ""
    )
    description = str(description).strip()

    # If we don't have a current value, fall back to qty * cost_basis (cost basis total)
    if current_value is None and cost_basis is not None:
        current_value = qty * cost_basis

    if current_value is None:
        return None

    return {
        "ticker": symbol,
        "shares": qty,
        "cost_basis": cost_basis,
        "type": "treasury",
        "current_value": float(current_value),
        "description": description,
    }


def parse_fidelity_csv_with_treasuries(csv_text: str, stock_parser):
    """Parse a Fidelity CSV, splitting Treasury rows out from stock rows.

    Args:
        csv_text: Raw CSV text from Fidelity export.
        stock_parser: The existing parse_fidelity_csv function from portfolio.py.
                      Called with a CSV string containing only non-Treasury rows.

    Returns:
        List of holding dicts. Treasury entries have type="treasury".
        Stock entries are returned exactly as the existing stock_parser produces them.
    """
    if not csv_text:
        return []

    # Find the header line (Fidelity CSVs sometimes have notes before the header)
    lines = csv_text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        lower = line.lower()
        if "symbol" in lower and ("quantity" in lower or "shares" in lower):
            header_idx = i
            break
        if "account" in lower and "symbol" in lower:
            header_idx = i
            break

    if header_idx is None:
        # Couldn't find a header; defer entirely to the stock parser
        return stock_parser(csv_text)

    # Build a DictReader from the header onward
    csv_body = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(csv_body))

    treasury_holdings = []
    non_treasury_rows = []
    header_line = lines[header_idx]
    non_treasury_rows.append(header_line)

    for row in reader:
        symbol = (
            row.get("Symbol")
            or row.get("symbol")
            or row.get("Account")
            or row.get("account")
            or ""
        )
        symbol = str(symbol).strip().upper()

        if is_treasury_cusip(symbol):
            parsed = parse_treasury_row(row)
            if parsed:
                treasury_holdings.append(parsed)
        else:
            # Reassemble this row as a CSV line for the stock parser
            row_values = [row.get(col, "") or "" for col in reader.fieldnames]
            row_line = ",".join(
                f'"{str(v).replace(chr(34), chr(34) + chr(34))}"' if "," in str(v) else str(v)
                for v in row_values
            )
            non_treasury_rows.append(row_line)

    # Run the existing stock parser on the non-Treasury rows
    stock_csv = "\n".join(lines[:header_idx] + non_treasury_rows)
    stock_holdings = stock_parser(stock_csv) or []

    # Tag stocks explicitly so downstream code can distinguish
    for h in stock_holdings:
        if "type" not in h:
            h["type"] = "stock"

    return stock_holdings + treasury_holdings


def split_holdings(holdings: list) -> tuple[list, list]:
    """Split a unified holdings list into (stocks, treasuries)."""
    stocks = []
    treasuries = []
    for h in holdings:
        if h.get("type") == "treasury":
            treasuries.append(h)
        else:
            stocks.append(h)
    return stocks, treasuries


def compute_treasury_total(treasuries: list) -> float:
    """Sum the current value of all Treasury holdings."""
    total = 0.0
    for t in treasuries:
        cv = t.get("current_value")
        if cv is not None:
            try:
                total += float(cv)
            except (TypeError, ValueError):
                continue
    return total


def compute_treasury_cost_basis_total(treasuries: list) -> float:
    """Sum cost basis (qty * cost_basis) across all Treasury holdings."""
    total = 0.0
    for t in treasuries:
        qty = t.get("shares")
        cb = t.get("cost_basis")
        if qty is not None and cb is not None:
            try:
                total += float(qty) * float(cb)
            except (TypeError, ValueError):
                continue
    return total


def format_treasury_description(description: str) -> tuple[str, str]:
    """Extract coupon rate and maturity date from a Treasury description.

    Example input: "UNITED STATES TREAS SER AK-2028 4.25000% 02/15/2028 NTS Feb-15-2028"
    Returns: (coupon_str, maturity_str), e.g. ("4.250%", "Feb-15-2028")
    """
    coupon = ""
    maturity = ""

    if not description:
        return coupon, maturity

    # Coupon: looks like "4.25000%" or "4.250%"
    coupon_match = re.search(r"(\d+\.\d+)\s*%", description)
    if coupon_match:
        coupon = f"{float(coupon_match.group(1)):.3f}%".rstrip("0").rstrip(".") + "%"
        if not coupon.endswith("%"):
            coupon = coupon + "%"

    # Maturity: prefer "Mon-DD-YYYY" pattern if present, else "MM/DD/YYYY"
    mat_match = re.search(r"([A-Z][a-z]{2}-\d{2}-\d{4})", description)
    if mat_match:
        maturity = mat_match.group(1)
    else:
        mat_match2 = re.search(r"(\d{2}/\d{2}/\d{4})", description)
        if mat_match2:
            maturity = mat_match2.group(1)

    return coupon, maturity
