"""Run the gold pipeline end-to-end for one or more patients.

Steps
-----
1. Clean  — delete all derived artefacts (DOCUMENTS, episodes, safety alerts,
             EncounterCandidates, ReviewTasks, Approvals)
2. Classify — pre-classify every encounter as admin / document / clinical
3. Extract  — run V3 LLM extraction + SNOMED coding for clinical encounters
4. Sync     — write DOCUMENTS relationships for auto-approved candidates
5. Anchors  — detect milestone anchors (referral, diagnosis, treatment start,
               specialist visit) from DOCUMENTS
6. Episodes — build EpisodeOfCare nodes from anchor combinations
7. Safety   — detect safety-net signals and calculate NCDA KPI metrics

Flags
-----
--skip-clean      skip step 1 (useful when re-running after a crash)
--skip-extract    skip steps 2-3 (useful to re-run analysis only)
--analysis-only   run steps 4-7 only (alias for --skip-clean --skip-extract)

Usage examples
--------------
  # Full end-to-end for one patient
  python scripts/run_gold_patients.py --patients 9990000002

  # 50 patients (sorted by encounter count)
  python scripts/run_gold_patients.py --limit 50

  # Only run analysis (after extraction already done)
  python scripts/run_gold_patients.py --patients 9990000002 --analysis-only
"""

from __future__ import annotations

import argparse
import asyncio
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

# Silence noisy sub-loggers
for _noisy in ("httpx", "httpcore", "botocore", "urllib3", "sentence_transformers"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_driver():
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", ""),
        ),
    )


# ---------------------------------------------------------------------------
# Step 1 — Clean
# ---------------------------------------------------------------------------


def step_clean(driver, patient_ids: list[str]) -> None:
    logger.info("Step 1: Cleaning %d patient(s)...", len(patient_ids))
    from scripts.clean_patients import clean_patient

    t0 = time.time()
    with driver.session() as session:
        for pid in patient_ids:
            clean_patient(session, pid)
            logger.info("  Cleaned patient %s", pid)
    logger.info("  Step 1 complete in %.1fs", time.time() - t0)


# ---------------------------------------------------------------------------
# Steps 2-3 — Classify + Extract
# ---------------------------------------------------------------------------


def step_extract(
    patient_ids: list[str],
    *,
    dry_run: bool = False,
    workers: int = 4,
) -> dict:
    """Classify encounters and run V3 extraction for clinical ones."""
    logger.info(
        "Step 2-3: Encounter classification + V3 extraction (%d patient(s))...",
        len(patient_ids),
    )

    from app.db.neo4j_client import PatientGraphClient, CodingGraphClient
    from app.services.encounter_classifier import (
        build_patient_encounter_index,
        persist_patient_encounter_classification,
    )
    from app.services.pipeline_service import PipelineService

    patient_client = PatientGraphClient()
    patient_client.initialize_schema()
    coding_client = CodingGraphClient()
    coding_client.initialize_schema()

    service = PipelineService(
        patient_client=patient_client,
        coding_client=coding_client,
    )

    orchestration_run_id = str(uuid.uuid4())
    total_encounters = 0
    total_clinical = 0
    processed_encounters = 0
    queued_for_review = 0
    rejected_hard_fail = 0
    auto_approved = 0
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
        logger.info("  Patient %s: %d total encounters", patient_id, len(encounters))

        index = build_patient_encounter_index(
            patient_id, encounters, orchestration_run_id
        )
        if not dry_run:
            persist_patient_encounter_classification(
                patient_client=patient_client,
                patient_id=patient_id,
                run_id=orchestration_run_id,
                index=index,
            )

        clinical_ids = [
            enc_id
            for enc_id, result in index.classifications.items()
            if result.content_type == "clinical"
        ]
        total_clinical += len(clinical_ids)
        logger.info(
            "  Patient %s classified: admin=%d doc=%d clinical=%d",
            patient_id,
            index.admin_count,
            index.document_transfer_count,
            len(clinical_ids),
        )

        events = []
        for i, encounter_id in enumerate(clinical_ids, 1):
            logger.info(
                "  Patient %s: extracting encounter %d/%d (%s)",
                patient_id,
                i,
                len(clinical_ids),
                encounter_id,
            )
            try:
                _run_id, stats = service.run_single_encounter(
                    patient_id=patient_id,
                    encounter_id=str(encounter_id),
                    dry_run=dry_run,
                    progress_hook=lambda e: events.append(e),
                )
                processed_encounters += stats.processed_encounters
                queued_for_review += stats.queued_for_review
                rejected_hard_fail += stats.rejected_hard_fail
                auto_approved += sum(
                    1
                    for ev in events
                    if ev.get("type") == "persist_completed" and ev.get("auto_approved")
                )
                events.clear()
                if stats.processed_encounters:
                    logger.info(
                        "  Encounter %s: coded %d terms (queued=%d hard_fail=%d)",
                        encounter_id,
                        stats.processed_encounters,
                        stats.queued_for_review,
                        stats.rejected_hard_fail,
                    )
            except Exception:
                logger.exception("  Failed to process encounter %s", encounter_id)

    elapsed = time.time() - t0
    patient_client.close()
    coding_client.close()

    summary = {
        "total_encounters": total_encounters,
        "total_clinical": total_clinical,
        "processed_encounters": processed_encounters,
        "queued_for_review": queued_for_review,
        "rejected_hard_fail": rejected_hard_fail,
        "auto_approved": auto_approved,
        "elapsed_s": round(elapsed, 1),
    }
    logger.info(
        "Step 2-3 complete in %.1fs: total=%d clinical=%d processed=%d "
        "auto_approved=%d review=%d hardfail=%d",
        elapsed,
        total_encounters,
        total_clinical,
        processed_encounters,
        auto_approved,
        queued_for_review,
        rejected_hard_fail,
    )
    return summary


