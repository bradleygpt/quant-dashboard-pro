"""
Patch config.py: Add WEIGHT_PRESETS for the two validated production candidates,
update DEFAULT_PILLAR_WEIGHTS to m_heavy (highest backtested CAGR), and add
ABSOLUTE_THRESHOLD constants for the breadth indicator.

Run from quant-dashboard-pro/ root.
"""

from pathlib import Path
import shutil

TARGET = Path("./config.py")

OLD = """DEFAULT_PILLAR_WEIGHTS = {
    "Valuation": 0.20,
    "Growth": 0.20,
    "Profitability": 0.20,
    "Momentum": 0.20,
    "EPS Revisions": 0.20,
}"""

NEW = """# ── Pillar Weight Presets ──────────────────────────────────────────
# Backtested across 1996-2026 (121 quarterly rebalances, TOP25 selection,
# 1Q hold-and-reselect). 5-pillar dashboard tests on 4 pillars (V/G/P/M)
# because EPS Revisions history pre-2010 is unreliable. New presets set
# EPS Revisions to 0% - honest about what was tested.
#
#   m_heavy: V=0.05 G=0.15 P=0.00 M=0.80  → +30.12% CAGR  Sharpe 1.30
#   v_heavy: V=0.45 G=0.10 P=0.25 M=0.20  → +28.18% CAGR  Sharpe 1.35
#   equal:   each pillar 20%               → +26.27% CAGR  Sharpe 1.21

WEIGHT_PRESETS = {
    "m_heavy": {
        "label": "Growth/Momentum (highest CAGR)",
        "weights": {
            "Valuation": 0.05,
            "Growth": 0.15,
            "Profitability": 0.00,
            "Momentum": 0.80,
            "EPS Revisions": 0.00,
        },
        "backtest_cagr": 30.12,
        "backtest_sharpe": 1.30,
        "backtest_max_dd": -32.04,
    },
    "v_heavy": {
        "label": "Value/Quality (highest Sharpe)",
        "weights": {
            "Valuation": 0.45,
            "Growth": 0.10,
            "Profitability": 0.25,
            "Momentum": 0.20,
            "EPS Revisions": 0.00,
        },
        "backtest_cagr": 28.18,
        "backtest_sharpe": 1.35,
        "backtest_max_dd": -37.39,
    },
    "equal": {
        "label": "Equal weight (legacy)",
        "weights": {
            "Valuation": 0.20,
            "Growth": 0.20,
            "Profitability": 0.20,
            "Momentum": 0.20,
            "EPS Revisions": 0.20,
        },
        "backtest_cagr": 26.27,
        "backtest_sharpe": 1.21,
        "backtest_max_dd": -35.67,
    },
}

DEFAULT_PRESET = "m_heavy"
DEFAULT_PILLAR_WEIGHTS = WEIGHT_PRESETS[DEFAULT_PRESET]["weights"]

# ── Absolute Threshold Breadth Indicator ──────────────────────────
# Median quarterly TOP25 cutoff composite score across 1996-2026 history.
# When the count of stocks above this threshold contracts, market breadth
# is thinning. When it expands, breadth is broadening. Display in screener.
#
# Per-scheme thresholds (derived from backtest):
#   m_heavy: 10.617 (count median 153, range 35-246)
#   v_heavy:  8.723 (count median  25, range  0-76)

ABSOLUTE_THRESHOLDS = {
    "m_heavy": 10.617,
    "v_heavy": 8.723,
    "equal":    8.5,  # approximate, untested - placeholder for legacy
}

ABSOLUTE_THRESHOLD_STATS = {
    "m_heavy": {"median_count": 153, "min_count": 35, "max_count": 246, "mean_count": 156.2},
    "v_heavy": {"median_count": 25,  "min_count": 0,  "max_count": 76,  "mean_count": 28.9},
    "equal":   {"median_count": None, "min_count": None, "max_count": None, "mean_count": None},
}"""


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from quant-dashboard-pro/ root.")
        return 1
    text = TARGET.read_text(encoding="utf-8")
    if "WEIGHT_PRESETS" in text:
        print("Already patched.")
        return 0
    if OLD not in text:
        print("ERROR: target DEFAULT_PILLAR_WEIGHTS block not found")
        print("Expected:")
        print(OLD[:200])
        return 1
    backup = Path("config.py.bak")
    shutil.copy(TARGET, backup)
    text = text.replace(OLD, NEW)
    TARGET.write_text(text, encoding="utf-8")
    print(f"Patched. Backup: {backup}")
    print()
    print("Added:")
    print("  - WEIGHT_PRESETS dict with m_heavy / v_heavy / equal")
    print("  - DEFAULT_PRESET = 'm_heavy'")
    print("  - DEFAULT_PILLAR_WEIGHTS now points to m_heavy preset")
    print("  - ABSOLUTE_THRESHOLDS dict for breadth indicator")
    print("  - ABSOLUTE_THRESHOLD_STATS for historical context")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
