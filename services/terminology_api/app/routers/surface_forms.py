"""Surface-form CRUD endpoints for the terminology API.

Atlas trace:
  UN: UN-72B60B2D
  DI: DI-47D2CD86
  DO: DO-5A88E0B9
  VT: VT-8DE34E84

Provides browsing, editing, and auditing of SurfaceForm->Concept mappings
stored in the Knowledge Graph.  These are consumed by the UI's
Settings -> Surface Forms page.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.service_auth import verify_service_token
from libs.neo4j_client.client import KnowledgeGraphClient
from libs.terminology.cache_invalidation import (
    invalidate_terminology_resolution_caches,
)
from services.terminology_api.app.queries.terminology import (
    AUDIT_SURFACE_FORM_DUPLICATES,
    COUNT_GROUPED_SURFACE_FORMS,
    COUNT_SURFACE_FORMS,
    DEDUPLICATE_SURFACE_FORM_RELS,
    DELETE_SURFACE_FORM,
    DELETE_SURFACE_FORM_MAPPING,
    GROUPED_SURFACE_FORMS,
    KEEP_SURFACE_FORM_MAPPING,
    LIST_SURFACE_FORMS,
    UPSERT_SURFACE_FORM_MAPPING,
)
from services.terminology_api.app.services.surface_form_admin import (
    approve_surface_form_mapping,
    deactivate_surface_form_mapping,
    list_mapping_audit_log,
    record_mapping_audit,
)

router = APIRouter()


# -- List (flat) ---------------------------------------------------------------


@router.get("/surface-forms")
def list_surface_forms(
    q: Optional[str] = Query(
        default=None, description="Filter by form text or concept name"
    ),
    concept_id: Optional[str] = Query(
        default=None, description="Filter by SNOMED concept ID"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Paginated list of surface forms with their mapped SNOMED concepts."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            LIST_SURFACE_FORMS, q=q, concept_id=concept_id, offset=offset, limit=limit
        )
        count_rows = client.run(COUNT_SURFACE_FORMS, q=q, concept_id=concept_id)
        total = count_rows[0]["total"] if count_rows else 0
        return {"items": rows, "total": total, "offset": offset, "limit": limit}
    finally:
        client.close()


# -- List (grouped by concept) -------------------------------------------------


@router.get("/surface-forms/grouped")
def list_grouped_surface_forms(
    q: Optional[str] = Query(
        default=None,
        description="Filter by surface form text, concept name, SNOMED ID, or Read code",
    ),
    status_filter: Optional[str] = Query(
        default=None,
        description="Filter by surface form status (e.g. 'pending', 'approved', 'active')",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return surface forms grouped by SNOMED concept, with pagination."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            GROUPED_SURFACE_FORMS,
            q=q,
            status_filter=status_filter,
            offset=offset,
            limit=limit,
        )
        count_rows = client.run(
            COUNT_GROUPED_SURFACE_FORMS,
            q=q,
            status_filter=status_filter,
        )
        total = count_rows[0]["total"] if count_rows else 0
        return {"items": rows, "total": total, "offset": offset, "limit": limit}
    finally:
        client.close()


# -- Duplicate audit -----------------------------------------------------------


@router.get("/surface-forms/duplicates")
def audit_surface_form_duplicates():
    """Return surface forms that have more than one MAPS_TO relationship."""
    client = KnowledgeGraphClient()
    try:
        return client.run(AUDIT_SURFACE_FORM_DUPLICATES)
    finally:
        client.close()


# -- Auto-deduplicate ----------------------------------------------------------


@router.post("/surface-forms/deduplicate")
def deduplicate_surface_forms(_: None = Depends(verify_service_token)):
    """Remove duplicate MAPS_TO relationships, keeping the highest-confidence mapping per surface form."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(DEDUPLICATE_SURFACE_FORM_RELS)
        removed = rows[0]["duplicates_removed"] if rows else 0
        if removed:
            invalidate_terminology_resolution_caches(reason="surface_form_deduplicate")
        return {"duplicates_removed": removed}
    finally:
        client.close()


# -- Upsert mapping ------------------------------------------------------------


class UpsertMappingRequest(BaseModel):
    normalized: str
    form: str
    concept_id: str
    confidence: float = 1.0
    source: str = "manual"
    provenance: str = "manual_correction"
    actor: str = "knowledge-admin"


