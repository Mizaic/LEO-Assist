"""Audit template and metric endpoints.

Atlas trace:
  DO: DO-3775670C, DO-A9863AB6
  DI: DI-64CA7740, DI-758B73A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3775670C")

Endpoints:
  GET  /audit-metrics                    -- metric catalogue (no Cypher exposed)
  POST /audit-metrics/{metric_id}/run    -- execute a metric with caller params
  GET  /audit-templates                  -- list templates (admin only)
  POST /audit-templates                  -- create template (admin only)
  PATCH /audit-templates/{template_id}   -- update template (admin only)
  DELETE /audit-templates/{template_id}  -- archive template (admin only)
  POST /audit-templates/{template_id}/publish -- publish to org (admin only)
  GET  /audit-templates/active           -- active template for caller's org

Security
--------
- Metric run: $scope_org_ids injected from CallerScope; callers cannot override it.
- Template write operations require is_admin (platform_admin).
- Active template lookup scopes to the caller's primary_org_id.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.audit_metric_queries import get_catalogue, get_metric
from libs.neo4j_client.client import PatientGraphClient
from services.analytics_api.app.models.audit_template import (
    AuditTemplate,
    AuditTemplateCreate,
    AuditTemplateUpdate,
    MetricRunRequest,
    MetricRunResponse,
    TemplateAssignment,
    TemplateAssignmentCreate,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_CREATE_TEMPLATE = """
MERGE (t:AuditTemplate {template_id: $template_id})
SET t.title       = $title,
    t.version     = $version,
    t.status      = $status,
    t.tiles_json  = $tiles_json,
    t.created_by  = $created_by,
    t.created_at  = $created_at,
    t.updated_at  = $updated_at
RETURN t
"""

_GET_TEMPLATE = """
MATCH (t:AuditTemplate {template_id: $template_id})
RETURN t
"""

_LIST_TEMPLATES = """
MATCH (t:AuditTemplate)
WHERE NOT t.status = 'archived'
RETURN t ORDER BY t.updated_at DESC
"""

_UPDATE_TEMPLATE = """
MATCH (t:AuditTemplate {template_id: $template_id})
SET t.title      = $title,
    t.tiles_json = $tiles_json,
    t.version    = t.version + 1,
    t.updated_at = $updated_at
RETURN t
"""

_ARCHIVE_TEMPLATE = """
MATCH (t:AuditTemplate {template_id: $template_id})
SET t.status     = 'archived',
    t.updated_at = $updated_at
RETURN t
"""

_CREATE_ASSIGNMENT = """
MERGE (a:AuditTemplateAssignment {
    scope_type: $scope_type,
    scope_id:   $scope_id
})
SET a.assignment_id  = $assignment_id,
    a.template_id    = $template_id,
    a.version        = $version,
    a.published_at   = $published_at,
    a.published_by   = $published_by
RETURN a
"""

_GET_ACTIVE_TEMPLATE = """
OPTIONAL MATCH (org_a:AuditTemplateAssignment {scope_type: 'org', scope_id: $org_id})
OPTIONAL MATCH (global_a:AuditTemplateAssignment {scope_type: 'global', scope_id: '__global__'})
WITH coalesce(org_a, global_a) AS a
OPTIONAL MATCH (t:AuditTemplate {template_id: a.template_id})
WHERE t.status <> 'archived'
RETURN t, a IS NOT NULL AS has_assignment
"""

_NCDA_DEFAULT_TEMPLATE_ID = "ncda-default-v1"

_GET_NCDA_DEFAULT = """
MATCH (t:AuditTemplate {template_id: $template_id})
RETURN t
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_admin(scope: CallerScope) -> None:
    if not scope.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Only platform administrators can manage audit templates.",
        )


def _row_to_template(row: dict[str, Any]) -> AuditTemplate:
    """Deserialise a Neo4j AuditTemplate node dict to the Pydantic model."""
    t = row.get("t") or row
    raw_tiles = t.get("tiles_json") or "[]"
    tiles_data = json.loads(raw_tiles) if isinstance(raw_tiles, str) else raw_tiles

    return AuditTemplate(
        template_id=t["template_id"],
        title=t.get("title", ""),
        version=t.get("version", 1),
        status=t.get("status", "draft"),
        tiles=tiles_data,
        created_by=t.get("created_by", ""),
        created_at=t.get("created_at", datetime.now(timezone.utc)),
        updated_at=t.get("updated_at", datetime.now(timezone.utc)),
    )


