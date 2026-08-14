"""SNOMED concept hierarchy and utility endpoints.

Atlas trace:
  DO: DO-A00CD165
  DI: DI-3FDBB57B
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A00CD165")
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from libs.llm_client.prompt_safety import INJECTION_GUARD
from libs.neo4j_client.client import KnowledgeGraphClient
from libs.terminology.semantic_tag import normalise_semantic_tag
from services.terminology_api.app.queries.terminology import (
    BATCH_RELATED_CONCEPTS_QUERY,
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
    - ``interpreted_by_findings`` -- findings that have this as their observable
      (e.g. *Finding of MCH level (finding)* via INTERPRETS)
    - ``component_of_procedures`` -- procedures that include this observable
      (e.g. *MCH determination (procedure)* via HAS_COMPONENT)
    - ``interprets_observables`` -- observables that this finding interprets
      (only populated when the queried concept is a finding)
    - ``has_components`` -- observables that this procedure measures
      (only populated when the queried concept is a procedure)
    - ``associated_findings`` -- findings linked via HAS_ASSOCIATED_FINDING
    - ``finding_sites`` -- body structures via HAS_FINDING_SITE
    - ``procedure_sites`` -- body structures via HAS_PROCEDURE_SITE
    """

    concept_id: str
    concept_fsn: str
    semantic_tag: Optional[str] = None
    interpreted_by_findings: List[RelatedConceptRef] = []
    component_of_procedures: List[RelatedConceptRef] = []
    interprets_observables: List[RelatedConceptRef] = []
    has_components: List[RelatedConceptRef] = []
    associated_findings: List[RelatedConceptRef] = []
    finding_sites: List[RelatedConceptRef] = []
    procedure_sites: List[RelatedConceptRef] = []


class BatchRelatedRequest(BaseModel):
    concept_ids: List[str]


class BatchRelatedResponse(BaseModel):
    results: dict[str, RelatedConceptsResult]


@router.get(
    "/concepts/{concept_id}/related",
    response_model=RelatedConceptsResult,
    summary="Get related lab-domain concepts via SNOMED ontology relationships",
    description=(
        "Traverse INTERPRETS, HAS_COMPONENT, HAS_ASSOCIATED_FINDING, "
        "HAS_FINDING_SITE, and HAS_PROCEDURE_SITE relationships "
        "to return the ontology family for a concept. "
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
        raise HTTPException(
            status_code=404, detail=f"Concept {concept_id} not found or inactive"
        )

    return _row_to_related_result(rows[0])


@router.post(
    "/concepts/batch-related",
    response_model=BatchRelatedResponse,
    summary="Batch-fetch SNOMED ontology neighbours for many concepts",
)
def batch_related_concepts(body: BatchRelatedRequest) -> BatchRelatedResponse:
    """Return related-concept maps keyed by concept id."""
    ids = [str(cid).strip() for cid in body.concept_ids if str(cid).strip()]
    unique = list(dict.fromkeys(ids))
    if not unique:
        return BatchRelatedResponse(results={})
    client = KnowledgeGraphClient()
    try:
        rows = client.run(BATCH_RELATED_CONCEPTS_QUERY, concept_ids=unique)
    finally:
        client.close()
    results: dict[str, RelatedConceptsResult] = {}
    for row in rows or []:
        if not row or not row.get("concept_id"):
            continue
        parsed = _row_to_related_result(row)
        results[parsed.concept_id] = parsed
    return BatchRelatedResponse(results=results)


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


def _row_to_related_result(row: dict[str, Any]) -> RelatedConceptsResult:
    return RelatedConceptsResult(
        concept_id=str(row["concept_id"]),
        concept_fsn=str(row.get("concept_fsn") or ""),
        semantic_tag=row.get("semantic_tag"),
        interpreted_by_findings=_to_refs(row.get("interpreted_by_findings")),
        component_of_procedures=_to_refs(row.get("component_of_procedures")),
        interprets_observables=_to_refs(row.get("interprets_observables")),
        has_components=_to_refs(row.get("has_components")),
        associated_findings=_to_refs(row.get("associated_findings")),
        finding_sites=_to_refs(row.get("finding_sites")),
        procedure_sites=_to_refs(row.get("procedure_sites")),
    )


@router.get("/concepts/{concept_id}/descendants", response_model=List[DescendantResult])
def get_descendants(
    concept_id: str,
    depth: int = Query(default=3, ge=1, le=5, description="IS_A traversal depth"),
    limit: int = Query(
        default=300, ge=1, le=500, description="Maximum number of results"
    ),
    semantic_tag: Optional[str] = Query(
        default=None, description="Filter by semantic tag"
    ),
):
    """Return active SNOMED descendants of a concept via IS_A relationships."""
    query = DESCENDANTS_TEMPLATE.format(depth=int(depth))
    semantic_tag_norm = normalise_semantic_tag(semantic_tag) if semantic_tag else None
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            query,
            concept_id=concept_id,
            semantic_tag=semantic_tag_norm,
            limit=limit,
        )
        if rows is None:
            raise HTTPException(
                status_code=404,
                detail=f"Concept {concept_id} not found or has no descendants",
            )
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
        raise HTTPException(
            status_code=404, detail=f"Concept {concept_id} not found or inactive"
        )

    row = rows[0]
    concept_fsn: str = row["concept_fsn"]
    semantic_tag: str = row.get("semantic_tag") or "clinical finding"
    existing: list[str] = row.get("existing_aliases") or []
    existing_lower = {e.lower() for e in existing}

    existing_list = ", ".join(f'"{e}"' for e in existing) if existing else "none yet"

    system_prompt = INJECTION_GUARD + (
        "You are a UK primary care clinical terminology assistant. "
        "You suggest short text strings that UK GPs write in free-text consultation notes. "
        "Focus on NHS-specific abbreviations, clinical shorthand, and common spelling variants. "
        'Respond ONLY with {"suggestions": ["alias1", "alias2"]}. '
        "Do not add explanation or markdown fences."
    )
    user_prompt = (
        f'Concept: "{concept_fsn}" (SNOMED {concept_id}, type: {semantic_tag})\n'
        f"Existing aliases: {existing_list}\n\n"
        "Suggest up to 10 additional short phrases (1-6 words each) a UK GP might write "
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
            json_mode=True,
            structured_schema={
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1, "maxLength": 80},
                        "maxItems": 10,
                    }
                },
                "required": ["suggestions"],
                "additionalProperties": False,
            },
            agent_task="terminology_api_synonym_suggester",
        )
        text = response.text.strip()
        payload = json.loads(text)
        raw = payload.get("suggestions") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            return {"suggestions": [], "concept_id": concept_id}
        suggestions = [
            s.strip()
            for s in raw
            if isinstance(s, str)
            and s.strip()
            and s.strip().lower() not in existing_lower
        ]
        return {"suggestions": suggestions[:10], "concept_id": concept_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("suggest-aliases LLM error for concept %s: %s", concept_id, exc)
        return {"suggestions": [], "concept_id": concept_id}
