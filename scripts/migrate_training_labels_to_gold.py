"""Migrate include=true TrainingLabel records into Knowledge Graph GoldLabel.

This script supports consolidation to a single training source of truth:
GoldLabel + TrainingCandidate on the Knowledge Graph.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.cypher.gold_label_queries import UPSERT_GOLD_LABEL
from libs.cypher.training_candidate_queries import UPSERT_TRAINING_CANDIDATE
from libs.cypher.training_label_queries import GET_TRAINING_LABELS_PAGE
from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient


def _candidate_id(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _fetch_page(session, *, skip: int, limit: int) -> list[dict[str, Any]]:
    rows = session.run(
        GET_TRAINING_LABELS_PAGE,
        source=None,
        include=True,
        search=None,
        skip=skip,
        limit=limit,
    )
    return [dict(row) for row in rows]


def migrate(*, page_size: int, dry_run: bool) -> dict[str, int]:
    patient_client = PatientGraphClient()
    kg_client = KnowledgeGraphClient()
    stats = {"read": 0, "written": 0, "skipped": 0, "failed": 0}
    try:
        skip = 0
        while True:
            with patient_client.session() as patient_session:
                page = _fetch_page(patient_session, skip=skip, limit=page_size)
            if not page:
                break
            stats["read"] += len(page)
            if dry_run:
                skip += page_size
                continue
            with kg_client.session() as kg_session:
                for row in page:
                    try:
                        entities_json = row.get("entities_json") or "[]"
                        entities = json.loads(entities_json)
                        text = str(row.get("text") or "").strip()
                        if not text or not entities:
                            stats["skipped"] += 1
                            continue
                        candidate_id = _candidate_id(text)
                        kg_session.run(
                            UPSERT_TRAINING_CANDIDATE,
                            candidate_id=candidate_id,
                            text=text,
                            entities_json=entities_json,
                            source="migrated_from_training_label",
                            status="completed",
                            schema_version=row.get("schema_version") or "v4",
                        )
                        kg_session.run(
                            UPSERT_GOLD_LABEL,
                            label_id=row["label_id"],
                            text=text,
                            entities_json=entities_json,
                            quality_score=float(row.get("quality_score") or 0.0),
                            source="migrated_from_training_label",
                            verified_by="training_label_migration",
                            candidate_id=candidate_id,
                            schema_version=row.get("schema_version") or "v4",
                        )
                        stats["written"] += 1
                    except Exception:
                        stats["failed"] += 1
            skip += page_size
    finally:
        patient_client.close()
        kg_client.close()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate TrainingLabel(include=true) records to GoldLabel."
    )
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_keyvault_secrets()
    stats = migrate(page_size=max(1, args.page_size), dry_run=args.dry_run)
    print(
        "Migration summary:",
        f"read={stats['read']}",
        f"written={stats['written']}",
        f"skipped={stats['skipped']}",
        f"failed={stats['failed']}",
        f"dry_run={args.dry_run}",
    )
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
