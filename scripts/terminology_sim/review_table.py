"""Write a review table (CSV, opens in Excel) of expected codes for a phrase set.

One row per phrase: the recorded code, the wording it matched on, how well
those words fit the phrase, what today's lookup attaches, the best-fitting
alternatives in the knowledge graph, and a draft verdict. The reviewer
columns are left blank; a code only counts as truth once a person fills
them in.

Draft verdicts:
  keep       the recorded code matched the phrase exactly or word for word.
  check      the recorded code matched only part of the phrase.
  change?    a better-fitting alternative exists (shown in alt_1).
  no_code?   nothing in the knowledge graph fits the phrase's words.

Usage:
    python -m scripts.terminology_sim.review_table POOLS.json.gz OUT.csv
        [--sample N] [--seed S] [--hidden]
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

from scripts.terminology_sim.features import Fit, best_fits
from scripts.terminology_sim.pool import Pool, attach, baseline_rank, load_pools
from scripts.terminology_sim.strategies import _norm_tag

_NON_CLINICAL = frozenset(
    {
        "qualifier_value",
        "attribute",
        "record_artifact",
        "environment",
        "staging_scale",
        "ethnic_group",
        "unit",
    }
)
COLUMNS = (
    "case_id",
    "phrase",
    "type",
    "recorded_code",
    "recorded_term",
    "recorded_evidence",
    "recorded_wording",
    "word_fit",
    "today_attaches",
    "today_matches_record",
    "alt_1",
    "alt_2",
    "alt_3",
    "draft",
    "reviewer_decision",
    "reviewer_code",
    "reviewer_notes",
)


def _fsn(pool: Pool) -> dict[str, str]:
    return {h.concept_id: h.fsn for h in pool.exact + pool.fulltext}


def _evidence(pool: Pool, code: str, fits: dict[str, Fit]) -> tuple[str, str, str]:
    exact = [h for h in pool.exact if h.concept_id == code]
    if exact:
        return f"exact ({exact[0].index})", exact[0].matched, "1.00 / 1.00"
    fit = fits.get(code)
    if fit is None:
        return "not found", "", ""
    return "partial words", fit.matched, f"{fit.precision:.2f} / {fit.recall:.2f}"


def _alternatives(pool: Pool, fits: dict[str, Fit], skip: set[str]) -> list[str]:
    tags = {h.concept_id: h.semantic_tag for h in pool.fulltext}
    fsn = _fsn(pool)
    ranked = sorted(
        (
            (f.precision * f.recall, f.recall, f.bm25, cid)
            for cid, f in fits.items()
            if cid not in skip and _norm_tag(tags.get(cid)) not in _NON_CLINICAL
        ),
        reverse=True,
    )
    out = []
    for score, _, _, cid in ranked[:3]:
        f = fits[cid]
        out.append(f"{cid} | {fsn.get(cid, '')} | via '{f.matched}' | fit {score:.2f}")
    return out


def _draft(pool: Pool, code: str, fits: dict[str, Fit]) -> str:
    if pool.case.expect_no_code:
        return "keep (no code)"
    if not code:
        return "check"
    if any(h.concept_id == code for h in pool.exact):
        return "keep"
    fit = fits.get(code)
    if fit and fit.precision >= 1.0 and fit.recall >= 1.0:
        return "keep"
    best = max(
        (f.precision * f.recall for cid, f in fits.items() if cid != code),
        default=0.0,
    )
    mine = fit.precision * fit.recall if fit else 0.0
    if best >= 0.99 and best > mine:
        return "change?"
    if max(best, mine) < 0.34:
        return "no_code?"
    return "check"


def review_row(pool: Pool) -> dict[str, str]:
    case = pool.case
    fits = best_fits(pool)
    fsn = _fsn(pool)
    code = case.expected[0] if case.expected else ""
    evidence, wording, fit = _evidence(pool, code, fits) if code else ("", "", "")
    today = attach(case.phrase, case.tag, baseline_rank(pool, case.tag))
    alts = _alternatives(pool, fits, {code, today or ""})
    return {
        "case_id": case.case_id,
        "phrase": case.phrase,
        "type": case.tag,
        "recorded_code": " ; ".join(case.expected)
        or ("no code" if case.expect_no_code else ""),
        "recorded_term": fsn.get(code, ""),
        "recorded_evidence": evidence,
        "recorded_wording": wording,
        "word_fit": fit,
        "today_attaches": f"{today} | {fsn.get(today, '')}" if today else "nothing",
        "today_matches_record": (
            "yes"
            if (today in case.expected if case.expected else today is None)
            else "no"
        ),
        "alt_1": alts[0] if alts else "",
        "alt_2": alts[1] if len(alts) > 1 else "",
        "alt_3": alts[2] if len(alts) > 2 else "",
        "draft": _draft(pool, code, fits),
        "reviewer_decision": "",
        "reviewer_code": "",
        "reviewer_notes": "",
    }


_ORDER = {"no_code?": 0, "change?": 1, "check": 2, "keep (no code)": 3, "keep": 4}


def write_table(pools: list[Pool], out: Path) -> dict[str, int]:
    rows = sorted(
        (review_row(p) for p in pools),
        key=lambda r: (_ORDER.get(r["draft"], 9), r["phrase"].lower()),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["draft"]] = counts.get(r["draft"], 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pools", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument(
        "--hidden",
        action="store_true",
        help="judge person-made surface forms on SNOMED wording only",
    )
    args = parser.parse_args(argv)
    pools = load_pools(args.pools)
    if args.sample:
        pools = random.Random(args.seed).sample(pools, min(args.sample, len(pools)))
    if args.hidden:
        pools = [p.hidden() for p in pools]
    counts = write_table(pools, args.out)
    print(f"Wrote {sum(counts.values())} rows to {args.out}: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
