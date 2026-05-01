"""
Crypto Module — Bitcoin cycle analysis + Ethereum supply dynamics + on-chain metrics

Coverage:
- Bitcoin: 4-year halving cycle position, Pi Cycle Top, Mayer Multiple, distance from ATH,
  historical cycle comparison, RSI
- Ethereum: ETH/BTC ratio, supply dynamics (post-Merge deflation), staking ratio, network activity
- On-chain (best-effort, free APIs): block height, hash rate, mempool fees

Data sources:
- yfinance: Price history for BTC-USD and ETH-USD
- CoinGecko free API: Current prices, market caps, supply, 24h changes
- Mempool.space free API: Block height, hash rate, mempool stats
- blockchain.info: Backup for block height

Honest caveats baked in:
- 4-year cycle theory has only 3 prior cycles as data — small sample
- Current cycle (2024-2028) has institutional dynamics absent in prior cycles
- On-chain metrics get gamed once popular
- This is NOT financial advice
"""

import requests
import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta


# ════════════════════════════════════════════════════════════════════
# Bitcoin Halving Constants
# ════════════════════════════════════════════════════════════════════
# Halvings cut block reward in half every 210,000 blocks (~4 years)
HALVINGS = [
    {"date": datetime(2012, 11, 28), "block": 210_000, "reward_after": 25.0},
    {"date": datetime(2016, 7, 9),   "block": 420_000, "reward_after": 12.5},
    {"date": datetime(2020, 5, 11),  "block": 630_000, "reward_after": 6.25},
    {"date": datetime(2024, 4, 19),  "block": 840_000, "reward_after": 3.125},
    # Estimated future halving (recalculated based on current block height)
    {"date": datetime(2028, 4, 1),   "block": 1_050_000, "reward_after": 1.5625, "estimated": True},
]

# Cycle phase definitions based on days since most recent halving
# These are heuristic — the actual peaks/troughs vary cycle to cycle
CYCLE_PHASES = [
    (0,    180,  "Post-Halving Quiet",   "Price often consolidates 3-6 months post-halving"),
    (180,  450,  "Early Markup",          "Historical pattern: gradual uptrend begins"),
    (450,  600,  "Late Markup / Peak Window", "Historical peaks occurred 12-18 months post-halving"),
    (600,  730,  "Distribution / Early Bear", "Historical pattern: peak forms, then decline begins"),
    (730,  1100, "Bear Market",           "Historical bear lasts 12-18 months"),
    (1100, 1460, "Accumulation",          "Pre-halving accumulation phase"),
]


# ════════════════════════════════════════════════════════════════════
# Bitcoin Cycle Analysis
# ════════════════════════════════════════════════════════════════════

def get_current_halving_info():
    """
    Determine which halving we're past and how many days since.

    Returns dict with:
        last_halving: datetime of most recent halving
        next_halving: datetime of estimated next halving
        days_since_last: int
        days_until_next: int
        cycle_progress_pct: float (0-100)
        current_reward: float (current block reward in BTC)
        next_reward: float
    """
    now = datetime.now()

    # Find the most recent halving
    past_halvings = [h for h in HALVINGS if h["date"] <= now]
    future_halvings = [h for h in HALVINGS if h["date"] > now]

    if not past_halvings:
        return None  # Pre-2012 — shouldn't happen

    last = past_halvings[-1]
    days_since = (now - last["date"]).days

    if future_halvings:
        next_h = future_halvings[0]
        days_until = (next_h["date"] - now).days
        cycle_length = (next_h["date"] - last["date"]).days
        progress = (days_since / cycle_length) * 100
    else:
        next_h = None
        days_until = None
        progress = None

    return {
        "last_halving": last["date"],
        "next_halving": next_h["date"] if next_h else None,
        "next_halving_estimated": next_h.get("estimated", False) if next_h else False,
        "days_since_last": days_since,
        "days_until_next": days_until,
        "cycle_progress_pct": round(progress, 1) if progress is not None else None,
        "current_reward": last["reward_after"],
        "next_reward": next_h["reward_after"] if next_h else None,
    }


