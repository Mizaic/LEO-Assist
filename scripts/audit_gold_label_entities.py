#!/usr/bin/env python3
"""Sweep every GoldLabel and audit each entity for self-consistency.

Why this script exists
----------------------
`scripts/validate_backfill_snomed.py` validates LLM-PROPOSED additions
before they enter the gold set. It does NOT inspect entities that are
ALREADY persisted on a GoldLabel.

On 2026-04-17 a manual seed script wrote 5+ GoldLabels with `label =
"finding"` while the attached SNOMED concept was actually a
`(qualifier value)` (e.g. "normal" -> 17621005 "Normal (qualifier
value)"). These bypassed the validator entirely and would have taught
the NER model that a qualifier-value concept is the right answer for a
finding-class span.

This script is the missing audit pass: it pulls every GoldLabel from
the Knowledge Graph and runs `audit_existing_entity()` on every entity
in `entities_json`, producing a JSONL report of issues plus an
aggregate summary keyed by issue code and severity.

The audit is OFFLINE (no terminology service call) -- it only checks
self-consistency of stored entity payloads.

Outputs
-------
data/audit/gold_label_entity_audit_<UTC-timestamp>.jsonl
data/audit/gold_label_entity_audit_<UTC-timestamp>.summary.json

Usage
-----
    .venv/bin/python scripts/audit_gold_label_entities.py
    .venv/bin/python scripts/audit_gold_label_entities.py --severity critical
    .venv/bin/python scripts/audit_gold_label_entities.py --source manual_gold_seed_2026_04_17

Design Controls: DI-LEO-AI-186, DO-LEO-AI-185, R-LEO-AI-180,
                 VT-LEO-AI-180.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

from libs.training.gold_label_snomed_check import (  # noqa: E402
    ENTITY_AUDIT_ISSUE_CODES,
    audit_gold_label_entities,
)

logger = logging.getLogger("audit_gold_label_entities")

_SEVERITY_RANK = {"clean": 0, "info": 1, "warning": 2, "critical": 3}


def main() -> int:
    args = _parse_args()
    _configure_logging(args.verbose)

    rows = _fetch_labels(args)
    logger.info("audit: fetched %d GoldLabels", len(rows))

    out_dir = _REPO_ROOT / "data" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"gold_label_entity_audit_{ts}.jsonl"
    summary_path = out_dir / f"gold_label_entity_audit_{ts}.summary.json"

    min_rank = _SEVERITY_RANK.get(args.severity, 0)
    issue_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    labels_with_issues = 0
    total_entities = 0
    total_with_issues = 0

    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            label_id = row.get("label_id") or ""
            entities_json = row.get("entities_json") or ""
            results = audit_gold_label_entities(label_id, entities_json)
            total_entities += len(results)

            label_issues = [r for r in results if not r.is_clean]
            if not label_issues:
                continue
            labels_with_issues += 1

            for r in label_issues:
                severity_counts[r.severity] += 1
                for code in r.issues:
                    issue_counts[code] += 1
                if _SEVERITY_RANK.get(r.severity, 0) < min_rank:
                    continue
                total_with_issues += 1
                payload = {
                    "label_id": r.label_id,
                    "entity_index": r.entity_index,
                    "label_text": row.get("text"),
                    "label_source": row.get("source"),
                    **r.to_dict(),
                }
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    summary = {
        "generated_at": ts,
        "input_labels": len(rows),
        "input_entities": total_entities,
        "labels_with_any_issue": labels_with_issues,
        "entities_emitted_to_report": total_with_issues,
        "min_severity_filter": args.severity,
        "issue_counts": dict(issue_counts),
        "severity_counts": dict(severity_counts),
        "issue_descriptions": ENTITY_AUDIT_ISSUE_CODES,
        "filters": {
            "source": args.source,
            "exclude_source": list(args.exclude_source),
            "limit": args.limit,
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    logger.info("audit: report=%s", out_path)
    logger.info("audit: summary=%s", summary_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _fetch_labels(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Pull GoldLabel rows from the Knowledge Graph honouring filters."""
    from libs.neo4j_client.client import KnowledgeGraphClient

    where_clauses = ["g.entities_json IS NOT NULL"]
    params: dict[str, Any] = {}

    if args.source:
        where_clauses.append("g.source = $source")
        params["source"] = args.source
    if args.exclude_source:
        where_clauses.append("NOT (g.source IN $exclude_source)")
        params["exclude_source"] = list(args.exclude_source)

    cypher = f"""
    MATCH (g:GoldLabel)
    WHERE {' AND '.join(where_clauses)}
    RETURN g.label_id AS label_id,
           g.text AS text,
           g.entities_json AS entities_json,
           g.source AS source,
           toString(g.updated_at) AS updated_at
    ORDER BY g.updated_at DESC
    """
    if args.limit > 0:
        cypher += "\n    LIMIT $limit"
        params["limit"] = int(args.limit)

    client = KnowledgeGraphClient()
    with client.session() as session:
        return [dict(r) for r in session.run(cypher, params)]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Audit every GoldLabel for entity-level self-consistency "
            "(qualifier-value-on-clinical-label, semantic-tag drift, "
            "blocked-assertion-with-concept, missing fields)."
        ),
    )
    p.add_argument(
        "--severity",
        choices=["info", "warning", "critical"],
        default="info",
        help=(
            "Minimum severity to emit to the JSONL report. Aggregate "
            "counts in the summary include ALL issues regardless of "
            "this filter."
        ),
    )
    p.add_argument(
        "--source",
        type=str,
        default=None,
        help="Restrict audit to GoldLabels with this `source` value.",
    )
    p.add_argument(
        "--exclude-source",
        type=str,
        nargs="*",
        default=[],
        help="GoldLabel sources to exclude from the audit.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap on the number of GoldLabels to fetch (0 = no cap).",
    )
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


if __name__ == "__main__":
    sys.exit(main())
