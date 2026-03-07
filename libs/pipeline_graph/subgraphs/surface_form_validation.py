"""Surface-form validation subgraph for gold training pipeline.

Checks terminology alignment after resolution and creates review tasks for
low-confidence/ambiguous mismatches.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.cypher.surface_form_task_queries import (
    UPSERT_SURFACE_FORM_TASK,
    make_surface_form_task_id,
)
from libs.terminology.client import TerminologyClient

logger = logging.getLogger(__name__)


class SurfaceFormValidationState(TypedDict, total=False):
    entities: list[dict]
    encounter_text: str
    candidate_id: str
    surface_form_validation_threshold: float
    surface_form_tasks_created: int
    errors: list[str]


def _find_mismatches(state: SurfaceFormValidationState) -> dict[str, Any]:
    entities = list(state.get("entities") or [])
    errors = list(state.get("errors") or [])
    mismatches: list[dict[str, Any]] = []
    client = TerminologyClient()
    threshold = float(state.get("surface_form_validation_threshold", 0.9))

    for ent in entities:
        text = (ent.get("text") or "").strip()
        if not text:
            continue
        concept_id = str(ent.get("snomed_concept_id") or ent.get("concept_id") or "")
        expected_label = ent.get("semantic_tag") or ent.get("label")
        resolved = client.resolve([text], expected_tags={text: expected_label} if expected_label else None)
        candidates = resolved.get(text, [])
        if not candidates:
            mismatches.append(
                {
                    "entity": ent,
                    "reason": "no_candidates",
                    "candidates": [],
                    "confidence": 0.0,
                    "suggested": None,
                }
            )
            continue
        best = candidates[0]
        same_concept = concept_id and best.concept_id == concept_id
        high_conf = float(best.score or 0.0) >= threshold
        if same_concept and high_conf:
            ent["surface_form_validated"] = True
            continue
        mismatches.append(
            {
                "entity": ent,
                "reason": "mismatch",
                "candidates": [
                    {
                        "concept_id": c.concept_id,
                        "term": c.term,
                        "semantic_tag": c.semantic_tag,
                        "score": c.score,
                    }
                    for c in candidates[:5]
                ],
                "confidence": float(best.score or 0.0),
                "suggested": {
                    "concept_id": best.concept_id,
                    "term": best.term,
                    "semantic_tag": best.semantic_tag,
                },
            }
        )
    return {"entities": entities, "surface_form_mismatches": mismatches, "errors": errors}


def _apply_or_queue(state: SurfaceFormValidationState) -> dict[str, Any]:
    mismatches = list(state.get("surface_form_mismatches") or [])
    entities = list(state.get("entities") or [])
    encounter_text = state.get("encounter_text") or ""
    candidate_id = state.get("candidate_id") or ""
    threshold = float(state.get("surface_form_validation_threshold", 0.9))
    tasks_created = 0
    errors = list(state.get("errors") or [])
    ent_by_id = {id(e): e for e in entities}

    if not mismatches:
        return {"entities": entities, "surface_form_tasks_created": 0, "errors": errors}

    try:
        from app.db.neo4j_client import PatientGraphClient

        client = PatientGraphClient()
        try:
            with client.session() as session:
                for mm in mismatches:
                    ent = mm.get("entity") or {}
                    suggested = mm.get("suggested") or {}
                    confidence = float(mm.get("confidence") or 0.0)
                    if suggested and confidence >= threshold:
                        ent["snomed_concept_id"] = suggested.get("concept_id")
                        ent["term"] = suggested.get("term")
                        ent["semantic_tag"] = suggested.get("semantic_tag") or ent.get("semantic_tag")
                        ent["surface_form_validated"] = True
                        ent["surface_form_auto_corrected"] = True
                        continue

                    task_id = make_surface_form_task_id(
                        candidate_id=candidate_id or "unknown",
                        entity_text=str(ent.get("text") or ""),
                        current_concept=str(ent.get("snomed_concept_id") or ""),
                    )
                    session.run(
                        UPSERT_SURFACE_FORM_TASK,
                        task_id=task_id,
                        entity_text=str(ent.get("text") or ""),
                        current_concept=str(ent.get("snomed_concept_id") or ""),
                        current_term=str(ent.get("term") or ""),
                        suggested_concept=str(suggested.get("concept_id") or ""),
                        suggested_term=str(suggested.get("term") or ""),
                        candidates_json=json.dumps(mm.get("candidates") or []),
                        context_text=encounter_text,
                        candidate_id=candidate_id,
                        confidence=confidence,
                    )
                    ent["surface_form_task_id"] = task_id
                    ent["surface_form_validated"] = False
                    tasks_created += 1
        finally:
            client.close()
    except Exception as exc:
        logger.exception("surface_form_validation failed")
        errors.append(f"surface_form_validation: {exc}")
    return {"entities": entities, "surface_form_tasks_created": tasks_created, "errors": errors}


def build_surface_form_validation_subgraph() -> CompiledStateGraph:
    g = StateGraph(SurfaceFormValidationState)
    g.add_node("validate_surface_forms", _find_mismatches)
    g.add_node("apply_or_queue", _apply_or_queue)
    g.add_edge(START, "validate_surface_forms")
    g.add_edge("validate_surface_forms", "apply_or_queue")
    g.add_edge("apply_or_queue", END)
    return g.compile()