@router.post("/surface-forms/upsert-mapping")
def upsert_surface_form_mapping(
    body: UpsertMappingRequest, _: None = Depends(verify_service_token)
):
    """Add or correct a MAPS_TO relationship. Creates the SurfaceForm node if it does not exist."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            UPSERT_SURFACE_FORM_MAPPING,
            normalized=body.normalized,
            form=body.form,
            concept_id=body.concept_id,
            confidence=body.confidence,
            source=body.source,
            provenance=body.provenance,
            actor=body.actor,
        )
        if not rows:
            raise HTTPException(
                status_code=404, detail=f"Concept {body.concept_id} not found"
            )
        row = rows[0]
        record_mapping_audit(
            client,
            normalized=body.normalized,
            action="upsert",
            actor=body.actor,
            outcome="success",
            detail="Mapping saved as pending review",
            concept_id=body.concept_id,
        )
        invalidate_terminology_resolution_caches(
            reason=f"surface_form_upsert:{body.normalized}"
        )
        return row
    finally:
        client.close()


class CreateLocalWithAliasRequest(BaseModel):
    display_name: str
    alias: str
    package_id: str
    concept_kind: str = "finding"
    concept_id: Optional[str] = None
    description: Optional[str] = None
    actor: str = "knowledge-admin"
    approve: bool = False
    org_id: Optional[str] = None


@router.post("/surface-forms/create-local-with-alias")
def create_local_with_alias(
    body: CreateLocalWithAliasRequest, _: None = Depends(verify_service_token)
):
    """Create a LEO-local Concept, bind it to a package, and map an alias.

    Happy path: concept + CONTAINS + pending (or approved) alias.
    Non-happy: missing package_id, package/org mismatch, empty alias.
    """
    from services.terminology_api.app.routers.local_concepts import (
        LocalConceptCreate,
        create_local_concept,
    )
    from services.terminology_api.app.services.local_package_admin import (
        CONTAINS_CONCEPT,
        GET_PACKAGE,
    )
    from services.terminology_api.app.services.surface_form_admin import (
        approve_surface_form_mapping,
    )

    package_id = (body.package_id or "").strip()
    if not package_id:
        raise HTTPException(status_code=422, detail="package_id is required")
    alias = (body.alias or "").strip()
    if not alias:
        raise HTTPException(status_code=422, detail="alias is required")
    normalized = " ".join(alias.lower().split())

    client = KnowledgeGraphClient()
    try:
        pkg_rows = client.run(GET_PACKAGE, id=package_id)
        if not pkg_rows:
            raise HTTPException(status_code=404, detail="Package not found")
        pkg = pkg_rows[0]
        if pkg.get("scope") == "tenant":
            caller_org = (body.org_id or "").strip() or None
            pkg_org = (pkg.get("org_id") or "").strip() or None
            if not caller_org or caller_org != pkg_org:
                raise HTTPException(
                    status_code=403,
                    detail="Tenant package does not match organisation scope.",
                )
    finally:
        client.close()

    concept = create_local_concept(
        LocalConceptCreate(
            display_name=body.display_name,
            concept_kind=body.concept_kind,  # type: ignore[arg-type]
            concept_id=body.concept_id,
            description=body.description,
            created_by=body.actor,
        )
    )
    client = KnowledgeGraphClient()
    try:
        link_rows = client.run(
            CONTAINS_CONCEPT, package_id=package_id, concept_id=concept.id
        )
        if not link_rows:
            raise HTTPException(
                status_code=500, detail="Failed to bind concept to package"
            )
    finally:
        client.close()

    mapping = upsert_surface_form_mapping(
        UpsertMappingRequest(
            normalized=normalized,
            form=alias,
            concept_id=concept.id,
            source="manual",
            provenance="create_local_with_alias",
            actor=body.actor,
        ),
        _=None,
    )
    if body.approve:
        client = KnowledgeGraphClient()
        try:
            mapping = approve_surface_form_mapping(
                client,
                normalized=normalized,
                reviewer=body.actor,
                concept_id=concept.id,
            )
        finally:
            client.close()
    return {
        "concept": concept.model_dump(),
        "mapping": mapping,
        "package_id": package_id,
    }


# -- Approve / deactivate ------------------------------------------------------


class ApproveMappingRequest(BaseModel):
    reviewer: str = "knowledge-admin"
    concept_id: Optional[str] = None


class DeactivateMappingRequest(BaseModel):
    actor: str = "knowledge-admin"


@router.post("/surface-forms/{normalized:path}/approve")
def approve_mapping(
    normalized: str,
    body: ApproveMappingRequest,
    _: None = Depends(verify_service_token),
):
    """Approve a pending surface form mapping for runtime resolve."""
    client = KnowledgeGraphClient()
    try:
        return approve_surface_form_mapping(
            client,
            normalized=normalized,
            reviewer=body.reviewer,
            concept_id=body.concept_id,
        )
    finally:
        client.close()


@router.post("/surface-forms/{normalized:path}/deactivate")
def deactivate_mapping(
    normalized: str,
    body: DeactivateMappingRequest,
    _: None = Depends(verify_service_token),
):
    """Deactivate a surface form mapping so it is excluded from runtime resolve."""
    client = KnowledgeGraphClient()
    try:
        return deactivate_surface_form_mapping(
            client,
            normalized=normalized,
            actor=body.actor,
        )
    finally:
        client.close()


# -- Audit log -----------------------------------------------------------------


@router.get("/surface-forms/audit-log")
def surface_form_audit_log(
    normalized: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return per-change audit entries for surface form mappings."""
    client = KnowledgeGraphClient()
    try:
        return list_mapping_audit_log(
            client,
            normalized=normalized,
            limit=limit,
            offset=offset,
        )
    finally:
        client.close()


