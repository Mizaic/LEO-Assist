"""SNOMED concept hierarchy and utility endpoints."""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import (
    DESCENDANTS_TEMPLATE,
    GET_CONCEPT_FOR_SUGGESTION,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class DescendantResult(BaseModel):
    snomed_concept_id: str
    term: str
    semantic_tag: Optional[str] = None


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
