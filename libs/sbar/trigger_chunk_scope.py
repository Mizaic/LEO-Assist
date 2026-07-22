"""Validate trigger chunk scope before extraction or SBAR retrieval (A3.1).

Every chunk in the trigger list must belong to the stated referral,
DocumentReference, patient and tenant. Preserves trigger order and rejects
duplicates or unknown chunk ids without returning clinical text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_CHUNK_SCOPE_QUERY = """
MATCH (c:Chunk {id: $chunk_id})
WHERE toString(coalesce(c.tenantId, '')) = $tenant_id
  AND (
    EXISTS {
      MATCH (rr:ReferralRequest {id: $referral_id})-[:HAS_DOCUMENT]->(dr:DocumentReference)
      -[:HAS_CHUNK]->(c)
      MATCH (rr)-[:FOR_PATIENT]->(p:Patient)
      WHERE toString(p.id) = $patient_id
    }
    OR (
      $document_reference_id <> ''
      AND EXISTS {
        MATCH (dr:DocumentReference {id: $document_reference_id})-[:HAS_CHUNK]->(c)
        MATCH (p:Patient)-[:HAS_DOCUMENT_REFERENCE]->(dr)
        WHERE toString(p.id) = $patient_id
      }
    )
  )
RETURN c.id AS id
LIMIT 1
"""


@dataclass(frozen=True)
class TriggerChunkScopeRequest:
    tenant_id: str
    patient_id: str
    chunk_ids: list[str]
    referral_id: str | None = None
    document_reference_id: str | None = None


@dataclass(frozen=True)
class TriggerChunkScopeError:
    code: str
    message: str
    chunk_id: str | None = None


@dataclass
class TriggerChunkScopeResult:
    ok: bool
    ordered_chunk_ids: list[str] = field(default_factory=list)
    errors: list[TriggerChunkScopeError] = field(default_factory=list)


def validate_trigger_chunk_scope(
    session: Any,
    request: TriggerChunkScopeRequest,
) -> TriggerChunkScopeResult:
    """Fail closed when any chunk is out of scope or duplicated."""
    tenant_id = str(request.tenant_id or "").strip()
    patient_id = str(request.patient_id or "").strip()
    referral_id = str(request.referral_id or "").strip()
    document_reference_id = str(request.document_reference_id or "").strip()
    errors: list[TriggerChunkScopeError] = []

    if not tenant_id:
        errors.append(
            TriggerChunkScopeError(
                code="tenant_missing",
                message="Tenant id is required to validate trigger chunks.",
            )
        )
    if not patient_id:
        errors.append(
            TriggerChunkScopeError(
                code="patient_missing",
                message="Patient id is required to validate trigger chunks.",
            )
        )
    if not referral_id and not document_reference_id:
        errors.append(
            TriggerChunkScopeError(
                code="scope_anchor_missing",
                message=(
                    "Referral id or document reference id is required "
                    "to validate trigger chunks."
                ),
            )
        )
    if errors:
        return TriggerChunkScopeResult(ok=False, errors=errors)

    seen: set[str] = set()
    ordered: list[str] = []
    for raw_id in request.chunk_ids:
        chunk_id = str(raw_id or "").strip()
        if not chunk_id:
            errors.append(
                TriggerChunkScopeError(
                    code="chunk_id_empty",
                    message="Trigger chunk id must not be empty.",
                )
            )
            continue
        if chunk_id in seen:
            errors.append(
                TriggerChunkScopeError(
                    code="chunk_duplicate",
                    message=f"Duplicate trigger chunk id {chunk_id!r}.",
                    chunk_id=chunk_id,
                )
            )
            continue
        seen.add(chunk_id)
        if not _chunk_in_scope(
            session,
            chunk_id=chunk_id,
            tenant_id=tenant_id,
            patient_id=patient_id,
            referral_id=referral_id,
            document_reference_id=document_reference_id,
        ):
            errors.append(
                TriggerChunkScopeError(
                    code="chunk_out_of_scope",
                    message=(
                        f"Chunk {chunk_id!r} is not linked to the stated "
                        "referral, document, patient or tenant."
                    ),
                    chunk_id=chunk_id,
                )
            )
            continue
        ordered.append(chunk_id)

    return TriggerChunkScopeResult(
        ok=not errors,
        ordered_chunk_ids=ordered,
        errors=errors,
    )


def _chunk_in_scope(
    session: Any,
    *,
    chunk_id: str,
    tenant_id: str,
    patient_id: str,
    referral_id: str,
    document_reference_id: str,
) -> bool:
    try:
        row = session.run(
            _CHUNK_SCOPE_QUERY,
            chunk_id=chunk_id,
            tenant_id=tenant_id,
            patient_id=patient_id,
            referral_id=referral_id,
            document_reference_id=document_reference_id,
        ).single()
    except Exception:
        return False
    return row is not None
