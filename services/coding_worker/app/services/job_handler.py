"""Service Bus handler: validate coding job messages and run CodingPipeline."""

from __future__ import annotations

import logging
import os
import re

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
        await _run_coding_job(job)
    except Exception:
        logger.exception("Coding job failed patient_id=%s", job.patient_id)


async def _run_coding_job(job: CodingJobMessage) -> None:
    from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
    from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

    coding_mode = os.getenv("CODING_MODE", "hitl")
    pc = PatientGraphClient()
    kc = KnowledgeGraphClient()
    try:
        pipeline = CodingPipeline(pc, kc, coding_mode=coding_mode)
        if job.mode == "extract_encounter":
            if not job.encounter_id:
                logger.error("extract_encounter job missing encounter_id")
                return
            await pipeline.run_single_encounter(
                job.patient_id,
                job.encounter_id,
                dry_run=job.dry_run,
            )
            return

        rows = pc.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid AND e.classification_content_type = 'clinical' "
            "RETURN e.id AS encounter_id",
            pid=job.patient_id,
        )
        if not rows:
            logger.warning("No clinical encounters for patient_id=%s", job.patient_id)
            return
        for row in rows:
            eid = str(row.get("encounter_id") or "").strip()
            if not eid:
                continue
            await pipeline.run_single_encounter(
                job.patient_id,
                eid,
                dry_run=job.dry_run,
            )
    finally:
        pc.close()
        kc.close()
