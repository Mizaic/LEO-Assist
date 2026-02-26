"""Handle incoming coding job messages from the message bus.

Each message contains a patient_id and optional encounter_id.
The handler runs the two-phase coding pipeline and publishes
progress events to Redis for the Core API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from libs.message_bus.base import Message
from libs.neo4j_client.client import PatientGraphClient, KnowledgeGraphClient
from services.coding_worker.app.services.progress_publisher import publish_progress
from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

logger = logging.getLogger(__name__)


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

        if encounter_id:
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

        logger.info("Coding job completed: run=%s", run_id)
    except Exception:
        logger.exception("Coding job failed: run=%s", run_id)
        publish_progress(run_id, {"type": "run_error", "run_id": run_id, "error": "internal_error"})
    finally:
        patient_client.close()
        knowledge_client.close()