# -- Delete (node or mapping) --------------------------------------------------


@router.delete("/surface-forms/{normalized:path}")
def delete_surface_form(
    normalized: str,
    concept_id: Optional[str] = Query(default=None),
    keep_concept_id: Optional[str] = Query(default=None),
    actor: str = Query(default="knowledge-admin"),
    _: None = Depends(verify_service_token),
):
    """Delete a surface form or one of its mappings.

    No params          -> detach-delete the entire SurfaceForm node.
    ?concept_id=X      -> remove only the MAPS_TO relationship to concept X.
    ?keep_concept_id=X -> remove all MAPS_TO relationships except to concept X.
    """
    client = KnowledgeGraphClient()
    try:
        if concept_id:
            rows = client.run(
                DELETE_SURFACE_FORM_MAPPING,
                normalized=normalized,
                concept_id=concept_id,
            )
            removed = rows[0]["removed"] if rows else 0
            if removed:
                record_mapping_audit(
                    client,
                    normalized=normalized,
                    action="delete_mapping",
                    actor=actor,
                    outcome="success",
                    detail=f"Removed MAPS_TO for concept {concept_id}",
                    concept_id=concept_id,
                )
                invalidate_terminology_resolution_caches(
                    reason=f"surface_form_delete_mapping:{normalized}"
                )
            return {
                "normalized": normalized,
                "concept_id": concept_id,
                "removed": removed,
            }
        if keep_concept_id:
            rows = client.run(
                KEEP_SURFACE_FORM_MAPPING,
                normalized=normalized,
                keep_concept_id=keep_concept_id,
            )
            removed = rows[0]["removed"] if rows else 0
            if removed:
                record_mapping_audit(
                    client,
                    normalized=normalized,
                    action="keep_mapping",
                    actor=actor,
                    outcome="success",
                    detail=f"Kept MAPS_TO for concept {keep_concept_id}",
                    concept_id=keep_concept_id,
                )
                invalidate_terminology_resolution_caches(
                    reason=f"surface_form_keep_mapping:{normalized}"
                )
            return {
                "normalized": normalized,
                "kept_concept_id": keep_concept_id,
                "removed": removed,
            }
        client.run(DELETE_SURFACE_FORM, normalized=normalized)
        record_mapping_audit(
            client,
            normalized=normalized,
            action="delete",
            actor=actor,
            outcome="success",
            detail="SurfaceForm node deleted",
        )
        invalidate_terminology_resolution_caches(
            reason=f"surface_form_delete:{normalized}"
        )
        return {"deleted": normalized}
    finally:
        client.close()
