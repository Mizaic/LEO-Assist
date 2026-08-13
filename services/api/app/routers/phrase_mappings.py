"""Phrase mappings inbox, drafts, review, and two-person publish.

Atlas trace:
  DI: DI-D90542E5, DI-6BD7B681
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-6BD7B681")

Mounted under /training by app.routers.training.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.services import phrase_mappings as service
from libs.auth.org_scope import CallerScope, get_caller_scope

router = APIRouter(tags=["phrase-mappings"])


class DraftRequest(BaseModel):
    phrase_key: str
    action: str
    concept_id: str = ""
    concept_term: str = ""
    reason: str = ""


class PhraseKeyRequest(BaseModel):
    phrase_key: str = Field(min_length=1)


@router.get("/phrase-mappings/counts")
def phrase_mapping_counts(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, int]:
    return service.counts(scope.email)


@router.get("/phrase-mappings")
def list_phrase_mappings(
    status: str = Query(default="inbox"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    skip = (page - 1) * page_size
    author = scope.email if status == "draft" else ""
    return service.list_phrases(status, author=author, skip=skip, limit=page_size)


@router.post("/phrase-mappings/draft")
def save_phrase_mapping_draft(
    body: DraftRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    return service.save_draft(
        body.phrase_key,
        action=body.action,
        actor=scope.email,
        concept_id=body.concept_id,
        concept_term=body.concept_term,
        reason=body.reason,
    )


@router.post("/phrase-mappings/submit")
def submit_phrase_mapping_drafts(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    return service.submit_drafts(scope.email)


@router.post("/phrase-mappings/send-back")
def send_back_phrase_mapping(
    body: PhraseKeyRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    _ = scope
    return service.send_back(body.phrase_key)


@router.post("/phrase-mappings/publish")
def publish_phrase_mapping(
    body: PhraseKeyRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    return service.publish(body.phrase_key, scope.email)
