"""Feed audit surface-form gaps into the SurfaceFormTask review queue.

Reads surface_form_gaps.json produced by audit_encounter_coding.py and
creates SurfaceFormTask nodes for gaps whose resolver score exceeds the
threshold. Idempotent: existing tasks are skipped.

Usage
-----
    python scripts/feed_audit_gaps_to_surface_forms.py
    python scripts/feed_audit_gaps_to_surface_forms.py --audit-dir path/to/dir
    python scripts/feed_audit_gaps_to_surface_forms.py --threshold 0.85
    python scripts/feed_audit_gaps_to_surface_forms.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.cypher.surface_form_task_queries import (  # noqa: E402
    COUNT_SURFACE_FORM_TASKS,
    UPSERT_SURFACE_FORM_TASK,
    make_surface_form_task_id,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("feed_audit_gaps")

_DEFAULT_AUDIT_DIR = (
    ROOT / "scripts" / "investigations" / "encounter_audit"
)

_CHECK_TASK_EXISTS = """
MATCH (t:SurfaceFormTask)
WHERE t.entity_text = $entity_text
  AND t.suggested_concept = $suggested_concept
  AND t.status IN ['pending', 'approved']
RETURN count(t) AS n
"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _task_exists(session, entity_text: str, suggested_concept: str) -> bool:
    row = session.run(
        _CHECK_TASK_EXISTS,
        entity_text=entity_text,
        suggested_concept=suggested_concept,
    ).single()
    return bool(row and row["n"] > 0)


def _pending_count(session) -> int:
    row = session.run(COUNT_SURFACE_FORM_TASKS, status="pending").single()
    return int(row["total"]) if row else 0


def feed_gaps(
    gaps: list[dict[str, Any]],
    threshold: float,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"created": 0, "skipped": 0, "below_threshold": 0}
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            for gap in gaps:
                score = float(gap.get("resolver_top_score") or 0.0)
                entity_text = str(gap.get("evidence") or "").strip()
                suggested_concept = str(
                    gap.get("resolver_top_concept_id")
                    or gap.get("expected_concept_id")
                    or ""
                ).strip()
                suggested_term = str(
                    gap.get("resolver_top_result") or ""
                ).strip()
                expected_concept = str(
                    gap.get("expected_concept_id") or ""
                ).strip()
                expected_term = str(
                    gap.get("expected_name") or entity_text
                ).strip()

                if not entity_text or not suggested_concept:
                    logger.debug("Skipping gap with missing fields: %r", gap)
                    counts["skipped"] += 1
                    continue

                if score < threshold:
                    counts["below_threshold"] += 1
                    continue

                if dry_run:
                    logger.info(
                        "[DRY RUN] Would create task: %r -> %s (score=%.2f)",
                        entity_text, suggested_concept, score,
                    )
                    counts["created"] += 1
                    continue

                if _task_exists(session, entity_text, suggested_concept):
                    logger.debug(
                        "Task already exists for %r -> %s -- skipping",
                        entity_text, suggested_concept,
                    )
                    counts["skipped"] += 1
                    continue

                normalized = _normalize(entity_text)
                task_id = make_surface_form_task_id(
                    candidate_id="audit_gap",
                    entity_text=normalized,
                    current_concept=expected_concept,
                )
                session.run(
                    UPSERT_SURFACE_FORM_TASK,
                    task_id=task_id,
                    entity_text=entity_text,
                    current_concept=expected_concept,
                    current_term=expected_term,
                    suggested_concept=suggested_concept,
                    suggested_term=suggested_term,
                    candidates_json="[]",
                    context_text=str(gap.get("encounter_id") or ""),
                    candidate_id="",
                    confidence=score,
                    source="audit_gap",
                )
                logger.info(
                    "Created SurfaceFormTask: %r -> %s (score=%.2f)",
                    entity_text, suggested_concept, score,
                )
                counts["created"] += 1
    finally:
        client.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Feed audit surface-form gaps to review queue"
    )
    parser.add_argument(
        "--audit-dir",
        default=str(_DEFAULT_AUDIT_DIR),
        metavar="DIR",
        help="Directory containing surface_form_gaps.json",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.75,
        metavar="SCORE",
        help="Minimum resolver score to create a task (default 0.75)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to Neo4j",
    )
    args = parser.parse_args()

    gaps_file = Path(args.audit_dir) / "surface_form_gaps.json"
    if not gaps_file.exists():
        logger.error("surface_form_gaps.json not found at %s", gaps_file)
        sys.exit(1)

    gaps = json.loads(gaps_file.read_text(encoding="utf-8"))
    logger.info("Loaded %d surface-form gaps from %s", len(gaps), gaps_file)

    counts = feed_gaps(gaps, threshold=args.threshold, dry_run=args.dry_run)
    logger.info(
        "Complete. created=%d  skipped=%d  below_threshold=%d",
        counts["created"], counts["skipped"], counts["below_threshold"],
    )


if __name__ == "__main__":
    main()