# ---------------------------------------------------------------------------
# Step 4 — Sync gold → DOCUMENTS
# ---------------------------------------------------------------------------


def step_sync_gold(patient_ids: list[str]) -> dict:
    """Write DOCUMENTS relationships for all approved EncounterCandidates."""
    logger.info(
        "Step 4: Syncing gold (writing DOCUMENTS) for %d patient(s)...",
        len(patient_ids),
    )
    from app.db.neo4j_client import PatientGraphClient
    from app.services.sync_service import sync_gold_to_patient

    client = PatientGraphClient()
    total_synced = 0
    total_links = 0
    t0 = time.time()

    try:
        with client.session() as session:
            for patient_id in patient_ids:
                result = sync_gold_to_patient(patient_id, patient_session=session)
                enc_synced = result.get("encounters_synced", 0)
                links = result.get("links_created", 0)
                total_synced += enc_synced
                total_links += links
                if result.get("error"):
                    logger.warning("  Patient %s sync: %s", patient_id, result["error"])
                else:
                    logger.info(
                        "  Patient %s synced: %d encounters → %d DOCUMENTS links",
                        patient_id,
                        enc_synced,
                        links,
                    )
    finally:
        client.close()

    logger.info(
        "Step 4 complete in %.1fs: %d encounters synced, %d DOCUMENTS links written",
        time.time() - t0,
        total_synced,
        total_links,
    )
    return {"encounters_synced": total_synced, "links_created": total_links}


# ---------------------------------------------------------------------------
# Steps 5-7 — Anchors + Episodes + Safety-net + KPIs
# ---------------------------------------------------------------------------


async def _run_analysis_async(patient_id: str, start_date: str, end_date: str) -> None:
    """Run the full analysis pipeline for a single patient (async)."""
    from libs.message_bus.base import Message
    from services.analysis_worker.app.services.job_handler import handle_analysis_job

    msg = Message(
        body={
            "patient_id": patient_id,
            "start_date": start_date,
            "end_date": end_date,
        }
    )
    await handle_analysis_job(msg)


def step_analyse(
    patient_ids: list[str],
    *,
    start_date: str = "2000-01-01",
    end_date: str = "2030-12-31",
) -> None:
    """Run anchors (5), episodes (6), safety-net + KPIs (7) for each patient."""
    logger.info("Steps 5-7: Full analysis for %d patient(s)...", len(patient_ids))
    t0 = time.time()

    for patient_id in patient_ids:
        logger.info(
            "  Analysing patient %s (anchors → episodes → safety-net → KPIs)...",
            patient_id,
        )
        try:
            asyncio.run(_run_analysis_async(patient_id, start_date, end_date))
            logger.info("  Patient %s analysis complete", patient_id)
        except Exception:
            logger.exception("  Analysis failed for patient %s", patient_id)

    logger.info("Steps 5-7 complete in %.1fs", time.time() - t0)


# ---------------------------------------------------------------------------
# Validation summary
# ---------------------------------------------------------------------------


