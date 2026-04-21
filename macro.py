"""
Macroeconomics Dashboard module.
Composite macro model for S&P 500 earnings forecasting using three inputs:
  1. CPI (inflation) - price channel
  2. Unemployment Rate - volume/demand channel
  3. ISM Composite - breadth/sentiment channel

Based on research from:
- BMO ETFs: "How to Forecast S&P 500 Earnings Using Macro Inputs" (Jan 2026)
- Federal Reserve FEDS 2024-049: Sharpe & Gil de Rubio Cruz (June 2024)
- Schwab 2026 Outlook: K-shaped economy, instability framework

Also includes: yield curve, Fed Funds rate tracker, key economic releases.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime


# ── Latest Macro Data (update manually or via FRED API) ────────────
# These need periodic manual updates until we add FRED API integration.
# Source: BLS, ISM, Federal Reserve

MACRO_DATA = {
    "last_updated": "2026-04-20",

    # CPI YoY % (BLS, latest release)
    "cpi_current": 2.4,
    "cpi_prior": 2.8,
    "cpi_trend": "falling",

    # Unemployment Rate % (BLS, latest release)
    "unemployment_current": 4.2,
    "unemployment_prior": 4.1,
    "unemployment_trend": "stable",

    # ISM Composite (weighted mfg + services by GDP share)
    # Mfg ~11% of GDP, Services ~89%
    "ism_manufacturing": 49.0,
    "ism_services": 54.4,
    "ism_composite": 53.8,  # 0.11*mfg + 0.89*svc
    "ism_trend": "expanding",

    # Fed Funds Rate
    "fed_funds_upper": 4.50,
    "fed_funds_lower": 4.25,
    "fed_next_meeting": "2026-05-06",
    "fed_dots_year_end": 3.75,

    # GDP
    "gdp_latest_qoq_annualized": 2.4,
    "gdp_quarter": "Q4 2025",

    # US 10Y and 2Y yields (fetched live)
    # Yield curve inversion = recession signal

    # Buffett Indicator (market cap / GDP)
    "us_gdp_trillions": 29.7,
}


def get_macro_summary() -> dict:
    """Return current macro data with interpretations."""
    d = MACRO_DATA.copy()

    # Compute BMO-style earnings forecast
    earnings = compute_earnings_forecast(
        cpi=d["cpi_current"],
        unemployment=d["unemployment_current"],
        ism=d["ism_composite"],
    )
    d["earnings_forecast"] = earnings

    # Macro health score (0-100)
    health = compute_macro_health(d)
    d["health_score"] = health

    return d


def compute_earnings_forecast(
    cpi: float,
    unemployment: float,
    ism: float,
    cpi_baseline: float = 2.7,
    unemp_baseline: float = 4.4,
    ism_baseline: float = 53.8,
) -> dict:
    """
    BMO-style 3-factor earnings growth model.
    Uses YoY changes in CPI, unemployment, ISM to forecast S&P 500 earnings growth.

    Model: E(growth) = intercept + b1*(CPI change) + b2*(Unemp change) + b3*(ISM change)

    Coefficients calibrated from historical relationships:
    - CPI: +2.5x (higher inflation -> higher nominal earnings, pro-cyclical)
    - Unemployment: -4.0x (higher unemployment -> lower earnings, counter-cyclical)
    - ISM: +0.8x (higher ISM -> broader expansion -> higher earnings)
    - Intercept: ~8% (base trend growth from productivity + buybacks)

    These are approximate coefficients. A proper calibration would use
    quarterly data from 1993-2025.
    """
    # Changes from baseline (current levels)
    cpi_delta = cpi - cpi_baseline
    unemp_delta = unemployment - unemp_baseline
    ism_delta = ism - ism_baseline

    # Model coefficients (approximate, based on BMO framework)
    intercept = 8.0
    b_cpi = 2.5      # Positive: higher inflation -> higher nominal earnings
    b_unemp = -4.0   # Negative: higher unemployment -> lower earnings
    b_ism = 0.8       # Positive: higher ISM -> broader expansion

    base_forecast = intercept + (b_cpi * cpi_delta) + (b_unemp * unemp_delta) + (b_ism * ism_delta)

    # Scenario analysis
    scenarios = {
        "Bull Case": {
            "cpi": cpi + 0.3,
            "unemployment": unemployment - 0.3,
            "ism": ism + 3,
            "description": "Inflation moderate rise, jobs strengthen, ISM expands",
        },
        "Base Case": {
            "cpi": cpi,
            "unemployment": unemployment,
            "ism": ism,
            "description": "Current conditions persist",
        },
        "Bear Case": {
            "cpi": cpi - 0.5,
            "unemployment": unemployment + 1.0,
            "ism": ism - 8,
            "description": "Disinflation, job losses, contraction",
        },
    }

    scenario_results = {}
    for name, s in scenarios.items():
        eg = intercept + b_cpi * (s["cpi"] - cpi_baseline) + b_unemp * (s["unemployment"] - unemp_baseline) + b_ism * (s["ism"] - ism_baseline)
        scenario_results[name] = {
            "earnings_growth": round(eg, 1),
            "cpi": s["cpi"],
            "unemployment": s["unemployment"],
            "ism": s["ism"],
            "description": s["description"],
        }

    # Sector sensitivity (from BMO regression betas)
    sector_sensitivity = {
        "Technology": 2.0,      # High beta to earnings
        "Communication Services": 1.0,
        "Energy": -0.95,        # Counter-cyclical to CPI
        "Basic Materials": 2.1, # High cyclical beta
        "Consumer Cyclical": 1.25,
        "Consumer Defensive": 0.56,
        "Industrials": 0.89,
        "Healthcare": 0.92,
        "Utilities": 0.37,
        "Financial Services": 1.79,
        "Real Estate": 0.32,
    }

    sector_forecasts = {}
    for sector, beta in sector_sensitivity.items():
        sector_eg = base_forecast * beta
        sector_forecasts[sector] = round(sector_eg, 1)

    return {
        "sp500_earnings_growth": round(base_forecast, 1),
        "scenarios": scenario_results,
        "sector_forecasts": sector_forecasts,
        "model_inputs": {
            "cpi": cpi, "unemployment": unemployment, "ism": ism,
            "cpi_delta": round(cpi_delta, 2),
            "unemp_delta": round(unemp_delta, 2),
            "ism_delta": round(ism_delta, 2),
        },
    }


def compute_macro_health(data: dict) -> dict:
    """
    Composite macro health score (0-100).
    Higher = healthier economy = more favorable for equities.

    Components:
    1. ISM Composite (25%) - above 50 = expansion
    2. Unemployment (25%) - lower = healthier
    3. GDP Growth (20%) - higher = healthier
    4. CPI Stability (15%) - 2-3% ideal, too high or too low = bad
    5. Yield Curve (15%) - inverted = recession warning
    """
    components = []

    # ISM: 45=0, 50=40, 55=70, 60=100
    ism = data.get("ism_composite", 50)
    ism_score = max(0, min(100, (ism - 45) * 6.67))
    components.append({"name": "ISM Composite", "score": round(ism_score), "weight": 0.25,
        "value": f"{ism:.1f}", "interpretation": "Expanding" if ism > 50 else "Contracting"})

    # Unemployment: 3.5%=100, 4.5%=60, 5.5%=30, 7%=0
    unemp = data.get("unemployment_current", 4.5)
    unemp_score = max(0, min(100, (7.0 - unemp) / 3.5 * 100))
    components.append({"name": "Unemployment Rate", "score": round(unemp_score), "weight": 0.25,
        "value": f"{unemp:.1f}%", "interpretation": "Healthy" if unemp < 4.5 else "Weakening" if unemp < 5.5 else "Weak"})

    # GDP: 0%=20, 1%=40, 2%=60, 3%=80, 4%=100
    gdp = data.get("gdp_latest_qoq_annualized", 2.0)
    gdp_score = max(0, min(100, gdp * 25))
    components.append({"name": "GDP Growth", "score": round(gdp_score), "weight": 0.20,
        "value": f"{gdp:.1f}%", "interpretation": "Strong" if gdp > 2.5 else "Moderate" if gdp > 1.0 else "Weak"})

    # CPI Stability: ideal 2.0-2.5, penalty for >3.5 or <1.0
    cpi = data.get("cpi_current", 2.5)
    if 2.0 <= cpi <= 2.5:
        cpi_score = 100
    elif 1.5 <= cpi <= 3.0:
        cpi_score = 75
    elif 1.0 <= cpi <= 3.5:
        cpi_score = 50
    else:
        cpi_score = max(0, 50 - abs(cpi - 2.5) * 20)
    components.append({"name": "CPI Stability", "score": round(cpi_score), "weight": 0.15,
        "value": f"{cpi:.1f}%", "interpretation": "On target" if 2 <= cpi <= 2.5 else "Sticky" if cpi > 2.5 else "Deflationary risk"})

    # Yield Curve (live fetch)
    yc = fetch_yield_curve()
    if yc:
        spread = yc.get("spread_10y_2y", 0)
        if spread > 0.5: yc_score = 80
        elif spread > 0: yc_score = 60
        elif spread > -0.5: yc_score = 30
        else: yc_score = 10
        components.append({"name": "Yield Curve (10Y-2Y)", "score": round(yc_score), "weight": 0.15,
            "value": f"{spread:+.2f}%", "interpretation": "Normal" if spread > 0 else "INVERTED"})
    else:
        components.append({"name": "Yield Curve", "score": 50, "weight": 0.15,
            "value": "N/A", "interpretation": "Data unavailable"})

    composite = sum(c["score"] * c["weight"] for c in components)

    if composite >= 75: classification, color = "Strong Expansion", "#00C805"
    elif composite >= 55: classification, color = "Moderate Growth", "#8BC34A"
    elif composite >= 40: classification, color = "Slowing", "#FFC107"
    elif composite >= 25: classification, color = "Contraction Risk", "#FF5722"
    else: classification, color = "Recession", "#D32F2F"

    return {
        "score": round(composite), "classification": classification, "color": color,
        "components": components,
    }


def fetch_yield_curve() -> dict | None:
    """Fetch 10Y and 2Y Treasury yields for yield curve analysis."""
    try:
        tnx = yf.Ticker("^TNX")  # 10-year
        twoyr = yf.Ticker("^IRX")  # 13-week T-bill (2Y not available on yfinance)

        h10 = tnx.history(period="5d")
        h2 = twoyr.history(period="5d")

        if h10.empty or h2.empty:
            return None

        y10 = float(h10["Close"].iloc[-1])
        y2 = float(h2["Close"].iloc[-1])

        return {
            "yield_10y": round(y10, 2),
            "yield_2y": round(y2, 2),  # Actually 13-week, used as proxy
            "spread_10y_2y": round(y10 - y2, 2),
        }
    except Exception:
        return None


def fetch_economic_calendar() -> list[dict]:
    """Return upcoming key economic releases."""
    return [
        {"date": "Weekly", "event": "Initial Jobless Claims", "importance": "High",
         "description": "Weekly new unemployment filings. Rising = weakening labor market."},
        {"date": "Monthly (1st Fri)", "event": "Nonfarm Payrolls / Unemployment", "importance": "Critical",
         "description": "Jobs added and unemployment rate. The single most market-moving release."},
        {"date": "Monthly (10th-14th)", "event": "CPI Report", "importance": "Critical",
         "description": "Consumer Price Index. Key inflation gauge for Fed policy decisions."},
        {"date": "Monthly (1st biz day)", "event": "ISM Manufacturing PMI", "importance": "High",
         "description": "Above 50 = expansion. Leading indicator for industrial sector."},
        {"date": "Monthly (3rd biz day)", "event": "ISM Services PMI", "importance": "High",
         "description": "Services sector health. 89% of GDP. More important than manufacturing."},
        {"date": "Quarterly", "event": "GDP Report", "importance": "High",
         "description": "Advance, second, and final estimates of economic growth."},
        {"date": "6 weeks", "event": "FOMC Rate Decision", "importance": "Critical",
         "description": "Federal Reserve interest rate decision and forward guidance."},
        {"date": "Monthly", "event": "Retail Sales", "importance": "Medium",
         "description": "Consumer spending health. 70% of GDP is consumption."},
        {"date": "Monthly", "event": "PCE Price Index", "importance": "High",
         "description": "Fed's preferred inflation measure. Often released with personal income data."},
        {"date": "Monthly", "event": "Housing Starts / Permits", "importance": "Medium",
         "description": "Leading indicator for construction and related sectors."},
    ]


# ── Fed Rate Probability (simplified) ─────────────────────────────

def get_fed_rate_outlook() -> dict:
    """
    Simplified Fed rate outlook based on current conditions.
    A proper implementation would use CME FedWatch (requires futures data).
    """
    d = MACRO_DATA
    current_rate = d["fed_funds_upper"]
    next_meeting = d["fed_next_meeting"]
    dots = d["fed_dots_year_end"]

    # Simple heuristic based on macro conditions
    cpi = d["cpi_current"]
    unemp = d["unemployment_current"]

    if cpi > 3.0:
        bias = "Hawkish (Hold/Hike)"
        cut_prob = 10
        hold_prob = 70
        hike_prob = 20
    elif cpi > 2.5 and unemp < 4.5:
        bias = "Cautious (Likely Hold)"
        cut_prob = 25
        hold_prob = 65
        hike_prob = 10
    elif cpi < 2.5 and unemp > 4.5:
        bias = "Dovish (Likely Cut)"
        cut_prob = 60
        hold_prob = 35
        hike_prob = 5
    elif cpi < 2.0:
        bias = "Strongly Dovish (Cut Expected)"
        cut_prob = 80
        hold_prob = 18
        hike_prob = 2
    else:
        bias = "Data Dependent"
        cut_prob = 35
        hold_prob = 55
        hike_prob = 10

    return {
        "current_rate": f"{d['fed_funds_lower']:.2f}%-{current_rate:.2f}%",
        "next_meeting": next_meeting,
        "year_end_dots": f"{dots:.2f}%",
        "bias": bias,
        "cut_probability": cut_prob,
        "hold_probability": hold_prob,
        "hike_probability": hike_prob,
        "note": "Probabilities are heuristic estimates. For precise data, use CME FedWatch.",
    }
