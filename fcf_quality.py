"""
fcf_quality.py — Quality-of-FCF distortion engine (Layer 1).
Version: 0.1.0  (2026-06-20)

NORTH STAR = the DISTORTION SCREEN (how much reported FCF overstates true FCF), not a
valuation/DCF engine. Per the agreed design:
  - Built on EDGAR XBRL (point-in-time, as-reported) via edgar_fundamentals — NOT yfinance,
    whose restated financials would inject look-ahead and whose cash-flow line items are patchy.
  - SBC is EXPENSED (true FCF = OCF - capex - SBC), not dilution-modelled: for buyback-heavy
    names net dilution ~0 understates the cost, so expensing is the honest treatment.
  - Hard rule: MISSING input -> NA, never 0 (and clears `fully_adjusted_complete`); an
    adjustment that legitimately does not apply -> 0. Signs are explicit per adjustment.
  - Layer-1 scope: SBC (core) + cash-tax normalisation (Tier-1). Working-capital normalisation
    and capitalized-dev are Tier-1 *hooks* — not auto-estimated in v1 (data is too patchy to
    guess); they report status "not_attempted" rather than a fake 0.

The PURE math (compute_distortion) is isolated from the EDGAR/price fetch and the universe loop
so the core can be called straight from QD78's pipeline later (the way FV/QBP columns are).
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime

VERSION = "0.1.0"

# ── Parameters (top-level, overridable per-ticker later via a CSV) ───────────────────────────
NORMALIZED_TAX_RATE = 0.21   # US statutory; cash tax running below this is treated as a non-repeatable benefit

# EDGAR us-gaap concept tags for the cash-flow items (flow concepts -> TTM sums). Kept LOCAL so we
# don't mutate the shared edgar_fundamentals.CONCEPT_MAPPING used by the bake.
TAGS = {
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets", "PaymentsForCapitalImprovements"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense",
            "ShareBasedCompensationExpense"],
    "cash_taxes": ["IncomeTaxesPaidNet", "IncomeTaxesPaid"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
}

FINANCIAL_SECTORS = {"Financial Services", "Financials", "Real Estate", "REIT"}


# ── PURE MATH ────────────────────────────────────────────────────────────────────────────────
@dataclass
class Inputs:
    ticker: str
    sector: str | None = None
    price: float | None = None
    shares: float | None = None
    market_cap: float | None = None
    total_debt: float | None = None
    cash: float | None = None
    # TTM cash-flow line items ($):
    ocf: float | None = None
    capex: float | None = None
    sbc: float | None = None
    cash_taxes: float | None = None
    pretax_income: float | None = None
    asof: str | None = None


def _cash_tax_adjustment(pretax, cash_taxes, rate=NORMALIZED_TAX_RATE):
    """Returns (adj_$, status). adj is NEGATIVE (subtract the non-repeatable benefit) when cash
    tax is running below the normalized rate; 0 when it legitimately doesn't apply; None if data missing."""
    if pretax is None or cash_taxes is None:
        return None, "missing"
    if pretax <= 0:
        return 0.0, "n/a (pretax<=0)"
    benefit = rate * pretax - cash_taxes  # >0 means cash tax below normal -> FCF flattered
    if benefit <= 0:
        return 0.0, "cash tax >= normal"
    return -benefit, "normalized"


