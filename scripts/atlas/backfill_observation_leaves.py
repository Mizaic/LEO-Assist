"""Phase 6d -- Backfill report for observation thresholds in existing rules.

Atlas trace:
    UN: UN-26E57FA1
    DI: DI-4C8A09C3
    DO: DO-CB6324A3
    VT: VT-1A7862B9 (execution_status=passed)

What this does:
    Scans every active / pending_review :AppropriatenessRule with its
    source :Recommendation.verbatim, and flags rules whose source text
    contains a numeric threshold on a known observable that the
    current logicJson does NOT encode as an OBSERVATION leaf.

    Produces a CSV diff that a reviewer can triage through the
    editor's normal save-new-version flow. The script deliberately
    **does NOT mutate any rule** -- all fixes go through
    ``decide_rule`` with an audit trail.

Report columns:
    rule_id, recommendation_id, guideline_id, rule_name, status,
    observable_term, observable_snomed_id, operator, value, unit,
    within_days, source_sentence, current_leaf_kind,
    suggested_action

Limitations (intentional for v1):
    - Reference-range language ("raised platelets", "above ULN") is
      out of scope and left as a future iteration.
    - Blood pressure "140/90 mmHg" is not parsed as a pair; the
      reviewer has to expand it into systolic AND diastolic by hand.
    - Trend language ("falling creatinine over 3 months") is out of
      scope.

Usage::

    source .venv/bin/activate
    python -m scripts.atlas.backfill_observation_leaves --dry-run \\
        --output /tmp/observation_backfill_report.csv

    # The --apply flag is deliberately not implemented -- this script
    # is a report generator, not a mutator.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from libs.units.observation_backfill_scanner import (
    ThresholdFinding,
    build_alias_index,
    default_within_days,
    iter_findings,
)

logger = logging.getLogger(__name__)


_FETCH_RULES = """
MATCH (g:Guideline)-[:HAS_RECOMMENDATION]->(rec:Recommendation)
      -[:HAS_RULE]->(rule:AppropriatenessRule)
WHERE rule.status IN ['active', 'pending_review']
RETURN rule.id       AS rule_id,
       rule.name     AS rule_name,
       rule.status   AS rule_status,
       rule.logicJson AS logic_json,
       rec.id        AS recommendation_id,
       rec.verbatim  AS verbatim,
       g.id          AS guideline_id
