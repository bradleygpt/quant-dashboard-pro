"""
Patch app.py:
  1. Add WEIGHT_PRESETS, DEFAULT_PRESET to imports from config
  2. Import breadth_indicator module
  3. Add preset selector in sidebar above pillar sliders (with backtest stats display)
  4. Sliders disabled when preset != "Custom"
  5. Add breadth indicator display above Stock Screener metrics row

Run from quant-dashboard-pro/ root.
Creates app.py.bak as backup.
"""

from pathlib import Path
import shutil

TARGET = Path("./app.py")

# ============================================================
# PATCH 1: Add imports
# ============================================================
IMPORT_OLD = """from config import (
DEFAULT_PILLAR_WEIGHTS, PILLAR_METRICS, GRADE_COLORS, RATING_COLORS,
GRADE_SCORES, DEFAULT_MARKET_CAP_FLOOR_B, MIN_MARKET_CAP_FLOOR_B, MAX_MARKET_CAP_FLOOR_B,
)"""

IMPORT_NEW = """from config import (
DEFAULT_PILLAR_WEIGHTS, PILLAR_METRICS, GRADE_COLORS, RATING_COLORS,
GRADE_SCORES, DEFAULT_MARKET_CAP_FLOOR_B, MIN_MARKET_CAP_FLOOR_B, MAX_MARKET_CAP_FLOOR_B,
WEIGHT_PRESETS, DEFAULT_PRESET,
)
from breadth_indicator import compute_breadth_indicator, format_breadth_indicator"""

# ============================================================
# PATCH 2: Session state init - add preset_name
# ============================================================
SESSION_OLD = '("weights",DEFAULT_PILLAR_WEIGHTS.copy()),'
SESSION_NEW = '("weights",DEFAULT_PILLAR_WEIGHTS.copy()),("preset_name",DEFAULT_PRESET),'

# ============================================================
# PATCH 3: Sidebar weight section - add preset selector above sliders
# ============================================================
SIDEBAR_OLD = """st.markdown("### Pillar Weights")
w_val=st.slider("Valuation",0.0,1.0,st.session_state.weights["Valuation"],0.05,key="w_val")
w_gro=st.slider("Growth",0.0,1.0,st.session_state.weights["Growth"],0.05,key="w_gro")
w_pro=st.slider("Profitability",0.0,1.0,st.session_state.weights["Profitability"],0.05,key="w_pro")
w_mom=st.slider("Momentum",0.0,1.0,st.session_state.weights["Momentum"],0.05,key="w_mom")
w_eps=st.slider("EPS Revisions",0.0,1.0,st.session_state.weights["EPS Revisions"],0.05,key="w_eps")
tw=w_val+w_gro+w_pro+w_mom+w_eps
if tw>0: st.session_state.weights={"Valuation":w_val/tw,"Growth":w_gro/tw,"Profitability":w_pro/tw,"Momentum":w_mom/tw,"EPS Revisions":w_eps/tw}"""

