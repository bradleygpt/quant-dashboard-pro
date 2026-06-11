# Ops note: fundamentals cache resilience (currentPrice null guard)

## Symptom & history
The bake's fail-loud `currentPrice` guard (`bake/bake.py`) refused to write on:
- 2026-06-10 — 1338/1358 null
- 2026-06-11 — CI run 27335709194, **21/1261 present (98.3% null)**

Two failures in three days → not "intermittent."

## Root cause
`build_cache.py` runs in **GitHub Actions** (`.github/workflows/refresh-daily*.yml`,
`ubuntu-latest`, cron twice daily). It made **~6,000 requests per run** (`t.info` +
`t.history` + `earnings_dates` + quarterly financials, ×1,261 tickers) and **swallowed
every failure** (`except Exception: return None`), so a throttled run silently dropped
nearly the whole universe, then force-pushed the near-empty cache — poisoning it. The
shared Actions runner IP is rate-limited by Yahoo's `quoteSummary`/`.info` (crumb)
endpoint; the keyless **v8 chart** endpoint (used by `/api/*`) is far more lenient.

## Mitigations shipped (this change)
1. **Instrumentation** — every failure is classified (`rate_limit_429` / `http_<code>`
   / `empty_info_no_marketcap` / `no_history`) and tallied; a `fundamentals_cache_meta.json`
   sidecar records `{n_fresh, n_rescued, n_batch_prices, backoff_pauses, failure_modes}`.
2. **Batch price preload** — `yf.download` over the whole universe (chart endpoint, a few
   dozen requests vs ~6k) fills a reliable `currentPrice`/history source.
3. **Merge / rescue** — when a ticker's `.info` is throttled, it stays in the cache with a
   fresh batch price + technicals and its **last-known fundamentals**, so a throttled run
   degrades to "fresh prices, stale fundamentals," never a blank universe.
4. **Anti-poison** — incremental saves go to a `.partial.json` scratch file; the canonical
   cache is written only at the end, and **refused** if `n_price < 50%` of the prior cache.
5. **Exponential backoff** across the run when failures cluster.
6. **Guard self-diagnosis** — `bake/bake.py`'s FATAL message now appends the sidecar's
   failure-mode breakdown, so the next occurrence explains itself.

We deliberately did **not** inject a `requests.Session` — yfinance 1.3 uses `curl_cffi`
(browser-TLS impersonation) by default, the correct anti-throttle transport, and rejects a
plain session.

## Structural fallback — FLAGGED, not implemented (needs your call)
If the runner-IP throttling proves unfixable even with the above (i.e., the batch endpoint
itself starts getting 429s from the Actions IP), the durable fix is to **move the cache
build off CI onto the local nightly chain** (home IP, already scheduled for the
quant-historical refresh) and have CI **consume the committed cache** rather than rebuild it.

Evidence this may be necessary:
- The failures are IP-correlated (CI runner), not code bugs — the same `build_cache.py`
  succeeds from a home IP.
- Yahoo throttling of datacenter/Actions IP ranges is escalating industry-wide.

Trade-off: the home machine must be reliably awake at the cron time; CI becomes a pure
consumer (bake + deploy). Recommend deciding after observing 1–2 runs of the mitigated
build (watch `fundamentals_cache_meta.json` → `failure_modes`). The guard stays either way.

## Related footgun (separate, not changed here)
`web/bake/bake.py` (v2 repo, 396 lines, 2026-06-03) has diverged from the canonical
`bake/bake.py` (parent/source, 813 lines). The nightly `web/.github/workflows/refresh.yml`
clones the source repo and runs **source/bake/bake.py** (the canonical 813-line one — the
`cp -r bake source/bake` nests into the existing dir rather than overwriting it), so the
stale v2 copy is currently inert. Worth deleting the stale copy to avoid future confusion.
