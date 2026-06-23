# c78q / Katalepsis — Earnings Handling & the Micron Call
*As of 2026-06-22 · old top-8 backtest logic · MU reports Wed June 24 (after close)*

---

## The call, up front

**Hold MU through Wednesday's print — but only at equal weight or below. Don't exit; don't run it oversized.**

- **Under the old top-8 logic (12.5% each), MU is already sized correctly — hold it through.** Exiting is an off-model discretionary bet the backtest never tested, and it forfeits the exact thing the strategy is built to capture (post-earnings drift).
- **On the live top-3 book (33% each), trim MU to ~15% into the print.** A 33% single name into the largest implied move in the book is precisely the concentrated tail the evidence says to cut.
- **Micron is a "trim," not an "exit."** It's extended and prone to beat-and-fade (→ trim the size), but it's *cheap on forward earnings* and the model's #1 conviction name (→ don't dodge the event). And it isn't idiosyncratic — it's the bellwether of a memory-cycle-concentrated book.

**The backtest now proves the rule on your own data: dodging earnings *lowers* c78q's CAGR in every variant tested.** (See §5.)

---

## 1 · How c78q actually handles earnings

The backtest **holds straight through every earnings announcement — by design.** Both the old top-8 monthly builder (`_c78q_broad_recompute.py`) and the live top-3/105-day builder (`_c78q_top3_rebake.py`) are pure calendar-driven price compounding: positions are marked daily from one rebalance to the next, earnings dates included. There is **no pre-earnings exit, trim, blackout, or earnings-date exclusion** anywhere in the holding logic.

Earnings enter the strategy **only on the signal side**: the posterior is fed an `e`-cluster **PEAD stream (E3 = post-earnings drift)** and `N1` 8-K events. The strategy is built to be *in* the name through the print to harvest the drift — the posterior has already "voted" on the earnings event.

**Methodological flag:** the headline numbers — **old top-8 monthly: 29.91% CAGR / 1.14 Sharpe / −38% maxDD**; live top-3: 36.2% / 1.04 / −42% — were all generated holding through every report. A live "exit before earnings" rule is a **different, un-backtested strategy** and those numbers no longer apply to it.

**Holdings for reference:**
- Old broad **top-8** (latest, 2026-05-29): MXL, VIAV, INTC, MU, STX, GLW, WDC, REX
- Live **top-3** (target, 2026-06-17): MU (0.893), RKLB (0.893), MXL (0.891) — MU is #1.

---

## 2 · What the evidence says about momentum into earnings

The academic weight of evidence is one-directional:

**You get *paid* to hold a momentum book through earnings.**
- Earnings-announcement premium: ~**61 bps/month (~7%/yr, up to 18%)** for owning announcers (Frazzini-Lamont 2007); ~**11%/yr** across 46 countries (Barber et al. 2013); ~**9.9%/yr** for scheduled announcers (Savor-Wilson 2016).
- Momentum's own alpha is disproportionately realized *at* earnings: ~**25%** of momentum profit lands in the 3-day windows around prints (Jegadeesh-Titman); anomaly returns are ~**6× higher on earnings days** (Engelberg-McLean-Pontiff 2018).
- Surprises mostly **confirm** momentum (winners are systematically positive-surprise names; PEAD runs in the surprise direction).

**But size the single name — the tail is fat.** Earnings days are <2% of trading days but ~**15% of annual variance**; single names routinely gap 5-10%+. The premium is harvested as a *diversified book of announcers*; individual gaps wash out only if you're actually diversified.

**The one evidence-based exception = trim the tail.** Momentum crash risk concentrates in **extended/post-rally, crowded, and *expensive* (glamour) winners**. The "priced-for-perfection torpedo" is specifically a **negative surprise on a high-forward-earnings-multiple name** (glamour stocks fall ~2× harder on a miss — Skinner-Sloan 2002). It is a *valuation/crowding* risk, not a pure-momentum risk.

**Net rule:** don't mechanically dodge announcers; **scale single-name size by implied move + crowding + valuation**; hold post-print in the surprise direction.

---

## 3 · Micron — scored against the rule

Setup (source-dated; figures move fast):
- **Reports Wed June 24, 2026, after close.** Confirmed.
- **Implied move ~14-17%** vs ~4.4% average over the prior four prints — an unusually binary event.
- **+~270-300% YTD, record price (~$1,100-1,210, in flux), P/B ~19** (elevated) — *but* **forward P/E only ~10-12×**.
- **Last two prints: beat-and-fade** — fell on a blowout March 2026 beat; +5%-then-−8% whipsaw on June 2025.
- **HBM4 / NVIDIA allocation is the fundamental swing** (SK Hynix leads HBM4). Supercycle backdrop otherwise excellent (sold-out HBM, ~15-yr-worst memory deficit, +58-75% QoQ DRAM/NAND pricing).
- **Positioning: crowded long** — Strong-Buy consensus, Street-high $1,500 targets, low ~3.3% short interest.

