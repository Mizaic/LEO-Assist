"""Audit and repair overlong GoldLabel training examples.

Default mode is read-only. Use --apply to:
- create derived sentence/window-level TrainingCandidate + GoldLabel records
- quarantine the overlong parent record so it no longer exports for training

This preserves original reviewer work while stopping partial whole-note labels
from teaching the span categorizer that unreviewed entities are negatives.
"""

from __future__ import annotations

import argparse
import json
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from libs.cypher.gold_label_queries import UPSERT_GOLD_LABEL
from libs.cypher.training_candidate_queries import UPSERT_TRAINING_CANDIDATE
from libs.neo4j_client.client import KnowledgeGraphClient
from libs.training_data.gold_granularity import (
    classify_gold_record,
    derive_sentence_records,
    parse_entities_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = REPO_ROOT / "data" / "training" / "gold_label_backups"


def _load_env() -> None:
    load_dotenv(REPO_ROOT / "secrets" / ".env.secrets", override=False)
    load_dotenv(REPO_ROOT / "secrets" / ".env.config", override=True)
    try:
        from libs.keyvault.loader import load_keyvault_secrets

        load_keyvault_secrets()
    except Exception:
        pass


def _serialise(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialise(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialise(v) for k, v in value.items()}
    return str(value)


def _fetch_completed_gold(kg: KnowledgeGraphClient) -> list[dict[str, Any]]:
    with kg.session() as session:
        return [
            dict(row)
            for row in session.run(
                """
                MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
                WHERE c.status = 'completed'
                  AND g.entities_json IS NOT NULL
                  AND coalesce(g.frozen_golden_set, false) = false
                RETURN
                  g.label_id AS label_id,
                  c.candidate_id AS candidate_id,
                  coalesce(g.text, '') AS text,
                  coalesce(g.entities_json, '[]') AS entities_json,
                  coalesce(g.source, '') AS source,
                  coalesce(g.training_quarantined, false) AS training_quarantined,
                  g.annotation_completeness AS annotation_completeness
                ORDER BY g.created_at ASC
                """
            )
        ]


def _write_backup(kg: KnowledgeGraphClient, run_id: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"{run_id}_backup.json"
    with kg.session() as session:
        rows = [
            _serialise(dict(row))
            for row in session.run(
                """
                MATCH (g:GoldLabel)
                OPTIONAL MATCH (c:TrainingCandidate)-[r:PRODUCED]->(g)
                RETURN g.label_id AS label_id,
                       properties(g) AS gold,
                       c.candidate_id AS candidate_id,
                       properties(c) AS candidate,
                       type(r) AS relationship_type,
                       properties(r) AS relationship
                ORDER BY g.label_id
                """
            )
        ]
    payload = {"repair_run_id": run_id, "records": rows, "record_count": len(rows)}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _candidate_id(run_id: str, parent_label_id: str, window_index: int, text: str) -> str:
    raw = f"{run_id}:{parent_label_id}:{window_index}:{text}".encode("utf-8")
    return "gold-repair-" + hashlib.sha256(raw).hexdigest()


def _label_id(candidate_id: str) -> str:
    return "manual-" + hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()


def _apply_repairs(
    kg: KnowledgeGraphClient,
    rows: list[dict[str, Any]],
    run_id: str,
) -> Counter:
    counts: Counter = Counter()
    repair_source = f"gold_sentence_repair_{run_id[-15:-7]}"
    with kg.session() as session:
        for row in rows:
            _process_repair_row(session, row, run_id, repair_source, counts)
    return counts


def _process_repair_row(
    session: Any,
    row: dict[str, Any],
    run_id: str,
    repair_source: str,
    counts: Counter,
) -> None:
    entities = parse_entities_json(row["entities_json"])
    classification = classify_gold_record(
        row["text"],
        entities,
        training_quarantined=bool(row["training_quarantined"]),
        annotation_completeness=row.get("annotation_completeness"),
    )
    counts[classification.classification] += 1
    if classification.classification != "needs_split":
        return
    derived = derive_sentence_records(
        parent_label_id=row["label_id"],
        parent_candidate_id=row["candidate_id"],
        text=row["text"],
        entities=entities,
        repair_run_id=run_id,
    )
    if not derived:
        _mark_parent_for_review(session, row, run_id, "needs_split_no_entity_window")
        counts["parents_marked_review"] += 1
        return
    for record in derived:
        _write_derived_record(session, row, record, run_id, repair_source)
        counts["derived_records_created"] += 1
    _quarantine_parent(session, row, run_id)
    counts["parents_quarantined"] += 1


def _write_derived_record(
    session: Any,
    parent: dict[str, Any],
    record: dict[str, Any],
    run_id: str,
    repair_source: str,
) -> None:
    cid = _candidate_id(
        run_id,
        parent["label_id"],
        int(record["window_index"]),
        str(record["text"]),
    )
    lid = _label_id(cid)
    entities_json = json.dumps(record["entities"], ensure_ascii=False)
    session.run(
        UPSERT_TRAINING_CANDIDATE,
        candidate_id=cid,
        text=record["text"],
        entities_json=entities_json,
        relation_changes=None,
        source=repair_source,
        status="completed",
        hitl_reason="derived from overlong gold parent",
        hitl_guidance=None,
        schema_version="v4",
    )
    session.run(
        UPSERT_GOLD_LABEL,
        label_id=lid,
        text=record["text"],
        entities_json=entities_json,
        quality_score=None,
        source=repair_source,
        verified_by="gold-repair-script",
        candidate_id=cid,
        schema_version="v4",
    )
    _link_derived_provenance(session, parent, cid, lid, run_id)


def _link_derived_provenance(
    session: Any, parent: dict[str, Any], candidate_id: str, label_id: str, run_id: str
) -> None:
    session.run(
        """
        MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
        MATCH (g:GoldLabel {label_id: $label_id})
        SET c.parent_candidate_id = $parent_candidate_id,
            c.parent_label_id = $parent_label_id,
            c.repair_run_id = $run_id,
            c.annotation_completeness = 'derived_sentence',
            g.parent_candidate_id = $parent_candidate_id,
            g.parent_label_id = $parent_label_id,
            g.repair_run_id = $run_id,
            g.annotation_completeness = 'derived_sentence',
            g.training_quarantined = false
        """,
        candidate_id=candidate_id,
        label_id=label_id,
        parent_candidate_id=parent["candidate_id"],
        parent_label_id=parent["label_id"],
        run_id=run_id,
    )


def _quarantine_parent(session: Any, row: dict[str, Any], run_id: str) -> None:
    session.run(
        """
        MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
        MATCH (g:GoldLabel {label_id: $label_id})
        SET c.training_quarantined = true,
            c.training_quarantine_reason = 'derived_sentence_records_created',
            c.training_quarantine_run_id = $run_id,
            c.annotation_completeness = 'partial_long_context',
            g.training_quarantined = true,
            g.training_quarantine_reason = 'derived_sentence_records_created',
            g.training_quarantine_run_id = $run_id,
            g.annotation_completeness = 'partial_long_context'
        """,
        candidate_id=row["candidate_id"],
        label_id=row["label_id"],
        run_id=run_id,
    )


def _mark_parent_for_review(
    session: Any, row: dict[str, Any], run_id: str, reason: str
) -> None:
    session.run(
        """
        MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
        MATCH (g:GoldLabel {label_id: $label_id})
        SET c.training_quarantined = true,
            c.training_quarantine_reason = $reason,
            c.training_quarantine_run_id = $run_id,
            c.annotation_completeness = 'needs_review',
            g.training_quarantined = true,
            g.training_quarantine_reason = $reason,
            g.training_quarantine_run_id = $run_id,
            g.annotation_completeness = 'needs_review'
        """,
        candidate_id=row["candidate_id"],
        label_id=row["label_id"],
        reason=reason,
        run_id=run_id,
    )


def _audit(rows: list[dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for row in rows:
        classification = classify_gold_record(
            row["text"],
            parse_entities_json(row["entities_json"]),
            training_quarantined=bool(row["training_quarantined"]),
            annotation_completeness=row.get("annotation_completeness"),
        )
        counts[classification.classification] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply repairs.")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup.")
    args = parser.parse_args()

    _load_env()
    run_id = "gold-repair-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    kg = KnowledgeGraphClient()
    try:
        rows = _fetch_completed_gold(kg)
        audit_counts = _audit(rows)
        print("repair_run_id", run_id)
        print("completed_gold_records", len(rows))
        print("audit_counts", json.dumps(dict(audit_counts), sort_keys=True))
        if not args.apply:
            return 0
        if not args.no_backup:
            print("backup_path", _write_backup(kg, run_id))
        repair_counts = _apply_repairs(kg, rows, run_id)
        print("repair_counts", json.dumps(dict(repair_counts), sort_keys=True))
    finally:
        kg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
