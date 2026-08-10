"""Preflight checks that SBAR task record ids belong to the stated patient.

Atlas trace:
  DO: DO-3CAFDCC3
  DI: DI-D394B618, DI-C07DF77C
  VT: VT-61E749AA
  Risk mitigated: R-0E8A90ED
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3CAFDCC3")

LEO CDS receives tasks from consuming systems. This module verifies graph
connectivity only: each referenced encounter, referral, document reference,
or chunk must be linked to the patient_id in the payload before any LLM
stage runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from libs.sbar.events import (
    BackgroundSourceType,
    SBARRequestPayload,
    SituationArtifactType,
)

_PATIENT_EXISTS = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
RETURN p.id AS id
LIMIT 1
"""

_ENCOUNTER_FOR_PATIENT = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter {id: $record_id})
WITH p, e
WHERE e IS NOT NULL
RETURN e.id AS id
LIMIT 1
UNION
MATCH (rr:ReferralRequest)-[:FOR_PATIENT]->(p:Patient)
WHERE toString(p.id) = $patient_id
  AND $record_id = toString(rr.id) + ':referral-assessment'
RETURN rr.id AS id
LIMIT 1
"""

_REFERRAL_FOR_PATIENT = """
MATCH (rr:ReferralRequest {id: $record_id})-[:FOR_PATIENT]->(p:Patient)
WHERE toString(p.id) = $patient_id
RETURN rr.id AS id
LIMIT 1
"""

_DOCUMENT_FOR_PATIENT = """
MATCH (dr:DocumentReference {id: $record_id})
WHERE EXISTS {
  MATCH (p:Patient)-[:HAS_DOCUMENT_REFERENCE]->(dr)
  WHERE toString(p.id) = $patient_id
} OR EXISTS {
  MATCH (rr:ReferralRequest)-[:HAS_DOCUMENT]->(dr)
  WHERE EXISTS {
    MATCH (rr)-[:FOR_PATIENT]->(p:Patient) WHERE toString(p.id) = $patient_id
  }
}
RETURN dr.id AS id
LIMIT 1
"""

_CHUNK_FOR_PATIENT = """
MATCH (:DocumentReference)-[:HAS_CHUNK]->(c:Chunk {id: $record_id})
WHERE EXISTS {
  MATCH (p:Patient)-[:HAS_DOCUMENT_REFERENCE]->(:DocumentReference)-[:HAS_CHUNK]->(c)
  WHERE toString(p.id) = $patient_id
} OR EXISTS {
  MATCH (rr:ReferralRequest)-[:HAS_DOCUMENT]->(:DocumentReference)-[:HAS_CHUNK]->(c)
  WHERE EXISTS {
    MATCH (rr)-[:FOR_PATIENT]->(p:Patient) WHERE toString(p.id) = $patient_id
  }
}
RETURN c.id AS id
LIMIT 1
"""

_PROCEDURE_EXISTS = """
MATCH (pr:ProcedureRequest {id: $record_id})
RETURN pr.id AS id
LIMIT 1
"""


@dataclass(frozen=True)
class ContextIntegrityError:
    code: str
    message: str
    record_type: str
    record_id: str


@dataclass
class ContextIntegrityResult:
    ok: bool
    errors: list[ContextIntegrityError] = field(default_factory=list)


def validate_sbar_context(
    session: Any, payload: SBARRequestPayload
) -> ContextIntegrityResult:
    """Return ok=True when every referenced record is connected to the patient."""
    patient_id = payload.situation.patient_id.strip()
    errors: list[ContextIntegrityError] = []

    if not _record_found(session, _PATIENT_EXISTS, patient_id=patient_id):
        return ContextIntegrityResult(
            ok=False,
            errors=[
                ContextIntegrityError(
                    code="patient_not_found",
                    message=(
                        "The patient id in this SBAR task was not found in "
                        "the patient graph."
                    ),
                    record_type="Patient",
                    record_id=patient_id,
                )
            ],
        )

    if payload.encounter_id:
        _append_if_missing(
            errors,
            session,
            _ENCOUNTER_FOR_PATIENT,
            patient_id=patient_id,
            record_id=payload.encounter_id.strip(),
            record_type="Encounter",
            code="encounter_patient_mismatch",
            message=(
                "The encounter in this SBAR task is not connected to the "
                "stated patient."
            ),
        )

    for ref in payload.situation.artifacts:
        if not ref.id:
            continue
        record_id = ref.id.strip()
        if ref.type is SituationArtifactType.encounter:
            _append_if_missing(
                errors,
                session,
                _ENCOUNTER_FOR_PATIENT,
                patient_id=patient_id,
                record_id=record_id,
                record_type="Encounter",
                code="encounter_patient_mismatch",
                message=(
                    "A situation encounter is not connected to the " "stated patient."
                ),
            )
        elif ref.type is SituationArtifactType.referral_request:
            _append_if_missing(
                errors,
                session,
                _REFERRAL_FOR_PATIENT,
                patient_id=patient_id,
                record_id=record_id,
                record_type="ReferralRequest",
                code="referral_patient_mismatch",
                message=(
                    "The referral in this SBAR task is not connected to "
                    "the stated patient."
                ),
            )
        elif ref.type is SituationArtifactType.procedure_request:
            if not _record_found(session, _PROCEDURE_EXISTS, record_id=record_id):
                errors.append(
                    ContextIntegrityError(
                        code="procedure_not_found",
                        message="The procedure request id was not found.",
                        record_type="ProcedureRequest",
                        record_id=record_id,
                    )
                )
        elif ref.type is SituationArtifactType.document_reference:
            _append_if_missing(
                errors,
                session,
                _DOCUMENT_FOR_PATIENT,
                patient_id=patient_id,
                record_id=record_id,
                record_type="DocumentReference",
                code="document_patient_mismatch",
                message=(
                    "A situation document is not connected to the " "stated patient."
                ),
            )

    for src in payload.background:
        record_id = src.id.strip()
        if src.type is BackgroundSourceType.encounter:
            _append_if_missing(
                errors,
                session,
                _ENCOUNTER_FOR_PATIENT,
                patient_id=patient_id,
                record_id=record_id,
                record_type="Encounter",
                code="encounter_patient_mismatch",
                message=(
                    "A background encounter is not connected to the " "stated patient."
                ),
            )
        elif src.type is BackgroundSourceType.document_reference:
            _append_if_missing(
                errors,
                session,
                _DOCUMENT_FOR_PATIENT,
                patient_id=patient_id,
                record_id=record_id,
                record_type="DocumentReference",
                code="document_patient_mismatch",
                message=(
                    "A background document is not connected to the " "stated patient."
                ),
            )
        elif src.type is BackgroundSourceType.chunk:
            _append_if_missing(
                errors,
                session,
                _CHUNK_FOR_PATIENT,
                patient_id=patient_id,
                record_id=record_id,
                record_type="Chunk",
                code="chunk_patient_mismatch",
                message=(
                    "A background document section is not connected to "
                    "the stated patient."
                ),
            )

    return ContextIntegrityResult(ok=not errors, errors=errors)


def _record_found(session: Any, query: str, **params: Any) -> bool:
    try:
        row = session.run(query, **params).single()
    except Exception:
        return False
    return row is not None


def _append_if_missing(
    errors: list[ContextIntegrityError],
    session: Any,
    query: str,
    *,
    patient_id: str,
    record_id: str,
    record_type: str,
    code: str,
    message: str,
) -> None:
    if _record_found(session, query, patient_id=patient_id, record_id=record_id):
        return
    errors.append(
        ContextIntegrityError(
            code=code,
            message=message,
            record_type=record_type,
            record_id=record_id,
        )
    )
