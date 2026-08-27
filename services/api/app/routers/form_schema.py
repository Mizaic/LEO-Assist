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
from app.org_catalog_auth import FORM_TEACHER_ROLES
from libs.llm_client.form_schema_detector import detect_form_sections
from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline.form_schema_store import (
    FormSchemaWrite,
    build_sections_from_request,
    load_form_schema,
    normalize_sections_for_request,
    save_form_schema,
)
from libs.pipeline.form_schema_template import (
    build_chunk_section_map,
    generate_normalised_template,
)
from libs.cypher.form_schema_queries import LIST_FORM_SCHEMAS, SAVE_NORMALISED_TEMPLATE

router = APIRouter(prefix="/form-schemas", tags=["form-schemas"])

# Roles that may teach a paused extraction form. Platform admins bypass
# via require_role. Do not widen this to any authenticated session.
require_form_teacher = require_role(*FORM_TEACHER_ROLES)


class AnalyteEntryRequest(BaseModel):
    label: str = ""
    snomed_code: str = ""
    display: str = ""


class FormSchemaItemRequest(BaseModel):
    pattern: str = ""
    entity_text: str = ""
    semantic_tag: str = "finding"
    assertion: str = "present"
    procedure_snomed: str = ""
    procedure_display: str = ""
    analytes: list[AnalyteEntryRequest] = Field(default_factory=list)
    value_placeholder: str = ""


class FormSectionRequest(BaseModel):
    section_id: str = Field(..., min_length=1)
    section_type: str = Field(..., min_length=1)
    label: str = ""
    start_pattern: str = ""
    items: list[FormSchemaItemRequest] = Field(default_factory=list)
    semantic_tags: list[str] = Field(default_factory=list)


class CompletenessGroupRequest(BaseModel):
    name: str = Field(..., min_length=1)
    kind: str = ""
    required: bool = True
    min_count: int = 1
    semantic_categories: list[str] = Field(default_factory=list)
    concept_ids: list[int] = Field(default_factory=list)
    members: list[dict[str, Any]] = Field(default_factory=list)
    if_group: dict[str, Any] | None = None
    then_group: dict[str, Any] | None = None


class SaveFormSchemaRequest(BaseModel):
    form_name: str = Field(..., min_length=1)
    sections: list[FormSectionRequest] = Field(..., min_items=1)
    saved_by: str = "unknown"
    status: str = "active"
    organization_id: str = ""
    service_id: str = ""
    completeness_groups: list[CompletenessGroupRequest] = Field(default_factory=list)


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
                "semantic_tags": list(s.semantic_tags),
                "items": [
                    {
                        "pattern": i.pattern,
                        "entity_text": i.entity_text,
                        "semantic_tag": i.semantic_tag,
                        "assertion": i.assertion,
                        "procedure_snomed": i.procedure_snomed,
                        "procedure_display": i.procedure_display,
                        "analytes": list(i.analytes),
                        "value_placeholder": i.value_placeholder,
                    }
                    for i in s.items
                ],
            }
            for s in schema.sections
        ],
        "created_at": schema.created_at,
        "created_by": schema.created_by,
        "organization_id": schema.organization_id,
        "service_id": schema.service_id,
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
    raw_sections = normalize_sections_for_request(
        [s.model_dump() for s in body.sections]
    )
    if not raw_sections:
        raise HTTPException(
            status_code=422,
            detail="At least one section with a start pattern is required.",
        )
    sections = build_sections_from_request(raw_sections)
    client = PatientGraphClient()
    try:
        schema = save_form_schema(
            client,
            FormSchemaWrite(
                fingerprint=fingerprint,
                form_name=body.form_name,
                sections=sections,
                created_by=(_session.get("email") or "").strip() or "unknown",
                status=body.status,
                organization_id=body.organization_id.strip(),
                service_id=body.service_id.strip(),
                completeness_groups=[g.model_dump() for g in body.completeness_groups],
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
                "organization_id": r.get("organization_id") or "",
                "service_id": r.get("service_id") or "",
            }
            for r in (rows or [])
        ]
    finally:
        client.close()
    return {"schemas": schemas}


class GenerateTemplateRequest(BaseModel):
    text: str = Field(..., min_length=10)


@router.post("/{fingerprint}/template")
def generate_template(
    fingerprint: str,
    body: GenerateTemplateRequest,
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    """Generate a de-identified form template and persist it on the schema.

    Returns the normalised_template string and chunk_section_map for display
    in the UI and runtime use in the normaliser.
    """
    import json as _json

    client = PatientGraphClient()
    try:
        schema = load_form_schema(client, fingerprint)
        if schema is None:
            raise HTTPException(
                status_code=404,
                detail="Schema not found. Save the form schema first.",
            )
        section_dicts = [
            {
                "section_id": s.section_id,
                "section_type": s.section_type,
                "start_pattern": s.start_pattern,
            }
            for s in schema.sections
        ]
        template = generate_normalised_template(body.text, section_dicts)
        chunks = body.text.split("\n\n")
        chunk_section_map = build_chunk_section_map(chunks, section_dicts)
        client.run(
            SAVE_NORMALISED_TEMPLATE,
            {
                "fingerprint": fingerprint,
                "normalised_template": template,
                "chunk_section_map": _json.dumps(chunk_section_map, ensure_ascii=True),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        client.close()
    return {
        "normalised_template": template,
        "chunk_section_map": chunk_section_map,
    }


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