def compute_distortion(inp: Inputs, tax_rate: float = NORMALIZED_TAX_RATE) -> dict:
    """PURE: fundamentals dict -> distortion row. No I/O. NA-never-0. Explicit signs."""
    mc = inp.market_cap
    # --- FCF tracks ---
    fcf_reported = (inp.ocf - inp.capex) if (inp.ocf is not None and inp.capex is not None) else None
    adj_sbc = (-inp.sbc) if inp.sbc is not None else None                 # subtract SBC (the real cost)
    fcf_sbc_expensed = (fcf_reported + adj_sbc) if (fcf_reported is not None and adj_sbc is not None) else None

    # Cash-tax normalisation: COMPUTED but demoted to a FLAG in v1. The EDGAR cash-tax tags
    # (IncomeTaxesPaidNet) are inconsistently period-matched across filers — META reads $2B cash
    # tax on $82B pretax (a spurious 2.5% -> a fake $15B "benefit") while AAPL reads a clean 21% —
    # and a flat-21% normal over-adjusts structurally-low payers. SBC is the clean v1 adjustment;
    # cash-tax returns in v1.1 with period validation + a smarter normal rate.
    eff_cash_rate = (inp.cash_taxes / inp.pretax_income) if (inp.cash_taxes is not None and inp.pretax_income not in (None, 0) and inp.pretax_income > 0) else None
    cash_tax_below_normal = bool(eff_cash_rate is not None and eff_cash_rate < tax_rate)

    # v1 fully_adjusted = SBC only (the defensible core). WC + capitalized-dev + cash-tax are
    # NOT applied (NA hooks / flag), so this never silently reads a missing input as 0.
    adjustments = {"adj_sbc": adj_sbc}
    not_attempted = ["adj_working_capital", "adj_capitalized_dev", "adj_cash_tax (flagged not applied — see cash_tax_*)"]
    complete = fcf_reported is not None and adj_sbc is not None
    applied = [v for v in adjustments.values() if v is not None]
    fcf_fully_adjusted = (fcf_reported + sum(applied)) if (fcf_reported is not None and applied) else None

    def frac(x, d):
        return round(x / d, 4) if (x is not None and d not in (None, 0)) else None

    total_distortion_usd = (fcf_reported - fcf_fully_adjusted) if (fcf_reported is not None and fcf_fully_adjusted is not None) else None
    # per-adjustment contribution fractions (which adjustment drives the distortion)
    denom = sum(abs(v) for v in applied) or None
    contrib = {k: (round(abs(v) / denom, 3) if (v is not None and denom) else None) for k, v in adjustments.items()}

    # applicability gating — emit the row regardless, flag why it's unreliable
    reasons = []
    if (inp.sector or "") in FINANCIAL_SECTORS:
        reasons.append("financial/REIT — FCFF framing N/A")
    if fcf_fully_adjusted is not None and fcf_fully_adjusted <= 0:
        reasons.append("adjusted FCF <= 0")
    if inp.price is None or inp.shares is None:
        reasons.append("missing price/shares")
    applicable = not reasons

    return {
        "ticker": inp.ticker, "sector": inp.sector, "asof": inp.asof,
        "price": inp.price, "shares": inp.shares, "market_cap": mc,
        # FCF tracks
        "fcf_reported": fcf_reported, "fcf_sbc_expensed": fcf_sbc_expensed, "fcf_fully_adjusted": fcf_fully_adjusted,
        # per-adjustment deltas ($) + signs explicit
        "adj_sbc": adj_sbc,
        "adj_working_capital": None, "adj_capitalized_dev": None, "tier1_not_attempted": not_attempted,
        # cash-tax: flagged, NOT applied in v1 (data-quality — see note above)
        "cash_tax_effective_rate": (round(eff_cash_rate, 3) if eff_cash_rate is not None else None),
        "cash_tax_below_normal": cash_tax_below_normal,
        "cash_tax_note": "computed but not applied in v1 — EDGAR cash-tax tags unreliable",
        # distortion — STABLE denominators (mktcap), not %-of-reported as the sort key
        "sbc": inp.sbc,
        "sbc_pct_ocf": frac(inp.sbc, inp.ocf),
        "sbc_pct_mktcap": frac(inp.sbc, mc),
        "total_distortion_usd": total_distortion_usd,
        "total_distortion_pct_mktcap": frac(total_distortion_usd, mc),
        "total_distortion_pct_reported": (round(total_distortion_usd / abs(fcf_reported), 3)
                                          if (total_distortion_usd is not None and fcf_reported not in (None, 0)) else None),
        "distortion_contribution": contrib,
        # yields / multiples (contrast)
        "reported_fcf_yield": frac(fcf_reported, mc),
        "true_fcf_yield": frac(fcf_fully_adjusted, mc),
        # flags
        "applicable": applicable, "exclude_reason": "; ".join(reasons) or None,
        "fully_adjusted_complete": complete, "version": VERSION,
    }
