"""Terminology writeback: approved surface-form -> SNOMED mappings.

Ported from PCA services/api/app/services/terminology_writeback_service.py.
Reads approved EncounterCandidates from Patient Graph, writes SurfaceForm
nodes into Knowledge Graph so the resolver learns from reviewer corrections.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from services.terminology_api.app.queries.terminology import (
    UPSERT_SURFACE_FORMS,
    LIST_APPROVED_WITH_REVIEWER,
    LIST_APPROVED_FOR_PATIENT_WITH_REVIEWER,
)

logger = logging.getLogger(__name__)


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
    stats = WritebackStats()
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []

    for record in candidates:
        candidate = dict(record["c"])
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
                    "source": "hitl_approved",
                    "status": "pending",
                    "provenance": "hitl_gold_sync",
                })

    return rows, stats


def writeback_approved_terms(
    *,
    patient_session,
    knowledge_session,
    patient_id: str | None = None,
    batch_size: int = 500,
) -> dict[str, Any]:
    if patient_id:
        records = list(patient_session.run(
            LIST_APPROVED_FOR_PATIENT_WITH_REVIEWER, patient_id=patient_id
        ))
    else:
        records = list(patient_session.run(LIST_APPROVED_WITH_REVIEWER))

    rows, stats = _extract_surface_form_rows(records)

    if not rows:
        return {
            "candidates_scanned": stats.candidates_scanned,
            "terms_scanned": stats.terms_scanned,
            "surface_forms_written": 0,
            "skipped_no_concept": stats.skipped_no_concept,
        }

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        result = knowledge_session.run(UPSERT_SURFACE_FORMS, rows=chunk)
        record = result.single()
        batch_written = record["written"] if record else len(chunk)
        stats.written += batch_written

    logger.info(
        "Writeback complete — %d candidates, %d terms, %d surface forms written",
        stats.candidates_scanned, stats.terms_scanned, stats.written,
    )
    return {
        "candidates_scanned": stats.candidates_scanned,
        "terms_scanned": stats.terms_scanned,
        "surface_forms_written": stats.written,
        "skipped_no_concept": stats.skipped_no_concept,
    }
