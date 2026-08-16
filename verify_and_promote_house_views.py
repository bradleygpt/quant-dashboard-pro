#!/usr/bin/env python3
"""
verify_and_promote_house_views.py

Verifies candidate macro house-view figures against their cited source documents
(PDF or HTML), then promotes only verified figures into the live
macro_house_views.json that the Forecast Consensus panel reads.

HARD RULE (Akribeia data-integrity policy): a figure is promoted ONLY if its
verbatim quote is found, near-verbatim, in the fetched source text. No figure is
ever written on the strength of an LLM's belief about what a source says.
Unverifiable figures stay in the candidates file flagged for manual review —
never silently dropped, never silently promoted.

SCHEMA (corrected 2026-08-15 against the real repo files; the original draft was
written against a guessed schema and matched neither file).

  macro_house_views_candidates.json
    {generated_utc, _warning, candidates: [
       {id, name, kind, status, as_of, prior_as_of, source, url,
        inflation_basis?, notes?,
        values: {metric: {year: {value, quote}}}}
    ]}
  Note: `source` is the REPORT TITLE, `name` is the display name, and the link
  field is `url` — not report_title/report_url. Figures are a nested
  metric->year map, not a flat list, and carry no per-figure verified/notes keys.

  macro_house_views.json  (THE FILE THE PANEL READS)
    {_note, _schema, forecasters: [
       {id, name, kind, as_of, source, url, notes, values: {metric: {year: NUMBER}}}
    ]}
  macro_forecasts.load_house_views() reads data["forecasters"] and skips any row
  missing `id` or `values`. Live values are BARE NUMBERS: no nested
  {value, quote, source_url} object. Writing the richer shape would silently
  break the panel, so verification metadata stays in the candidates file and the
  live file keeps its schema exactly.

PROVENANCE ON PARTIAL REFRESH: a candidate usually restates only some of a
forecaster's metrics. Promoting them bumps the row's as_of to the new report,
which would misdate any metric carried over from the previous one. Retained
metrics are therefore listed explicitly in the row's `notes` rather than left to
look like they came from the new report.

Usage:
    python verify_and_promote_house_views.py \
        --candidates macro_house_views_candidates.json \
        --live macro_house_views.json \
        [--dry-run] [--only ID[,ID...]] [--url-override ID=URL]

Exit codes: 0 all checked figures verified; 2 one or more need manual review.
"""

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Missing dependency: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AkribeiaHouseViewsBot/1.0; "
                  "+internal research tool, not for redistribution)"
}

# Pages that are really a paywall/login/consent interstitial return HTTP 200 with
# perfectly good text — none of which is the report. Matching a quote against one
# is impossible, but the FETCH still "succeeds", so the distinction between "the
# source does not say this" and "we never saw the source" would be lost. Flagged
# separately so a human sees why it failed.
INTERSTITIAL_MARKERS = (
    "sign in", "log in", "login", "subscribe to continue", "create an account",
    "access denied", "enable javascript", "are you a robot", "captcha",
)


