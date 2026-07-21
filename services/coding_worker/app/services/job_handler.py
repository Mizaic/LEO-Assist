"""Service Bus handler: validate coding jobs and run WorkflowEngine.

Atlas trace:
  DO: DO-4641EEE1
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4641EEE1")
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from libs.message_bus.base import Message

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_ALLOWED_MODES = frozenset(
    {"all", "extract_encounter", "extract_patient", "episode_bundle"}
)


class CodingJobMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    patient_id: str = Field(..., min_length=1, max_length=128)
    encounter_id: str | None = Field(default=None, max_length=128)
    episode_id: str | None = Field(default=None, max_length=128)
    encounter_ids: list[str] | None = Field(default=None)
    episode_context: dict[str, Any] | None = Field(default=None)
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

    @field_validator("episode_id")
    @classmethod
    def _validate_episode_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _ID_RE.fullmatch(value):
            raise ValueError("invalid episode_id")
        return value

    @field_validator("encounter_ids")
    @classmethod
    def _validate_encounter_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for raw in value:
            if not isinstance(raw, str) or not _ID_RE.fullmatch(raw):
                raise ValueError("invalid encounter_id in encounter_ids")
            cleaned.append(raw)
        return cleaned

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


async def _dispatch_engine_for_episode_bundle(
    handler,
    step_callback,
    base_body: dict[str, Any],
    *,
    patient_id: str,
    episode_id: str,
    encounter_ids: list[str],
    episode_context: dict[str, Any] | None,
    run_id: str,
    dry_run: bool,
    trigger_analysis: bool,
) -> None:
    """Dispatch a single episode-bundle event.

    The event holds the episode envelope plus the ordered list of
    encounter_ids that belong to it. WorkflowEngine receives a single
    `episode_bundle` event and decides internally how to fan out per
    encounter so each LLM call sees the bundle context.
    """
    body = {
        "event_type": "episode_bundle",
        "patient_id": patient_id,
        "encounter_id": (encounter_ids[0] if encounter_ids else None),
        "plan_definition_id": str(
            base_body.get("plan_definition_id") or "pd-episode-bundle-coding"
        ),
        "context": {
            "dry_run": dry_run,
            "mode": "episode_bundle",
            "episode_id": episode_id,
            "encounter_ids": list(encounter_ids),
            "episode_context": dict(episode_context or {}),
            "trigger_analysis": trigger_analysis,
        },
    }
    await handler.handle_message(
        Message(body=body, correlation_id=run_id, subject="episode-bundle"),
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

        if job.mode == "episode_bundle":
            if not job.episode_id or not job.encounter_ids:
                logger.error(
                    "episode_bundle job missing episode_id or encounter_ids"
                )
                return
            await _dispatch_engine_for_episode_bundle(
                handler,
                _build_progress_callback(run_id, patient_id=job.patient_id),
                body,
                patient_id=job.patient_id,
                episode_id=job.episode_id,
                encounter_ids=job.encounter_ids,
                episode_context=job.episode_context,
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

        encounter_ids = [
            str(row.get("encounter_id") or "").strip()
            for row in rows
            if str(row.get("encounter_id") or "").strip()
        ]

        # Bound per-patient encounter parallelism. Each encounter still
        # holds the upstream LLM rate limit etc., so we cap with a
        # semaphore. Default 4 concurrent encounters per patient.
        try:
            max_parallel = max(
                1, int(os.getenv("CODING_ENCOUNTER_PARALLELISM", "4"))
            )
        except ValueError:
            max_parallel = 4
        sem = asyncio.Semaphore(max_parallel)

        async def _run_one(encounter_id: str) -> None:
            async with sem:
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

        await asyncio.gather(
            *(_run_one(eid) for eid in encounter_ids), return_exceptions=False
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
