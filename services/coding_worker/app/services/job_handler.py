"""Handle incoming coding job messages from the message bus.

Each message contains a patient_id and optional encounter_id.
The handler runs the two-phase coding pipeline and publishes
progress events to Redis for the Core API.

Message modes
-------------
all               — classify + extract all encounters for a patient
unprocessed       — classify + extract only uncoded encounters
extract_patient   — skip classification, extract only pre-classified clinical encounters
extract_encounter — worker: run_single_encounter for one clinical encounter,
                    track completion, last triggers analysis job

Checkpointing
-------------
Extraction fan-out progress is tracked in Redis using per-run counters so the
worker can trigger analysis when the final encounter is processed.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from libs.message_bus.base import Message
from libs.neo4j_client.client import PatientGraphClient, KnowledgeGraphClient
from libs.redis_client.checkpoint import CheckpointStore
from libs.utils.logging import logging_context
from services.coding_worker.app.services.progress_publisher import publish_progress
from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

logger = logging.getLogger(__name__)

ANALYSIS_QUEUE = os.getenv("ANALYSIS_QUEUE_NAME", "analysis-jobs")
CODING_QUEUE = os.getenv("CODING_QUEUE_NAME", "coding-jobs")


async def handle_coding_job(msg: Message) -> None:
    body = msg.body
    patient_id = body.get("patient_id")
    encounter_id = body.get("encounter_id")
    run_id = msg.correlation_id or msg.message_id
    dry_run = body.get("dry_run", False)
    mode = body.get("mode", "all")
    with logging_context(correlation_id=run_id):
        await _handle_coding_job_inner(
            body=body,
            patient_id=patient_id,
            encounter_id=encounter_id,
            run_id=run_id,
            dry_run=dry_run,
            mode=mode,
        )


async def _handle_coding_job_inner(
    *,
    body: dict[str, Any],
    patient_id: str,
    encounter_id: str | None,
    run_id: str,
    dry_run: bool,
    mode: str,
) -> None:
    logger.info(
        "Received coding job: patient=%s encounter=%s run=%s mode=%s",
        patient_id, encounter_id, run_id, mode,
    )

    patient_client = PatientGraphClient()
    knowledge_client = KnowledgeGraphClient()

    try:
        pipeline = CodingPipeline(
            patient_client=patient_client,
            knowledge_client=knowledge_client,
        )

        def progress_hook(payload: dict[str, Any]) -> None:
            payload["run_id"] = run_id
            publish_progress(run_id, payload)

        if mode in {"consensus", "consensus_fanout", "consensus_chunk"}:
            raise ValueError(f"unsupported mode in canonical pipeline: {mode}")
        elif mode == "extract_encounter":
            await _run_extract_encounter(
                patient_id=patient_id,
                run_id=run_id,
                encounter_id=encounter_id or body.get("encounter_id", ""),
                pipeline=pipeline,
                dry_run=dry_run,
                trigger_analysis=body.get("trigger_analysis", True),
                progress_hook=progress_hook,
            )
        elif mode == "extract_patient":
            await _run_extract_patient(
                patient_id=patient_id,
                run_id=run_id,
                pipeline=pipeline,
                dry_run=dry_run,
                trigger_analysis=body.get("trigger_analysis", True),
                progress_hook=progress_hook,
            )
        elif encounter_id:
            await pipeline.run_single_encounter(
                patient_id=patient_id,
                encounter_id=encounter_id,
                dry_run=dry_run,
                progress_hook=progress_hook,
            )
        elif mode == "unprocessed":
            await pipeline.run_unprocessed(
                patient_ids=[patient_id],
                dry_run=dry_run,
                progress_hook=progress_hook,
                run_id=run_id,
            )
        else:
            await pipeline.run(
                patient_ids=[patient_id],
                dry_run=dry_run,
                progress_hook=progress_hook,
                run_id=run_id,
            )

        logger.info("Coding job completed: run=%s mode=%s", run_id, mode)
    except Exception:
        logger.exception("Coding job failed: run=%s", run_id)
        publish_progress(run_id, {"type": "run_error", "run_id": run_id, "error": "internal_error"})
        raise  # re-raise so the Azure adapter abandons the message for retry
    finally:
        patient_client.close()
        knowledge_client.close()


# ------------------------------------------------------------------
# Extract worker — codes a single clinical encounter
# ------------------------------------------------------------------

async def _run_extract_encounter(
    patient_id: str,
    run_id: str,
    encounter_id: str,
    pipeline: CodingPipeline,
    dry_run: bool,
    trigger_analysis: bool,
    progress_hook,
) -> None:
    """Extract and code a single clinical encounter.

    Atomically increments the extracted counter.  When all extractions
    are complete, triggers the analysis job if requested.
    """
    store = CheckpointStore()

    logger.info("Patient %s — extracting encounter %s", patient_id, encounter_id)
    await pipeline.run_single_encounter(
        patient_id=patient_id,
        encounter_id=encounter_id,
        dry_run=dry_run,
        progress_hook=progress_hook,
    )
    logger.info("Patient %s — encounter %s extraction complete", patient_id, encounter_id)

    extracted = store.incr(f"fanout:{run_id}:extracted:{patient_id}")
    total_raw = store.get(f"fanout:{run_id}:extract_total:{patient_id}")
    total = int(total_raw.get("value", 0)) if total_raw else 0

    logger.info(
        "Patient %s — extracted %d/%d encounters", patient_id, extracted, total
    )

    if total > 0 and extracted >= total:
        logger.info(
            "Patient %s — all %d encounters extracted — run complete", patient_id, total
        )
        progress_hook({
            "type": "extraction_done",
            "patient_id": patient_id,
            "clinical_processed": extracted,
        })
        if trigger_analysis:
            await _publish_analysis_job(patient_id, run_id)


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def _fetch_clinical_encounter_ids_sync(patient_client, patient_id: str) -> list[str]:
    """Return IDs of encounters already classified as clinical in Neo4j.

    Used by ``extract_patient`` mode to skip classification and jump straight
    to extraction using the existing classification results.
    """
    with patient_client.session() as session:
        result = session.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "  AND e.classification_content_type = 'clinical' "
            "RETURN toString(e.id) AS encounter_id "
            "ORDER BY e.date",
            pid=patient_id,
        )
        return [row["encounter_id"] for row in result]


async def _run_extract_patient(
    patient_id: str,
    run_id: str,
    pipeline: CodingPipeline,
    dry_run: bool,
    trigger_analysis: bool,
    progress_hook,
) -> None:
    """Fan out extraction for a patient whose encounters are already classified.

    Reads ``classification_content_type = 'clinical'`` directly from Neo4j,
    bypassing the classification step entirely.  Publishes one
    ``extract_encounter`` message per clinical encounter.

    Use this to re-run the coding (extraction) step after fixing a persist bug
    without paying the cost of re-classifying every encounter again.
    """
    store = CheckpointStore()

    clinical_ids = await asyncio.to_thread(
        _fetch_clinical_encounter_ids_sync, pipeline.patient_client, patient_id
    )

    if not clinical_ids:
        logger.info(
            "Patient %s — no clinical encounters found in Neo4j, nothing to extract",
            patient_id,
        )
        progress_hook({
            "type": "extraction_done",
            "patient_id": patient_id,
            "clinical_processed": 0,
        })
        return

    logger.info(
        "Patient %s — extract_patient: found %d clinical encounters, fanning out",
        patient_id, len(clinical_ids),
    )

    if dry_run:
        logger.info("Patient %s — dry_run, skipping fan-out", patient_id)
        progress_hook({
            "type": "extraction_done",
            "patient_id": patient_id,
            "clinical_processed": 0,
        })
        return

    # Set the extraction total so the last worker can detect completion
    store.set(f"fanout:{run_id}:extract_total:{patient_id}", {"value": len(clinical_ids)})

    from libs.message_bus.factory import create_message_bus
    bus = create_message_bus()
    try:
        for enc_id in clinical_ids:
            msg = Message(
                body={
                    "patient_id": patient_id,
                    "encounter_id": enc_id,
                    "mode": "extract_encounter",
                    "dry_run": dry_run,
                    "trigger_analysis": trigger_analysis,
                },
                correlation_id=run_id,
            )
            await bus.send(CODING_QUEUE, msg)
    finally:
        await bus.close()

    logger.info(
        "Patient %s — published %d extract_encounter messages (extract_patient mode)",
        patient_id, len(clinical_ids),
    )
    progress_hook({
        "type": "extract_patient_fanout_done",
        "patient_id": patient_id,
        "clinical_count": len(clinical_ids),
    })


async def _publish_analysis_job(patient_id: str, run_id: str) -> None:
    """Publish an analysis job to the analysis-jobs queue."""
    try:
        from libs.message_bus.factory import create_message_bus
        bus = create_message_bus()
        await bus.send(ANALYSIS_QUEUE, Message(
            body={"patient_id": patient_id, "trigger": "coding_complete"},
            correlation_id=run_id,
        ))
        await bus.close()
        logger.info("Published analysis job for patient %s", patient_id)
    except Exception:
        logger.warning("Failed to publish analysis job for %s", patient_id, exc_info=True)
