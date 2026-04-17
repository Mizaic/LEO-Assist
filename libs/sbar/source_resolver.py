"""Resolve SBAR Situation/Background inputs into text + SNOMED codes.

This module is the single source of truth for fetching the raw material
that the SBAR LLM prompts and the deterministic Assessment formatter
consume. It hides Neo4j details from the orchestrator so that the
orchestrator stays purely about flow control.

Conventions
-----------
- Patient-level facts (name, dob, demographic context) are fetched
  separately by ``get_patient_context``.
- For Encounter inputs we PREFER any :DOCUMENTS->Concept SNOMED codes
  attached to the encounter. If none exist, we fall back to the
  encounter ``text`` property.
- For DocumentReference inputs we look for child :Chunk nodes with
  :DOCUMENTS codes first; if absent we fall back to the document text.
- For Chunk inputs we read codes if present, else the chunk text.
- Code dedup happens in this layer: each (concept_id, assertion) is
  only returned once, with provenance metadata aggregated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from libs.sbar.events import (
    BackgroundSourceType,
    SBARArtifactRef,
    SBARBackgroundSourceRef,
    SBARSituationInput,
    SituationArtifactType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ResolvedCode:
    concept_id: str
    term: str
    semantic_tag: str | None = None
    assertion: str | None = "present"
    evidence: str | None = None
    confidence: float | None = None
    source_label: str | None = None
    source_id: str | None = None


@dataclass
class ResolvedSource:
    """Text and codes resolved from one Background input."""

    source_label: str
    source_id: str
    text: str | None = None
    codes: list[ResolvedCode] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_codes(self) -> bool:
        return bool(self.codes)


@dataclass
class ResolvedSituation:
    patient_id: str
    patient_summary: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------


_PATIENT_CONTEXT_QUERY = """
MATCH (p:Patient {id: $patient_id})
RETURN p.id              AS id,
       coalesce(p.name, '')        AS name,
       coalesce(p.gender, '')      AS gender,
       coalesce(p.birthDate, '')   AS birth_date,
       coalesce(p.tenantId, '')    AS tenant_id
"""


_REFERRAL_REQUEST_QUERY = """
MATCH (rr:ReferralRequest {id: $artifact_id})
RETURN coalesce(rr.id, '')          AS id,
       coalesce(rr.specialty, '')   AS specialty,
       coalesce(rr.priority, '')    AS priority,
       coalesce(rr.reason, '')      AS reason,
       coalesce(rr.status, '')      AS status,
       coalesce(rr.created_at, '')  AS created_at
"""


_PROCEDURE_REQUEST_QUERY = """
MATCH (pr:ProcedureRequest {id: $artifact_id})
RETURN coalesce(pr.id, '')          AS id,
       coalesce(pr.code, '')        AS code,
       coalesce(pr.display, '')     AS display,
       coalesce(pr.intent, '')      AS intent,
       coalesce(pr.priority, '')    AS priority,
       coalesce(pr.created_at, '')  AS created_at
"""


_ENCOUNTER_TEXT_AND_CODES = """
MATCH (e:Encounter {id: $source_id})
OPTIONAL MATCH (e)-[d:DOCUMENTS]->(s)
RETURN coalesce(e.text, '')         AS text,
       coalesce(e.date, '')         AS date,
       coalesce(e.encounter_type, '') AS encounter_type,
       collect({
         concept_id:    toString(s.conceptId),
         term:          coalesce(s.name, ''),
         semantic_tag:  coalesce(s.semanticTag, ''),
         evidence:      coalesce(d.evidence, ''),
         confidence:    coalesce(d.confidence, 0.0),
         assertion:     coalesce(d.context, '')
       })                            AS codes
