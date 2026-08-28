"""REST endpoints for per-form schema annotation.

GET  /form-schemas/blood-panel-presets -- standard NHS blood table preset
GET  /form-schemas/{fingerprint}   -- load schema for a fingerprint (or null)
PUT  /form-schemas/{fingerprint}   -- save / update schema
GET  /form-schemas                 -- list all saved schemas
POST /form-schemas/fingerprint     -- compute content fingerprint from sample text
POST /form-schemas/detect          -- LLM auto-detect sections from form text
GET  /form-schemas/letter-text     -- fetch referral letter text by UBRN
POST /form-schemas/seed-defaults   -- seed built-in templates (skips existing)

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
"""

from __future__ import annotations

import asyncio
import sys
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from fastapi import Query

_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from seed_sfh_gynae_2ww_template import (  # noqa: E402
    FINGERPRINT as _SFH_GYNAE_FINGERPRINT,
    build_payload as _build_sfh_gynae_payload,
)

from app.deps import require_role
from app.org_catalog_auth import FORM_TEACHER_ROLES
from libs.cypher.chunk_queries import GET_CHUNKS_BY_UBRN
from libs.llm_client.form_schema_detector import detect_form_sections
from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline.blood_panel_presets import (
    blood_panel_preset_payload,
    unverified_preset_codes,
)
from libs.pipeline.document_chunk_loader import build_document_chunk_state
from libs.pipeline.form_schema_request import (
    build_sections_from_request,
    filter_schema_summaries,
    normalize_sections_for_request,
    schema_summary_from_row,
    schema_to_dict,
)
from libs.pipeline.form_schema_section_types import validate_section_type
from libs.pipeline.form_schema_store import (
    FormSchemaLookupError,
    FormSchemaWrite,
    delete_form_schema,
    load_form_schema,
    rebind_form_schema_ids,
    resolve_form_schema_traced,
    save_form_schema,
)
from libs.pipeline.form_schema_template import (
    build_chunk_section_map,
    generate_normalised_template,
)
from libs.pipeline.document_quality import form_fingerprint
from libs.cypher.form_schema_queries import (
    LIST_FORM_SCHEMAS,
    LIST_FORM_SCHEMA_SECTIONS,
    SAVE_NORMALISED_TEMPLATE,
)
from libs.pipeline.form_schema_similarity import (
    find_similar_sections,
    merge_borrowed_and_detected,
)

router = APIRouter(prefix="/form-schemas", tags=["form-schemas"])

# A failed lookup must never read as "this form was never taught".
_LOOKUP_UNAVAILABLE = (
    "We could not reach the form database, so we cannot tell you whether "
    "this form has been taught. Nothing was changed. Please try again in a "
    "moment, and tell support if it keeps happening."
)

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

    @field_validator("section_type")
    @classmethod
    def _known_section_type(cls, value: str) -> str:
        """Reject a section type the checkbox normaliser cannot dispatch on."""
        return validate_section_type(value)


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
    organization_name: str = ""
    service_name: str = ""
    completeness_groups: list[CompletenessGroupRequest] = Field(default_factory=list)


_schema_to_dict = schema_to_dict


