#!/usr/bin/env python3
"""Aggregate the latest detector dry-run by year x cancer-type x SNOMED.

Reads the JSON output from ``run_full_cancer_episode_detection.py`` (dry-run
mode) and prints two tables:

  1. Episode candidates per (year, cancer_type) cell.
  2. SNOMED diagnosis concept counts per cancer_type, with per-episode
     attribution.

Year is derived from ``dx.encounter_date`` when present, otherwise
``ftr.encounter_date``.  ``cancer_type`` is inferred from the candidate's
dx text + site via ``infer_cancer_type_from_dx_text`` so the values match
the canonical NCDA vocabulary.

Usage:
    python scripts/ncda/_summarize_dry_run_by_year_cancer.py \\
        artifacts/ncda_full_run/full_ncda_dry_run_20260430T113047Z.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.oncology.cancer_types import (  # noqa: E402
    CANONICAL_CANCER_TYPES,
    infer_cancer_type_from_dx_text,
    normalise_cancer_type,
)


def _row_year(row: dict) -> str:
    for key in ("dx", "ftr"):
        d = (row.get(key) or {}).get("encounter_date")
        if d:
            return str(d)[:4]
    return "????"


def _row_cancer_type(row: dict) -> str:
    site = row.get("site") or ""
    dx_text = (row.get("dx") or {}).get("text_preview") or ""
    if dx_text:
        ct = infer_cancer_type_from_dx_text(site, dx_text)
        if ct:
            return ct
    return normalise_cancer_type(site)


def _format_table(
    rows_by_year: dict[str, Counter],
    *,
    year_order: list[str],
    types_order: list[str],
) -> str:
    if not types_order:
        return "(no episode candidates)"
    width = max(11, max(len(c) for c in types_order))
    header = "  ".join([f"{'cancer_type':<{width}}"] + [f"{y:>5}" for y in year_order] + [f"{'total':>6}"])
    rule = "-" * len(header)
    lines = [header, rule]
    grand_total = Counter()
    for ct in types_order:
        cells = []
        row_total = 0
        for y in year_order:
            n = rows_by_year[y].get(ct, 0)
            cells.append(f"{n:>5}" if n else f"{'.':>5}")
            row_total += n
            grand_total[y] += n
        lines.append(
            "  ".join([f"{ct:<{width}}"] + cells + [f"{row_total:>6}"])
        )
    lines.append(rule)
    cells = [f"{grand_total[y]:>5}" for y in year_order]
    lines.append("  ".join([f"{'TOTAL':<{width}}"] + cells + [f"{sum(grand_total.values()):>6}"]))
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: _summarize_dry_run_by_year_cancer.py <dry_run_json>",
            file=sys.stderr,
        )
        return 2
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text())
    candidates = payload.get("episode_candidates") or []

    by_year_type: dict[str, Counter] = defaultdict(Counter)
    snomed_by_type: dict[str, Counter] = defaultdict(Counter)
    snomed_label_by_id: dict[str, str] = {}
    cohort_by_type: dict[str, Counter] = defaultdict(Counter)

    for row in candidates:
        year = _row_year(row)
        ct = _row_cancer_type(row)
        by_year_type[year][ct] += 1
        cohort_by_type[ct][row.get("cohort") or "?"] += 1
        for concept in row.get("diagnosis_concepts") or []:
            cid = str(concept.get("concept_id") or concept.get("id") or "").strip()
            if not cid:
                continue
            label = (
                concept.get("concept_name")
                or concept.get("name")
                or concept.get("label")
                or ""
            ).strip()
            if cid and label:
                snomed_label_by_id[cid] = label
            snomed_by_type[ct][cid] += 1

    years = sorted(y for y in by_year_type if y != "????")
    if "????" in by_year_type:
        years.append("????")

    # Order cancer types by canonical vocab, then any extras observed.
    seen = {ct for c in by_year_type.values() for ct in c}
    types_order = [c for c in CANONICAL_CANCER_TYPES if c in seen]
    extras = sorted(seen - set(types_order))
    types_order.extend(extras)

    print()
    print("=" * 80)
    print("DETECTOR DRY-RUN: episode candidates by year x cancer type")
    print(f"Source: {path}")
    print(f"Total candidates: {len(candidates)}")
    print("=" * 80)
    print(_format_table(by_year_type, year_order=years, types_order=types_order))

    print()
    print("=" * 80)
    print("Per-cancer-type breakdown: SNOMED diagnosis concepts (DOCUMENTS edges)")
    print("Counts are episode candidates whose patient has the SNOMED concept.")
    print("=" * 80)
    for ct in types_order:
        cohort_summary = ", ".join(
            f"{coh}={cnt}" for coh, cnt in sorted(cohort_by_type[ct].items())
        )
        n = sum(by_year_type[y].get(ct, 0) for y in by_year_type)
        print(f"\n{ct}  ({n} episodes; cohorts: {cohort_summary})")
        snomed_counts = snomed_by_type.get(ct, Counter())
        if not snomed_counts:
            print("  (no SNOMED concepts attached to these candidates' patients)")
            continue
        for cid, cnt in snomed_counts.most_common():
            label = snomed_label_by_id.get(cid, "<unknown>")
            print(f"  {cnt:>3}  {cid:>12}  {label}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