"""


_DOCUMENT_REFERENCE_CHUNKS = """
MATCH (dr:DocumentReference {id: $source_id})
OPTIONAL MATCH (dr)-[r:HAS_CHUNK]->(c:Chunk)
WITH dr, c, r
ORDER BY coalesce(r.ordinal, 0) ASC
WITH dr, collect(c) AS chunks
OPTIONAL MATCH (dr)-[:HAS_CONTENT]->(drc:DocumentReferenceContent)
RETURN coalesce(dr.id, '') AS id,
       chunks               AS chunks,
       coalesce(drc.data, '') AS fallback_text
"""


_CHUNK_TEXT_AND_CODES = """
MATCH (c:Chunk {id: $source_id})
OPTIONAL MATCH (c)-[d:DOCUMENTS]->(s)
RETURN coalesce(c.text, '')        AS text,
       coalesce(c.ordinal, 0)      AS ordinal,
       collect({
         concept_id:    toString(s.conceptId),
         term:          coalesce(s.name, ''),
         semantic_tag:  coalesce(s.semanticTag, ''),
         evidence:      coalesce(d.evidence, ''),
         confidence:    coalesce(d.confidence, 0.0),
         assertion:     coalesce(d.context, '')
       })                          AS codes
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _coerce_codes(raw: list[dict[str, Any]] | None,
                  *, source_label: str, source_id: str) -> list[ResolvedCode]:
    """Filter out null/empty rows produced by OPTIONAL MATCH and dedup."""
    if not raw:
        return []
    out: dict[tuple[str, str], ResolvedCode] = {}
    for row in raw:
        cid = str(row.get("concept_id") or "").strip()
        if not cid or cid.lower() == "none":
            continue
        assertion = (row.get("assertion") or "present").strip() or "present"
        key = (cid, assertion)
        if key in out:
            continue
        out[key] = ResolvedCode(
            concept_id=cid,
            term=str(row.get("term") or "").strip(),
            semantic_tag=(row.get("semantic_tag") or None) or None,
            assertion=assertion,
            evidence=(row.get("evidence") or None) or None,
            confidence=float(row.get("confidence") or 0.0),
            source_label=source_label,
            source_id=source_id,
        )
    return list(out.values())


def get_patient_context(session: Any, patient_id: str) -> dict[str, Any]:
    rec = session.run(_PATIENT_CONTEXT_QUERY, patient_id=patient_id).single()
    if rec is None:
        return {"id": patient_id}
    return {
        "id": rec["id"],
        "name": rec["name"] or None,
        "gender": rec["gender"] or None,
        "birth_date": rec["birth_date"] or None,
        "tenant_id": rec["tenant_id"] or None,
    }


def resolve_situation(
    session: Any, situation: SBARSituationInput
) -> ResolvedSituation:
    """Pull the Patient context + each requested record artefact."""
    summary = get_patient_context(session, situation.patient_id)
    artifacts: list[dict[str, Any]] = []
    for ref in situation.artifacts:
        try:
            artifacts.append(_resolve_artifact(session, ref))
        except Exception:
            logger.warning(
                "resolve_situation: failed to resolve artefact %s/%s",
                ref.type.value,
                ref.id or ref.text,
                exc_info=True,
            )
            artifacts.append({
                "type": ref.type.value,
                "id": ref.id,
                "text": ref.text,
                "error": "resolve_failed",
            })
    return ResolvedSituation(
        patient_id=situation.patient_id,
        patient_summary=summary,
        artifacts=artifacts,
    )


def _resolve_artifact(session: Any, ref: SBARArtifactRef) -> dict[str, Any]:
    if ref.type is SituationArtifactType.fixed_text:
        return {"type": ref.type.value, "text": ref.text}
    if ref.type is SituationArtifactType.patient_context:
        return {
            "type": ref.type.value,
            "id": ref.id,
            "text": ref.text or "",
        }
    if ref.type is SituationArtifactType.referral_request:
        rec = session.run(_REFERRAL_REQUEST_QUERY, artifact_id=ref.id).single()
        if rec is None:
            return {"type": ref.type.value, "id": ref.id, "error": "not_found"}
        return {"type": ref.type.value, **dict(rec)}
    if ref.type is SituationArtifactType.procedure_request:
        rec = session.run(_PROCEDURE_REQUEST_QUERY, artifact_id=ref.id).single()
        if rec is None:
            return {"type": ref.type.value, "id": ref.id, "error": "not_found"}
        return {"type": ref.type.value, **dict(rec)}
    return {"type": ref.type.value, "id": ref.id}