def step_validate(driver, patient_ids: list[str]) -> None:
    """Print a final summary of what was written to Neo4j."""
    logger.info("Validation summary:")
    with driver.session() as session:
        for pid in patient_ids:
            docs = session.run(
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[d:DOCUMENTS]->() "
                "WHERE toString(p.id) = $pid RETURN count(d) AS n",
                pid=pid,
            ).single()
            episodes = session.run(
                "MATCH (p:Patient)-[:HAS_EPISODE]->(ep) "
                "WHERE toString(p.id) = $pid RETURN count(ep) AS n",
                pid=pid,
            ).single()
            alerts = session.run(
                "MATCH (p:Patient)-[:HAS_SAFETY_NET_ALERT]->(a) "
                "WHERE toString(p.id) = $pid RETURN count(a) AS n",
                pid=pid,
            ).single()
            # Legacy CSS alerts (pre-rename)
            css = session.run(
                "MATCH (p:Patient)-[:HAS_CSS_ALERT]->(a) "
                "WHERE toString(p.id) = $pid RETURN count(a) AS n",
                pid=pid,
            ).single()
            candidates = session.run(
                "MATCH (c:EncounterCandidate) WHERE c.patient_id = $pid "
                "RETURN count(c) AS n, "
                "       sum(CASE WHEN c.approval_status = 'approved' THEN 1 ELSE 0 END) AS approved",
                pid=pid,
            ).single()
            logger.info(
                "  Patient %s: DOCUMENTS=%d | candidates=%d (approved=%d) | "
                "episodes=%d | safety_alerts=%d",
                pid,
                docs["n"] if docs else 0,
                candidates["n"] if candidates else 0,
                candidates["approved"] if candidates else 0,
                episodes["n"] if episodes else 0,
                (alerts["n"] if alerts else 0) + (css["n"] if css else 0),
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Run gold pipeline (7 steps)")
    parser.add_argument("--patients", type=str, help="Comma-separated patient IDs")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of patients if --patients not given",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Skip all persistence (extraction only)"
    )
    parser.add_argument(
        "--skip-clean", action="store_true", help="Skip step 1 (cleanup)"
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip steps 2-3 (classification + extraction)",
    )
    parser.add_argument(
        "--analysis-only", action="store_true", help="Run steps 4-7 only"
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip steps 5-7 (anchors, episodes, safety-net)",
    )
    parser.add_argument("--workers", type=int, default=4, help="Extraction parallelism")
    parser.add_argument(
        "--start-date", type=str, default="2000-01-01", help="Analysis window start"
    )
    parser.add_argument(
        "--end-date", type=str, default="2030-12-31", help="Analysis window end"
    )
    args = parser.parse_args()

    if args.analysis_only:
        args.skip_clean = True
        args.skip_extract = True

    driver = _make_driver()

    if args.patients:
        patient_ids = [p.strip() for p in args.patients.split(",")]
    else:
        patient_ids = get_patient_ids(driver, limit=args.limit)

    logger.info("Gold pipeline: %d patient(s) — %s", len(patient_ids), patient_ids)

    t_total = time.time()

    # ------------------------------------------------------------------
    # Step 1: Clean
    # ------------------------------------------------------------------
    if not args.skip_clean:
        step_clean(driver, patient_ids)
    else:
        logger.info("Step 1: Skipped (--skip-clean)")

    # ------------------------------------------------------------------
    # Steps 2-3: Classify + Extract
    # ------------------------------------------------------------------
    if not args.skip_extract:
        extract_summary = step_extract(
            patient_ids,
            dry_run=args.dry_run,
            workers=args.workers,
        )
    else:
        logger.info("Steps 2-3: Skipped (--skip-extract)")
        extract_summary = {}

    # ------------------------------------------------------------------
    # Step 4: Sync gold
    # ------------------------------------------------------------------
    if not args.dry_run and not args.skip_analysis:
        sync_summary = step_sync_gold(patient_ids)
    else:
        logger.info("Step 4: Skipped (dry-run or --skip-analysis)")
        sync_summary = {}

    # ------------------------------------------------------------------
    # Steps 5-7: Anchors + Episodes + Safety-net + KPIs
    # ------------------------------------------------------------------
    if not args.skip_analysis and not args.dry_run:
        step_analyse(patient_ids, start_date=args.start_date, end_date=args.end_date)
    else:
        logger.info("Steps 5-7: Skipped (dry-run or --skip-analysis)")

    # ------------------------------------------------------------------
    # Validation summary
    # ------------------------------------------------------------------
    step_validate(driver, patient_ids)

    driver.close()

    elapsed = time.time() - t_total
    logger.info("=" * 60)
    logger.info("GOLD PIPELINE COMPLETE in %.1fs (%.1f min)", elapsed, elapsed / 60)
    logger.info("=" * 60)
    if extract_summary:
        logger.info(
            "  Extraction:   total=%d clinical=%d processed=%d auto_approved=%d review=%d",
            extract_summary.get("total_encounters", 0),
            extract_summary.get("total_clinical", 0),
            extract_summary.get("processed_encounters", 0),
            extract_summary.get("auto_approved", 0),
            extract_summary.get("queued_for_review", 0),
        )
    if sync_summary:
        logger.info(
            "  Sync gold:    %d encounters → %d DOCUMENTS",
            sync_summary.get("encounters_synced", 0),
            sync_summary.get("links_created", 0),
        )


if __name__ == "__main__":
    main()
