"""Pydantic data models for the VerificationLock primitive.

A VerificationLock marks a reviewer-confirmed entity as immutable to
all automated mutation paths. The composite key ``(entity_type,
entity_id)`` uniquely identifies the locked entity; ``lock_id`` is an
opaque UUID used for release operations and audit references.

Atlas trace:
  DI: DI-C424BB44 (VerificationLock cross-entity primitive)
  VT: VT-96455BC1
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

LockEntityType = Literal[
    "episode",
    "encounter",
    "is_part_of_edge",
    "coded_link",
    "assertion",
]

LOCK_ENTITY_TYPES: tuple[LockEntityType, ...] = (
    "episode",
    "encounter",
    "is_part_of_edge",
    "coded_link",
    "assertion",
)

LockSource = Literal[
    "reconcile_pathway",
    "encounter_coding_review",
    "qa_override",
    "back_office",
]


class VerificationLock(BaseModel):
    """A reviewer-confirmed lock on a patient-graph entity."""

    lock_id: str = Field(..., min_length=8)
    entity_type: LockEntityType
    entity_id: str = Field(..., min_length=1)
    locked_by: str = Field(..., min_length=1)
    locked_by_role: str = Field(..., min_length=1)
    lock_reason: str = Field(..., min_length=1, max_length=500)
    source: LockSource
    locked_at: datetime
    updated_at: datetime

    @field_validator("entity_id")
    @classmethod
    def _entity_id_no_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("entity_id must not have leading/trailing whitespace")
        return value


class LockReleaseRequest(BaseModel):
    """Audit-stamped request to release an existing lock."""

    lock_id: str = Field(..., min_length=8)
    released_by: str = Field(..., min_length=1)
    released_by_role: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=500)
