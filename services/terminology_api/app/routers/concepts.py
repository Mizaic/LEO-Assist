"""SNOMED concept hierarchy and utility endpoints."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import (
    DESCENDANTS_TEMPLATE,
    GET_CONCEPT_FOR_SUGGESTION,
    RELATED_CONCEPTS_QUERY,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class DescendantResult(BaseModel):
    snomed_concept_id: str
    term: str
    semantic_tag: Optional[str] = None


class RelatedConceptRef(BaseModel):
    id: str
    fsn: str
    semantic_tag: Optional[str] = None
    rel: str


class RelatedConceptsResult(BaseModel):
    """Full ontology family for a lab-domain concept.

    For an observable_entity like ``MCH (observable entity)``:
    - ``interpreted_by_findings``  — findings that have this as their observable
      (e.g. *Finding of MCH level (finding)* via INTERPRETS)
    - ``component_of_procedures`` — procedures that include this observable
      (e.g. *MCH determination (procedure)* via HAS_COMPONENT)
    - ``interprets_observables``   — observables that this finding interprets
      (only populated when the queried concept is a finding)
    - ``has_components``           — observables that this procedure measures
      (only populated when the queried concept is a procedure)
    - ``associated_findings``      — findings linked via HAS_ASSOCIATED_FINDING
    """

    concept_id: str
    concept_fsn: str
    semantic_tag: Optional[str] = None
    interpreted_by_findings: List[RelatedConceptRef] = []
    component_of_procedures: List[RelatedConceptRef] = []
    interprets_observables: List[RelatedConceptRef] = []
    has_components: List[RelatedConceptRef] = []
    associated_findings: List[RelatedConceptRef] = []


@router.get(
    "/concepts/{concept_id}/related",
    response_model=RelatedConceptsResult,
    summary="Get related lab-domain concepts via SNOMED ontology relationships",
    description=(
        "Traverse INTERPRETS, HAS_COMPONENT, and HAS_ASSOCIATED_FINDING relationships "
        "to return the full observable_entity / procedure / finding family for a concept. "
        "Relationships are materialised by the phase-3 SNOMED attribute projection loader."
    ),
)
def get_related_concepts(concept_id: str) -> RelatedConceptsResult:
    """Return the SNOMED ontology family for a lab-domain concept."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(RELATED_CONCEPTS_QUERY, concept_id=concept_id)
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Concept {concept_id} not found or inactive")

    row = rows[0]

    def _to_refs(items: Any) -> List[RelatedConceptRef]:
        if not items:
            return []
        return [
            RelatedConceptRef(
                id=str(item["id"]),
                fsn=str(item["fsn"]),
                semantic_tag=item.get("semantic_tag"),
                rel=item.get("rel", ""),
            )
            for item in items
            if item and item.get("id") and item.get("fsn")
        ]

    return RelatedConceptsResult(
        concept_id=str(row["concept_id"]),
        concept_fsn=str(row["concept_fsn"]),
        semantic_tag=row.get("semantic_tag"),
        interpreted_by_findings=_to_refs(row.get("interpreted_by_findings")),
        component_of_procedures=_to_refs(row.get("component_of_procedures")),
        interprets_observables=_to_refs(row.get("interprets_observables")),
        has_components=_to_refs(row.get("has_components")),
        associated_findings=_to_refs(row.get("associated_findings")),
    )


@router.get("/concepts/{concept_id}/descendants", response_model=List[DescendantResult])
def get_descendants(
    concept_id: str,
    depth: int = Query(default=3, ge=1, le=5, description="IS_A traversal depth"),
    limit: int = Query(default=300, ge=1, le=500, description="Maximum number of results"),
    semantic_tag: Optional[str] = Query(default=None, description="Filter by semantic tag"),
):
    """Return active SNOMED descendants of a concept via IS_A relationships."""
    query = DESCENDANTS_TEMPLATE.format(depth=int(depth))
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            query,
            concept_id=concept_id,
            semantic_tag=semantic_tag,
            limit=limit,
        )
        if rows is None:
            raise HTTPException(status_code=404, detail=f"Concept {concept_id} not found or has no descendants")
        return rows
    finally:
        client.close()


@router.post("/concepts/{concept_id}/suggest-aliases")
def suggest_aliases_for_concept(concept_id: str):
    """Use a small LLM to suggest additional surface-form aliases for a SNOMED concept."""
    from libs.llm_client.factory import create_llm

    client = KnowledgeGraphClient()
    try:
        rows = client.run(GET_CONCEPT_FOR_SUGGESTION, concept_id=concept_id)
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Concept {concept_id} not found or inactive")

    row = rows[0]
    concept_fsn: str = row["concept_fsn"]
    semantic_tag: str = row.get("semantic_tag") or "clinical finding"
    existing: list[str] = row.get("existing_aliases") or []
    existing_lower = {e.lower() for e in existing}

    existing_list = ", ".join(f'"{e}"' for e in existing) if existing else "none yet"

    system_prompt = (
        "You are a UK primary care clinical terminology assistant. "
        "You suggest short text strings that UK GPs write in free-text consultation notes. "
        "Focus on NHS-specific abbreviations, clinical shorthand, and common spelling variants. "
        "Respond ONLY with a valid JSON array of strings — no explanation, no markdown fences."
    )
    user_prompt = (
        f'Concept: "{concept_fsn}" (SNOMED {concept_id}, type: {semantic_tag})\n'
        f"Existing aliases: {existing_list}\n\n"
        "Suggest up to 10 additional short phrases (1–6 words each) a UK GP might write "
        "in a free-text consultation note to mean this concept. "
        "Include abbreviations, misspellings, acronyms, and NHS shorthand. "
        "Do NOT repeat the existing aliases.\n"
        'Output format: ["alias1", "alias2", ...]'
    )

    try:
        llm = create_llm(tier="small")
        response = llm.converse(
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=512,
            temperature=0.3,
        )
        text = response.text.strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return {"suggestions": [], "concept_id": concept_id}
        raw = json.loads(match.group())
        suggestions = [
            s.strip()
            for s in raw
            if isinstance(s, str) and s.strip() and s.strip().lower() not in existing_lower
        ]
        return {"suggestions": suggestions[:10], "concept_id": concept_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("suggest-aliases LLM error for concept %s: %s", concept_id, exc)
        return {"suggestions": [], "concept_id": concept_id}
