"""Ticker -> Markets-Engine anchor mapping (engine-wiring handoff Phase 1, 2026-07-20).

The engine measures SECTOR/MACRO ANCHORS, not single names. This module maps each
scored ticker to its sector's anchor so the Stock Detail entry point can pre-fill
gate-validated queries. The bake calls build_map() and ships ticker_anchor_map.json.

VERIFIED ANCHOR MANIFEST — pulled 2026-07-20 from markets-llm/relational/engine.py
(ANCHORS + SECTOR_LABELS, the config load_anchor_levels() actually loads), NOT from
examples or memory. 22 anchors total: 10 macro + derived 2s10s + 11 sector ETF
proxies. There is NO communication-services anchor (XLC absent; IYR is the
real-estate proxy, longer history than XLRE) — Communication Services therefore
maps to `none` and the UI renders a disabled state. Never send a question the
engine will decline.

`alias` is the DETECTION-GATE-SAFE wording for that anchor, verified against
markets-llm/generation/relational_escalation.py ASSET_MAP (word-boundary,
longest-match). Query templates must use the alias, never the ETF ticker — "SMH"
and "XLK" are NOT in the gate vocabulary; "semiconductors" and "tech stocks" are.

mapping_kind: sector_proxy | industry_proxy | none. Industry overrides are
permitted ONLY for anchors confirmed in the manifest — currently just
semiconductors -> ANCHOR_SMH.
"""

# sector (yfinance taxonomy, as baked) -> (anchor, gate-safe alias, human label)
SECTOR_TO_ANCHOR = {
    "Technology":         ("ANCHOR_XLK", "tech stocks",            "technology (XLK ETF proxy)"),
    "Financial Services": ("ANCHOR_XLF", "financials",             "financials (XLF ETF proxy)"),
    "Healthcare":         ("ANCHOR_XLV", "healthcare",             "healthcare (XLV ETF proxy)"),
    "Consumer Cyclical":  ("ANCHOR_XLY", "consumer discretionary", "consumer discretionary (XLY ETF proxy)"),
    "Consumer Defensive": ("ANCHOR_XLP", "consumer staples",       "consumer staples (XLP ETF proxy)"),
    "Industrials":        ("ANCHOR_XLI", "industrials",            "industrials (XLI ETF proxy)"),
    "Energy":             ("ANCHOR_XLE", "energy stocks",          "energy (XLE ETF proxy)"),
    "Utilities":          ("ANCHOR_XLU", "utilities",              "utilities (XLU ETF proxy)"),
    "Basic Materials":    ("ANCHOR_XLB", "materials",              "materials (XLB ETF proxy)"),
    "Real Estate":        ("ANCHOR_IYR", "real estate",            "real estate (IYR ETF proxy)"),
    # Communication Services: XLC anchor ADDED 2026-07-23. The GICS sector was created
    # 2018-06, so XLC (its only ETF) has no long-history alternative and is a documented
    # SHORT-HISTORY anchor — see SHORT_HISTORY_ANCHORS. Flips GOOGL/META/NFLX + 51 more
    # from `none` to live.
    "Communication Services": ("ANCHOR_XLC", "communication services", "communication services (XLC ETF proxy)"),
}

# Anchors whose data starts well after the 2004 window floor. The SHORT-HISTORY label
# travels with every mapping to these — an S5 obligation the UI must render at the
# click-out, not only on the engine tab. Mirrors engine.SHORT_HISTORY_STARTS.
SHORT_HISTORY_ANCHORS = {
    "ANCHOR_XLC": "2018-06",
}

# industry substring -> override, manifest-confirmed anchors only
INDUSTRY_OVERRIDES = [
    ("Semiconductor", ("ANCHOR_SMH", "semiconductors", "semiconductors (SMH ETF proxy)")),
]


def _decorate(anc, alias, label, kind):
    d = {"anchor": anc, "alias": alias, "anchor_name": label, "mapping_kind": kind}
    start = SHORT_HISTORY_ANCHORS.get(anc)
    if start:
        d["short_history"] = True
        d["coverage_start"] = start
        d["short_history_note"] = (f"{label} is measured only since {start} — the sector's "
                                    f"ETF has no earlier history. Evidence spans ~1 cycle; thin.")
    return d


def map_ticker(sector, industry):
    """Return {anchor, alias, anchor_name, mapping_kind[, short_history, coverage_start,
    short_history_note]}. `none` kind for unmapped sectors (ETF, Unknown, blank) — the UI
    disables the block. Communication Services now maps to XLC (short-history)."""
    for needle, (anc, alias, label) in INDUSTRY_OVERRIDES:
        if industry and needle.lower() in str(industry).lower():
            return _decorate(anc, alias, label, "industry_proxy")
    hit = SECTOR_TO_ANCHOR.get(str(sector or "").strip())
    if hit:
        anc, alias, label = hit
        return _decorate(anc, alias, label, "sector_proxy")
    return {"anchor": None, "alias": None, "anchor_name": None, "mapping_kind": "none"}


def build_map(base_raw):
    """base_raw = fundamentals cache dict. ETFs and non-dict rows -> none/skipped."""
    out = {}
    for tk, d in base_raw.items():
        if not isinstance(d, dict):
            continue
        sector = d.get("sector")
        if sector == "ETF" or d.get("type") == "etf":
            continue  # non-equity entry point doesn't render at all for ETFs
        out[tk] = map_ticker(sector, d.get("industry"))
    return out
