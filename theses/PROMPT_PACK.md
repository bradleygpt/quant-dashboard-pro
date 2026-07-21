# Investment Thesis Prompt-Pack — v1 (2026-07-20; scope reworked 2026-07-21)

**INTERNAL TOOLING ONLY (2026-07-21 rework).** The PRODUCT path is now on-demand
generation in the app: `/api/ai?kind=thesis` (Gemini, same edge function as the AI
Analysis card) with this pack's anti-slop contract adapted into the prompt and
`validate_thesis.py`'s checks ported server-side. No product surface references this
queue. This file + `build_thesis_dossier.py` + `theses/queue|baked` survive as the
internal path for seed/curated theses (source: claude-code) and the grading corpus.

Contract for generating bull/bear theses from a queued dossier. The generator is
Claude Code on Bradley's subscription (zero marginal cost). This file is where "not
slop" is enforced — `validate_thesis.py` mechanically gates part of it; the rest is
generator discipline.

## Pipeline

1. Dossier: `theses/queue/<TICKER>_<YYYYMMDD>.json` — built by `build_thesis_dossier.py <TICKER>`
   (or downloaded from the app's Generate Thesis button and dropped here). The dossier is the
   ONLY input: every number cited in the thesis must come from it. If a needed input is
   "N/A", say so — never invent or fetch elsewhere.
2. Generate per the rules below → write `theses/baked/<TICKER>_<YYYYMMDD>_v1.json`
   (bump `_v2` etc. for regenerations of the same day's dossier).
3. Run `python validate_thesis.py theses/baked/<file>` — fix until it passes.
4. Commit both queue + baked files. The next bake copies baked theses into
   `public/data/theses/` + `theses_index.json`; Stock Detail renders the latest.

## Generation rules (§2.2 of the 2026-07-20 handoff)

- **Two genuinely opposing theses.** Not "great company but risks exist" twice. The bull
  must be a case FOR owning it that would embarrass the bear if right, and vice versa.
- Each side:
  - `claim`: ONE sentence, the core claim. Falsifiable, specific to this company now.
  - `pillars`: 3–4. Every pillar must cite at least one specific dossier number
    (score, growth rate, margin, FV gap, rank...) AND make a claim that could be wrong.
    A pillar that just recites a metric ("revenue grew 23.8% YoY") is invalid — say what
    the number implies and what you're betting it means.
  - `catalysts`: 2–4, each with rough timing ("next 1–2 quarters", "H1 2027").
  - `falsifiers`: 2–3 for its OWN side — concrete observations that would kill THIS thesis
    ("two consecutive quarters of net-margin compression below X%", not "things get worse").
- `synthesis`:
  - `crux_variables`: the 1–2 variables the two cases ACTUALLY disagree on. Not a topic
    list — the specific quantity whose path decides who wins.
  - `divergence_summary`: 2–4 sentences naming where the cases split and what to watch.
- **Style bans** (validator enforces the phrase list): no metric-recitation sentence
  templates; no "strong fundamentals", "attractive valuation", "well-positioned",
  "best-in-class", "robust growth", "solid execution" unless tied to a number AND a
  comparison in the same sentence. No hedging both ways inside one pillar.
- Numbers-only-fed discipline (standing convention): the LLM never does price arithmetic
  beyond simple ratios of dossier numbers, and never reviews earnings without the numbers.

## Output schema (§2.3 — also the post-mortem substrate)

```json
{
  "ticker": "T",
  "generated_at": "YYYY-MM-DDTHH:MM:SS",
  "generator": "claude-code <model-id>",
  "snapshot_hash": "<copied verbatim from the dossier>",
  "books": [ ...inputs.books copied verbatim (A2-addendum Task 3, S5): live-book
             membership AT SNAPSHOT TIME, e.g. {"book":"c78q","label":"Katalepsis",
             "as_of":"2026-07-20"}; [] = off-book. The panel renders it as a chip;
             canonical labels are the dashboard's strategy names (Katalepsis, Aristeia)... ],
  "bull": { "claim": "...", "pillars": ["..."], "catalysts": ["..."], "falsifiers": ["..."] },
  "bear": { "claim": "...", "pillars": ["..."], "catalysts": ["..."], "falsifiers": ["..."] },
  "synthesis": { "crux_variables": ["..."], "divergence_summary": "..." },
  "grading": { "h3m": null, "h6m": null, "h12m": null }
}
```

`grading` stays null at generation. `grade_theses.py` (run at +3/6/12 months) fills each with
`{ "realized_return_pct": x, "winner": "bull"|"bear"|"push", "falsifiers_triggered": [...] }`.

## Post-mortem honesty constraint (§2.4)

Input-stickiness analysis (which dossier inputs predicted the winning side) is meaningless
below ~30–50 graded theses. The schema exists now; DO NOT report stickiness results from
small N.
