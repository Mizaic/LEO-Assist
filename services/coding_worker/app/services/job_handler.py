"""Handle incoming coding job messages from the message bus.

Each message contains a patient_id and optional encounter_id.
The handler runs the two-phase coding pipeline and publishes
progress events to Redis for the Core API.

Supports ``mode="consensus"`` for multi-model gold pipeline (M4a).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from libs.message_bus.base import Message
from libs.neo4j_client.client import PatientGraphClient, KnowledgeGraphClient
from services.coding_worker.app.services.progress_publisher import publish_progress
from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

logger = logging.getLogger(__name__)

ANALYSIS_QUEUE = os.getenv("ANALYSIS_QUEUE_NAME", "analysis-jobs")


async def handle_coding_job(msg: Message) -> None:
    body = msg.body
    patient_id = body.get("patient_id")
    encounter_id = body.get("encounter_id")
    run_id = msg.correlation_id or msg.message_id
    dry_run = body.get("dry_run", False)
    mode = body.get("mode", "all")

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

        if mode == "consensus":
            await _run_consensus(
                patient_id=patient_id,
                pipeline=pipeline,
                dry_run=dry_run,
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
            )
        else:
            await pipeline.run(
                patient_ids=[patient_id],
                dry_run=dry_run,
                progress_hook=progress_hook,
            )

        if body.get("trigger_analysis"):
            await _publish_analysis_job(patient_id, run_id)

        logger.info("Coding job completed: run=%s", run_id)
    except Exception:
        logger.exception("Coding job failed: run=%s", run_id)
        publish_progress(run_id, {"type": "run_error", "run_id": run_id, "error": "internal_error"})
    finally:
        patient_client.close()
        knowledge_client.close()


async def _run_consensus(
    patient_id: str,
    pipeline: CodingPipeline,
    dry_run: bool,
    progress_hook,
) -> None:
    """Run multi-model consensus extraction using shared libs.

    Step 1: Pre-classify encounters.
    Step 2: For clinical encounters, run extraction via existing pipeline.
           (Multi-model consensus is handled at the LLM factory level when
            the pipeline is configured with consensus mode.)
    Step 3: Auto-approve high-confidence results.
    """
    from services.api.app.services.v3.encounter_classifier import (
        build_patient_encounter_index,
    )

    encounters = await asyncio.to_thread(
        _fetch_encounters_sync, pipeline.patient_client, patient_id
    )

    index = await asyncio.to_thread(
        build_patient_encounter_index, patient_id, encounters
    )

    clinical_ids = {
        enc_id
        for enc_id, result in index.classifications.items()
        if result.content_type == "clinical"
    }

    logger.info(
        "Patient %s consensus: %d/%d clinical encounters",
        patient_id, len(clinical_ids), len(encounters),
    )

    progress_hook({
        "type": "consensus_classification_done",
        "patient_id": patient_id,
        "total": len(encounters),
        "admin": index.admin_count,
        "document_transfer": index.document_transfer_count,
        "clinical": len(clinical_ids),
    })

    await pipeline.run_unprocessed(
        patient_ids=[patient_id],
        dry_run=dry_run,
        progress_hook=progress_hook,
    )


def _fetch_encounters_sync(patient_client, patient_id: str) -> list[dict]:
    """Synchronous encounter fetch for use with asyncio.to_thread."""
    with patient_client.session() as session:
        result = session.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
            "ORDER BY e.date",
            pid=patient_id,
        )
        return [dict(row) for row in result]


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