@router.get("")
def list_schemas(
    organization_id: str = Query(""),
    service_id: str = Query(""),
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        rows = client.run(LIST_FORM_SCHEMAS)
        schemas = [schema_summary_from_row(r) for r in (rows or [])]
    finally:
        client.close()
    return {
        "schemas": filter_schema_summaries(
            schemas,
            organization_id=organization_id,
            service_id=service_id,
        )
    }


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


@router.get("/blood-panel-presets")
def blood_panel_presets(
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    """Return the standard NHS blood table as ordered_tests rows.

    Declared before ``GET /{fingerprint}`` so the literal path is not
    read as a form fingerprint.
    """
    return {
        "batteries": blood_panel_preset_payload(),
        "needs_clinical_review": unverified_preset_codes(),
    }


@router.post("/seed-defaults")
def seed_defaults(
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    """Seed built-in templates. Bind ids come from the fixture file."""
    client = PatientGraphClient()
    try:
        return _seed_sfh_gynae(client)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        client.close()


def _seed_sfh_gynae(client: Any) -> dict[str, Any]:
    """Create the SFH Gynae 2WW schema, or rebind live Organization/Service ids."""
    payload = _build_sfh_gynae_payload()
    raw_sections = normalize_sections_for_request(payload["sections"])
    sections = build_sections_from_request(raw_sections)
    action = rebind_form_schema_ids(
        client,
        FormSchemaWrite(
            fingerprint=_SFH_GYNAE_FINGERPRINT,
            form_name=payload["form_name"],
            sections=sections,
            created_by=payload.get("saved_by") or "seed-defaults",
            status=payload.get("status") or "active",
            organization_id=payload.get("organization_id") or "",
            service_id=payload.get("service_id") or "",
            organization_name=payload.get("organization_name") or "",
            service_name=payload.get("service_name") or "",
            organization_ods_code=payload.get("organization_ods_code") or "",
            completeness_groups=payload.get("completeness_groups") or [],
        ),
    )
    empty: list[str] = []
    return {
        "seeded": [_SFH_GYNAE_FINGERPRINT] if action == "seeded" else empty,
        "skipped": [_SFH_GYNAE_FINGERPRINT] if action == "skipped" else empty,
        "updated": [_SFH_GYNAE_FINGERPRINT] if action == "updated" else empty,
    }


@router.get("/{fingerprint}")
def get_schema(
    fingerprint: str,
    organization_id: str = Query(""),
    service_id: str = Query(""),
    ers_service_id: str = Query(""),
    _session: dict = Depends(require_form_teacher),
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        schema, match, _key, _label = resolve_form_schema_traced(
            client,
            fingerprint,
            organization_id=organization_id,
            service_id=service_id,
            ers_service_id=ers_service_id,
        )
    except FormSchemaLookupError as exc:
        raise HTTPException(status_code=503, detail=_LOOKUP_UNAVAILABLE) from exc
    finally:
        client.close()
    if schema is None:
        return {"schema": None, "match": "none"}
    return {"schema": _schema_to_dict(schema), "match": match}


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
                organization_name=body.organization_name.strip(),
                service_name=body.service_name.strip(),
                organization_ods_code=body.organization_id.strip(),
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
            fingerprint=fingerprint,
            normalised_template=template,
            chunk_section_map=_json.dumps(chunk_section_map, ensure_ascii=True),
        )
    except HTTPException:
        raise
    except FormSchemaLookupError as exc:
        raise HTTPException(status_code=503, detail=_LOOKUP_UNAVAILABLE) from exc
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
    """Auto-detect sections, pre-populating any that match a known schema.

    Step 1: load all active FormSchema nodes and run fuzzy similarity
    against the new form text (no LLM cost, instant).
    Step 2: call the big-tier LLM for the remaining unmatched content.
    Step 3: merge -- borrowed sections take priority over LLM output for
    the same heading, but LLM sections for novel headings are kept.

    Borrowed sections carry a ``borrowed_from`` key with org, service,
    form name, and confidence so the clinician can see provenance and
    override or skip.
    """
    loop = asyncio.get_event_loop()
    known_schemas = _load_known_schema_dicts()
    try:
        llm_sections = await loop.run_in_executor(
            None, partial(detect_form_sections, body.text)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not known_schemas:
        return {"sections": llm_sections, "borrowed_count": 0}

    chunks = body.text.split("\n\n")
    borrowed = find_similar_sections(chunks, known_schemas)
    merged = merge_borrowed_and_detected(borrowed, llm_sections)
    return {"sections": merged, "borrowed_count": len(borrowed)}


def _load_known_schema_dicts() -> list[dict[str, Any]]:
    """Fetch all active FormSchema section data from Neo4j.

    Returns an empty list on any error so the detect endpoint degrades
    gracefully to LLM-only detection.
    """
    import json as _json

    client = PatientGraphClient()
    try:
        rows = client.run(LIST_FORM_SCHEMA_SECTIONS) or []
    except Exception:
        return []
    finally:
        client.close()

    result: list[dict[str, Any]] = []
    for row in rows:
        sections_json = row.get("sections_json") or "[]"
        try:
            sections = _json.loads(sections_json)
        except Exception:
            sections = []
        result.append(
            {
                "fingerprint": row.get("fingerprint") or "",
                "form_name": row.get("form_name") or "",
                "organization_id": row.get("organization_id") or "",
                "service_id": row.get("service_id") or "",
                "sections": sections,
            }
        )
    return result
