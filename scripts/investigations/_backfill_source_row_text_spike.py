"""Stage 1 spike: deterministic source_row_text backfill, dry-run only.

Read-only report against every AppropriatenessRule (status pending_review
or active). For every CONCEPT / DEMOGRAPHIC / OBSERVATION leaf missing
`source_row_text`, tries the exact same matching strategy the wizard uses
client-side (see services/ui/.../SentenceEditor/recommendationTextMatch.ts
and .../HighlightWizard/leafTextMatch.ts), shared via
scripts/investigations/_rule_text_match.py:

  1. exact (case/whitespace/dash-normalised) substring match
  2. token-overlap fallback (score >= 0.5)

No writes. Prints per-guideline and overall counts so we know how many
rules/leaves Stage 1 (pure text matching, no LLM) can clear before any
LLM-assisted or human-queue work is considered.

Run from repo root:
    python scripts/investigations/_backfill_source_row_text_spike.py
    python scripts/investigations/_backfill_source_row_text_spike.py --guideline NG12
    python scripts/investigations/_backfill_source_row_text_spike.py --dump-unmatched out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from scripts.investigations._rule_kg_io import connect, fetch_rule_rows  # noqa: E402
from scripts.investigations._rule_text_match import (  # noqa: E402
    first_matching_span,
    leaf_candidates,
    walk_leaves,
)


@dataclass
class LeafReport:
    rule_id: str
    guideline_id: str
    kind: str
    label: str
    status: str  # "already_set" | "matched" | "unmatched"
    text: str | None = None


@dataclass
class RuleReport:
    rule_id: str
    guideline_id: str
    status: str
    has_text: bool
    leaves: list[LeafReport] = field(default_factory=list)

    @property
    def all_matched(self) -> bool:
        return all(l.status != "unmatched" for l in self.leaves)


def evaluate_rule(
    rule_id: str, guideline_id: str, status: str, logic_json: str | None, text: str | None
) -> RuleReport | None:
    if not logic_json:
        return None
    try:
        tree = json.loads(logic_json)
    except (json.JSONDecodeError, TypeError):
        return None

    report = RuleReport(
        rule_id=rule_id, guideline_id=guideline_id, status=status,
        has_text=bool(text and text.strip()),
    )
    for leaf in walk_leaves(tree):
        kind = (leaf.get("kind") or "").upper()
        if leaf.get("source_row_text"):
            label = leaf.get("source_row_text", "")
            report.leaves.append(LeafReport(rule_id, guideline_id, kind, label, "already_set"))
            continue

        label, candidates = leaf_candidates(leaf)
        span = first_matching_span(text, candidates)
        status_label = "matched" if span else "unmatched"
        report.leaves.append(LeafReport(rule_id, guideline_id, kind, label, status_label, text))

    return report


def print_summary(reports: list[RuleReport]) -> None:
    total_rules = len(reports)
    rules_all_matched = sum(1 for r in reports if r.leaves and r.all_matched)
    rules_with_gaps = sum(1 for r in reports if any(l.status == "unmatched" for l in r.leaves))
    rules_no_leaves = sum(1 for r in reports if not r.leaves)
    rules_no_text = sum(1 for r in reports if not r.has_text and r.leaves)

    all_leaves = [l for r in reports for l in r.leaves]
    missing_leaves = [l for l in all_leaves if l.status != "already_set"]
    matched_leaves = [l for l in missing_leaves if l.status == "matched"]
    unmatched_leaves = [l for l in missing_leaves if l.status == "unmatched"]

    rule_by_id = {r.rule_id: r for r in reports}
    unmatched_no_text = [l for l in unmatched_leaves if not rule_by_id[l.rule_id].has_text]
    unmatched_genuine_gap = [l for l in unmatched_leaves if rule_by_id[l.rule_id].has_text]

    print("=" * 72)
    print("STAGE 1 DETERMINISTIC BACKFILL -- DRY RUN (no writes)")
    print("=" * 72)
    print(f"Rules scanned (schema_version=2, pending_review/active): {total_rules}")
    print(f"  rules with no missing/unmatched leaves already:        {rules_all_matched}")
    print(f"  rules with at least one leaf Stage 1 cannot anchor:    {rules_with_gaps}")
    print(f"  rules with no leaves at all (empty tree):              {rules_no_leaves}")
    print(f"  rules with leaves but NO linked recommendation text:   {rules_no_text}")
    print()
    print(f"Leaves missing source_row_text (total): {len(missing_leaves)}")
    print(f"  auto-fixable now (Stage 1 deterministic match): {len(matched_leaves)}")
    print(f"  needs Stage 2 (LLM-assisted) or human:          {len(unmatched_leaves)}")
    print(f"    of which -- rule has NO text at all (data gap, not a synonym gap): {len(unmatched_no_text)}")
    print(f"    of which -- rule HAS text but term genuinely doesn't anchor:       {len(unmatched_genuine_gap)}")
    print()

    by_kind = Counter((l.kind, l.status) for l in missing_leaves)
    print("By leaf kind:")
    for kind in sorted({k for k, _ in by_kind}):
        matched_n = by_kind.get((kind, "matched"), 0)
        unmatched_n = by_kind.get((kind, "unmatched"), 0)
        print(f"  {kind:12s} matched={matched_n:5d}  unmatched={unmatched_n:5d}")
    print()

    by_guideline: dict[str, Counter] = {}
    for l in missing_leaves:
        by_guideline.setdefault(l.guideline_id, Counter())[l.status] += 1
    print("By guideline:")
    for gid in sorted(by_guideline):
        c = by_guideline[gid]
        print(f"  {gid:20s} matched={c['matched']:5d}  unmatched={c['unmatched']:5d}")
    print()

    if unmatched_genuine_gap:
        print("Sample GENUINE synonym-gap leaves -- text exists, term doesn't anchor")
        print("(these are the Stage-2 LLM-assisted candidates, up to 25):")
        for l in unmatched_genuine_gap[:25]:
            print(f"  [{l.guideline_id}] {l.rule_id}  {l.kind:12s} {l.label!r}")
        print()

    if unmatched_no_text:
        print("Sample NO-TEXT rules -- recommendation not linked (data gap, up to 10 rule ids):")
        for rid in list(dict.fromkeys(l.rule_id for l in unmatched_no_text))[:10]:
            print(f"  [{rule_by_id[rid].guideline_id}] {rid}")


def dump_unmatched(reports: list[RuleReport], out_path: Path) -> None:
    rule_by_id = {r.rule_id: r for r in reports}
    rows = []
    for r in reports:
        for l in r.leaves:
            if l.status != "unmatched" or not rule_by_id[l.rule_id].has_text:
                continue
            rows.append(
                {
                    "rule_id": l.rule_id,
                    "guideline_id": l.guideline_id,
                    "kind": l.kind,
                    "label": l.label,
                    "recommendation_text": l.text,
                }
            )
    out_path.write_text(json.dumps(rows, indent=2))
    print(f"Dumped {len(rows)} unmatched genuine-gap leaves to {out_path}")


def fetch_reports(guideline: str | None) -> list[RuleReport]:
    driver = connect()

    reports: list[RuleReport] = []
    try:
        rows = fetch_rule_rows(driver, guideline)
        print(f"Fetched {len(rows)} rules from Neo4j.\n")
        for row in rows:
            report = evaluate_rule(
                row["rule_id"], row["guideline_id"], row["status"],
                row["logic_json"], row["recommendation_text"],
            )
            if report is not None:
                reports.append(report)
    finally:
        driver.close()
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guideline", default=None, help="Restrict to one guideline id, e.g. NG12")
    parser.add_argument("--dump-unmatched", default=None, help="Write unmatched genuine-gap leaves to this JSON path")
    args = parser.parse_args()

    reports = fetch_reports(args.guideline)
    print_summary(reports)
    if args.dump_unmatched:
        dump_unmatched(reports, Path(args.dump_unmatched))


if __name__ == "__main__":
    main()
