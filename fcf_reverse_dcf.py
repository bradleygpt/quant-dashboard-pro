"""
fcf_reverse_dcf.py — Layer 2 core: REVERSE DCF (implied-growth) + SBC-sensitivity.
Version 0.1.0 (2026-06-20)

Instead of assuming a growth rate and emitting a fragile IV (Layer-3 forward DCF), we SOLVE for
the near-term FCF growth the CURRENT PRICE embeds — under reported FCF vs SBC-expensed (true) FCF.
The SIGNAL is the SBC-SENSITIVITY: how much higher the required growth becomes once SBC is real.
A big jump (or "no growth justifies the price" once true FCF is used) = the market is paying for a
number that's heavily flattered. This needs NO growth assumption (the weakest DCF input) and is
backtestable point-in-time: rank by implied-growth (or its SBC-jump), form portfolios, measure
forward returns. WACC + terminal growth are the remaining assumptions (kept explicit/overridable).

Pure math (implied_growth) isolated from any fetch, per the QD78 integration seam.
"""
from __future__ import annotations

VERSION = "0.1.0"
WACC_DEFAULT = 0.09      # flat for the prototype; Layer-2.1 = CAPM per-name (beta), overridable
G_TERMINAL = 0.025       # perpetuity growth
STAGE1_YEARS = 10


def two_stage_value(fcf0_ps: float, g: float, wacc: float, g_term: float = G_TERMINAL, n: int = STAGE1_YEARS) -> float:
    """PV/share of a 2-stage FCF stream: n years at g, then perpetuity at g_term. Monotonic in g."""
    pv, f = 0.0, fcf0_ps
    for t in range(1, n + 1):
        f *= (1 + g)
        pv += f / (1 + wacc) ** t
    tv = f * (1 + g_term) / (wacc - g_term)   # g_term < wacc enforced by caller
    return pv + tv / (1 + wacc) ** n


def implied_growth(price: float | None, fcf0_ps: float | None, wacc: float = WACC_DEFAULT,
                   g_term: float = G_TERMINAL, n: int = STAGE1_YEARS) -> dict:
    """Solve for the stage-1 growth the price embeds. Returns {growth, status}.
    status: 'solved' | 'priced_below_model' (even -50% growth overshoots -> cheap) |
            'priced_beyond_model' (even +100% growth can't reach -> priced for more than the model spans) |
            'no_positive_fcf' (true FCF <= 0 -> no finite growth justifies a positive price)."""
    if price is None or fcf0_ps is None or wacc <= g_term:
        return {"growth": None, "status": "bad_inputs"}
    if fcf0_ps <= 0:
        return {"growth": None, "status": "no_positive_fcf"}
    lo, hi = -0.50, 1.00
    if two_stage_value(fcf0_ps, lo, wacc, g_term, n) > price:
        return {"growth": lo, "status": "priced_below_model"}
    if two_stage_value(fcf0_ps, hi, wacc, g_term, n) < price:
        return {"growth": hi, "status": "priced_beyond_model"}
    for _ in range(64):
        mid = (lo + hi) / 2
        if two_stage_value(fcf0_ps, mid, wacc, g_term, n) < price:
            lo = mid
        else:
            hi = mid
    return {"growth": round((lo + hi) / 2, 4), "status": "solved"}


def sbc_sensitivity(price, shares, fcf_reported, fcf_true, wacc=WACC_DEFAULT, g_term=G_TERMINAL, n=STAGE1_YEARS) -> dict:
    """Implied growth under reported vs true (SBC-expensed) FCF, and the SBC-jump between them."""
    if not (price and shares):
        return {"status": "missing_price_shares"}
    rep = implied_growth(price, (fcf_reported / shares) if fcf_reported is not None else None, wacc, g_term, n)
    tru = implied_growth(price, (fcf_true / shares) if fcf_true is not None else None, wacc, g_term, n)
    jump = (None if (rep["growth"] is None or tru["growth"] is None) else round(tru["growth"] - rep["growth"], 4))
    return {"implied_g_reported": rep["growth"], "status_reported": rep["status"],
            "implied_g_true": tru["growth"], "status_true": tru["status"],
            "sbc_growth_jump": jump, "wacc": wacc, "g_terminal": g_term, "stage1_years": n, "version": VERSION}
