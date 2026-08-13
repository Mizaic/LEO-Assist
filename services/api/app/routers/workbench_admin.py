"""Workbench admin endpoints -- NER guard rule CRUD and impact preview.

Atlas trace:
  DI: DI-34712A9A
  DO: DO-6413D5BC

These routes back the Guards Workbench UI (/admin/workbench/guards).
They expose the :NerGuardRule nodes created by Phase 1 of the
configurable pipeline components work.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.deps import require_admin
from libs.auth.org_scope import CallerScope, get_caller_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/workbench", tags=["workbench-admin"])

try:
    from app.db.neo4j_client import PatientGraphClient
    from libs.cypher.guard_rule_queries import (
        GET_ALL_RULES,
        GET_RULES_BY_FAMILY,
        GET_RULE_BY_ID,
        GET_RULE_HISTORY,
        UPSERT_RULE,
        DEACTIVATE_RULE,
    )
except Exception:
    from libs.neo4j_client.client import PatientGraphClient  # type: ignore[assignment]
    from libs.cypher.guard_rule_queries import (  # type: ignore[assignment]
        GET_ALL_RULES,
        GET_RULES_BY_FAMILY,
        GET_RULE_BY_ID,
        GET_RULE_HISTORY,
        UPSERT_RULE,
        DEACTIVATE_RULE,
    )


def _parse_payload(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return {}


def _row_to_rule(row: dict) -> dict:
    payload = _parse_payload(row.get("payload"))
    return {
        "rule_id": row.get("rule_id"),
        "family": row.get("family"),
        "org_id": row.get("org_id"),
        "plan_definition_id": row.get("plan_definition_id"),
        "priority": row.get("priority", 10),
        "created_by": row.get("created_by"),
        "created_at": str(row.get("created_at") or ""),
        "active": bool(row.get("active", True)),
        "pattern": payload.get("pattern", ""),
        "rule_type": payload.get("rule_type", ""),
        "source": "custom",
        "readonly": False,
    }


def _reject_builtin_mutation(rule_id: str) -> None:
    from libs.pipeline.builtin_guard_catalog import is_builtin_rule_id

    if is_builtin_rule_id(rule_id):
        raise HTTPException(
            403,
            "Built-in rules cannot be changed. Add a new rule to extend them.",
        )


def _fetch_custom_rules(family: str | None) -> list[dict]:
    try:
        client = PatientGraphClient()
    except Exception:
        logger.warning(
            "Could not list custom guard rules -- showing builtins only",
            exc_info=True,
        )
        return []
    try:
        if family:
            rows = client.run(GET_RULES_BY_FAMILY, family=family)
        else:
            rows = client.run(GET_ALL_RULES)
        return [_row_to_rule(dict(r)) for r in rows]
    except Exception:
        logger.warning(
            "Could not list custom guard rules -- showing builtins only",
            exc_info=True,
        )
        return []
    finally:
        client.close()


class CreateRuleRequest(BaseModel):
    family: str
    pattern: str
    rule_type: str
    org_id: str | None = None
    plan_definition_id: str | None = None
    priority: int = 10


class UpdateRuleRequest(BaseModel):
    pattern: str | None = None
    rule_type: str | None = None
    active: bool | None = None
    priority: int | None = None


@router.get("/guard-rules")
def list_guard_rules(
    family: str | None = Query(default=None),
    scope: CallerScope = Depends(get_caller_scope),
):
    """List built-in and custom NER guard rules, optionally filtered by family."""
    from libs.pipeline.builtin_guard_catalog import merge_listed_rules

    return merge_listed_rules(_fetch_custom_rules(family), family)


@router.post("/guard-rules", status_code=201)
def create_guard_rule(
    body: CreateRuleRequest,
    scope: CallerScope = Depends(require_admin),
):
    """Create a new NER guard rule."""
    rule_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps({"pattern": body.pattern, "rule_type": body.rule_type})
    client = PatientGraphClient()
    try:
        client.run(
            UPSERT_RULE,
            rule_id=rule_id,
            family=body.family,
            org_id=body.org_id or "",
            plan_definition_id=body.plan_definition_id or "",
            priority=body.priority,
            created_by=getattr(scope, "user_id", "workbench"),
            created_at=now,
            updated_by=getattr(scope, "user_id", "workbench"),
            updated_at=now,
            payload=payload,
        )
        return {"rule_id": rule_id, "created": True}
    finally:
        client.close()


@router.put("/guard-rules/{rule_id}")
def update_guard_rule(
    rule_id: str,
    body: UpdateRuleRequest,
    scope: CallerScope = Depends(require_admin),
):
    """Update fields on an existing NER guard rule."""
    _reject_builtin_mutation(rule_id)
    client = PatientGraphClient()
    try:
        rows = client.run(GET_RULE_BY_ID, rule_id=rule_id)
        if not rows:
            raise HTTPException(404, f"Rule {rule_id} not found")
        existing = _row_to_rule(dict(rows[0]))

        pattern = (
            body.pattern if body.pattern is not None else existing["pattern"]
        )
        rule_type = (
            body.rule_type if body.rule_type is not None else existing["rule_type"]
        )
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps({"pattern": pattern, "rule_type": rule_type})
        client.run(
            UPSERT_RULE,
            rule_id=rule_id,
            family=existing["family"],
            org_id=existing.get("org_id") or "",
            plan_definition_id=existing.get("plan_definition_id") or "",
            priority=(
                body.priority
                if body.priority is not None
                else existing.get("priority", 10)
            ),
            created_by=existing.get("created_by") or "workbench",
            created_at=existing.get("created_at") or now,
            updated_by=getattr(scope, "user_id", "workbench"),
            updated_at=now,
            payload=payload,
        )
        return {"rule_id": rule_id, "updated": True}
    finally:
        client.close()


@router.delete("/guard-rules/{rule_id}", status_code=204)
def deactivate_guard_rule(
    rule_id: str,
    scope: CallerScope = Depends(require_admin),
):
    """Soft-delete (deactivate) a NER guard rule."""
    _reject_builtin_mutation(rule_id)
    now = datetime.now(timezone.utc).isoformat()
    client = PatientGraphClient()
    try:
        rows = client.run(
            DEACTIVATE_RULE,
            rule_id=rule_id,
            updated_at=now,
            updated_by=getattr(scope, "user_id", "workbench"),
        )
        if not rows:
            raise HTTPException(404, f"Rule {rule_id} not found")
    finally:
        client.close()


@router.get("/guard-rules/{rule_id}/history")
def get_guard_rule_history(
    rule_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return version history for a guard rule."""
    client = PatientGraphClient()
    try:
        rows = client.run(GET_RULE_HISTORY, rule_id=rule_id)
        versions = []
        for i, row in enumerate(rows):
            payload = _parse_payload(row.get("payload"))
            versions.append({
                "version": row.get("version", len(rows) - i),
                "changed_at": str(row.get("changed_at") or ""),
                "changed_by": str(row.get("changed_by") or ""),
                "pattern": payload.get("pattern", ""),
                "rule_type": payload.get("rule_type", ""),
                "active": True,
                "revert_available": True,
            })
        return versions
    finally:
        client.close()


