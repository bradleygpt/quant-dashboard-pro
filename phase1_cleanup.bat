@echo off
REM ═══════════════════════════════════════════════════════════════════
REM Phase 1 — Repo Hygiene Cleanup Script (Windows .bat)
REM
REM Run this from: C:\Users\bmhar\Downloads\quant-dashboard-pro\
REM
REM What this does:
REM   1. Untracks the large cache binaries (keeps local copies)
REM   2. Untracks redundant backtest variant JSONs
REM   3. Untracks the unrelated Sales_Analyst_Exercise zip
REM   4. Stages the new .gitignore
REM   5. Shows you what's about to be committed
REM
REM What this does NOT do:
REM   - Delete any local files (cache files stay on disk for the app to use)
REM   - Push to remote (you review and push manually after inspecting)
REM   - Touch any actively used .py source files
REM
REM After running, you should:
REM   1. Inspect with: git status
REM   2. If happy, commit with: git commit -m "Repo hygiene: untrack caches and consolidate backtest variants"
REM   3. Push with: git push origin main
REM ═══════════════════════════════════════════════════════════════════

echo.
echo ============================================================
echo Phase 1: Repo Hygiene Cleanup
echo ============================================================
echo.

REM First, replace the .gitignore
echo [1/6] Installing new .gitignore...
copy /Y .gitignore .gitignore.backup >nul
echo       (backup saved to .gitignore.backup)
echo.

REM Untrack large cache files (keep local copies with --cached)
echo [2/6] Untracking large cache files (local copies preserved)...
git rm --cached prices_cache.parquet 2>nul
git rm --cached edgar_cache.tar.gz 2>nul
git rm --cached fundamentals_cache.json 2>nul
git rm --cached correlations_cache.json 2>nul
git rm --cached indicator_snapshots.json 2>nul
git rm --cached pundits_cache.json 2>nul
git rm -r --cached edgar_cache/ 2>nul
git rm -r --cached __pycache__/ 2>nul
echo.

REM Untrack redundant backtest variant JSONs
echo [3/6] Untracking redundant backtest variants...
git rm --cached backtest_variant_h1a.json 2>nul
git rm --cached backtest_variant_h1b.json 2>nul
git rm --cached backtest_variant_h2.json 2>nul
git rm --cached backtest_variant_h_trail.json 2>nul
git rm --cached backtest_variant_pead.json 2>nul
git rm --cached backtest_variant_regime.json 2>nul
git rm --cached quant_backtest_results_short_2018.json 2>nul
git rm --cached quant_backtest_results_quarterly_full.json 2>nul
echo.

REM Untrack unrelated zip
echo [4/6] Untracking unrelated archives...
git rm --cached Sales_Analyst_Exercise_.zip 2>nul
echo.

REM Untrack the one-off patch script (already applied)
echo [5/6] Untracking one-off patch scripts...
git rm --cached patch_build_cache_universe.py 2>nul
echo.

REM Stage the new .gitignore
echo [6/6] Staging new .gitignore...
git add .gitignore
echo.

echo ============================================================
echo  Cleanup staging complete. Review with: git status
echo ============================================================
echo.
echo Files preserved on disk (still usable by the app):
echo   - prices_cache.parquet
echo   - edgar_cache.tar.gz + edgar_cache/
echo   - fundamentals_cache.json
echo   - correlations_cache.json
echo   - indicator_snapshots.json
echo   - pundits_cache.json
echo.
echo To commit:
echo   git commit -m "Repo hygiene: untrack caches and binary artifacts"
echo.
echo To push:
echo   git push origin main
echo.

pause
