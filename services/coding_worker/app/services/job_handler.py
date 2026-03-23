from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from libs.message_bus.base import Message

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class CodingJobMessage(BaseModel):
    patient_id: str = Field(..., min_length=1, max_length=128)
    encounter_id: str | None = Field(default=None, max_length=128)
    mode: Literal["all", "extract_encounter"] = "all"
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


async def handle_coding_job(message: Message) -> None:
    try:
        CodingJobMessage.model_validate(message.body or {})
    except ValidationError:
        logger.error("Malformed coding job message dropped")
        return
