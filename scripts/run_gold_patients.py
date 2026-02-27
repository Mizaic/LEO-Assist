"""Run the gold consensus pipeline end-to-end.

1. Clean specified patients (remove old artefacts).
2. Run pre-classification + consensus extraction via the V3 pipeline.
3. Report stats (auto-approved vs review-queue vs low-confidence).

Usage:
    python scripts/run_gold_patients.py --patients P1,P2,...
    python scripts/run_gold_patients.py --limit 50
    python scripts/run_gold_patients.py --limit 50 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("run_gold")


def get_patient_ids(driver, limit: int) -> list[str]:
    """Fetch patients ordered by encounter count (most encounters first)."""
    with driver.session() as session:
        result = session.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WITH p, count(e) AS enc_count "
            "RETURN toString(p.id) AS patient_id, enc_count "
            "ORDER BY enc_count DESC LIMIT $limit",
            limit=limit,
        )
        return [row["patient_id"] for row in result]


def main():
    parser = argparse.ArgumentParser(description="Run gold consensus pipeline")
    parser.add_argument("--patients", type=str, help="Comma-separated patient IDs")
    parser.add_argument("--limit", type=int, default=50, help="Number of patients (if --patients not given)")
    parser.add_argument("--dry-run", action="store_true", help="Skip persistence")
    parser.add_argument("--skip-clean", action="store_true", help="Skip cleanup step")
    parser.add_argument("--workers", type=int, default=4, help="Pipeline parallelism")
    args = parser.parse_args()

    from neo4j import GraphDatabase
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    if args.patients:
        patient_ids = [p.strip() for p in args.patients.split(",")]
    else:
        patient_ids = get_patient_ids(driver, limit=args.limit)

    logger.info("Gold pipeline: %d patients", len(patient_ids))

    # Step 1: Clean
    if not args.skip_clean:
        logger.info("Step 1: Cleaning patient data...")
        from scripts.clean_patients import clean_patient
        t0 = time.time()
        with driver.session() as session:
            for pid in patient_ids:
                clean_patient(session, pid)
        logger.info("  Cleaned in %.1fs", time.time() - t0)
    else:
        logger.info("Step 1: Skipped (--skip-clean)")

    # Step 2: Run classification + clinical-only extraction
    logger.info("Step 2: Running encounter classification + V3 extraction...")
    from app.db.neo4j_client import PatientGraphClient, CodingGraphClient
    from app.services.v3.encounter_classifier import (
        build_patient_encounter_index,
        persist_patient_encounter_classification,
    )
    from app.services.v3.pipeline_service import V3PipelineService

    patient_client = PatientGraphClient()
    patient_client.initialize_schema()
    coding_client = CodingGraphClient()
    coding_client.initialize_schema()

    service = V3PipelineService(
        patient_client=patient_client,
        coding_client=coding_client,
    )

    events = []

    def progress_hook(event):
        events.append(event)
        etype = event.get("type", "")
        if etype in ("patient_started", "run_completed", "pipeline_error", "persist_completed"):
            logger.info("  %s", json.dumps(event, default=str))

    orchestration_run_id = str(uuid.uuid4())
    extraction_run_ids: list[str] = []
    total_encounters = 0
    total_classified = 0
    clinical_total = 0
    non_clinical_total = 0
    processed_encounters = 0
    queued_for_review = 0
    rejected_hard_fail = 0
    warnings_only = 0

    t0 = time.time()
    for patient_id in patient_ids:
        encounters = patient_client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
            "ORDER BY e.date",
            pid=patient_id,
        )
        total_encounters += len(encounters)
        index = build_patient_encounter_index(patient_id, encounters, orchestration_run_id)
        total_classified += len(index.classifications)

        if not args.dry_run:
            persist_patient_encounter_classification(
                patient_client=patient_client,
                patient_id=patient_id,
                run_id=orchestration_run_id,
                index=index,
            )

        clinical_ids = [
            encounter_id
            for encounter_id, result in index.classifications.items()
            if result.content_type == "clinical"
        ]
        clinical_total += len(clinical_ids)
        non_clinical_total += (len(encounters) - len(clinical_ids))

        logger.info(
            "  Patient %s classified: total=%d admin=%d doc=%d clinical=%d skipped_non_clinical=%d",
            patient_id,
            len(encounters),
            index.admin_count,
            index.document_transfer_count,
            len(clinical_ids),
            len(encounters) - len(clinical_ids),
        )

        for encounter_id in clinical_ids:
            encounter_run_id, encounter_stats = service.run_single_encounter(
                patient_id=patient_id,
                encounter_id=str(encounter_id),
                dry_run=args.dry_run,
                progress_hook=progress_hook,
            )
            extraction_run_ids.append(encounter_run_id)
            processed_encounters += encounter_stats.processed_encounters
            queued_for_review += encounter_stats.queued_for_review
            rejected_hard_fail += encounter_stats.rejected_hard_fail
            warnings_only += encounter_stats.warnings_only

    elapsed = time.time() - t0

    # Step 3: Report
    unique_extraction_run_ids = sorted(set(extraction_run_ids))
    logger.info("=" * 60)
    logger.info("GOLD PIPELINE COMPLETE")
    logger.info("=" * 60)
    logger.info("  Orchestration run ID: %s", orchestration_run_id)
    logger.info("  Extraction run IDs:   %d unique", len(unique_extraction_run_ids))
    logger.info("  Patients:             %d", len(patient_ids))
    logger.info("  Total encounters:     %d", total_encounters)
    logger.info("  Classified:           %d", total_classified)
    logger.info("  Clinical processed:   %d", clinical_total)
    logger.info("  Skipped non-clinical: %d", non_clinical_total)
    logger.info("  Processed encounters: %d", processed_encounters)
    logger.info("  Queued for review:    %d", queued_for_review)
    logger.info("  Hard fail:            %d", rejected_hard_fail)
    logger.info("  Warnings only:        %d", warnings_only)
    logger.info("  Elapsed:              %.1fs", elapsed)

    auto_approved = sum(
        1 for e in events if e.get("type") == "persist_completed" and e.get("auto_approved")
    )
    logger.info("  Auto-approved:        %d", auto_approved)

    # Encounter-level validation
    logger.info("\nStep 3: Validating data chain...")
    with driver.session() as session:
        for pid in patient_ids[:5]:
            r = session.run(
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[d:DOCUMENTS]->() "
                "WHERE toString(p.id) = $pid "
                "RETURN count(d) AS doc_count",
                pid=pid,
            ).single()
            doc_count = r["doc_count"] if r else 0

            r2 = session.run(
                "MATCH (c:EncounterCandidate) WHERE c.patient_id = $pid "
                "RETURN count(c) AS cand_count, "
                "       sum(CASE WHEN c.approval_status = 'approved' THEN 1 ELSE 0 END) AS approved",
                pid=pid,
            ).single()
            cand_count = r2["cand_count"] if r2 else 0
            approved = r2["approved"] if r2 else 0

            logger.info(
                "  Patient %s: %d DOCUMENTS, %d candidates (%d approved)",
                pid, doc_count, cand_count, approved,
            )

    logger.info("=" * 60)
    patient_client.close()
    coding_client.close()
    driver.close()


if __name__ == "__main__":
    main()