"""


@dataclass(frozen=True)
class ReportRow:
    """One CSV row: a single observable threshold candidate for a rule."""

    rule_id: str
    recommendation_id: str
    guideline_id: str
    rule_name: str
    status: str
    observable_term: str
    observable_snomed_id: str
    operator: str
    value: str
    unit: str
    within_days: int
    source_sentence: str
    current_leaf_kind: str
    suggested_action: str

    def as_csv_row(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__annotations__}


_CSV_FIELDS = list(ReportRow.__annotations__.keys())


def _existing_observation_leaves(
    node: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        return []
    kind = str(node.get("kind") or "").lower()
    if kind == "observation":
        return [node]
    out: list[dict[str, Any]] = []
    for child in node.get("children") or []:
        if isinstance(child, dict):
            out.extend(_existing_observation_leaves(child))
    return out


def _already_encoded(
    finding: ThresholdFinding, leaves: list[dict[str, Any]]
) -> bool:
    return any(
        str((leaf.get("criterion") or {}).get("snomed_concept_id") or "")
        == finding.observable_id
        for leaf in leaves
    )


def _format_value(value: float | list[float]) -> str:
    if isinstance(value, list):
        return f"{value[0]}..{value[1]}"
    return f"{value}"


def _build_row(
    rule_row: dict[str, Any],
    finding: ThresholdFinding,
    existing: list[dict[str, Any]],
) -> ReportRow:
    already = _already_encoded(finding, existing)
    current_kind = (
        "OBSERVATION (same observable already encoded)"
        if already
        else "CONCEPT (observable appears as presence check only)"
    )
    suggestion = (
        "Reviewer: confirm the existing OBSERVATION leaf matches the "
        "source threshold; otherwise update operator / value / unit."
        if already
        else (
            "Reviewer: open rule, replace the CONCEPT leaf for "
            f"{finding.observable_term} with an OBSERVATION leaf using "
            f"operator={finding.operator}, value={finding.value_canonical}, "
            f"unit={finding.unit_canonical}."
        )
    )
    return ReportRow(
        rule_id=str(rule_row.get("rule_id") or ""),
        recommendation_id=str(rule_row.get("recommendation_id") or ""),
        guideline_id=str(rule_row.get("guideline_id") or ""),
        rule_name=str(rule_row.get("rule_name") or ""),
        status=str(rule_row.get("rule_status") or ""),
        observable_term=finding.observable_term,
        observable_snomed_id=finding.observable_id,
        operator=finding.operator,
        value=_format_value(finding.value_canonical),
        unit=finding.unit_canonical,
        within_days=default_within_days(finding.observable_id),
        source_sentence=finding.source_sentence,
        current_leaf_kind=current_kind,
        suggested_action=suggestion,
    )


def scan_rules(
    rule_rows: list[dict[str, Any]],
    alias_index: dict[str, tuple[str, str]] | None = None,
) -> list[ReportRow]:
    """Pure function: take fetched rule rows, return report rows.

    Extracted so unit tests can feed fixtures without a live Neo4j.
    """
    alias_index = alias_index or build_alias_index()
    report: list[ReportRow] = []
    for rule_row in rule_rows:
        verbatim = str(rule_row.get("verbatim") or "")
        if not verbatim:
            continue
        try:
            logic = json.loads(rule_row.get("logic_json") or "{}")
        except (ValueError, TypeError):
            logic = {}
        existing = _existing_observation_leaves(
            logic.get("logic_tree") if isinstance(logic, dict) else None
        )
        for finding in iter_findings(verbatim, alias_index):
            report.append(_build_row(rule_row, finding, existing))
    return report


def _open_neo4j_session():
    from dotenv import load_dotenv
    from neo4j import GraphDatabase

    root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(root / "secrets" / ".env.config", override=True)
    load_dotenv(root / "secrets" / ".env", override=False)
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI"))
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER"))
    password = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD")
    )
    if not uri or not user or not password:
        raise RuntimeError(
            "Missing Neo4j credentials in secrets/.env*; "
            "set KNOWLEDGE_GRAPH_NEO4J_URI/USERNAME/PASSWORD."
        )
    return GraphDatabase.driver(uri, auth=(user, password))


def _dry_run_summary(report: list[ReportRow]) -> None:
    for row in report[:20]:
        print(
            f"  {row.rule_id}  {row.observable_term}  {row.operator} "
            f"{row.value} {row.unit}  -- {row.suggested_action[:60]}"
        )
    if len(report) > 20:
        print(
            f"  ... and {len(report) - 20} more; pass without --dry-run "
            "to write CSV."
        )


def _write_csv(report: list[ReportRow], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in report:
            writer.writerow(row.as_csv_row())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch rules and print summary; skip CSV write.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("observation_backfill_report.csv"),
        help="CSV output path.",
    )
    parser.add_argument(
        "--guideline",
        default=None,
        help="Optional guideline id to restrict the scan (for smoke tests).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        driver = _open_neo4j_session()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    query = _FETCH_RULES
    params: dict[str, Any] = {}
    if args.guideline:
        query = _FETCH_RULES.replace(
            "MATCH (g:Guideline)",
            "MATCH (g:Guideline {id: $guideline_id})",
        )
        params["guideline_id"] = args.guideline

    with driver.session() as session:
        rows = [dict(r) for r in session.run(query, **params)]
    driver.close()

    report = scan_rules(rows)
    logger.info(
        "Scanned %d rules; %d candidate threshold findings across "
        "%d distinct rules.",
        len(rows),
        len(report),
        len({r.rule_id for r in report}),
    )

    if args.dry_run:
        _dry_run_summary(report)
        return 0

    _write_csv(report, args.output)
    print(
        f"Wrote {len(report)} candidate rows to {args.output}. "
        "This script never mutates rules -- triage through the editor."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
