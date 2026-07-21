"""LEO-local concept CRUD for guidance triggers and narrative actions.

Atlas trace:
  DO: DO-77A48DBC
  DI: DI-4746A178, DI-B7FEA996, DI-F8634363
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-77A48DBC")

Atlas: local-concept design controls (guidance + extraction recovery).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from libs.neo4j_client.client import KnowledgeGraphClient
from libs.terminology.local_concepts import CODE_SYSTEM_LEO_LOCAL, is_local_concept_id
from services.terminology_api.app.services.local_concept_admin import (
    CONFLICTING_SNOMED,
    COUNT_LOCAL_CONCEPTS,
    CREATE_LOCAL_CONCEPT,
    DEACTIVATE_LOCAL_CONCEPT,
    ENSURE_ACTION_TEMPLATE,
    ENSURE_LOCAL_TERM,
    GET_LOCAL_CONCEPT,
    LIST_LOCAL_CONCEPTS,
    build_create_params,
    seed_reserved_action_params,
)

router = APIRouter(prefix="/local-concepts", tags=["local-concepts"])


class LocalConceptCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=200)
    concept_kind: Literal["finding", "procedure", "narrative_action", "both"] = (
        "finding"
    )
    concept_id: Optional[str] = None
    description: Optional[str] = None
    semantic_tag: Optional[str] = None
    created_by: str = "admin"


class LocalConceptOut(BaseModel):
    id: str
    fsn: str
    preferred_term: Optional[str] = None
    semantic_tag: Optional[str] = None
    code_system: str = CODE_SYSTEM_LEO_LOCAL
    concept_kind: Optional[str] = None
    is_local: bool = True
    active: bool = True
    description: Optional[str] = None


class LocalConceptList(BaseModel):
    items: list[LocalConceptOut]
    total: int
    offset: int
    limit: int


def _row_to_out(row: dict[str, Any]) -> LocalConceptOut:
    return LocalConceptOut(
        id=str(row["id"]),
        fsn=str(row.get("fsn") or row["id"]),
        preferred_term=row.get("preferred_term"),
        semantic_tag=row.get("semantic_tag"),
        code_system=str(row.get("code_system") or CODE_SYSTEM_LEO_LOCAL),
        concept_kind=row.get("concept_kind"),
        is_local=bool(row.get("is_local", True)),
        active=bool(row.get("active", True)),
        description=row.get("description"),
    )


@router.post("", response_model=LocalConceptOut, status_code=201)
def create_local_concept(body: LocalConceptCreate) -> LocalConceptOut:
    """Create or update a LEO-local Concept and index a Term for search."""
    try:
        params = build_create_params(
            concept_id=body.concept_id,
            display_name=body.display_name,
            concept_kind=body.concept_kind,
            description=body.description,
            created_by=body.created_by,
            semantic_tag=body.semantic_tag,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    client = KnowledgeGraphClient()
    try:
        conflict = client.run(
            CONFLICTING_SNOMED,
            id=params["id"],
            code_system=CODE_SYSTEM_LEO_LOCAL,
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Concept id {params['id']} already exists as a non-local "
                    "SNOMED concept and cannot be overwritten."
                ),
            )
        rows = client.run(CREATE_LOCAL_CONCEPT, **params)
        if not rows:
            raise HTTPException(
                status_code=500, detail="Failed to create local concept"
            )
        client.run(
            ENSURE_LOCAL_TERM,
            id=params["id"],
            term_normalized=params["term_normalized"],
            term_id=params["term_id"],
            preferred_term=params["preferred_term"],
        )
        return _row_to_out(rows[0])
    finally:
        client.close()


@router.get("", response_model=LocalConceptList)
def list_local_concepts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> LocalConceptList:
    """List LEO-local concepts."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            LIST_LOCAL_CONCEPTS,
            code_system=CODE_SYSTEM_LEO_LOCAL,
            offset=offset,
            limit=limit,
        )
        total_rows = client.run(COUNT_LOCAL_CONCEPTS, code_system=CODE_SYSTEM_LEO_LOCAL)
        total = int(total_rows[0]["total"]) if total_rows else 0
        return LocalConceptList(
            items=[_row_to_out(r) for r in rows or []],
            total=total,
            offset=offset,
            limit=limit,
        )
    finally:
        client.close()


