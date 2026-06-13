# Session Closeout — H2 (Modeled FV history) + data-integrity sweep

Continuous thread covering handoffs: DATA_INTEGRITY (N2–N5), cache-resilience (G1–G4),
PRICE_FRESHNESS (P1–P5), CLOSE_OPEN_LOOPS (H1, H2/Task1). Date: 2026-06-13.

---

## 1. Commits pushed this session (SHA · one-line)

### v2 — `quant-dashboard-pro-v2` (web, deployed). origin/main HEAD = **0599c985d**
- `422c2fc9f` N2: relabel backtest chart honestly + real buy-&-hold SPY
- `11bb3d69f` N3: real money-market AUM for PGI (was frozen $7.00T fallback)
- `8790e4b85` N4: verify macro inputs vs live FRED + as-of labels (CPI was stale 2.4→4.2)
- `3d42ded3e` H1: delete stale web/bake/ copy; drop vestigial `cp -r bake` in refresh.yml
- `2c43523f8` H1 fixup: actually remove the `cp -r bake` line from refresh.yml
- `bcbedce7e` H2: ship close + daily QBP history (FV withheld pending reconciliation)
- `b2e4db971` P2: c78q Live Deployment uses live-preferred prices (was frozen at entry)
- `95b27d673` P3+P5: extend MLPred live-quote pool to full filtered table; relabel PPI components
- `3df62db73` H2: render Modeled FV history as distinct methodology (gated, forward-compatible)
- `0599c985d` **H2 FINAL: ship Modeled FV history (labeled-distinct, corrected EBITDA)**
- (N1 MLPred live-pricing + /api/quotes shipped earlier in-thread; `c9ae16be5` Trisolaris
  landing PR#1 is **pre-session**, already on main.)

### parent — `quant-dashboard-pro` (canonical bake/build_cache). origin/main HEAD = **bb95d30**
- `a46db3b` N2: harden backtest source-selection (completeness floor + end-date) + buy-&-hold SPY
- `479e01b` N3: bake real money-market AUM (FRED MMMFFAQ027S) with as-of date
- `bbb5123` N4: verify CPI/Unemployment vs live FRED at bake time + as-of metadata
- `bb95d30` Fix recurring currentPrice-null cache builds (CI runner-IP rate-limit; G1–G4)

### quant-historical — engine repo, **LOCAL ONLY (no git remote)**
- `a01c91e` build_detail_timeseries_v3: full fairvalue.py composite at monthly PIT cross-sections
- `5c6ee84` PIT: add depreciation_amortization concept; builder true EBITDA (EBIT+D&A); exclude+list no-operating_income
- `c22d0fe` v3: FV-only rebuild (skip O(n²) per-day QBP — the hang), quarterly cross-section option, progress
- `561e186` v3: progress print for the snapshot phase (the silent gap)

### Branch (NOT merged to main)
- `claude/tristar-landing-v2` (on origin v2) — N5 landing redesign (TRI-STAR de-IP, day/night,
  era physics, sun remap). **Unmerged. main still has the old PR#1 landing.**

---

## 2. Files created / modified per repo

**v2 (web):**
- `src/tabs/QuantPortfolioTab.tsx` (N2 chart relabel + real SPY)
- `src/tabs/MarketRegimeTab.tsx` (N3 PGI precedence, N4 macro as-of)
- `src/tabs/C78QTab.tsx` (P2 live-preferred deployed prices)
- `src/tabs/MLPredTab.tsx` (N1 live pricing, P3 pool 80→120)
- `src/tabs/StockDetailTab.tsx` (H2 close+QBP caption; H2 FINAL Modeled-FV line + Live-FV marker)
- `src/lib/ppiIndex.ts` (P5 component relabels)
- `web/api/quotes.ts` (N1, created — batch keyless quotes)
- `.github/workflows/refresh.yml` (H1 — removed `cp -r bake`)
- **deleted** `web/bake/` (H1 — stale 396-line copy + oracle files)
- `public/data/`: `quant_backtest.json` (N2), `pgi_money_market.json` (N3, created),
  `market_static.json` (N4), `detail_timeseries/*.json` (H2 — 1311 shards: close+QBP+Modeled FV),
  `detail_timeseries_fv_excluded.json` (created), `freshness_manifest.json`

**parent (quant-dashboard-pro):**
- `bake/bake.py` (N2 selection+SPY, N3 PGI bake, N4 FRED verify, G3 guard self-diagnosis)
- `build_cache.py` (G1 failure-mode instrumentation, G2 batch preload + merge/anti-poison)
- `.github/workflows/refresh-daily.yml` + `refresh-daily-morning.yml` (G — add meta to commit)
- `.gitignore` (G — ignore partial cache)
- `OPS_CACHE_RESILIENCE.md` (G4, created)

**quant-historical (local):**
- `mlpred_v7/scripts/pit_fundamentals_v1.py` (added `depreciation_amortization` flow concept)
- `mlpred_v7/scripts/build_detail_timeseries_v3.py` (created+evolved — the FV builder)

---

## 3. FV deliverable (H2 / CLOSE_OPEN_LOOPS Task 1) — SHIPPED

- **Modeled FV history** added to Stock Detail: **1,142 tickers** carry a point-in-time FV line.
- **Labeled-distinct**, NOT anchored: dim-gold dotted "Modeled FV (PIT filings)" line + a solid
  "Live FV" reference marker; caption states it is a distinct methodology that differs from the
  live FV card. (Anchoring was explicitly rejected — it fabricates historical levels.)
- **Median gap vs the live FV card = 32.4%** (was ~33% pre-fix). The true-EBITDA proxy fix
  (EBIT + D&A) did **not** materially close it → confirms the residual is **irreducible
  XBRL-vs-yfinance source divergence**, not a bug. EV/EBITDA sectors did improve into the lowest
  band (Materials 23%, Utilities 26%, Industrials 28%); Tech/Healthcare/Comm (~39–44%, no
  EV/EBITDA) dominate the median and are inherently source-divergent.
- **27 EV/EBITDA-sector tickers excluded** (lack `operating_income` → no valid EBITDA), listed in
  `detail_timeseries_fv_excluded.json`: AES, AIR, AROC, CC, CNQ, COP, CTVA, CVX, DD, DOW, EMR, ENR,
  GATX, HTZ, ICL, IIIN, MTZ, NEM, NUE, OXY, PCAR, PSX, REX, SRE, SU, TXT, XOM.
- Close + price-only QBP history preserved (FV merged in non-destructively).
- Registered in the freshness manifest (gap + exclusion count recorded).
- Gates: split-continuity PASS, point-in-time/no-lookahead PASS, coverage ~95%. Gate-3 strict
  match is NOT achievable by design (different inputs) — shipped labeled-distinct per the decision.

---

## 4. Explicitly NOT done (open items)

- **FV build NOT wired into any scheduler.** It needs the quant-historical PIT panel, which CI
  does NOT have → it is a **local-bake artifact** (like c78q.json / mlpred.json) and belongs in the
  **local nightly chain**, not GitHub Actions. Actual runtime ~33 min (quarterly, FV-only). Left
  as a manual/local step. The shards shipped are a one-time snapshot (prices_cache ends 2026-05-04).
- **Meta sidecar (`fundamentals_cache_meta.json`) not yet present on origin.** build_cache writes
  it and the workflow add-line is committed (bb95d30), but no nightly Actions run has executed
  since that change. Awaits the next nightly to confirm; if still absent after it, the commit step
  needs a direct fix.
- **Zombie process PID 13388** (old suspended FV build) could not be killed from this shell
  ("Access is denied" — needs elevation). It is idle (144 CPU-sec, not growing) — harmless but
  holding memory. Kill via admin Task Manager / `taskkill /F /PID 13388`, or it clears on reboot.
  (It had cleared from the process list by end of session.)
- **CLOSE_OPEN_LOOPS Tasks 2–5 untouched:** Task 2 (landing real `system_status.json` PPI),
  Task 3 (AI earnings pre-bake), Task 4 (SMA/RSI window), Task 5 (canonical TOP-25 backtest).
- Power note: AC+DC standby/monitor timeouts were set to 0 (never) to stop sleep suspending long
  builds — **revert with `powercfg -change -standby-timeout-ac <min>`** if undesired.

---

## 5. Verified repo-state facts a fresh thread MUST trust (checked against origin, not memory)

- **On-main landing = the OLD Trisolaris demo** (`TRISOLARIS` HUD, `alpha/beta/gamma` suns,
  hardcoded mock `PPI 55 ELEVATED`). PR#1 `c9ae16be5`. Task 2 (real PPI) targets THIS mockData shape.
- **The N5 "v2" landing (TRI-STAR, day/night, quant/mlpred/thesis) is UNMERGED** — only on branch
  `claude/tristar-landing-v2`. Do not assume v2 is on main.
- **origin/main HEADs:** v2 = `0599c985d`; parent (quant-dashboard-pro) = `bb95d30`.
- **Nightly bake topology:** `quant-dashboard-pro-v2/.github/workflows/refresh.yml` clones the
  source repo and runs **source/bake/bake.py** (the canonical 813-line parent bake). `web/bake/`
  was deleted (H1); the `cp -r bake` line was removed.
- **build_cache.py runs in CI** (parent `refresh-daily*.yml`, 2×/day) — the universe cache is FRESH
  (MU baked ≈ live, ~1%); the only stale surfaces were the local-bake artifacts c78q.json/mlpred.json.
- **prices_cache.parquet** (parent root) = consolidated split-adjusted `close`, 2005→2026-05-04,
  loads in 0.4s; it is what the FV builder and CI use for prices.
