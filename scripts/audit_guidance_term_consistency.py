#!/usr/bin/env python3
"""Periodic backstop: which free-text terms resolve to more than one
SNOMED concept across the guidance rule library?

The concept-mapping nudge (``services/terminology_api/app/services/
prior_resolutions.py``) helps a reviewer avoid creating a NEW
inconsistency at authoring time by suggesting their own prior pick as
a default. It never auto-applies, so a reviewer is always free to
pick a different code -- correctly, sometimes. This script is the
lower-frequency backstop for whatever drift already happened, or
happens anyway: it walks every rule's logicJson, groups CONCEPT
criteria by normalised term, and flags any term mapped to more than
one distinct SNOMED concept ID.

Read-only. Intended to run on a schedule (e.g. a weekly CI job) rather
than on every request -- see the highlight-to-build wizard plan's
"periodic query... as a lower-frequency backstop" resolution.

Usage:
    python scripts/audit_guidance_term_consistency.py
    python scripts/audit_guidance_term_consistency.py --min-count 2
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets", override=False)

from libs.cypher.terminology_queries import ALL_RULES_WITH_LOGIC_JSON  # noqa: E402
from libs.guidance.logic_tree_terms import (  # noqa: E402
    concept_terms,
    parse_logic_json,
    walk_concept_criteria,
)
from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402

DEFAULT_REPORT_DIR = _REPO_ROOT / "artifacts" / "guidance_term_consistency_audits"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Only report a term-concept pairing seen at least this many "
        "times (default 1 -- report every distinct pairing).",
    )
    return parser.parse_args()


def _fetch_rules() -> list[dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        return client.run(ALL_RULES_WITH_LOGIC_JSON)
    finally:
        client.close()


def _index_terms(rules: list[dict[str, Any]]) -> dict[str, dict[str, dict]]:
    """term -> concept_id -> {preferred_term, count, rule_ids}."""
    index: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rules:
        tree = parse_logic_json(row.get("logic_json"))
        if not tree:
            continue
        rule_id = str(row.get("rule_id") or "")
        for criterion in walk_concept_criteria(tree):
            _index_criterion(index, criterion, rule_id)
    return index


def _index_criterion(
    index: dict[str, dict[str, dict]], criterion: dict, rule_id: str
) -> None:
    concept_id = str(criterion["snomed_concept_id"])
    for term in concept_terms(criterion):
        entry = index[term].setdefault(
            concept_id,
            {
                "preferred_term": criterion.get("preferred_term")
                or criterion.get("term")
                or concept_id,
                "count": 0,
                "rule_ids": [],
            },
        )
        entry["count"] += 1
        if rule_id and rule_id not in entry["rule_ids"]:
            entry["rule_ids"].append(rule_id)


def _find_conflicts(
    index: dict[str, dict[str, dict]], min_count: int
) -> list[dict[str, Any]]:
    conflicts = []
    for term, by_concept in sorted(index.items()):
        eligible = {
            cid: data for cid, data in by_concept.items() if data["count"] >= min_count
        }
        if len(eligible) < 2:
            continue
        conflicts.append(
            {
                "term": term,
                "concept_count": len(eligible),
                "total_occurrences": sum(d["count"] for d in eligible.values()),
                "concepts": [
                    {"snomed_concept_id": cid, **data}
                    for cid, data in sorted(
                        eligible.items(), key=lambda kv: -kv[1]["count"]
                    )
                ],
            }
        )
    return sorted(conflicts, key=lambda c: -c["total_occurrences"])


def _write_report(
    report_dir: Path, conflicts: list[dict[str, Any]], summary: dict
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = report_dir / f"term_consistency_audit_{stamp}.json"
    json_path.write_text(
        json.dumps({"summary": summary, "conflicts": conflicts}, indent=2),
        encoding="utf-8",
    )
    return json_path


def main() -> int:
    args = _parse_args()
    rules = _fetch_rules()
    index = _index_terms(rules)
    conflicts = _find_conflicts(index, args.min_count)
    summary = {
        "rules_scanned": len(rules),
        "distinct_terms_seen": len(index),
        "terms_with_conflicting_codes": len(conflicts),
    }
    report_path = _write_report(args.report_dir, conflicts, summary)
    print(json.dumps({"report": str(report_path), **summary}, indent=2))
    for conflict in conflicts:
        codes = ", ".join(
            f"{c['snomed_concept_id']} ({c['preferred_term']}) x{c['count']}"
            for c in conflict["concepts"]
        )
        print(f'CONFLICT: "{conflict["term"]}" -> {codes}')
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
