"""Self-contained Pullback Pressure Index (PPI) — faithful Python port of
web/src/lib/ppiIndex.ts. Inputs are ONLY live market data (SPY/VIX/VVIX from keyless
Yahoo) + baked-universe breadth — NO c78q.json, NO quant-historical. Runs in CI on
every bake so system_status.ppi is a real computed gauge, decoupled from the monthly
c78q ETL. Keep in sync with ppiIndex.ts (same 7 components, weights, thresholds)."""
import json, math, urllib.request, urllib.parse

PPI_WEIGHTS = {"mri": 0.20, "rsi14_sustained": 0.15, "rsi2_extreme": 0.10,
               "vix_structure": 0.15, "vvix_spike": 0.10, "breadth": 0.15, "drawdown_from_peak": 0.15}
_NICE = {"mri": "MRI", "rsi14_sustained": "Overbought persistence (RSI14>70, 10d)",
         "rsi2_extreme": "Short-term extreme (RSI2)", "vix_structure": "VIX structure",
         "vvix_spike": "VVIX spike", "breadth": "Breadth", "drawdown_from_peak": "Drawdown from peak"}


def _clip(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def _rsi(closes, window):
    n = len(closes)
    out = [None] * n
    if n < window + 1:
        return out
    gain, loss = [0.0], [0.0]
    for i in range(1, n):
        d = closes[i] - closes[i - 1]
        gain.append(d if d > 0 else 0.0)
        loss.append(-d if d < 0 else 0.0)
    for i in range(window, n):
        g = sum(gain[i - window + 1:i + 1]) / window
        l = sum(loss[i - window + 1:i + 1]) / window
        if l == 0:
            out[i] = None
            continue
        rs = g / l
        out[i] = 100 - 100 / (1 + rs)
    return out


def _mri(spy):
    if len(spy) < 252:
        return 50, "insufficient data"
    cur12m = spy[-1] / spy[-252] - 1
    total = spy[-1] / spy[0] - 1
    nyears = len(spy) / 252
    avg = (1 + total) ** (1 / max(nyears, 0.5)) - 1
    dr = [(spy[i] - spy[i - 1]) / spy[i - 1] for i in range(1, len(spy))]
    mean = sum(dr) / len(dr)
    vol = math.sqrt(sum((r - mean) ** 2 for r in dr) / len(dr)) * math.sqrt(252)
    mri = (cur12m - avg) / max(vol, 0.01)
    return _clip(50 + mri * 20), f"12m {cur12m*100:+.1f}%, MRI {mri:+.2f}"


def _rsi14(spy):
    if len(spy) < 30:
        return 50, "insufficient data"
    rsi = [x for x in _rsi(spy, 14)[-10:] if x is not None]
    if not rsi:
        return 50, "no RSI values"
    cur = rsi[-1]
    days_above = sum(1 for x in rsi if x > 70)
    score = days_above * 10
    if cur > 80:
        score = min(score + 20, 100)
    return score, f"RSI14 {cur:.1f}, days>70: {days_above}/10"


def _rsi2(spy):
    if len(spy) < 10:
        return 50, "insufficient data"
    rsi2 = [x for x in _rsi(spy, 2) if x is not None]
    if not rsi2:
        return 50, "RSI-2 all NaN"
    return _clip(rsi2[-1]), f"RSI2 {rsi2[-1]:.1f}"


def _vix(vix):
    if not vix or len(vix) < 20:
        return 50, "no VIX data"
    cur = vix[-1]
    v5 = vix[-5] if len(vix) >= 5 else cur
    chg = (cur - v5) / max(v5, 0.01)
    base = 55 if cur < 14 else 30 if cur < 20 else 50 if cur < 30 else 80
    if cur < 20 and chg > 0.15:
        base += 20
    elif chg > 0.30:
        base += 15
    return _clip(base), f"VIX {cur:.1f}, 5d {chg*100:+.1f}%"


def _vvix(vvix):
    if not vvix:
        return 50, "no VVIX data"
    cur = vvix[-1]
    score = 90 if cur > 130 else 75 if cur > 120 else 55 if cur > 100 else 35 if cur > 80 else 45
    return score, f"VVIX {cur:.1f}"


def _breadth(pct):
    if pct is None:
        return 50, "breadth unavailable"
    p = pct / 100
    score = 20 if p > 0.70 else 35 if p > 0.55 else 55 if p > 0.40 else 75 if p > 0.25 else 90
    return score, f"{pct:.0f}% above 50-SMA (baked universe)"


def _drawdown(spy):
    if len(spy) < 252:
        return 50, "insufficient data"
    w = spy[-252:]
    high = max(w)
    dd = (spy[-1] - high) / high
    score = 45 if dd > -0.02 else 55 if dd > -0.05 else 70 if dd > -0.10 else 80 if dd > -0.15 else 90 if dd > -0.20 else 95
    return score, f"{dd*100:+.1f}% from 52w high"


def compute_ppi(spy, vix, vvix, breadth_pct):
    """Return {score, level, color, action, band_deploy_pct, components} or None."""
    if not spy or len(spy) < 30:
        return None
    raw = {"mri": _mri(spy), "rsi14_sustained": _rsi14(spy), "rsi2_extreme": _rsi2(spy),
           "vix_structure": _vix(vix), "vvix_spike": _vvix(vvix), "breadth": _breadth(breadth_pct),
           "drawdown_from_peak": _drawdown(spy)}
    score = sum(raw[k][0] * w for k, w in PPI_WEIGHTS.items())
    if score < 20:
        level, color, action, band = "LOW", "#00C805", "Market healthy. Deploy normally.", 100
    elif score < 40:
        level, color, action, band = "MODERATE", "#8BC34A", "Normal fluctuation. No timing concern.", 100
    elif score < 60:
        level, color, action, band = "ELEVATED", "#FF9800", "Consider scaling in vs full deployment.", 50
    elif score < 80:
        level, color, action, band = "HIGH", "#FF5722", "Delay new deployment. Pullback likely.", 25
    else:
        level, color, action, band = "EXTREME", "#D32F2F", "Active correction. Wait for resolution.", 0
    comps = [{"key": k, "name": _NICE[k], "weight": PPI_WEIGHTS[k], "score": round(raw[k][0]),
              "detail": raw[k][1],
              "available": not any(s in raw[k][1] for s in ("unavailable", "no ", "insufficient"))}
             for k in PPI_WEIGHTS]
    return {"score": round(score * 10) / 10, "level": level, "color": color, "action": action,
            "band_deploy_pct": band, "components": comps}


def _yahoo_closes(symbol, rng):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?range={rng}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; QuantDashboard/2.0)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.load(r)["chart"]["result"][0]
    cl = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    return [c for c in cl if isinstance(c, (int, float))]


def fetch_market():
    """SPY 2y, ^VIX 6mo, ^VVIX 6mo daily closes from keyless Yahoo (CI-runnable)."""
    import urllib.parse  # noqa
    spy = vix = vvix = None
    try:
        spy = _yahoo_closes("SPY", "2y")
    except Exception:
        pass
    try:
        vix = _yahoo_closes("^VIX", "6mo")
    except Exception:
        pass
    try:
        vvix = _yahoo_closes("^VVIX", "6mo")
    except Exception:
        pass
    return spy, vix, vvix