| Trim-the-tail criterion | MU | Verdict |
|---|---|---|
| Extended / post-rally | +270% YTD, record price | **✓ trim** |
| Beat-and-fade history | Fell on last two beats | **✓ trim** (strongest MU-specific signal) |
| Implied move / binary risk | ~14-17% vs 4.4% norm | **✓ trim** |
| Crowded positioning | Euphoric sell-side, low SI | **✓ partial** |
| Expensive / glamour (the torpedo) | Forward P/E ~10-12× = cheap | **✗ — disconfirms full exit** |
| Model conviction | Posterior 0.893, #1 | **✗ — disconfirms full exit** |

**This is why it's a trim, not an exit.** MU lights up the *size-reduction* criteria but fails the glamour-torpedo test (cheap on forward earnings) and is the model's max-conviction name with a real supercycle tailwind.

**On the "outlier" intuition:** half right. MU is an outlier on extension / implied-move / fade behavior (→ trim the *size*), not in a way that justifies a full exit — and it isn't an *idiosyncratic* outlier at all (see §4).

---

## 4 · The whole book — MU isn't idiosyncratic, it's the first domino

The old top-8 is **not eight independent bets.** It's a **memory / AI-hardware cycle book**: **MU + STX (Seagate) + WDC (Western Digital)** are all the DRAM/NAND/storage cycle; **INTC + MXL** are semis; **GLW (Corning) + VIAV** are AI-datacenter optical. The "diversification" that makes hold-through safe is partly illusory for this sleeve — a memory-cycle surprise moves several names at once.

MU prints *first* and is the **sector bellwether.** Its Wednesday reaction is a read-through catalyst for STX and WDC (and the semis) *before they even report.* The real question isn't "exit MU" — it's "how much of my 8 names is effectively one correlated memory bet, and is MU the right size for the first domino?" → hold MU at (not above) equal weight precisely *because* a bad print bleeds into ~3-4 other positions.

---

## 5 · The backtest — dodging earnings HURTS c78q (proven on the 2010-2026 panel)

The old top-8 monthly engine was rebuilt byte-for-byte (**baseline reproduced exactly: 29.91% / 1.143 / −38.02%**). Earnings dates came from **EDGAR 10-K/10-Q filing dates** (the same SEC source the PEAD stream uses; 100% ticker coverage). Coverage: 1,480 held name-months, **477 (32%) carried an earnings event**, 480 events total.

| Variant | CAGR | Sharpe | maxDD | ΔCAGR |
|---|---|---|---|---|
| **Baseline — hold through** | **29.91%** | **1.143** | −38.02% | — |
| Exit [0], redistribute | 28.31% | 1.121 | −37.74% | −1.60pp |
| Exit [0], cash | 28.50% | 1.141 | −36.23% | −1.40pp |
| Exit [−1,+1], redistribute | 29.18% | 1.174 | −38.45% | −0.73pp |
| Exit [−1,+1], cash | 26.74% | 1.131 | −33.47% | −3.16pp |
| Exit [0,+2], redistribute | 28.00% | 1.105 | −42.24% | −1.91pp |
| Exit [0,+2], cash | 26.91% | 1.098 | −38.22% | −3.00pp |

**Attribution:** earnings-window [−1,+1] days are **6.1% of held days but 8.6% of return** — held names earn **0.173%/day around earnings vs 0.119%/day normally (1.45× edge)**, drifting *up* through the print (+0.27% over [−1,+1], +0.52% over [0,+2]).

**Verdict:** every dodge variant loses −0.7 to −3.2pp of CAGR. Earnings days carry disproportionately positive return for these high-posterior names; flattening into earnings forfeits alpha. **Keep holding through.**

**The MU wrinkle in the event data:** MU's last print (2026-02-27 rebalance, posterior 0.94) ran **−18% through the hold** (−8.4% over [−1,+1]) — the live embodiment of the fat tail. So the rule is hold-through (the edge), and MU's recent behavior is exactly why it's the *size-trim* exception, not a rule-break.

Data files: `c78q_earnings_events.csv` (full 480-event history), `c78q_earnings_overlay_results.json`, `_c78q_earnings_overlay.py` (reproducible study).

---

## 6 · Recommendation

- **Top-8 book:** hold MU through; keep it at 12.5% (equal weight); no exit.
- **Top-3 book:** trim MU from ~33% to ~15% into the print; hold the rest through; park the trim in cash or redistribute to RKLB/MXL.
- **After the print:** if it's a confirming beat, hold the drift (PEAD tailwind). MU is not the expensive-name-miss torpedo profile.
- **The rule stands:** the strategy's edge *is* holding through earnings — validated on your own 2010-2026 data. Manage MU through *position size*, not by breaking the hold-through discipline.
