"""
Price Cache Updater (append-only)
=================================

prices_cache.parquet was built ONCE, on 2026-05-04 (prefetch_prices.py), for the backtests,
and is committed to the repo (99 MiB, just under GitHub's 100 MiB file limit). The bake later
began reading it through price_cache.py for every buy point's technicals (Bollinger band,
50-day SMA, support) and for the per-ticker price shards behind the research charts -- but
nothing ever refreshed it, so all of those froze at 2026-05-04.

This appends new daily bars to an UNTRACKED live cache, prices_cache_live.parquet, which
price_cache.py reads in preference to the committed snapshot:

  - the first run seeds it from prices_cache.parquet; existing rows are never rewritten or
    dropped, and the committed snapshot is never touched (the Sunday quant-backtest workflow
    in CI keeps reading it);
  - per ticker, only sessions after its last cached date are added, and only completed
    sessions (a session counts once 16:30 ET has passed), so a partial intraday bar never
    enters the cache;
  - a universe ticker missing from the cache gets its full history from 2005;
  - Yahoo applies splits (and spin-offs, which it books as fractional splits) to its whole
    history, so after one the cached bars sit on the old scale. When the overlapping bar's
    change matches the split events Yahoo reports since the ticker's last cached date, the
    events are recorded in prices_cache_live_events.json and the new bars are appended;
    price_cache.py rescales the bars stored up to each event's applies_through date when it
    loads them, so the stored history is never rewritten. 2026-05-04 -> 10-19 had 16 (KLAC 10:1, CRWD 4:1, APH 2:1, FDX/SPGI/HON spin-offs).
    A change no reported event explains is not appended; the ticker is listed instead.

Free data only: yfinance, the same source prefetch_prices.py used.

Usage:  python update_price_cache.py [--dry-run] [--tickers NVDA,MU,SPY]
Prints one JSON summary line last. Exit 0 when the cache is current or was extended
(partial misses are listed); exit 1 when nothing could be fetched at all.
"""

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

SNAPSHOT_FILE = "prices_cache.parquet"
LIVE_FILE = "prices_cache_live.parquet"
EVENTS_FILE = "prices_cache_live_events.json"
UNIVERSE_FILE = "fundamentals_cache.json"
COLUMNS = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
BATCH_SIZE = 50
OVERLAP_DAYS = 10            # re-fetch this far back to compare against the cached close
OVERLAP_TOLERANCE = 0.005    # 0.5%: beyond this, the series' scale changed
SESSION_CLOSE_ET = dtime(16, 30)
FULL_HISTORY_START = "2005-01-01"
ET = ZoneInfo("America/New_York")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def last_completed_session(now=None):
    """The latest date whose session has closed (16:30 ET); weekends simply have no bars."""
    now_et = (now or datetime.now(ET)).astimezone(ET)
    day = now_et.date()
    return day if now_et.time() >= SESSION_CLOSE_ET else day - timedelta(days=1)


def universe_tickers():
    with open(UNIVERSE_FILE) as f:
        cache = json.load(f)
    if isinstance(cache.get("tickers"), dict):
        cache = cache["tickers"]
    return sorted(k for k in cache if isinstance(k, str) and k.isupper() and 1 <= len(k) <= 6)


def download(tickers, start, end):
    for attempt in range(2):
        try:
            df = yf.download(tickers=tickers, start=start, end=end, progress=False,
                             auto_adjust=False, group_by="ticker", threads=True)
            if df is not None and not df.empty:
                return df
        except Exception as e:  # noqa: BLE001
            log(f"  download attempt {attempt + 1} failed: {str(e)[:100]}")
        time.sleep(5)
    return None