def get_cycle_phase(days_since_halving):
    """Map days-since-halving to a heuristic cycle phase."""
    for low, high, label, description in CYCLE_PHASES:
        if low <= days_since_halving < high:
            return {
                "phase": label,
                "description": description,
                "days_in_phase": days_since_halving - low,
                "phase_duration": high - low,
            }
    # Beyond expected cycle length
    return {
        "phase": "Beyond Historical Pattern",
        "description": "We are past the typical 4-year cycle window. Pattern is breaking down or extended.",
        "days_in_phase": days_since_halving,
        "phase_duration": None,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_btc_history(period="max"):
    """Fetch Bitcoin price history from yfinance."""
    try:
        btc = yf.Ticker("BTC-USD")
        hist = btc.history(period=period)
        if hist.empty:
            return None
        return hist
    except Exception as e:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_eth_history(period="max"):
    """Fetch Ethereum price history from yfinance."""
    try:
        eth = yf.Ticker("ETH-USD")
        hist = eth.history(period=period)
        if hist.empty:
            return None
        return hist
    except Exception as e:
        return None


def compute_btc_valuation_indicators(btc_history):
    """
    Compute multiple BTC valuation indicators.

    Returns dict with:
        current_price, ath, distance_from_ath_pct
        pi_cycle_signal: "Top" if 111-DMA > 350-DMA*2, else "Below Top"
        mayer_multiple: price / 200-DMA (>2.4 historically signals top)
        rsi_weekly: 14-period RSI on weekly data
        sma_200d, sma_111d, sma_350d_x2
    """
    if btc_history is None or btc_history.empty:
        return None

    close = btc_history["Close"]
    current = float(close.iloc[-1])
    ath = float(close.max())
    ath_date = close.idxmax()
    distance_from_ath = ((current - ath) / ath) * 100

    # Pi Cycle Top Indicator
    sma_111 = close.rolling(111).mean()
    sma_350 = close.rolling(350).mean()
    sma_350_x2 = sma_350 * 2

    pi_cycle_signal = "Top Triggered" if (sma_111.iloc[-1] > sma_350_x2.iloc[-1]) else "Below Top"
    pi_cycle_distance = ((sma_111.iloc[-1] - sma_350_x2.iloc[-1]) / sma_350_x2.iloc[-1]) * 100

    # Mayer Multiple (price / 200-DMA)
    sma_200 = close.rolling(200).mean()
    mayer = current / sma_200.iloc[-1] if sma_200.iloc[-1] > 0 else None

    # Weekly RSI
    weekly = close.resample("W").last()
    delta = weekly.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_current = float(rsi.iloc[-1]) if not rsi.empty and pd.notna(rsi.iloc[-1]) else None

    return {
        "current_price": current,
        "ath": ath,
        "ath_date": ath_date,
        "distance_from_ath_pct": round(distance_from_ath, 2),
        "pi_cycle_signal": pi_cycle_signal,
        "pi_cycle_distance_pct": round(pi_cycle_distance, 2),
        "sma_111d": float(sma_111.iloc[-1]) if pd.notna(sma_111.iloc[-1]) else None,
        "sma_350d_x2": float(sma_350_x2.iloc[-1]) if pd.notna(sma_350_x2.iloc[-1]) else None,
        "sma_200d": float(sma_200.iloc[-1]) if pd.notna(sma_200.iloc[-1]) else None,
        "mayer_multiple": round(mayer, 3) if mayer else None,
        "rsi_weekly": round(rsi_current, 1) if rsi_current is not None else None,
    }


def interpret_valuation(indicators):
    """Build human-readable interpretation of valuation indicators."""
    if indicators is None:
        return []

    interps = []

    # Mayer Multiple
    mm = indicators.get("mayer_multiple")
    if mm is not None:
        if mm > 2.4:
            interps.append(("Mayer Multiple", f"{mm:.2f}", "🔴 Historically extreme — past tops occurred near 2.4+"))
        elif mm > 1.5:
            interps.append(("Mayer Multiple", f"{mm:.2f}", "🟠 Elevated — caution zone"))
        elif mm > 1.0:
            interps.append(("Mayer Multiple", f"{mm:.2f}", "🟡 Above 200-DMA — neutral to bullish"))
        elif mm > 0.7:
            interps.append(("Mayer Multiple", f"{mm:.2f}", "🟢 Below 200-DMA — historically a buy zone"))
        else:
            interps.append(("Mayer Multiple", f"{mm:.2f}", "🟢 Deep discount — historically bear-market lows"))

    # RSI Weekly
    rsi = indicators.get("rsi_weekly")
    if rsi is not None:
        if rsi > 80:
            interps.append(("Weekly RSI", f"{rsi:.0f}", "🔴 Extreme overbought"))
        elif rsi > 70:
            interps.append(("Weekly RSI", f"{rsi:.0f}", "🟠 Overbought"))
        elif rsi > 50:
            interps.append(("Weekly RSI", f"{rsi:.0f}", "🟡 Bullish bias"))
        elif rsi > 30:
            interps.append(("Weekly RSI", f"{rsi:.0f}", "🟡 Neutral to weak"))
        else:
            interps.append(("Weekly RSI", f"{rsi:.0f}", "🟢 Oversold — historically a buy zone"))

    # Pi Cycle
    pi = indicators.get("pi_cycle_signal")
    pi_dist = indicators.get("pi_cycle_distance_pct")
    if pi:
        if pi == "Top Triggered":
            interps.append(("Pi Cycle Top", "TRIGGERED", "🔴 111-DMA > 350-DMA × 2 — historical top signal"))
        else:
            interps.append(("Pi Cycle Top", f"{pi_dist:+.1f}% from trigger", "🟢 Below historical top threshold"))

    # Distance from ATH
    dist = indicators.get("distance_from_ath_pct")
    if dist is not None:
        if dist > -5:
            interps.append(("From ATH", f"{dist:+.1f}%", "🔴 At or near all-time high"))
        elif dist > -20:
            interps.append(("From ATH", f"{dist:+.1f}%", "🟡 Modest pullback from ATH"))
        elif dist > -50:
            interps.append(("From ATH", f"{dist:+.1f}%", "🟠 Significant correction"))
        else:
            interps.append(("From ATH", f"{dist:+.1f}%", "🟢 Deep bear territory — historical buy zone"))

    return interps


# ════════════════════════════════════════════════════════════════════
# CoinGecko API (free, no auth)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner=False)  # 10 min cache
def fetch_coingecko_market_data():
    """
    Fetch current market data for BTC and ETH from CoinGecko.

    Returns dict with btc and eth sections containing price, market_cap, supply, etc.
    """
    try:
        url = (
            "https://api.coingecko.com/api/v3/coins/markets"
            "?vs_currency=usd&ids=bitcoin,ethereum"
            "&order=market_cap_desc&per_page=2&page=1"
            "&sparkline=false&price_change_percentage=24h,7d,30d,1y"
        )
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None

        data = r.json()
        result = {}
        for coin in data:
            key = "btc" if coin["id"] == "bitcoin" else "eth"
            result[key] = {
                "price": coin.get("current_price"),
                "market_cap": coin.get("market_cap"),
                "volume_24h": coin.get("total_volume"),
                "circulating_supply": coin.get("circulating_supply"),
                "max_supply": coin.get("max_supply"),
                "ath": coin.get("ath"),
                "ath_date": coin.get("ath_date"),
                "ath_change_pct": coin.get("ath_change_percentage"),
                "change_24h_pct": coin.get("price_change_percentage_24h"),
                "change_7d_pct": coin.get("price_change_percentage_7d_in_currency"),
                "change_30d_pct": coin.get("price_change_percentage_30d_in_currency"),
                "change_1y_pct": coin.get("price_change_percentage_1y_in_currency"),
            }
        return result
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════
# On-chain metrics (free APIs)
# ════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner=False)
def fetch_btc_block_height():
    """Fetch current Bitcoin block height. Used to estimate next halving."""
    # Try mempool.space first
    try:
        r = requests.get("https://mempool.space/api/blocks/tip/height", timeout=10)
        if r.status_code == 200:
            return int(r.text.strip())
    except Exception:
        pass

    # Fall back to blockchain.info
    try:
        r = requests.get("https://blockchain.info/q/getblockcount", timeout=10)
        if r.status_code == 200:
            return int(r.text.strip())
    except Exception:
        pass

    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_btc_mempool_stats():
    """Fetch BTC mempool fees and hash rate from mempool.space."""
    result = {}

    # Recommended fees
    try:
        r = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=10)
        if r.status_code == 200:
            result["fees"] = r.json()
    except Exception:
        pass

    # Hash rate (current)
    try:
        r = requests.get("https://mempool.space/api/v1/mining/hashrate/3d", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if "currentHashrate" in data:
                # Convert to EH/s
                result["hashrate_ehs"] = round(data["currentHashrate"] / 1e18, 2)
            if "currentDifficulty" in data:
                result["difficulty"] = data["currentDifficulty"]
    except Exception:
        pass

    return result if result else None


def estimate_next_halving_from_block(current_block):
    """
    Estimate next halving date based on current block height.

    Block 1,050,000 is the next halving (~April 2028).
    Average block time is 10 minutes but tends to be slightly faster (~9.7 min)
    in modern era due to hash rate increases.
    """
    if current_block is None:
        return None

    next_halving_block = ((current_block // 210_000) + 1) * 210_000
    blocks_to_go = next_halving_block - current_block
    minutes_to_go = blocks_to_go * 9.85  # use 9.85 min as historical avg
    days_to_go = minutes_to_go / (60 * 24)

    estimated_date = datetime.now() + timedelta(days=days_to_go)
    return {
        "next_halving_block": next_halving_block,
        "blocks_remaining": blocks_to_go,
        "estimated_date": estimated_date,
        "days_remaining": int(days_to_go),
    }


# ════════════════════════════════════════════════════════════════════
# Ethereum-specific
# ════════════════════════════════════════════════════════════════════

# Hardcoded reference points for ETH supply dynamics
# (Updated periodically — these are approximations as of 2026)
ETH_SUPPLY_REFERENCES = {
    "merge_date": datetime(2022, 9, 15),
    "merge_supply": 120_521_000,  # ETH supply at The Merge
    "approximate_annual_issuance_pct": 0.55,  # ~0.5-0.7% per year
    "post_merge_burn_active": True,  # EIP-1559 burns ETH paid in gas
    "staking_ratio_pct_approx": 28,  # ~28% of ETH currently staked
}


def compute_eth_supply_metrics(coingecko_eth_data):
    """
    Compute ETH supply dynamics. Best-effort — for precise on-chain data,
    a paid API (Glassnode, ultrasound.money) would be needed.
    """
    if coingecko_eth_data is None:
        return None

    current_supply = coingecko_eth_data.get("circulating_supply")
    if current_supply is None:
        return None

    merge_supply = ETH_SUPPLY_REFERENCES["merge_supply"]
    merge_date = ETH_SUPPLY_REFERENCES["merge_date"]
    days_since_merge = (datetime.now() - merge_date).days
    years_since_merge = days_since_merge / 365.25

    # Net change since Merge
    net_change = current_supply - merge_supply
    net_change_pct = (net_change / merge_supply) * 100
    annualized_pct = net_change_pct / years_since_merge if years_since_merge > 0 else 0

    return {
        "current_supply": current_supply,
        "merge_supply": merge_supply,
        "net_change_since_merge": net_change,
        "net_change_pct": round(net_change_pct, 3),
        "annualized_change_pct": round(annualized_pct, 3),
        "years_since_merge": round(years_since_merge, 2),
        "is_deflationary": net_change < 0,
        "is_disinflationary": annualized_pct < ETH_SUPPLY_REFERENCES["approximate_annual_issuance_pct"],
        "staking_ratio_pct": ETH_SUPPLY_REFERENCES["staking_ratio_pct_approx"],
    }


def compute_eth_btc_ratio(eth_history, btc_history):
    """Compute the ETH/BTC ratio history."""
    if eth_history is None or btc_history is None:
        return None
    if eth_history.empty or btc_history.empty:
        return None

    # Align dates
    eth_close = eth_history["Close"]
    btc_close = btc_history["Close"]
    common_dates = eth_close.index.intersection(btc_close.index)

    if len(common_dates) == 0:
        return None

    ratio = eth_close.loc[common_dates] / btc_close.loc[common_dates]
    return ratio


# ════════════════════════════════════════════════════════════════════
# Historical cycle comparison
# ════════════════════════════════════════════════════════════════════

def build_cycle_overlay_data(btc_history):
    """
    Build a normalized comparison of price action across the 3 most recent halving cycles.

    Returns DataFrame with columns: days_since_halving, cycle_2016, cycle_2020, cycle_2024
    Where each cycle column is price normalized to 100 at halving date.

    NOTE: Cycle 1 (2012) is intentionally excluded from THIS PRICE-BASED overlay chart
    because yfinance does not have reliable BTC price history before 2014. The 2012 cycle
    IS still included in date-based timing analyses (cycle_timeline.py).
    """
    if btc_history is None or btc_history.empty:
        return None

    cycles = {}
    for halving_idx, halving in enumerate(HALVINGS[:-1]):  # Skip estimated future halving
        if halving_idx < 1:
            # Skip 2012 cycle for price overlay (yfinance lacks pre-2014 BTC data).
            # Date-based components still use it via cycle_timeline.HISTORICAL_CYCLES.
            continue

        halving_date = halving["date"]
        # Get price action from halving forward
        cycle_data = btc_history[btc_history.index >= pd.Timestamp(halving_date, tz=btc_history.index.tz)]

        if cycle_data.empty:
            continue

        # Limit to next 4 years (1460 days) max
        cycle_end = pd.Timestamp(halving_date + timedelta(days=1460), tz=btc_history.index.tz)
        cycle_data = cycle_data[cycle_data.index <= cycle_end]

        if cycle_data.empty:
            continue

        # Normalize to 100 at halving
        first_price = cycle_data["Close"].iloc[0]
        normalized = (cycle_data["Close"] / first_price) * 100

        # Days since halving
        days_since = (cycle_data.index - pd.Timestamp(halving_date, tz=btc_history.index.tz)).days

        cycle_label = f"cycle_{halving_date.year}"
        cycle_df = pd.DataFrame({
            "days_since_halving": days_since,
            cycle_label: normalized.values,
        })
        cycles[cycle_label] = cycle_df

    if not cycles:
        return None

    # Merge all cycles on days_since_halving
    result = None
    for label, df in cycles.items():
        if result is None:
            result = df
        else:
            result = result.merge(df, on="days_since_halving", how="outer")

    return result.sort_values("days_since_halving").reset_index(drop=True) if result is not None else None
