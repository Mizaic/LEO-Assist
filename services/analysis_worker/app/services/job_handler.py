"""Service Bus handler: anchor detection + episode build per patient."""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from libs.domain_config.registry import DomainRegistry
from libs.message_bus.base import Message
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)


class AnalysisJobMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    patient_id: str = Field(..., min_length=1, max_length=128)
    start_date: str = Field(default="2000-01-01", min_length=8, max_length=32)
    end_date: str = Field(default="2030-12-31", min_length=8, max_length=32)
    domain_id: str = Field(default="cancer_audit", min_length=1, max_length=128)

    @field_validator("patient_id")
    @classmethod
    def _pid(cls, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise ValueError("patient_id required")
        return v


async def handle_analysis_job(message: Message) -> None:
    try:
        job = AnalysisJobMessage.model_validate(message.body or {})
    except ValidationError:
        logger.error("Malformed analysis job message dropped")
        return

    registry = DomainRegistry.from_defaults()
    from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors
    from services.analysis_worker.app.analyzers.episode_builder import build_episodes

    patient_client = PatientGraphClient()
    try:
        anchors = detect_anchors(
            patient_id=job.patient_id,
            start_date=job.start_date,
            end_date=job.end_date,
            patient_client=patient_client,
            registry=registry,
        )
        result = await build_episodes(
            patient_id=job.patient_id,
            anchors=anchors,
            patient_client=patient_client,
            domain_id=job.domain_id or os.getenv("ANALYSIS_DOMAIN_ID", "cancer_audit"),
        )
        logger.info(
            "Analysis job complete patient_id=%s episodes_created=%s errors=%s",
            job.patient_id,
            result.episodes_created,
            len(result.errors or []),
        )
    except Exception:
        logger.exception("Analysis job failed patient_id=%s", job.patient_id)
    finally:
        patient_client.close()
