"""Service Bus handler: validate coding jobs and run WorkflowEngine.

Atlas trace:
  DO: DO-A26CD350
  DI: DI-705C806B
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A26CD350")
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from libs.message_bus.base import Message

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_ALLOWED_MODES = frozenset({"all", "extract_encounter", "extract_patient"})


class CodingJobMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    patient_id: str = Field(..., min_length=1, max_length=128)
    encounter_id: str | None = Field(default=None, max_length=128)
    mode: str = "all"
    dry_run: bool = False
    trigger_analysis: bool = False

    @field_validator("patient_id")
    @classmethod
    def _validate_patient_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value or ""):
            raise ValueError("invalid patient_id")
        return value

    @field_validator("encounter_id")
    @classmethod
    def _validate_encounter_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _ID_RE.fullmatch(value):
            raise ValueError("invalid encounter_id")
        return value

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, value: str) -> str:
        m = (value or "all").strip()
        if m not in _ALLOWED_MODES:
            raise ValueError("invalid mode")
        return m


async def handle_coding_job(message: Message) -> None:
    try:
        job = CodingJobMessage.model_validate(message.body or {})
    except ValidationError:
        logger.error("Malformed coding job message dropped")
        return

    try:
        await _run_coding_job(job, message)
    except Exception:
        logger.exception("Coding job failed patient_id=%s", job.patient_id)


def _build_progress_callback(
    run_id: str,
    *,
    patient_id: str,
    suppress_run_completed: bool = False,
):
    from services.coding_worker.app.services.progress_publisher import publish_progress
    from libs.redis_client.rebuild_status import update_from_event

    def _callback(event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("run_id", run_id)
        payload.setdefault("patient_id", patient_id)
        if suppress_run_completed and payload.get("type") == "run_completed":
            payload["type"] = "encounter_completed"
        publish_progress(run_id, payload)
        try:
            update_from_event(patient_id, run_id, payload)
        except Exception:
            logger.debug(
                "rebuild status update failed patient=%s run=%s",
                patient_id,
                run_id,
                exc_info=True,
            )

    return _callback


async def _dispatch_engine_for_encounter(
    handler,
    step_callback,
    base_body: dict[str, Any],
    *,
    patient_id: str,
    encounter_id: str,
    run_id: str,
    dry_run: bool,
    trigger_analysis: bool,
) -> None:
    body = {
        "event_type": str(base_body.get("event_type") or "encounter-created"),
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "plan_definition_id": str(
            base_body.get("plan_definition_id") or "pd-gp-encounter-coding"
        ),
        "context": {
            "dry_run": dry_run,
            "mode": "extract_encounter",
            "encounter_id": encounter_id,
            "trigger_analysis": trigger_analysis,
        },
    }
    await handler.handle_message(
        Message(body=body, correlation_id=run_id, subject="encounter-created"),
        step_callback=step_callback,
    )


async def _run_coding_job(job: CodingJobMessage, raw_message: Message) -> None:
    from libs.neo4j_client.client import (
        PatientGraphClient,
        get_async_driver,
        get_async_patient_driver,
    )
    from libs.workflow.engine import WorkflowEngine
    from libs.workflow.events import ServiceBusEventHandler

    body = raw_message.body if isinstance(raw_message.body, dict) else {}
    run_id = str(
        raw_message.correlation_id or body.get("run_id") or raw_message.message_id or ""
    ).strip()
    if not run_id:
        run_id = f"run-{job.patient_id}"

    driver = get_async_driver()
    audit_driver = None
    try:
        audit_driver = get_async_patient_driver()
    except Exception:
        logger.warning(
            "Patient Graph async driver unavailable — spend audit writes disabled"
        )
    try:
        engine = WorkflowEngine(
            neo4j_driver=driver,
            audit_neo4j_driver=audit_driver,
        )
        handler = ServiceBusEventHandler(engine)

        if job.mode == "extract_encounter":
            if not job.encounter_id:
                logger.error("extract_encounter job missing encounter_id")
                return
            await _dispatch_engine_for_encounter(
                handler,
                _build_progress_callback(run_id, patient_id=job.patient_id),
                body,
                patient_id=job.patient_id,
                encounter_id=job.encounter_id,
                run_id=run_id,
                dry_run=job.dry_run,
                trigger_analysis=job.trigger_analysis,
            )
            return

        pc = PatientGraphClient()
        try:
            rows = pc.run(
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
                "WHERE toString(p.id) = $pid "
                "  AND coalesce(e.classification_content_type, 'clinical') = 'clinical' "
                "  AND trim(coalesce(e.text, '')) <> '' "
                "RETURN toString(e.id) AS encounter_id",
                pid=job.patient_id,
            )
        finally:
            pc.close()

        if not rows:
            logger.warning("No clinical encounters for patient_id=%s", job.patient_id)
            return

        for row in rows:
            encounter_id = str(row.get("encounter_id") or "").strip()
            if not encounter_id:
                continue
            await _dispatch_engine_for_encounter(
                handler,
                _build_progress_callback(
                    run_id,
                    patient_id=job.patient_id,
                    suppress_run_completed=True,
                ),
                body,
                patient_id=job.patient_id,
                encounter_id=encounter_id,
                run_id=run_id,
                dry_run=job.dry_run,
                trigger_analysis=job.trigger_analysis,
            )
        from services.coding_worker.app.services.progress_publisher import (
            publish_progress,
        )

        publish_progress(
            run_id,
            {
                "type": "run_completed",
                "run_id": run_id,
                "patient_id": job.patient_id,
                "status": "completed",
            },
        )
        try:
            from libs.redis_client.rebuild_status import update_from_event

            update_from_event(
                job.patient_id,
                run_id,
                {
                    "type": "run_completed",
                    "run_id": run_id,
                    "patient_id": job.patient_id,
                    "status": "completed",
                },
            )
        except Exception:
            logger.debug(
                "final rebuild status update failed patient=%s run=%s",
                job.patient_id,
                run_id,
                exc_info=True,
            )
    finally:
        if audit_driver is not None:
            await audit_driver.close()
        await driver.close()