def normalize(text: str) -> str:
    """Collapse whitespace/punctuation noise so PDF-extraction artifacts
    (line wraps, hyphenation, odd spacing) don't cause false negatives."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace(" ", " ")
    text = re.sub(r"-\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def looks_like_interstitial(text: str, url: str) -> str | None:
    """Explain WHY a quote was not found — never used to skip the check.

    An earlier version gated verification on these markers and was wrong: nearly every
    publisher puts "Sign In" in its nav, so a perfectly public page trips the match.
    It condemned yardeniquicktakes.com unread, whose article text plainly contains
    "we are raising our year-end s&p 500 target from 7700 to 8250" — a verifiable
    figure, rejected on a heuristic. Verification now always runs first; this only
    labels a failure afterwards, so a false positive costs a wrong label, not a
    wrongly-blocked figure.
    """
    n = normalize(text)
    if len(n) < 600:
        # A real wall serves almost nothing; a preview that carries the number is longer.
        hit = next((m for m in INTERSTITIAL_MARKERS if m in n), None)
        return (f"page is {len(n)} chars and looks like a login/consent wall "
                f"(matched {hit!r})") if hit else f"fetched text is nearly empty ({len(n)} chars)"
    return None


def fetch_text(url: str) -> tuple[str, str]:
    """Fetch a URL, return (extracted plain text, final URL after redirects).

    Some publishers reject the self-identifying bot UA with 403/406 while serving
    the same public page to any browser (goldmansachs.com does exactly this:
    403 for the bot string, 200 + 627KB for a plain browser string). One retry
    with a standard UA, and the substitution is printed so it is never invisible.
    This is a UA string on a public, unauthenticated page — it is NOT a way past
    a login or paywall, and pages that need credentials stay unread by design."""
    resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    if resp.status_code in (403, 406):
        print(f"  note: {resp.status_code} for the bot UA; retrying once as a browser")
        resp = requests.get(url, headers={**HEADERS, "User-Agent": BROWSER_UA,
                                          "Accept-Language": "en-US,en;q=0.9"},
                            timeout=30, allow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")

    if "pdf" in content_type.lower() or resp.url.lower().endswith(".pdf"):
        if pdfplumber is None:
            raise RuntimeError("pdfplumber not installed; cannot verify PDF source")
        # NamedTemporaryFile, not a hardcoded /tmp path: the original draft wrote
        # /tmp/_hv_fetch.pdf, which does not exist on Windows where this runs.
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)
        try:
            parts = []
            with pdfplumber.open(tmp_path) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
            return "\n".join(parts), resp.url
        finally:
            tmp_path.unlink(missing_ok=True)

    if BeautifulSoup is not None:
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator=" "), resp.url
    return re.sub(r"<[^>]+>", " ", resp.text), resp.url


# A quote can pass verification while not stating a POINT estimate: "above 3
# percent", "around 2 percent", "near current levels". The number is genuinely in
# the source, so the hard rule is satisfied, but storing it as a bare point value
# drops the qualifier. macro_house_views.json already has a convention for this
# (its _note: ranges "stored as the midpoint with the exact published range
# preserved in 'notes'"), so qualified figures carry their verbatim quote into
# the row's notes instead of being silently flattened.
QUALIFIERS = ("above", "below", "at least", "at most", "around", "about", "near",
              "more than", "less than", "upwards of", "in excess of", "roughly",
              "close to", "over ", "under ")


def quote_qualifier(quote: str, value) -> str | None:
    """Return the qualifier word if the quote hedges the number rather than
    stating it outright. Looks only in the window around the number itself, so a
    hedge elsewhere in a long sentence doesn't flag an otherwise exact figure."""
    nq = normalize(quote)
    num = str(value).rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
    # EVERY occurrence, not the first. Goldman's quote reads "...cutting its policy
    # rate in 2027 ... expects US GDP to expand around 2% this year": find() landed
    # on the 2 inside "2027" and reported no hedge, so a genuinely qualified figure
    # would have been stored as a flat point value. A false negative here defeats
    # the whole check, so any occurrence carrying a qualifier counts.
    hits = [m.start() for m in re.finditer(rf"(?<!\d){re.escape(num)}(?!\d)", nq)]
    if not hits:
        return None
    # prefer occurrences that are actually the figure (followed by % / percent)
    figure_like = [i for i in hits if re.match(r"[\d.]*\s*(%|percent)", nq[i + len(num):i + len(num) + 12])]
    for i in (figure_like or hits):
        window = nq[max(0, i - 28):i]
        for q in QUALIFIERS:
            if q in window:
                return q.strip()
    return None


# A quote can be perfectly verbatim and still be the WRONG KIND OF NUMBER. The
# 2026-08-01 run drafted these as Yardeni's 2026 forecasts:
#   gdp       "The US economy expanded at a 1.5% annualized rate in Q2-2026..."
#   inflation "Headline PCED inflation declined 0.1% m/m in June, but was still up 3.7% y/y"
# Both are realized prints — a Q2 GDP release and a June PCE reading — not forecasts.
# Quote-matching alone would have waved them through into a forward-looking panel, so
# a figure whose quote reads as backward-looking is refused and sent to manual review.
BACKWARD_MARKERS = (
    "expanded at", "grew at", "rose at", "increased at", "declined", "fell ", "was up",
    "were up", "was down", "came in at", "printed at", "annualized rate in",
    "m/m in", "y/y in", "reported", "last month", "in the second quarter",
    "in the first quarter", "in the third quarter", "in the fourth quarter",
)
_QUARTER = re.compile(r"\bq[1-4][- ]?(?:19|20)\d\d\b")