def _validate_metric_params(
    metric_id: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Validate caller params against the metric's param_schema.

    Returns merged params (schema defaults filled in) or raises 400.
    Raises 404 if the metric is unknown.
    """
    metric = get_metric(metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail=f"Metric '{metric_id}' not found.")

    schema = metric.get("param_schema", {})
    unknown = set(params) - set(schema)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown metric params: {sorted(unknown)}",
        )

    merged: dict[str, Any] = {}
    for name, spec in schema.items():
        if name in params:
            merged[name] = params[name]
        elif "default" in spec:
            merged[name] = spec["default"]
        else:
            merged[name] = None

    return merged


# ---------------------------------------------------------------------------
# Metric endpoints
# ---------------------------------------------------------------------------


@router.get("/audit-metrics")
def list_metrics(
    _scope: CallerScope = Depends(get_caller_scope),
) -> list[dict[str, Any]]:
    """Return the metric catalogue. No Cypher is exposed to callers."""
    return get_catalogue()


@router.post("/audit-metrics/{metric_id}/run", response_model=MetricRunResponse)
def run_metric(
    metric_id: str,
    body: MetricRunRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> MetricRunResponse:
    """Execute a pre-configured metric with caller-supplied params.

    $scope_org_ids is injected server-side from the authenticated session.
    Admin callers may supply preview_org_id to scope the query to a specific
    organisation for template preview purposes. Non-admin callers cannot
    override tenant scoping.
    """
    metric = get_metric(metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail=f"Metric '{metric_id}' not found.")

    merged_params = _validate_metric_params(metric_id, body.params)

    # Admin preview: allow scoping to a specific org for template testing.
    # Non-admin callers always get their own session's org list.
    if body.preview_org_id and scope.is_admin:
        scope_org_ids = [body.preview_org_id]
    else:
        scope_org_ids = scope.org_ids

    cypher_params: dict[str, Any] = {
        **merged_params,
        "scope_org_ids": scope_org_ids,
    }

    client = PatientGraphClient()
    try:
        rows = client.run(metric["cypher"], **cypher_params)
    except Exception as exc:
        logger.error("audit_metrics.run_failed metric=%s err=%s", metric_id, exc)
        raise HTTPException(status_code=502, detail="Metric query failed.") from exc
    finally:
        client.close()

    if not rows:
        return MetricRunResponse(metric_id=metric_id, columns=[], rows=[])

    columns = list(rows[0].keys())
    data_rows = [[row.get(col) for col in columns] for row in rows]
    return MetricRunResponse(metric_id=metric_id, columns=columns, rows=data_rows)


# ---------------------------------------------------------------------------
# Template CRUD (admin only)
# ---------------------------------------------------------------------------


@router.get("/audit-templates")
def list_templates(
    scope: CallerScope = Depends(get_caller_scope),
) -> list[AuditTemplate]:
    """List all non-archived templates. Admin only."""
    _require_admin(scope)
    client = PatientGraphClient()
    try:
        rows = client.run(_LIST_TEMPLATES)
    finally:
        client.close()

    return [_row_to_template(r) for r in rows]


@router.post("/audit-templates", status_code=201)
def create_template(
    body: AuditTemplateCreate,
    scope: CallerScope = Depends(get_caller_scope),
) -> AuditTemplate:
    """Create a new draft audit template. Admin only."""
    _require_admin(scope)

    template_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    tiles_json = json.dumps([t.model_dump() for t in body.tiles])

    client = PatientGraphClient()
    try:
        rows = client.run(
            _CREATE_TEMPLATE,
            template_id=template_id,
            title=body.title,
            version=1,
            status="draft",
            tiles_json=tiles_json,
            created_by=scope.email,
            created_at=now,
            updated_at=now,
        )
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=500, detail="Failed to create template.")

    return _row_to_template(rows[0])


@router.get("/audit-templates/{template_id}")
def get_template(
    template_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> AuditTemplate:
    """Fetch a single template by ID. Admin only."""
    _require_admin(scope)
    client = PatientGraphClient()
    try:
        rows = client.run(_GET_TEMPLATE, template_id=template_id)
    finally:
        client.close()
    if not rows or not rows[0].get("t"):
        raise HTTPException(status_code=404, detail="Template not found.")
    return _row_to_template(rows[0])


@router.patch("/audit-templates/{template_id}")
def update_template(
    template_id: str,
    body: AuditTemplateUpdate,
    scope: CallerScope = Depends(get_caller_scope),
) -> AuditTemplate:
    """Update the title and/or tiles of a draft template. Admin only."""
    _require_admin(scope)

    client = PatientGraphClient()
    try:
        existing = client.run(_GET_TEMPLATE, template_id=template_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found.")

        current = _row_to_template(existing[0])
        new_title = body.title if body.title is not None else current.title
        new_tiles = (
            json.dumps([t.model_dump() for t in body.tiles])
            if body.tiles is not None
            else current.tiles
        )
        if isinstance(new_tiles, list):
            new_tiles = json.dumps(new_tiles)

        rows = client.run(
            _UPDATE_TEMPLATE,
            template_id=template_id,
            title=new_title,
            tiles_json=new_tiles,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=500, detail="Failed to update template.")

    return _row_to_template(rows[0])


@router.delete("/audit-templates/{template_id}", status_code=204)
def archive_template(
    template_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> None:
    """Archive a template. Admin only."""
    _require_admin(scope)

    client = PatientGraphClient()
    try:
        existing = client.run(_GET_TEMPLATE, template_id=template_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found.")

        client.run(
            _ARCHIVE_TEMPLATE,
            template_id=template_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Publish endpoint (admin only)
# ---------------------------------------------------------------------------


@router.post("/audit-templates/{template_id}/publish", status_code=200)
def publish_template(
    template_id: str,
    body: TemplateAssignmentCreate,
    scope: CallerScope = Depends(get_caller_scope),
) -> TemplateAssignment:
    """Assign a template to an org or group.

    Publishing to org A does not affect any other org's active template.
    """
    _require_admin(scope)

    if body.template_id != template_id:
        raise HTTPException(
            status_code=422,
            detail="Body template_id must match the URL template_id.",
        )

    client = PatientGraphClient()
    try:
        existing = client.run(_GET_TEMPLATE, template_id=template_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found.")

        current = _row_to_template(existing[0])
        if current.status == "archived":
            raise HTTPException(
                status_code=422, detail="Cannot publish an archived template."
            )

        now = datetime.now(timezone.utc).isoformat()
        assignment_id = str(uuid.uuid4())

        rows = client.run(
            _CREATE_ASSIGNMENT,
            assignment_id=assignment_id,
            template_id=template_id,
            version=current.version,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            published_at=now,
            published_by=scope.email,
        )
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=500, detail="Failed to create assignment.")

    a = rows[0].get("a") or rows[0]
    return TemplateAssignment(
        assignment_id=a.get("assignment_id", assignment_id),
        template_id=a.get("template_id", template_id),
        version=a.get("version", current.version),
        scope_type=a.get("scope_type", body.scope_type),
        scope_id=a.get("scope_id", body.scope_id),
        published_at=a.get("published_at", now),
        published_by=a.get("published_by", scope.email),
    )


# ---------------------------------------------------------------------------
# Active template (any authenticated user)
# ---------------------------------------------------------------------------


@router.get("/audit-templates/active")
def get_active_template(
    scope: CallerScope = Depends(get_caller_scope),
) -> Optional[AuditTemplate]:
    """Return the template assigned to the caller's primary org.

    Falls back to the platform-default NCDA template if no org-specific
    assignment exists. Returns null if no template is found.
    """
    org_id = scope.primary_org_id or ""

    client = PatientGraphClient()
    try:
        rows = client.run(_GET_ACTIVE_TEMPLATE, org_id=org_id)
        if rows and rows[0].get("t"):
            return _row_to_template(rows[0])

        # Fall back to named NCDA default
        ncda_rows = client.run(
            _GET_NCDA_DEFAULT, template_id=_NCDA_DEFAULT_TEMPLATE_ID
        )
        if ncda_rows and ncda_rows[0].get("t"):
            return _row_to_template(ncda_rows[0])
    except Exception as exc:
        logger.error("audit_templates.active_failed org=%s err=%s", org_id, exc)
        raise HTTPException(
            status_code=502, detail="Failed to fetch active template."
        ) from exc
    finally:
        client.close()

    return None
