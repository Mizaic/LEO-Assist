"""REST endpoints for per-form schema annotation.

GET  /form-schemas/{fingerprint}   -- load schema for a fingerprint (or null)
PUT  /form-schemas/{fingerprint}   -- save / update schema
GET  /form-schemas                 -- list all saved schemas
POST /form-schemas/fingerprint     -- compute content fingerprint from sample text
POST /form-schemas/detect          -- LLM auto-detect sections from form text
GET  /form-schemas/letter-text     -- fetch referral letter text by UBRN

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fastapi import Query

from app.deps import require_role
from app.org_catalog_auth import FORM_TEACHER_ROLES
from libs.cypher.chunk_queries import GET_CHUNKS_BY_UBRN
from libs.llm_client.form_schema_detector import detect_form_sections
from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline.document_chunk_loader import build_document_chunk_state
from libs.pipeline.form_schema_store import (
    FormSchemaWrite,
    build_sections_from_request,
    delete_form_schema,
    load_form_schema,
    normalize_sections_for_request,
    save_form_schema,
)
from libs.pipeline.form_schema_template import (
    build_chunk_section_map,
    generate_normalised_template,
)
from libs.pipeline.document_quality import form_fingerprint
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
                "updated_at": str(r.get("updated_at") or ""),
                "organization_id": r.get("organization_id") or "",
                "service_id": r.get("service_id") or "",
            }
            for r in (rows or [])
        ]
    finally:
        client.close()
    return {"schemas": schemas}


class FingerprintRequest(BaseModel):
    text: str = Field(..., min_length=10)


@router.post("/fingerprint")
def compute_fingerprint(
    body: FingerprintRequest,
    _session: dict = Depends(require_form_teacher),
) -> dict[str, str]:
    """Return the content fingerprint for sample referral letter text."""
    return {"fingerprint": form_fingerprint(body.text)}


@router.get("/letter-text")
def get_letter_text_by_ubrn(
    ubrn: str = Query(..., description="UBRN or referral identifier"),
    organization_id: str = Query(..., description="Tenant organisation ID"),
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    """Return joined referral letter text from Neo4j for a given UBRN.

    Fetches :Chunk nodes linked via :HAS_DOCUMENT->:DocumentReference->:HAS_CHUNK,
    joins them in ordinal order, and strips PDF attachments.  The caller can
    use the returned ``text`` and ``fingerprint`` to auto-populate the teach
    dialog without manual copy-paste.

    Returns 404 when no chunks are found for the UBRN.
    """
    ubrn_clean = ubrn.strip()
    org_clean = organization_id.strip()
    if not ubrn_clean:
        raise HTTPException(status_code=400, detail="ubrn must not be empty")
    if not org_clean:
        raise HTTPException(status_code=400, detail="organization_id must not be empty")

    client = PatientGraphClient()
    try:
        rows = client.run(
            GET_CHUNKS_BY_UBRN,
            ubrn=ubrn_clean,
            organization_id=org_clean,
        )
    finally:
        client.close()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No referral letter found for UBRN {ubrn_clean!r}. "
            "Check the UBRN and organisation ID, then try again.",
        )

    state = build_document_chunk_state(rows)
    text = state.get("encounter_text") or ""
    if not text.strip():
        raise HTTPException(
            status_code=404,
            detail="Referral found but it contains no readable text. "
            "The document may not have been ingested yet.",
        )

    return {
        "text": text,
        "fingerprint": form_fingerprint(text),
        "chunk_count": len(state.get("sentences") or []),
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


@router.delete("/{fingerprint}")
def remove_schema(
    fingerprint: str,
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    fp = fingerprint.strip()
    if not fp or fp == "unknown":
        raise HTTPException(
            status_code=422, detail="A valid form fingerprint is required."
        )
    client = PatientGraphClient()
    try:
        deleted = delete_form_schema(client, fp)
    finally:
        client.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Form schema not found.")
    return {"deleted": True, "fingerprint": fp}


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