def looks_backward_looking(quote: str) -> str | None:
    """Return the marker if the quote describes realized data rather than a forecast."""
    n = normalize(quote)
    if _QUARTER.search(n):
        return "cites a specific quarter's realized print"
    for m in BACKWARD_MARKERS:
        if m in n:
            return f"past-tense/realized wording ({m.strip()!r})"
    return None


def loosen(t: str) -> str:
    t = t.replace("%", " percent")
    t = re.sub(r"[^\w\s.]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def quote_is_verified(quote: str, source_text: str, min_len: int = 30) -> bool:
    """Exact normalized substring match, then a percent/punctuation-loosened
    match. Quotes shorter than min_len are refused outright: a short generic
    phrase can match by chance and would rubber-stamp an unchecked number."""
    nq, ns = normalize(quote), normalize(source_text)
    if not nq or len(nq) < min_len:
        return False
    if nq in ns:
        return True
    return loosen(nq) in loosen(ns)


def load_json(path: Path) -> dict:
    if not path.exists():
        print(f"ERROR: {path} not found.", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


# macro_house_views.json is hand-curated and reviewed through git diffs, and it
# writes the innermost {year: value} maps inline. A plain indent=2 dump expands
# every one of them, so changing three numbers produced a 101-line diff that
# buries the actual edit. This re-collapses those leaf maps to match the file's
# existing style: a reviewer then sees only the figures that really changed.
_LEAF = re.compile(
    r'\{\s*\n\s*("(?:19|20)\d\d":\s*-?[\d.]+)'
    r'(?:,\s*\n\s*("(?:19|20)\d\d":\s*-?[\d.]+))*\s*\n\s*\}')


def _collapse_leaf(m: re.Match) -> str:
    pairs = re.findall(r'"(?:19|20)\d\d":\s*-?[\d.]+', m.group(0))
    return "{" + ", ".join(pairs) + "}"


def save_json_curated(path: Path, data: dict) -> None:
    """Write with indent=2 but keep year->value leaf maps on one line."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(_LEAF.sub(_collapse_leaf, text) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--live", required=True)
    ap.add_argument("--dry-run", action="store_true", help="Report only; write nothing")
    ap.add_argument("--only", default="", help="Comma-separated candidate ids to check")
    ap.add_argument("--url-override", action="append", default=[],
                    metavar="ID=URL",
                    help="Replace a candidate's url for this run (e.g. a corrected "
                         "link). Recorded in the report so the substitution is visible.")
    args = ap.parse_args()

    cand_path, live_path = Path(args.candidates), Path(args.live)
    cand = load_json(cand_path)
    live = load_json(live_path)

    if "forecasters" not in live:
        print("ERROR: live file has no 'forecasters' array — this is not the file "
              "macro_forecasts.load_house_views() reads. Refusing to write.", file=sys.stderr)
        return 1
    by_id = {f.get("id"): f for f in live["forecasters"] if isinstance(f, dict)}

    overrides = {}
    for ov in args.url_override:
        if "=" not in ov:
            print(f"ERROR: --url-override must be ID=URL (got {ov!r})", file=sys.stderr)
            return 1
        k, v = ov.split("=", 1)
        overrides[k.strip()] = v.strip()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    checked = verified = failed = 0
    promoted, unreachable, no_figures = [], [], []

    for entry in cand.get("candidates", []):
        cid = entry.get("id") or "UNKNOWN"
        if only and cid not in only:
            continue
        name = entry.get("name", cid)
        as_of = entry.get("as_of", "")
        url = overrides.get(cid) or entry.get("url", "")
        values = entry.get("values") or {}

        print(f"\n=== {name} [{cid}] ({as_of}) ===")
        if cid in overrides:
            print(f"URL OVERRIDE: {url}")
        else:
            print(f"URL: {url[:120]}")

        n_figs = sum(len(y) for y in values.values())
        if not n_figs:
            print("  NO FIGURES drafted — nothing to verify or promote.")
            no_figures.append(cid)
            continue
        if not url:
            print("  SKIP: no url.")
            unreachable.append((cid, "no url"))
            continue

        try:
            text, final_url = fetch_text(url)
        except Exception as e:
            why = f"{type(e).__name__}: {str(e)[:100]}"
            print(f"  FETCH FAILED: {why}")
            print(f"  {n_figs} figure(s) left UNVERIFIED. No promotion.")
            unreachable.append((cid, f"fetch failed: {type(e).__name__}"))
            failed += n_figs
            checked += n_figs
            # Mark them explicitly. Leaving `verified` unset would read as "not yet
            # looked at" when it was in fact looked at and could not be reached —
            # the policy is never silently dropped, and an absent flag is silent.
            for years in values.values():
                for fig in years.values():
                    fig["verified"] = False
                    fig["notes"] = f"FETCH FAILED ({why}) as of {now} — manual review"
            continue

        bad = looks_like_interstitial(text, final_url)
        if bad:
            print(f"  WARNING: {bad}")
            print(f"  final URL: {final_url[:120]}")
            print("  checking anyway — a page that carries the number is verifiable "
                  "even if it also shows a paywall banner.")

        ok_figs = {}
        qualified = []
        for metric, years in values.items():
            for year, fig in years.items():
                checked += 1
                quote = fig.get("quote", "")
                val = fig.get("value")
                backward = looks_backward_looking(quote)
                if backward:
                    # refused even if the quote matches: a realized print is not a forecast
                    failed += 1
                    fig["verified"] = False
                    fig["notes"] = (f"NOT A FORECAST — {backward} — as of {now}; "
                                    f"realized data must not enter a forecast panel")
                    print(f"  [REFUSED] {metric} {year} = {val}  NOT A FORECAST: {backward}")
                    continue
                if quote_is_verified(quote, text):
                    verified += 1
                    fig["verified"] = True
                    fig["notes"] = f"Verified {now} against {final_url}"
                    ok_figs.setdefault(metric, {})[year] = val
                    qual = quote_qualifier(quote, val)
                    if qual:
                        qualified.append((metric, year, qual, quote.strip()))
                        print(f"  [OK*]  {metric} {year} = {val}   "
                              f"QUALIFIED by {qual!r} — verbatim quote kept in notes")
                    else:
                        print(f"  [OK]   {metric} {year} = {val}")
                else:
                    failed += 1
                    fig["verified"] = False
                    reason = (f"UNREADABLE SOURCE ({bad})" if bad else "QUOTE NOT FOUND in source")
                    fig["notes"] = f"{reason} as of {now} — manual review"
                    print(f"  [FAIL] {metric} {year} = {val}  "
                          f"({'source unreadable' if bad else 'quote not located'})")

        if not ok_figs:
            continue

        promoted.append(cid)
        if args.dry_run:
            continue

        row = by_id.get(cid)
        if row is None:                      # new forecaster: build a schema-shaped row
            row = {"id": cid, "name": name, "kind": entry.get("kind", "house"),
                   "values": {}}
            live["forecasters"].append(row)
            by_id[cid] = row

        prior_as_of = row.get("as_of")
        retained = [f"{m} {y}" for m, ys in (row.get("values") or {}).items()
                    for y in ys if y not in ok_figs.get(m, {})]

        vals = row.setdefault("values", {})
        for metric, years in ok_figs.items():
            vals.setdefault(metric, {}).update(years)   # only verified figures land

        row["as_of"] = as_of
        row["source"] = entry.get("source", row.get("source", ""))
        row["url"] = final_url
        note = (entry.get("notes") or "").strip()
        for metric, year, qual, quote in qualified:
            # verbatim, so the hedge survives into what a reader of the panel sees
            note = f'{note} {metric} {year} is qualified ({qual}): "{quote}"'.strip()
        if retained and prior_as_of and prior_as_of != as_of:
            carry = (f"Refreshed to {as_of} from {final_url}; "
                     f"{', '.join(retained)} retained from the {prior_as_of} report.")
            note = f"{note} {carry}".strip() if note else carry
        if note:
            row["notes"] = note

    print("\n" + "=" * 60)
    print(f"Checked: {checked}   Verified: {verified}   Failed: {failed}")
    print(f"Promoted: {promoted or 'NONE'}")
    if no_figures:
        print(f"No figures drafted: {no_figures}")
    if unreachable:
        print("Source not readable (distinct from 'source disagrees'):")
        for cid, why in unreachable:
            print(f"  {cid}: {why}")

    if args.dry_run:
        print("\nDRY RUN — no files written.")
        return 2 if failed else 0

    if promoted:
        save_json_curated(live_path, live)
        print(f"\nWrote verified figures to {live_path}")
    save_json(cand_path, cand)
    print(f"Updated verification status in {cand_path}")

    if failed:
        print(f"\n{failed} figure(s) need manual review — left unverified, not promoted.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