@router.post("/seed-action-templates")
def seed_action_templates() -> dict[str, Any]:
    """Ensure reserved LEO-ACT-* templates exist in the global package."""
    from services.terminology_api.app.services.local_package_admin import (
        CONTAINS_CONCEPT,
        ENSURE_GLOBAL_PACKAGE,
        GLOBAL_DEFAULT_PACKAGE_ID,
    )

    client = KnowledgeGraphClient()
    created: list[str] = []
    try:
        client.run(
            ENSURE_GLOBAL_PACKAGE,
            id=GLOBAL_DEFAULT_PACKAGE_ID,
            name="LEO global local terminology",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        for params in seed_reserved_action_params():
            rows = client.run(ENSURE_ACTION_TEMPLATE, **params)
            if rows:
                cid = str(rows[0]["id"])
                created.append(cid)
                client.run(
                    CONTAINS_CONCEPT,
                    package_id=GLOBAL_DEFAULT_PACKAGE_ID,
                    concept_id=cid,
                )
        return {
            "seeded": created,
            "count": len(created),
            "package_id": GLOBAL_DEFAULT_PACKAGE_ID,
        }
    finally:
        client.close()


class DryRunAlias(BaseModel):
    form: str
    concept_id: str
    fsn: str = ""
    semantic_tag: str = "finding"


class DryRunRecoveryRequest(BaseModel):
    sample_text: str
    aliases: list[DryRunAlias] = Field(default_factory=list)


@router.post("/dry-run-recovery")
def dry_run_recovery(body: DryRunRecoveryRequest) -> dict[str, Any]:
    """Exact-match recovery dry-run for wizard sample text (no Neo4j write)."""
    from libs.ner.local_concept_recovery import (
        LocalConceptPattern,
        recover_local_concept_entities,
    )

    if not (body.sample_text or "").strip():
        raise HTTPException(status_code=422, detail="sample_text is required")
    patterns = [
        LocalConceptPattern(
            normalized=" ".join(a.form.lower().split()),
            form=a.form.strip(),
            concept_id=a.concept_id.strip().upper(),
            fsn=a.fsn or a.concept_id,
            semantic_tag=a.semantic_tag or "finding",
        )
        for a in body.aliases
        if a.form.strip() and is_local_concept_id(a.concept_id)
    ]
    recovered = recover_local_concept_entities(body.sample_text, [], patterns)
    return {
        "matched_count": len(recovered),
        "entities": recovered,
        "pattern_count": len(patterns),
    }


@router.get("/{concept_id}", response_model=LocalConceptOut)
def get_local_concept(concept_id: str) -> LocalConceptOut:
    """Fetch one LEO-local concept by id."""
    if not is_local_concept_id(concept_id):
        raise HTTPException(
            status_code=422,
            detail="concept_id must be a LEO-LOCAL-* or LEO-ACT-* identifier.",
        )
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            GET_LOCAL_CONCEPT,
            id=concept_id.strip().upper(),
            code_system=CODE_SYSTEM_LEO_LOCAL,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Local concept not found")
        return _row_to_out(rows[0])
    finally:
        client.close()


@router.post("/{concept_id}/deactivate", response_model=LocalConceptOut)
def deactivate_local_concept(
    concept_id: str,
    updated_by: str = Query(default="admin"),
) -> LocalConceptOut:
    """Deactivate a local concept (fail-closed at resolve)."""
    if not is_local_concept_id(concept_id):
        raise HTTPException(
            status_code=422,
            detail="concept_id must be a LEO-LOCAL-* or LEO-ACT-* identifier.",
        )
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            DEACTIVATE_LOCAL_CONCEPT,
            id=concept_id.strip().upper(),
            code_system=CODE_SYSTEM_LEO_LOCAL,
            updated_at=datetime.now(timezone.utc).isoformat(),
            updated_by=updated_by,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Local concept not found")
        fetched = client.run(
            GET_LOCAL_CONCEPT,
            id=concept_id.strip().upper(),
            code_system=CODE_SYSTEM_LEO_LOCAL,
        )
        if not fetched:
            raise HTTPException(status_code=404, detail="Local concept not found")
        return _row_to_out(fetched[0])
    finally:
        client.close()
