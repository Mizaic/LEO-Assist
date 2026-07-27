"""Guidance concept helpers for the rule authoring UI.

Atlas trace:
  DI: DI-42246DA7
  DO: DO-F8C56339
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")

Currently hosts POST /guidance/concepts/expand-topic -- the "Ask LEO for
ideas" endpoint that turns a vague guideline phrase into plain-English
candidate terms. The UI then grounds each ticked term via terminology
search so SNOMED IDs never come from the LLM.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import require_admin
from libs.auth.org_scope import CallerScope
from libs.llm_client.topic_expansion import expand_topic_terms

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/guidance", tags=["guidance-concepts"])


class ExpandTopicBody(BaseModel):
    phrase: str = Field(..., min_length=2, max_length=400)
    tier: str = Field(default="small", max_length=16)


class ExpandTopicResponse(BaseModel):
    terms: list[str]
    reason: str = ""
    model_id: str = ""


@router.post("/concepts/expand-topic", response_model=ExpandTopicResponse)
def expand_topic(
    body: ExpandTopicBody,
    _scope: CallerScope = Depends(require_admin),
) -> ExpandTopicResponse:
    """Return plain-English clinical terms for a vague guideline phrase."""
    try:
        result = expand_topic_terms(phrase=body.phrase, tier=body.tier)
    except Exception as exc:
        logger.exception("guidance.concepts.expand-topic failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to ask LEO for ideas right now.",
        ) from exc
    return ExpandTopicResponse(
        terms=result.terms,
        reason=result.reason,
        model_id=result.model_id,
    )
