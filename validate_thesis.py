"""Validate a baked thesis JSON against the PROMPT_PACK contract (anti-slop gate).

Usage: python validate_thesis.py theses/baked/<file>.json [...]
Exit 0 = all pass; nonzero = violations printed. Run before committing a thesis.

Mechanical checks only — genuine opposition and crux quality remain generator
discipline (see theses/PROMPT_PACK.md).
"""
import json
import re
import sys

# Fillers banned unless the SAME sentence carries a number and a comparison word.
BANNED = [
    "strong fundamentals", "attractive valuation", "well-positioned", "well positioned",
    "best-in-class", "robust growth", "solid execution", "compelling opportunity",
    "poised to benefit", "strong track record",
]
COMPARE = re.compile(r"(vs\.?|than|above|below|versus|×|x\b|%|percentile|rank)", re.I)
HAS_NUM = re.compile(r"\d")


def check(path):
    errs = []
    try:
        t = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return [f"unparseable JSON: {e}"]

    for k in ("ticker", "generated_at", "snapshot_hash", "inputs", "bull", "bear", "synthesis", "grading"):
        if k not in t:
            errs.append(f"missing top-level key: {k}")
    if errs:
        return errs

    for side in ("bull", "bear"):
        s = t[side]
        for k in ("claim", "pillars", "catalysts", "falsifiers"):
            if k not in s:
                errs.append(f"{side}: missing {k}")
        claim = s.get("claim", "")
        if not isinstance(claim, str) or not (20 <= len(claim) <= 300):
            errs.append(f"{side}.claim: must be one sentence, 20-300 chars (got {len(str(claim))})")
        pillars = s.get("pillars") or []
        if not (3 <= len(pillars) <= 4):
            errs.append(f"{side}.pillars: need 3-4, got {len(pillars)}")
        for i, p in enumerate(pillars):
            if not HAS_NUM.search(str(p)):
                errs.append(f"{side}.pillars[{i}]: cites no dossier number")
        if not (2 <= len(s.get("catalysts") or []) <= 4):
            errs.append(f"{side}.catalysts: need 2-4")
        if not (2 <= len(s.get("falsifiers") or []) <= 3):
            errs.append(f"{side}.falsifiers: need 2-3 (for its OWN side)")
        blob = " ".join([claim] + [str(x) for x in pillars])
        for sent in re.split(r"(?<=[.;])\s+", blob):
            low = sent.lower()
            for b in BANNED:
                if b in low and not (HAS_NUM.search(sent) and COMPARE.search(sent)):
                    errs.append(f"{side}: banned filler '{b}' without number+comparison: \"{sent[:90]}\"")

    syn = t["synthesis"]
    crux = syn.get("crux_variables") or []
    if not (1 <= len(crux) <= 2):
        errs.append(f"synthesis.crux_variables: need 1-2, got {len(crux)}")
    if not isinstance(syn.get("divergence_summary"), str) or len(syn.get("divergence_summary", "")) < 50:
        errs.append("synthesis.divergence_summary: missing or too short (<50 chars)")

    g = t["grading"]
    for h in ("h3m", "h6m", "h12m"):
        if h not in g:
            errs.append(f"grading.{h}: key must exist (null until graded)")
    return errs


def main():
    paths = sys.argv[1:]
    if not paths:
        print(__doc__, file=sys.stderr)
        raise SystemExit(1)
    bad = 0
    for p in paths:
        errs = check(p)
        if errs:
            bad += 1
            print(f"FAIL {p}")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"OK   {p}")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