def to_long(df, tickers):
    """yfinance batch output -> long rows in the cache's schema."""
    frames = []
    multi = isinstance(df.columns, pd.MultiIndex)
    for t in tickers:
        if multi:
            if t not in df.columns.get_level_values(0):
                continue
            sub = df[t]
        else:
            if len(tickers) != 1:
                continue
            sub = df
        sub = sub.dropna(how="all")
        if sub.empty or "Close" not in sub.columns:
            continue
        frames.append(pd.DataFrame({
            "date": pd.to_datetime(sub.index).tz_localize(None),
            "ticker": t,
            "open": pd.to_numeric(sub.get("Open"), errors="coerce").values,
            "high": pd.to_numeric(sub.get("High"), errors="coerce").values,
            "low": pd.to_numeric(sub.get("Low"), errors="coerce").values,
            "close": pd.to_numeric(sub.get("Close"), errors="coerce").values,
            "adj_close": pd.to_numeric(sub.get("Adj Close"), errors="coerce").values,
            "volume": pd.to_numeric(sub.get("Volume"), errors="coerce").values,
        }))
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    out = pd.concat(frames, ignore_index=True)
    return out[out["close"].notna()]


def emit(summary, path=None):
    """The JSON summary: last stdout line, and the file the nightly reads (its log tail is short)."""
    print(json.dumps(summary))
    if path:
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="fetch and report; write nothing")
    ap.add_argument("--tickers", default=None, help="comma list (default: the bake universe)")
    ap.add_argument("--summary-path", default=None, help="also write the JSON summary here")
    args = ap.parse_args()
    t0 = time.time()

    source = LIVE_FILE if os.path.exists(LIVE_FILE) else SNAPSHOT_FILE
    if not os.path.exists(source):
        log(f"no {SNAPSHOT_FILE} to extend")
        print(json.dumps({"ok": False, "reason": f"{SNAPSHOT_FILE} missing"}))
        return 1
    log(f"loading {source} ...")
    cache = pd.read_parquet(source)
    cache["date"] = pd.to_datetime(cache["date"])
    n_before = len(cache)
    last_dates = cache.groupby("ticker")["date"].max()
    last_close = cache.sort_values("date").groupby("ticker")["close"].last()

    cutoff = pd.Timestamp(last_completed_session())
    tickers = args.tickers.split(",") if args.tickers else universe_tickers()
    stale = [t for t in tickers if t in last_dates.index and last_dates[t] < cutoff]
    missing = [t for t in tickers if t not in last_dates.index]
    log(f"universe {len(tickers)} | behind {len(stale)} | not cached {len(missing)} | "
        f"cutoff {cutoff.date()}")

    end = (cutoff + timedelta(days=1)).strftime("%Y-%m-%d")
    new_parts, unfetched, rescaled, split_candidates = [], [], [], []
    events = {"version": 1, "splits": {}}
    if source == LIVE_FILE and os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE) as f:
            events = json.load(f)
    new_events = {}

    for i in range(0, len(stale), BATCH_SIZE):
        batch = stale[i:i + BATCH_SIZE]
        start = (min(last_dates[t] for t in batch) - timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%d")
        df = download(batch, start, end)
        rows = to_long(df, batch) if df is not None else pd.DataFrame(columns=COLUMNS)
        for t in batch:
            got = rows[rows["ticker"] == t]
            if got.empty:
                unfetched.append(t)
                continue
            fresh = got[(got["date"] > last_dates[t]) & (got["date"] <= cutoff)]
            # The cached last bar must still read the same, or the scale changed (split).
            same_day = got[got["date"] == last_dates[t]]
            if same_day.empty:
                rescaled.append(t)
                continue
            ratio = float(same_day["close"].iloc[0]) / float(last_close[t])
            if abs(ratio - 1) > OVERLAP_TOLERANCE:
                split_candidates.append((t, ratio, fresh))
                continue
            if not fresh.empty:
                new_parts.append(fresh)
        log(f"  [{i + len(batch)}/{len(stale)}] appended so far: {sum(len(p) for p in new_parts):,} rows")
        time.sleep(1.0)

    # A scale change is accepted only when Yahoo's reported split events since the ticker's last
    # cached bar explain it: cached_close / product(factors) == today's reading of that bar.
    for t, ratio, fresh in split_candidates:
        try:
            splits = yf.Ticker(t).splits
        except Exception:  # noqa: BLE001
            splits = pd.Series(dtype=float)
        if len(splits):
            splits.index = pd.to_datetime(splits.index).tz_localize(None).normalize()
            splits = splits[(splits.index > last_dates[t]) & (splits.index <= cutoff)]
        product = float(splits.prod()) if len(splits) else 1.0
        if len(splits) == 0 or abs(ratio * product - 1) > OVERLAP_TOLERANCE:
            rescaled.append(t)
            continue
        # applies_through: the last bar stored on the old scale. Yahoo returns every bar it
        # sends now -- including ones dated before the split -- already on the new scale.
        new_events[t] = [{"date": str(d.date()), "factor": float(v),
                          "applies_through": str(last_dates[t].date())} for d, v in splits.items()]
        if not fresh.empty:
            new_parts.append(fresh)

    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i:i + BATCH_SIZE]
        df = download(batch, FULL_HISTORY_START, end)
        rows = to_long(df, batch) if df is not None else pd.DataFrame(columns=COLUMNS)
        rows = rows[rows["date"] <= cutoff]
        unfetched += [t for t in batch if t not in set(rows["ticker"])]
        if not rows.empty:
            new_parts.append(rows)

    added = pd.concat(new_parts, ignore_index=True) if new_parts else pd.DataFrame(columns=COLUMNS)
    summary = {
        "ok": True, "source": source, "cutoff": str(cutoff.date()),
        "rows_before": n_before, "rows_added": len(added),
        "tickers_extended": int(added["ticker"].nunique()) if len(added) else 0,
        "unfetched": sorted(unfetched), "rescaled_not_appended": sorted(rescaled),
        "split_events_recorded": new_events,
        "duration_s": round(time.time() - t0, 1),
    }
    if stale and not new_parts and len(unfetched) == len(stale) + len(missing):
        summary.update(ok=False, reason="nothing could be fetched")
        emit(summary, args.summary_path)
        return 1
    if args.dry_run or added.empty:
        summary["written"] = False
        emit(summary, args.summary_path)
        return 0

    merged = pd.concat([cache, added[COLUMNS]], ignore_index=True)
    merged = merged.sort_values(["ticker", "date"]).reset_index(drop=True)
    # Append-only, proven: every old (ticker, date) row is still there with the same close.
    if merged.duplicated(["ticker", "date"]).any():
        raise SystemExit("refusing to write: an appended bar duplicates a cached one")
    check = cache[["ticker", "date", "close"]].merge(
        merged[["ticker", "date", "close"]], on=["ticker", "date"], how="left", suffixes=("", "_new"))
    if len(merged) != n_before + len(added) or check["close_new"].isna().sum() != check["close"].isna().sum() \
            or not ((check["close"] == check["close_new"]) | check["close"].isna()).all():
        raise SystemExit("refusing to write: existing history would change")
    # Events first: applied to a cache that lacks the new bars, they only rescale it whole.
    for t, evs in new_events.items():
        known = {(e["date"], e["factor"]) for e in events["splits"].get(t, [])}
        events["splits"][t] = events["splits"].get(t, []) + [e for e in evs if (e["date"], e["factor"]) not in known]
    if new_events:
        with open(EVENTS_FILE + ".tmp", "w") as f:
            json.dump(events, f, indent=2, sort_keys=True)
        os.replace(EVENTS_FILE + ".tmp", EVENTS_FILE)
    tmp = LIVE_FILE + ".tmp"
    merged.to_parquet(tmp, compression="zstd", index=False)
    os.replace(tmp, LIVE_FILE)
    summary.update(written=True, live_file=LIVE_FILE, rows_after=len(merged),
                   size_mb=round(os.path.getsize(LIVE_FILE) / 2**20, 1))
    emit(summary, args.summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
