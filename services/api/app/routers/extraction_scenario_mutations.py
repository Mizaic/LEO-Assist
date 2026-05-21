"""Extraction scenario create, update, and delete routes.

Routes
------
POST   /extraction-scenarios              Create a scenario
PUT    /extraction-scenarios/:case_id     Replace editable scenario fields
DELETE /extraction-scenarios/:case_id     Remove a scenario

Atlas trace:
  DI: DI-1B3B5375
  DO: DO-416BA91D
  Risk: R-80E8BD96
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import require_admin
from app.services.extraction_scenario_crud import (
    ScenarioValidationError,
    create_scenario,
    delete_scenario,
    update_scenario,
)
from libs.auth.org_scope import CallerScope

router = APIRouter(prefix="/extraction-scenarios", tags=["extraction-scenarios"])


class ExpectedPhrase(BaseModel):
    text: str
    semantic_tag: str = "finding"


class ScenarioWriteBody(BaseModel):
    site: str
    format: str
    markdown_body: str
    expected_strings: list[ExpectedPhrase] = Field(min_length=1)
    must_not_extract: list[str] = Field(default_factory=list)
    phrase_classes: list[str] = Field(default_factory=list)
    difficulty: list[str] = Field(default_factory=list)
    notes_for_clinician_review: str | None = None
    expected_observables: list[dict[str, Any]] | None = None
    synthetic_patient: dict[str, Any] | None = None
    blood_results: Any | None = None
    source_template_markdown: str | None = None
    schema_version: int = 1


class CreateScenarioBody(ScenarioWriteBody):
    case_id: str


def _coding_client():
    from app.db.neo4j_client import CodingGraphClient

    return CodingGraphClient()


def _body_dict(body: ScenarioWriteBody) -> dict[str, Any]:
    return body.model_dump()


@router.post("")
def create_scenario_route(
    body: CreateScenarioBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new extraction validation scenario."""
    client = _coding_client()
    try:
        return create_scenario(client, body.case_id.strip(), _body_dict(body))
    except ScenarioValidationError as exc:
        detail = str(exc)
        status = 409 if "already exists" in detail else 422
        raise HTTPException(status_code=status, detail=detail) from exc
    finally:
        client.close()


@router.put("/{case_id}")
def update_scenario_route(
    case_id: str,
    body: ScenarioWriteBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Replace editable fields and reset clinician approval."""
    client = _coding_client()
    try:
        return update_scenario(client, case_id, _body_dict(body))
    except ScenarioValidationError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail else 422
        raise HTTPException(status_code=status, detail=detail) from exc
    finally:
        client.close()


@router.delete("/{case_id}")
def delete_scenario_route(
    case_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Delete one extraction validation scenario."""
    client = _coding_client()
    try:
        return delete_scenario(client, case_id)
    except ScenarioValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()