@router.post("/rule-impact-preview")
def rule_impact_preview(
    body: dict,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Preview how many recent encounters a guard rule pattern would match.

    Runs a simple regex check against the last 200 encounter text snippets
    in the Knowledge Graph and returns a match count.
    """
    import re

    pattern = (body.get("pattern") or "").strip()
    if not pattern:
        return {
            "match_count": 0,
            "encounter_sample": [],
            "message": "No pattern provided.",
        }

    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {
            "match_count": 0,
            "encounter_sample": [],
            "message": f"Invalid regex: {e}",
        }

    try:
        from libs.neo4j_client.client import KnowledgeGraphClient

        client = KnowledgeGraphClient()
        try:
            rows = client.run(
                "MATCH (e:Entity) RETURN e.text AS text LIMIT 200"
            )
        finally:
            client.close()

        texts = [str(r.get("text") or "") for r in rows if r.get("text")]
        matched = [t for t in texts if rx.search(t)]
        sample = matched[:5]
        count = len(matched)
        total = len(texts)
        msg = (
            f"Matches {count} of the last {total} entity texts sampled."
            if count > 0
            else f"No matches found in {total} entity texts sampled."
        )
        return {"match_count": count, "encounter_sample": sample, "message": msg}
    except Exception as exc:
        logger.warning("Impact preview query failed: %s", exc)
        return {
            "match_count": 0,
            "encounter_sample": [],
            "message": "Could not run preview -- knowledge graph may be unavailable.",
        }
