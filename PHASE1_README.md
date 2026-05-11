# Phase 1 — Repo Hygiene

**Goal:** Remove tracked binaries, cache files, and redundant backtest variants from git tracking. The app keeps working — local files stay on disk.

---

## What changes

**Untracked from git (local files preserved):**

| File | Reason |
|---|---|
| `prices_cache.parquet` | 99MB regenerable cache |
| `edgar_cache.tar.gz` | 270MB LFS file, regenerable |
| `edgar_cache/` | Working cache directory |
| `fundamentals_cache.json` | Built by `build_cache.py` |
| `correlations_cache.json` | Built by `build_correlations.py` |
| `indicator_snapshots.json` | Built by `build_indicator_snapshots.py` |
| `pundits_cache.json` | Built by `build_pundits_cache.py` |
| `__pycache__/` | Python compiled bytecode |
| `Sales_Analyst_Exercise_.zip` | Unrelated to dashboard |
| `patch_build_cache_universe.py` | One-off patch script, already applied |

**Backtest variants untracked (consolidate later):**

- `backtest_variant_h1a.json`
- `backtest_variant_h1b.json`
- `backtest_variant_h2.json`
- `backtest_variant_h_trail.json`
- `backtest_variant_pead.json`
- `backtest_variant_regime.json`
- `quant_backtest_results_short_2018.json`
- `quant_backtest_results_quarterly_full.json`

These are research experiments. The canonical current-truth backtest result remains:
- `backtest_results.json` (kept)
- `quant_backtest_results.json` (kept)

If you want any of the untracked variants preserved in git history for reference, they're still in git history — just no longer tracked going forward. To archive them with intent, you can move them to `/docs/archive/` and add that path back to `.gitignore` exceptions, but that's optional.

**New `.gitignore`:**

Replaces the 5-line file with a comprehensive ~70-line version covering Python, venvs, IDE files, Streamlit secrets, the cache files above, OS files, and logs.

---

## How to run this

### Option A: Run the batch script (recommended)

1. Copy these two files into your repo folder `C:\Users\bmhar\Downloads\quant-dashboard-pro\`:
   - `.gitignore` (replaces existing)
   - `phase1_cleanup.bat`

2. Open a terminal in that folder and run:
   ```
   phase1_cleanup.bat
   ```

3. Review what's staged:
   ```
   git status
   ```

4. If happy, commit:
   ```
   git commit -m "Phase 1: Repo hygiene — untrack caches and binary artifacts"
   ```

5. Push:
   ```
   git push origin main
   ```

### Option B: Manual (if you prefer to do each step yourself)

```bash
# Replace .gitignore with the new version (copy the new file in first)

# Untrack large caches (keeps local files)
git rm --cached prices_cache.parquet
git rm --cached edgar_cache.tar.gz
git rm --cached fundamentals_cache.json
git rm --cached correlations_cache.json
git rm --cached indicator_snapshots.json
git rm --cached pundits_cache.json
git rm -r --cached edgar_cache/
git rm -r --cached __pycache__/

# Untrack backtest variants
git rm --cached backtest_variant_h1a.json
git rm --cached backtest_variant_h1b.json
git rm --cached backtest_variant_h2.json
git rm --cached backtest_variant_h_trail.json
git rm --cached backtest_variant_pead.json
git rm --cached backtest_variant_regime.json
git rm --cached quant_backtest_results_short_2018.json
git rm --cached quant_backtest_results_quarterly_full.json

# Untrack misc
git rm --cached Sales_Analyst_Exercise_.zip
git rm --cached patch_build_cache_universe.py

# Stage new gitignore
git add .gitignore

# Review
git status

# Commit
git commit -m "Phase 1: Repo hygiene — untrack caches and binary artifacts"

# Push
git push origin main
```

---

## What this does NOT do

- **Does not delete any local files.** Your cache files stay on disk so the app keeps working. `git rm --cached` removes from git tracking only.
- **Does not push.** You inspect and push manually.
- **Does not touch active `.py` source files.** Zero risk to the running app.
- **Does not rewrite history.** The old commits with the binaries are still in your git history. If you want to permanently purge them from history (to shrink the repo size on disk and on GitHub), that's a separate operation using `git filter-repo` — recommend deferring that to a later session.

---

## After running

Your `git status` should show roughly:

```
Changes to be committed:
  modified:   .gitignore
  deleted:    backtest_variant_h1a.json (and 7 other variants)
  deleted:    correlations_cache.json
  deleted:    edgar_cache.tar.gz
  deleted:    fundamentals_cache.json
  deleted:    indicator_snapshots.json
  deleted:    patch_build_cache_universe.py
  deleted:    prices_cache.parquet
  deleted:    pundits_cache.json
  deleted:    Sales_Analyst_Exercise_.zip
  ... and a bunch of __pycache__ files and edgar_cache/ entries
```

The "deleted" here means "removed from git tracking," not "deleted from disk."

If anything in `git status` looks wrong, run `git restore --staged <filename>` to unstage that file before committing.

---

## Once this is committed

The repo on GitHub will:
- Drop from ~400MB+ (with LFS) to under 50MB
- No longer surface caches and binaries in the file tree
- Have a proper `.gitignore` that prevents future accidents

**This is purely cosmetic and operational. The deployed Streamlit app is unaffected** — Streamlit Cloud rebuilds caches on its own using the `build_cache.py` scripts, so removing them from the repo doesn't break production.

---

## Next: Phase 2

Once this is committed and pushed, ping me and I'll produce Phase 2: the `config.py` and `premium_gate.py` edits to remove the m_heavy/v_heavy presets.
