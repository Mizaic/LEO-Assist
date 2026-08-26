"""REST endpoints for per-form schema annotation.

GET  /form-schemas/{fingerprint}   -- load schema for a fingerprint (or null)
PUT  /form-schemas/{fingerprint}   -- save / update schema
GET  /form-schemas                 -- list all saved schemas
POST /form-schemas/detect          -- LLM auto-detect sections from form text

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import require_role
from libs.llm_client.form_schema_detector import detect_form_sections
from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline.form_schema_store import (
    build_sections_from_request,
    load_form_schema,
    save_form_schema,
)
from libs.cypher.form_schema_queries import LIST_FORM_SCHEMAS

router = APIRouter(prefix="/form-schemas", tags=["form-schemas"])

# Roles that may teach a paused extraction form. Platform admins bypass
# via require_role. Do not widen this to any authenticated session.
FORM_TEACHER_ROLES = (
    "validation",
    "operations_manager",
    "clinician_admin",
    "administrator",
)
require_form_teacher = require_role(*FORM_TEACHER_ROLES)


class FormSchemaItemRequest(BaseModel):
    pattern: str = Field(..., min_length=1)
    entity_text: str = Field(..., min_length=1)
    semantic_tag: str = "finding"
    assertion: str = "present"


class FormSectionRequest(BaseModel):
    section_id: str = Field(..., min_length=1)
    section_type: str = Field(..., min_length=1)
    label: str = ""
    start_pattern: str = Field(..., min_length=1)
    items: list[FormSchemaItemRequest] = Field(default_factory=list)


class SaveFormSchemaRequest(BaseModel):
    form_name: str = Field(..., min_length=1)
    sections: list[FormSectionRequest] = Field(..., min_items=1)
    saved_by: str = "unknown"
    status: str = "active"


def _schema_to_dict(schema: Any) -> dict[str, Any]:
    return {
        "schema_id": schema.schema_id,
        "fingerprint": schema.fingerprint,
        "form_name": schema.form_name,
        "version": schema.version,
        "status": schema.status,
        "sections": [
            {
                "section_id": s.section_id,
                "section_type": s.section_type,
                "label": s.label,
                "start_pattern": s.start_pattern,
                "items": [
                    {
                        "pattern": i.pattern,
                        "entity_text": i.entity_text,
                        "semantic_tag": i.semantic_tag,
                        "assertion": i.assertion,
                    }
                    for i in s.items
                ],
            }
            for s in schema.sections
        ],
        "created_at": schema.created_at,
        "created_by": schema.created_by,
    }


@router.get("/{fingerprint}")
def get_schema(
    fingerprint: str,
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        schema = load_form_schema(client, fingerprint)
    finally:
        client.close()
    if schema is None:
        return {"schema": None}
    return {"schema": _schema_to_dict(schema)}


@router.put("/{fingerprint}")
def save_schema(
    fingerprint: str,
    body: SaveFormSchemaRequest,
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    sections = build_sections_from_request([s.model_dump() for s in body.sections])
    client = PatientGraphClient()
    try:
        schema = save_form_schema(
            client,
            fingerprint=fingerprint,
            form_name=body.form_name,
            sections=sections,
            created_by=(_session.get("email") or "").strip()
            or "unknown",
            status=body.status,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        client.close()
    return {"schema": _schema_to_dict(schema), "saved": True}


@router.get("")
def list_schemas(
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        rows = client.run(LIST_FORM_SCHEMAS)
        schemas = [
            {
                "schema_id": r["schema_id"],
                "fingerprint": r["fingerprint"],
                "form_name": r["form_name"],
                "version": r["version"],
                "status": r["status"],
                "created_at": str(r.get("created_at") or ""),
            }
            for r in (rows or [])
        ]
    finally:
        client.close()
    return {"schemas": schemas}


class DetectFormRequest(BaseModel):
    text: str = Field(..., min_length=10)


@router.post("/detect")
async def detect_schema(
    body: DetectFormRequest,
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    """Use the LLM to auto-detect sections and suggest entity text.

    Runs detect_form_sections (one big-tier converse call) in a thread
    pool so the async event loop is not blocked.
    """
    loop = asyncio.get_event_loop()
    try:
        sections = await loop.run_in_executor(
            None, partial(detect_form_sections, body.text)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"sections": sections}
