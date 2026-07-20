"""One-line CLI for the monthly manual ISM update (10-second step).

Usage:
    python update_ism.py 53.3 2026-06              # manufacturing PMI
    python update_ism.py --svcs 54.0 2026-06       # services PMI
    python update_ism.py 53.3 2026-06 --svcs 54.0 2026-06   # both at once

Writes/merges macro_baked.json (committed). The bake's ISM chain prefers the
fresher period per component between this file and manual_macro.json (the
grounded Gemini fetch), so a manual entry immediately overrides a stale fetch.
Remember to commit + push: the nightly CI bake reads the repo copy.
"""
import json
import os
import re
import sys
from datetime import date

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "macro_baked.json")


def die(msg):
    print(f"ERROR: {msg}\n\n{__doc__}", file=sys.stderr)
    raise SystemExit(1)


def parse_args(argv):
    out = {}
    key = "ism_mfg"
    vals = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--svcs":
            if vals:
                out[key] = vals
            key, vals = "ism_svcs", []
        else:
            vals.append(a)
        i += 1
    if vals:
        out[key] = vals
    for k, v in out.items():
        if len(v) != 2:
            die(f"{k}: expected <value> <YYYY-MM>, got {v}")
        try:
            val = float(v[0])
        except ValueError:
            die(f"{k}: value '{v[0]}' is not a number")
        if not (30 <= val <= 70):
            die(f"{k}: {val} outside the plausible PMI band [30, 70]")
        if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", v[1]):
            die(f"{k}: period '{v[1]}' is not YYYY-MM")
        out[k] = (val, v[1])
    return out


def main():
    updates = parse_args(sys.argv[1:])
    if not updates:
        die("no values given")
    data = {}
    if os.path.exists(PATH):
        data = json.load(open(PATH))
    label = {"ism_mfg": "Manufacturing", "ism_svcs": "Services"}
    for k, (val, period) in updates.items():
        data[k] = {
            "value": val,
            "period": period,
            "entered": date.today().isoformat(),
            "source": f"ISM {label[k]} PMI (manual entry)",
        }
        print(f"{k}: {val} for {period} (entered {data[k]['entered']})")
    json.dump(data, open(PATH, "w"), indent=2)
    print(f"wrote {PATH} — commit + push so the nightly bake picks it up")


if __name__ == "__main__":
    main()