SIDEBAR_NEW = """st.markdown("### Pillar Weights")
# Preset selector — backtested 1996-2026 on TOP25 1Q-reselect strategy
_preset_options = list(WEIGHT_PRESETS.keys()) + ["Custom"]
_preset_labels = {k: WEIGHT_PRESETS[k]["label"] for k in WEIGHT_PRESETS}
_preset_labels["Custom"] = "Custom (manual sliders)"
_current_preset = st.session_state.get("preset_name", DEFAULT_PRESET)
if _current_preset not in _preset_options:
    _current_preset = DEFAULT_PRESET
_selected_preset = st.selectbox(
    "Weight Preset",
    _preset_options,
    index=_preset_options.index(_current_preset),
    format_func=lambda k: _preset_labels.get(k, k),
    key="sb_preset",
    help="Backtested 1996-2026, TOP25 1Q-reselect. m_heavy = highest CAGR. v_heavy = highest Sharpe. equal = legacy."
)
if _selected_preset != "Custom":
    _p = WEIGHT_PRESETS[_selected_preset]
    st.session_state.weights = _p["weights"].copy()
    st.session_state.preset_name = _selected_preset
    st.caption(
        f"📈 Backtest: **{_p['backtest_cagr']:+.2f}%/yr CAGR** · "
        f"Sharpe **{_p['backtest_sharpe']:+.2f}** · "
        f"MaxDD **{_p['backtest_max_dd']:+.2f}%**"
    )
else:
    st.session_state.preset_name = "Custom"
_locked = (_selected_preset != "Custom")
w_val=st.slider("Valuation",0.0,1.0,st.session_state.weights["Valuation"],0.05,key="w_val",disabled=_locked)
w_gro=st.slider("Growth",0.0,1.0,st.session_state.weights["Growth"],0.05,key="w_gro",disabled=_locked)
w_pro=st.slider("Profitability",0.0,1.0,st.session_state.weights["Profitability"],0.05,key="w_pro",disabled=_locked)
w_mom=st.slider("Momentum",0.0,1.0,st.session_state.weights["Momentum"],0.05,key="w_mom",disabled=_locked)
w_eps=st.slider("EPS Revisions",0.0,1.0,st.session_state.weights["EPS Revisions"],0.05,key="w_eps",disabled=_locked)
if _selected_preset == "Custom":
    tw=w_val+w_gro+w_pro+w_mom+w_eps
    if tw>0: st.session_state.weights={"Valuation":w_val/tw,"Growth":w_gro/tw,"Profitability":w_pro/tw,"Momentum":w_mom/tw,"EPS Revisions":w_eps/tw}"""

# ============================================================
# PATCH 4: Breadth indicator in Screener tab
# ============================================================
SCREENER_OLD = """# ═══ Stock Screener ═══
st.markdown("---")
st.markdown("#### Stock Screener")
st.caption("Browse and filter the scored universe.")"""

SCREENER_NEW = """# ═══ Stock Screener ═══
st.markdown("---")
st.markdown("#### Stock Screener")
st.caption("Browse and filter the scored universe.")
# Breadth indicator — count of stocks above absolute quality threshold for the active preset
try:
    _breadth = compute_breadth_indicator(scored_df, st.session_state.get("preset_name", DEFAULT_PRESET))
    _breadth_text = format_breadth_indicator(_breadth)
    _signal = _breadth.get("signal", "normal")
    if _signal == "broad":
        st.success(_breadth_text)
    elif _signal == "thin":
        st.warning(_breadth_text)
    else:
        st.info(_breadth_text)
except Exception as _bi_err:
    st.caption(f"Breadth indicator unavailable: {_bi_err}")"""


def apply_patch(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new.split("\n")[0].strip() in text and old not in text:
        # Already patched — first line of new content is present
        print(f"  [{label}] already patched, skipping")
        return text, False
    if old not in text:
        print(f"  [{label}] ERROR: anchor not found")
        return text, False
    new_text = text.replace(old, new, 1)
    print(f"  [{label}] applied")
    return new_text, True


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from quant-dashboard-pro/ root.")
        return 1

    text = TARGET.read_text(encoding="utf-8")
    backup = Path("app.py.bak")
    shutil.copy(TARGET, backup)
    print(f"Backup: {backup}")
    print()

    applied_count = 0
    text, ok = apply_patch(text, IMPORT_OLD, IMPORT_NEW, "1. imports")
    applied_count += int(ok)
    text, ok = apply_patch(text, SESSION_OLD, SESSION_NEW, "2. session state")
    applied_count += int(ok)
    text, ok = apply_patch(text, SIDEBAR_OLD, SIDEBAR_NEW, "3. sidebar preset selector")
    applied_count += int(ok)
    text, ok = apply_patch(text, SCREENER_OLD, SCREENER_NEW, "4. screener breadth indicator")
    applied_count += int(ok)

    if applied_count == 0:
        print("\nNothing changed. Either fully patched or anchors missed.")
        return 1

    TARGET.write_text(text, encoding="utf-8")
    print(f"\nWrote {TARGET} with {applied_count} patches applied.")
    print("\nNext: streamlit run app.py")
    print("  - Sidebar should show 'Weight Preset' dropdown above pillar sliders")
    print("  - Default selection: m_heavy")
    print("  - Sliders locked when preset != Custom")
    print("  - Screener tab should show breadth indicator above the metrics row")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
