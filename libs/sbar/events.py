"""Queue contract for SBAR generation jobs.

A producer (Admin UI playground, encounter-created hook, referral writer)
publishes a ``sbar_requested`` message to the ``pipeline-jobs`` queue. The
pipeline worker dispatches the payload to ``SBAROrchestrator``.

Schema (validated with Pydantic) decouples producers from the orchestrator
and provides a single place to validate and document the contract -- see
DI-LEO-AI-186.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SituationArtifactType(str, Enum):
    """Permitted Situation input artefact node labels.

    The Situation always includes the patient. Optionally, callers may
    attach one or more record artefacts (a referral request, a procedure
    request, a fixed Patient context block, or a fixed text label such as
    'NCDA' or '<specialty> clinic'). The enum is open for extension --
    add new types here and update ``source_resolver._resolve_situation``.
    """

    referral_request = "ReferralRequest"
    procedure_request = "ProcedureRequest"
    patient_context = "PatientContext"
    fixed_text = "FixedText"


class BackgroundSourceType(str, Enum):
    """Permitted Background input source node labels."""

    encounter = "Encounter"
    document_reference = "DocumentReference"
    chunk = "Chunk"


class SBARSituationInput(BaseModel):
    """Situation inputs.

    ``patient_id`` is mandatory. ``artifacts`` is an ordered list of
    record-artefact references (zero or more). ``fixed_text`` entries
    may carry a literal ``text`` value rather than a Neo4j node id (used
    for 'NCDA' or specialty-clinic context labels).
    """

    patient_id: str = Field(..., min_length=1)
    artifacts: list["SBARArtifactRef"] = Field(default_factory=list)


class SBARArtifactRef(BaseModel):
    type: SituationArtifactType
    id: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _validate_id_or_text(self) -> "SBARArtifactRef":
        if self.type is SituationArtifactType.fixed_text:
            if not (self.text or "").strip():
                raise ValueError("fixed_text artefacts require non-empty text")
        else:
            if not (self.id or "").strip():
                raise ValueError(
                    f"{self.type.value} artefacts require a Neo4j node id"
                )
        return self


class SBARBackgroundSourceRef(BaseModel):
    """One Background input source -- an Encounter, DocumentReference, or Chunk.

    For DocumentReferences, the orchestrator resolves child :Chunk nodes
    automatically when present (and falls back to the document text body
    otherwise).
    """

    type: BackgroundSourceType
    id: str = Field(..., min_length=1)


class SBARRequestPayload(BaseModel):
    """Body of a ``sbar_requested`` pipeline-jobs message."""

    event_type: Literal["sbar_requested"] = "sbar_requested"
    run_id: str = Field(..., min_length=1)
    requested_by: str | None = None
    tenant_id: str | None = None

    situation: SBARSituationInput
    background: list[SBARBackgroundSourceRef] = Field(default_factory=list)

    # Optional restriction to a subset of guidelines for the Assessment
    # roaring-bitmap evaluation. Empty -> evaluate against the global scope.
    guideline_ids: list[str] = Field(default_factory=list)

    # Optional client-provided assessment id. If omitted the orchestrator
    # generates one (uuid4 hex). Useful for retries / idempotency tests.
    assessment_id: str | None = None

    # Optional encounter id used to reach back to a Patient or to attach a
    # HAS_ASSESSMENT relationship from a future/same-day encounter.
    encounter_id: str | None = None

    extra: dict[str, Any] = Field(default_factory=dict)

    def to_pipeline_message(self) -> dict[str, Any]:
        """Serialise to the dict form consumed by the workflow event handler."""
        return {
            "event_type": self.event_type,
            "run_id": self.run_id,
            "patient_id": self.situation.patient_id,
            "encounter_id": self.encounter_id or "",
            "context": self.model_dump(mode="json"),
        }


SBARSituationInput.model_rebuild()
