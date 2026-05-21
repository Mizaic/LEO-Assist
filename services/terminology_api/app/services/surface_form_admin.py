"""Surface-form approval, deactivation, and audit helpers.

Atlas trace:
  UN: UN-72B60B2D
  DI: DI-47D2CD86
  DO: DO-5A88E0B9
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException

from libs.terminology.cache_invalidation import (
    invalidate_terminology_resolution_caches,
)
from services.terminology_api.app.queries.terminology import (
    APPEND_SURFACE_FORM_AUDIT_LOG,
    APPROVE_SURFACE_FORM_MAPPING,
    COUNT_SURFACE_FORM_AUDIT_LOG,
    DEACTIVATE_SURFACE_FORM_MAPPING,
    GET_SURFACE_FORM_MAPPING,
    LIST_SURFACE_FORM_AUDIT_LOG,
)


def record_mapping_audit(
    client: Any,
    *,
    normalized: str,
    action: str,
    actor: str,
    outcome: str,
    detail: str = "",
    concept_id: str = "",
) -> str:
    log_id = str(uuid.uuid4())
    client.run(
        APPEND_SURFACE_FORM_AUDIT_LOG,
        log_id=log_id,
        normalized=normalized,
        action=action,
        actor=actor,
        outcome=outcome,
        detail=detail,
        concept_id=concept_id,
    )
    return log_id


def get_mapping_row(client: Any, normalized: str) -> dict[str, Any]:
    rows = client.run(GET_SURFACE_FORM_MAPPING, normalized=normalized)
    if not rows:
        raise HTTPException(
            status_code=404, detail=f"No mapping found for {normalized!r}"
        )
    return rows[0]


def approve_surface_form_mapping(
    client: Any,
    *,
    normalized: str,
    reviewer: str,
    concept_id: str | None = None,
) -> dict[str, Any]:
    rows = client.run(
        APPROVE_SURFACE_FORM_MAPPING,
        normalized=normalized,
        reviewer=reviewer,
        concept_id=concept_id,
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No pending or editable mapping found for {normalized!r}",
        )
    row = rows[0]
    record_mapping_audit(
        client,
        normalized=normalized,
        action="approve",
        actor=reviewer,
        outcome="success",
        detail="Mapping approved for runtime resolve",
        concept_id=str(row.get("concept_id") or concept_id or ""),
    )
    invalidate_terminology_resolution_caches(
        reason=f"surface_form_approve:{normalized}"
    )
    return row


def deactivate_surface_form_mapping(
    client: Any,
    *,
    normalized: str,
    actor: str,
) -> dict[str, Any]:
    rows = client.run(
        DEACTIVATE_SURFACE_FORM_MAPPING,
        normalized=normalized,
        actor=actor,
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No active mapping found for {normalized!r}",
        )
    row = rows[0]
    record_mapping_audit(
        client,
        normalized=normalized,
        action="deactivate",
        actor=actor,
        outcome="success",
        detail="Mapping deactivated; excluded from runtime resolve",
        concept_id=str(row.get("concept_id") or ""),
    )
    invalidate_terminology_resolution_caches(
        reason=f"surface_form_deactivate:{normalized}"
    )
    return row


def list_mapping_audit_log(
    client: Any,
    *,
    normalized: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    items = client.run(
        LIST_SURFACE_FORM_AUDIT_LOG,
        normalized=normalized,
        limit=limit,
        offset=offset,
    )
    count_rows = client.run(COUNT_SURFACE_FORM_AUDIT_LOG, normalized=normalized)
    total = count_rows[0]["total"] if count_rows else 0
    return {"items": items, "total": total, "offset": offset, "limit": limit}