def resolve_background_sources(
    session: Any, sources: list[SBARBackgroundSourceRef]
) -> list[ResolvedSource]:
    out: list[ResolvedSource] = []
    for src in sources:
        try:
            if src.type is BackgroundSourceType.encounter:
                out.append(_resolve_encounter(session, src.id))
            elif src.type is BackgroundSourceType.document_reference:
                out.extend(_resolve_document_reference(session, src.id))
            elif src.type is BackgroundSourceType.chunk:
                out.append(_resolve_chunk(session, src.id))
        except Exception:
            logger.warning(
                "resolve_background_sources: failed for %s/%s",
                src.type.value,
                src.id,
                exc_info=True,
            )
            out.append(
                ResolvedSource(
                    source_label=src.type.value,
                    source_id=src.id,
                    metadata={"error": "resolve_failed"},
                )
            )
    return out


def _resolve_encounter(session: Any, encounter_id: str) -> ResolvedSource:
    rec = session.run(_ENCOUNTER_TEXT_AND_CODES, source_id=encounter_id).single()
    if rec is None:
        return ResolvedSource(
            source_label="Encounter",
            source_id=encounter_id,
            metadata={"error": "not_found"},
        )
    codes = _coerce_codes(
        rec["codes"], source_label="Encounter", source_id=encounter_id
    )
    return ResolvedSource(
        source_label="Encounter",
        source_id=encounter_id,
        text=rec["text"] or None,
        codes=codes,
        metadata={
            "date": rec["date"] or None,
            "encounter_type": rec["encounter_type"] or None,
        },
    )


def _resolve_document_reference(
    session: Any, document_reference_id: str
) -> list[ResolvedSource]:
    """Expand a DocumentReference into its child Chunks (or fallback text).

    Returns one ResolvedSource per chunk when chunks exist, otherwise
    a single ResolvedSource carrying the full document text.
    """
    rec = session.run(
        _DOCUMENT_REFERENCE_CHUNKS, source_id=document_reference_id
    ).single()
    if rec is None:
        return [
            ResolvedSource(
                source_label="DocumentReference",
                source_id=document_reference_id,
                metadata={"error": "not_found"},
            )
        ]
    chunks = rec["chunks"] or []
    if not chunks:
        return [
            ResolvedSource(
                source_label="DocumentReference",
                source_id=document_reference_id,
                text=rec["fallback_text"] or None,
                metadata={"chunked": False},
            )
        ]
    out: list[ResolvedSource] = []
    for chunk in chunks:
        cid = chunk.get("id") if isinstance(chunk, dict) else getattr(chunk, "id", None)
        if not cid:
            continue
        out.append(_resolve_chunk(session, cid))
    return out


def _resolve_chunk(session: Any, chunk_id: str) -> ResolvedSource:
    rec = session.run(_CHUNK_TEXT_AND_CODES, source_id=chunk_id).single()
    if rec is None:
        return ResolvedSource(
            source_label="Chunk",
            source_id=chunk_id,
            metadata={"error": "not_found"},
        )
    codes = _coerce_codes(
        rec["codes"], source_label="Chunk", source_id=chunk_id
    )
    return ResolvedSource(
        source_label="Chunk",
        source_id=chunk_id,
        text=rec["text"] or None,
        codes=codes,
        metadata={"ordinal": rec["ordinal"]},
    )


def aggregate_codes(sources: list[ResolvedSource]) -> list[ResolvedCode]:
    """Dedup codes across all background sources for the Assessment stage."""
    out: dict[tuple[str, str], ResolvedCode] = {}
    for src in sources:
        for code in src.codes:
            key = (code.concept_id, code.assertion or "present")
            if key not in out:
                out[key] = code
    return list(out.values())
