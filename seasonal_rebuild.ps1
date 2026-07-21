# seasonal_rebuild.ps1 - post-10-Q-season rebuild of the two seasonal data artifacts
# ==================================================================================
# B4 of the outstanding-items handoff (2026-07-20). Per the chain freeze these are
# deliberately NOT on the nightly path - quarterly filings only change once a season,
# so this runs MANUALLY about 4x/year, ~45 days after each quarter end (when the bulk
# of 10-Qs have filed): mid-Feb, mid-May, mid-Aug, mid-Nov. The rebalance checklist
# owns the reminder; the UI owns the guard - both the Stock Detail earnings chart and
# the ETF Center badge STALE when either artifact is older than ~100 days, so a
# forgotten run is loud, not silent (S6: no unguarded operator burden).
#
# What it rebuilds:
#   1. quarterly_deep.json      (this repo)  - EDGAR-deepened quarterly rev/NI history
#                                              feeding the Stock Detail YoY chart.
#                                              Requires a fresh edgar_cache (the SEC
#                                              fetch task refreshes it Tue/Thu/Sat).
#   2. etf_lookthrough.json     (pro-v2)     - ETF look-through scores + AUM census,
#                                              built by quant-historical's builder.
#
# Usage:  powershell -File seasonal_rebuild.ps1
# Then commit what it tells you to commit. Nothing here touches the nightly/Sunday chains.

$ErrorActionPreference = "Stop"
$here  = "C:\Users\bmhar\code\quant-dashboard-react"
$hist  = "C:\Users\bmhar\code\quant-historical"
Set-Location $here

Write-Host "=== 1/2 quarterly_deep.json (EDGAR deep quarterly history) ==="
python build_quarterly_deep.py
if ($LASTEXITCODE -ne 0) { throw "build_quarterly_deep.py failed" }

Write-Host "=== 2/2 etf_lookthrough.json (ETF look-through + AUM) ==="
python "$hist\build_etf_lookthrough.py"
if ($LASTEXITCODE -ne 0) { throw "build_etf_lookthrough.py failed" }

Write-Host ""
Write-Host "DONE. Now commit the refreshed artifacts:"
Write-Host "  1. quant-dashboard-pro (this repo):  git add quarterly_deep.json; commit; push"
Write-Host "     (the nightly CI bake merges it into quarterly.json and clears the badge)"
Write-Host "  2. pro-v2 (web checkout):            git add public/data/etf_lookthrough.json; commit; push"
Write-Host "     (Vercel redeploys; the ETF Center badge clears)"
