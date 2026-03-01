"""Write approved surface-form -> SNOMED mappings back to the coding graph.

Reads approved EncounterCandidates from the patient graph, extracts
surface-form -> concept mappings, and writes SurfaceForm nodes + MAPS_TO
relationships into the coding graph so the resolver can learn from
reviewer corrections.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


UPSERT_SURFACE_FORMS = """
UNWIND $rows AS r
MATCH (c:Concept {id: r.concept_id})
MERGE (sf:SurfaceForm {normalized: r.normalized})
ON CREATE SET sf.created_at = datetime(), sf.created_by = r.approved_by
SET sf.form = r.form,
    sf.source = r.source,
    sf.status = r.status,
    sf.last_seen_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.created_by = r.approved_by
SET m.confidence = r.confidence,
    m.approved_by = r.approved_by,
    m.approved_at = datetime(),
    m.provenance = r.provenance
RETURN count(sf) AS written
"""

LIST_APPROVED_WITH_REVIEWER = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved'
OPTIONAL MATCH (c)-[:HAS_TASK]->(:ReviewTask)-[:HAS_APPROVAL]->(a:Approval)
RETURN c, a.reviewer AS reviewer
ORDER BY c.patient_id, c.encounter_id
"""

LIST_APPROVED_FOR_PATIENT_WITH_REVIEWER = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved' AND c.patient_id = $patient_id
OPTIONAL MATCH (c)-[:HAS_TASK]->(:ReviewTask)-[:HAS_APPROVAL]->(a:Approval)
RETURN c, a.reviewer AS reviewer
ORDER BY c.encounter_id
"""


def _normalize(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


@dataclass
class WritebackStats:
    candidates_scanned: int = 0
    terms_scanned: int = 0
    eligible: int = 0
    written: int = 0
    skipped_no_concept: int = 0


def _extract_surface_form_rows(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], WritebackStats]:
    """Extract surface-form -> concept rows from approved candidates."""
    stats = WritebackStats()
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []

    for record in candidates:
        candidate = dict(record["c"])
        reviewer = record.get("reviewer") or "system"
        stats.candidates_scanned += 1

        try:
            sentences = json.loads(candidate.get("sentences_json", "[]"))
        except json.JSONDecodeError:
            sentences = []

        for sentence in sentences:
            for term in sentence.get("terms", []):
                stats.terms_scanned += 1
                coding = term.get("coding", {})
                concept_id = str(coding.get("snomed_concept_id", "") or "").strip()
                surface_text = str(term.get("text", "") or "").strip()

                if not concept_id or not surface_text:
                    stats.skipped_no_concept += 1
                    continue

                normalized = _normalize(surface_text)
                key = (normalized, concept_id)
                if key in seen:
                    continue
                seen.add(key)

                stats.eligible += 1
                rows.append({
                    "form": surface_text,
                    "normalized": normalized,
                    "concept_id": concept_id,
                    "confidence": float(coding.get("score", 0.9)),
                    "approved_by": reviewer,
                    "source": "hitl_approved",
                    "status": "approved",
                    "provenance": "hitl_gold_sync",
                })

    return rows, stats


def writeback_approved_terms(
    *,
    patient_session,
    coding_session,
    patient_id: str | None = None,
    batch_size: int = 500,
) -> dict[str, Any]:
    """
    Read approved candidates from patient graph, write SurfaceForm nodes
    to coding graph. Returns stats dict.
    """
    if patient_id:
        records = list(patient_session.run(
            LIST_APPROVED_FOR_PATIENT_WITH_REVIEWER,
            patient_id=patient_id,
        ))
    else:
        records = list(patient_session.run(LIST_APPROVED_WITH_REVIEWER))

    rows, stats = _extract_surface_form_rows(records)

    if not rows:
        logger.info(
            "Writeback: %d candidates scanned, no eligible surface forms",
            stats.candidates_scanned,
        )
        return {
            "candidates_scanned": stats.candidates_scanned,
            "terms_scanned": stats.terms_scanned,
            "surface_forms_written": 0,
            "skipped_no_concept": stats.skipped_no_concept,
        }

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        result = coding_session.run(UPSERT_SURFACE_FORMS, rows=chunk)
        record = result.single()
        batch_written = record["written"] if record else len(chunk)
        stats.written += batch_written
        logger.info(
            "Writeback: wrote %d/%d surface forms",
            stats.written, len(rows),
        )

    logger.info(
        "Writeback complete - %d candidates, %d terms, %d surface forms written",
        stats.candidates_scanned, stats.terms_scanned, stats.written,
    )
    return {
        "candidates_scanned": stats.candidates_scanned,
        "terms_scanned": stats.terms_scanned,
        "surface_forms_written": stats.written,
        "skipped_no_concept": stats.skipped_no_concept,
    }
