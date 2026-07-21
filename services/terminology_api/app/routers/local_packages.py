"""LocalTerminologyPackage CRUD, activate/retire, and active-patterns.

Atlas trace:
  DO: DO-77A48DBC
  DI: DI-4746A178, DI-B7FEA996, DI-F8634363
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-77A48DBC")

Atlas:
  DI: DI-FB0066CA
  DO: DO-7CF39715
  VT: VT-F266ECFB
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.services.local_package_admin import (
    CONTAINS_CONCEPT,
    COUNT_PACKAGES,
    CREATE_PACKAGE,
    ENSURE_GLOBAL_PACKAGE,
    GET_PACKAGE,
    GLOBAL_DEFAULT_PACKAGE_ID,
    LIST_PACKAGES,
    SET_STATUS,
    new_package_params,
)

router = APIRouter(prefix="/local-packages", tags=["local-packages"])


class PackageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    scope: Literal["global", "tenant"] = "global"
    org_id: Optional[str] = None
    created_by: str = "knowledge-admin"


class PackageOut(BaseModel):
    id: str
    name: str
    scope: str
    org_id: Optional[str] = None
    status: str
    version: int = 1
    concept_count: int = 0


class PackageList(BaseModel):
    items: list[PackageOut]
    total: int
    offset: int = 0
    limit: int = 50


def _row(row: dict[str, Any]) -> PackageOut:
    return PackageOut(
        id=str(row["id"]),
        name=str(row.get("name") or row["id"]),
        scope=str(row.get("scope") or "global"),
        org_id=row.get("org_id"),
        status=str(row.get("status") or "draft"),
        version=int(row.get("version") or 1),
        concept_count=int(row.get("concept_count") or 0),
    )


@router.post("", response_model=PackageOut, status_code=201)
def create_package(body: PackageCreate) -> PackageOut:
    """Create a draft LocalTerminologyPackage."""
    try:
        params = new_package_params(
            name=body.name,
            scope=body.scope,
            org_id=body.org_id,
            created_by=body.created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    client = KnowledgeGraphClient()
    try:
        rows = client.run(CREATE_PACKAGE, **params)
        if not rows:
            raise HTTPException(status_code=500, detail="Failed to create package")
        return _row(rows[0])
    finally:
        client.close()


@router.get("", response_model=PackageList)
def list_packages(
    status: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default=None),
    org_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PackageList:
    """List packages, optionally filtered by status/scope/org."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            LIST_PACKAGES,
            status=status,
            scope=scope,
            org_id=org_id,
            offset=offset,
            limit=limit,
        )
        total_rows = client.run(
            COUNT_PACKAGES, status=status, scope=scope, org_id=org_id
        )
        total = int(total_rows[0]["total"]) if total_rows else 0
        return PackageList(
            items=[_row(r) for r in rows or []],
            total=total,
            offset=offset,
            limit=limit,
        )
    finally:
        client.close()


@router.post("/{package_id}/activate", response_model=PackageOut)
def activate_package(package_id: str) -> PackageOut:
    """Activate a draft package that contains at least one concept."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(GET_PACKAGE, id=package_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Package not found")
        pkg = rows[0]
        if int(pkg.get("concept_count") or 0) < 1:
            raise HTTPException(
                status_code=422,
                detail="Cannot activate an empty package. Add at least one concept.",
            )
        updated = client.run(
            SET_STATUS,
            id=package_id,
            status="active",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        return _row(updated[0])
    finally:
        client.close()


@router.post("/{package_id}/retire", response_model=PackageOut)
def retire_package(package_id: str) -> PackageOut:
    client = KnowledgeGraphClient()
    try:
        rows = client.run(GET_PACKAGE, id=package_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Package not found")
        updated = client.run(
            SET_STATUS,
            id=package_id,
            status="retired",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        return _row(updated[0])
    finally:
        client.close()


@router.post("/seed-global-defaults")
def seed_global_defaults() -> dict[str, Any]:
    """Ensure the platform global package exists (active)."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            ENSURE_GLOBAL_PACKAGE,
            id=GLOBAL_DEFAULT_PACKAGE_ID,
            name="LEO global local terminology",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return {
            "package": _row(
                {
                    **rows[0],
                    "org_id": None,
                    "version": 1,
                    "concept_count": 0,
                }
            ).model_dump()
        }
    finally:
        client.close()


@router.get("/active-patterns")
def get_active_patterns(
    org_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """Return approved local aliases from active global (+ tenant) packages."""
    from libs.ner.local_concept_recovery import (
        load_active_package_patterns,
    )

    client = KnowledgeGraphClient()
    try:
        patterns = load_active_package_patterns(client, org_id)
        return {
            "org_id": org_id,
            "pattern_count": len(patterns),
            "patterns": [
                {
                    "normalized": p.normalized,
                    "form": p.form,
                    "concept_id": p.concept_id,
                    "fsn": p.fsn,
                    "semantic_tag": p.semantic_tag,
                }
                for p in patterns
            ],
        }
    finally:
        client.close()


@router.get("/{package_id}", response_model=PackageOut)
def get_package(package_id: str) -> PackageOut:
    client = KnowledgeGraphClient()
    try:
        rows = client.run(GET_PACKAGE, id=package_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Package not found")
        return _row(rows[0])
    finally:
        client.close()


@router.post("/{package_id}/contains/{concept_id}")
def link_concept(package_id: str, concept_id: str) -> dict[str, str]:
    """Attach a leo_local Concept to a package."""
    client = KnowledgeGraphClient()
    try:
        pkg = client.run(GET_PACKAGE, id=package_id)
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")
        rows = client.run(
            CONTAINS_CONCEPT, package_id=package_id, concept_id=concept_id
        )
        if not rows:
            raise HTTPException(
                status_code=404, detail="Concept not found or link failed"
            )
        return {
            "package_id": str(rows[0]["package_id"]),
            "concept_id": str(rows[0]["concept_id"]),
        }
    finally:
        client.close()


__all__ = [
    "router",
    "PackageCreate",
    "create_package",
    "activate_package",
    "retire_package",
    "list_packages",
    "get_active_patterns",
]
