"""Post-processor rules, coding-ignore-rules, ConText rules, and surface-form admin router.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Extracted from services/api/app/routers/training.py (2026-07 CTO peer-review
item 2: core-api router decomposition). Pure move, no behaviour change --
existing DO/DI trace headers carried over unchanged.

Routes: post-processor-rules (list/create/update), coding-ignore-rules (list/delete), context-rules (list/create/deactivate), surface-forms revoke/approve, surface-form-tasks (list/stats/get/resolve). Groups the user-configurable NLP rule surfaces that were previously scattered across training.py.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
)
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from app.deps import require_admin
from libs.cypher.coding_review_queries import (
    DEACTIVATE_CODING_IGNORE_RULE,
    GET_ALL_CODING_IGNORE_RULES,
    DEACTIVATE_CONTEXT_RULE,
    GET_CONTEXT_RULES,
    UPSERT_CODING_IGNORE_RULE,
    UPSERT_CONTEXT_RULE,
)
from libs.cypher.surface_form_task_queries import (
    COUNT_SURFACE_FORM_TASKS,
    CREATE_REVOCATION_CASCADE_REVIEW,
    GET_ENCOUNTERS_FOR_REVOKED_CONCEPT,
    GET_SURFACE_FORM_TASK_BY_ID,
    LIST_PENDING_SURFACE_FORM_TASKS,
    RESOLVE_SURFACE_FORM_TASK,
    REVOKE_SURFACE_FORM,
    UPSERT_SURFACE_FORM_TASK,
    make_surface_form_task_id,
)
from services.terminology_api.app.queries.terminology import (
    APPROVE_SURFACE_FORM,
)
from libs.cypher.post_processor_rule_queries import (
    GET_POST_PROCESSOR_RULES,
    UPSERT_POST_PROCESSOR_RULE,
    UPDATE_POST_PROCESSOR_RULE_ACTIVE,
)

logger = logging.getLogger(__name__)

router = APIRouter()


_REDOS_PROBE_LOWER = "a" * 38
_REDOS_PROBE_SIMPLE = "a" * 50 + "b"


def _validate_regex(pattern: str, max_length: int = 200) -> None:
    """Validate a user-supplied regex for safety before persisting.

    Raises HTTPException(422) if:
    - The pattern exceeds max_length characters.
    - The pattern contains a regex syntax error.
    - The pattern exhibits catastrophic backtracking (ReDoS).

    Uses a subprocess for the ReDoS probe so the GIL cannot block the timeout.
    The subprocess is killed at the OS level if it does not complete within 0.5s.
    """
    if len(pattern) > max_length:
        raise HTTPException(
            status_code=422,
            detail=f"context_regex must not exceed {max_length} characters",
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(status_code=422, detail=f"Invalid regex: {exc}") from exc

    probe_code = (
        "import re, sys\n"
        f"compiled = re.compile({pattern!r})\n"
        f"compiled.search({_REDOS_PROBE_LOWER!r})\n"
        f"compiled.search({_REDOS_PROBE_SIMPLE!r})\n"
        "sys.exit(0)\n"
    )
    try:
        subprocess.run(
            [sys.executable, "-c", probe_code],
            timeout=0.5,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ReDoS probe timed out for regex: %r", pattern[:80])
        raise HTTPException(
            status_code=422,
            detail="context_regex exhibits catastrophic backtracking and is not permitted",
        )


class PostProcessorRuleRequest(BaseModel):
    action: str  # suppress | rewrite | relabel
    match_text: str | None = None
    match_label: str | None = None
    context_regex: str | None = None
    window_chars: int = 40
    rewrite_text: str | None = None
    rewrite_label: str | None = None
    priority: int = 100
    active: bool = True
    notes: str = ""
    created_by: str = "operations_ui"


class UpdatePostProcessorRuleRequest(BaseModel):
    active: bool


class ResolveSurfaceFormTaskRequest(BaseModel):
    status: str  # approved | rejected | modified
    resolved_concept: str | None = None
    resolved_by: str = "operations_ui"


@router.get("/post-processor-rules")
def list_post_processor_rules(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List all persisted post-processor rules."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_POST_PROCESSOR_RULES)
            rules = [dict(r) for r in rows]
        return {"rules": rules, "total": len(rules)}
    finally:
        client.close()


@router.post("/post-processor-rules")
def create_post_processor_rule(
    body: PostProcessorRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create or update a post-processor rule used by export and runtime pipeline."""
    valid_actions = {"suppress", "rewrite", "relabel"}
    if body.action not in valid_actions:
        raise HTTPException(
            status_code=422, detail=f"action must be one of {sorted(valid_actions)}"
        )
    if body.context_regex:
        _validate_regex(body.context_regex)
    if body.action in {"rewrite", "relabel"} and not body.rewrite_label:
        raise HTTPException(
            status_code=422,
            detail="rewrite_label is required for rewrite/relabel actions",
        )
    if body.action == "rewrite" and not body.rewrite_text:
        raise HTTPException(
            status_code=422, detail="rewrite_text is required for rewrite action"
        )
    if not body.match_text and not body.match_label and not body.context_regex:
        raise HTTPException(
            status_code=422, detail="at least one matcher must be provided"
        )

    rule_id = str(uuid.uuid4())
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPSERT_POST_PROCESSOR_RULE,
                rule_id=rule_id,
                active=body.active,
                priority=body.priority,
                action=body.action,
                match_text=body.match_text,
                match_label=body.match_label,
                context_regex=body.context_regex,
                window_chars=body.window_chars,
                rewrite_text=body.rewrite_text,
                rewrite_label=body.rewrite_label,
                created_by=body.created_by,
                notes=body.notes,
            ).single()
        return {"rule_id": row["rule_id"], "status": "created"}
    finally:
        client.close()


@router.patch("/post-processor-rules/{rule_id}")
def update_post_processor_rule(
    rule_id: str,
    body: UpdatePostProcessorRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Toggle active status for an existing post-processor rule."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_POST_PROCESSOR_RULE_ACTIVE,
                rule_id=rule_id,
                active=body.active,
            ).single()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Rule {rule_id!r} not found"
                )
        return {"rule_id": row["rule_id"], "active": row["active"]}
    finally:
        client.close()


def _create_surface_form_task_for_correction(
    entity_text: str,
    original_concept_id: str,
    resolved_concept_id: str,
    resolved_term: str,
    reviewer: str,
) -> bool:
    """Queue a SurfaceFormTask for second-reviewer approval (CSO-001).

    Returns True if the task was created successfully.
    """
    normalized = re.sub(r"\s+", " ", entity_text.strip().lower())
    task_id = make_surface_form_task_id(
        candidate_id=reviewer or "unknown",
        entity_text=normalized,
        current_concept=original_concept_id,
    )
    try:
        client = PatientGraphClient()
        with client.session() as session:
            session.run(
                UPSERT_SURFACE_FORM_TASK,
                task_id=task_id,
                entity_text=entity_text.strip(),
                current_concept=original_concept_id,
                current_term="",
                suggested_concept=resolved_concept_id,
                suggested_term=resolved_term or "",
                candidates_json="[]",
                context_text="",
                candidate_id="",
                confidence=0.9,
                source="reviewer_correction",
            )
        client.close()
        logger.info(
            "SurfaceFormTask queued for second review: %r -> %s (task=%s)",
            entity_text,
            resolved_concept_id,
            task_id,
        )
        return True
    except Exception:
        logger.warning(
            "Failed to create SurfaceFormTask for %r",
            entity_text,
            exc_info=True,
        )
        return False


def _write_coding_ignore_rule(
    entity_text: str,
    entity_label: str,
    reason: str,
    created_by: str,
) -> None:
    """Upsert a CodingIgnoreRule so the term is suppressed in future runs."""
    normalized = re.sub(r"\s+", " ", entity_text.strip().lower())
    if not normalized:
        return
    rule_id = str(uuid.uuid4())
    client = PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_CODING_IGNORE_RULE,
                rule_id=rule_id,
                entity_text=normalized,
                entity_label=entity_label or None,
                reason=reason or "ignored via coding review",
                created_by=created_by,
            )
        logger.info(
            "Coding ignore rule created: %r (label=%r)", normalized, entity_label
        )
    except Exception:
        logger.warning(
            "Failed to write coding ignore rule for %r", normalized, exc_info=True
        )
    finally:
        client.close()


@router.get("/coding-ignore-rules")
def list_coding_ignore_rules(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List all coding ignore rules (active and inactive)."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(GET_ALL_CODING_IGNORE_RULES)]
        return {"rules": rows, "total": len(rows)}
    finally:
        client.close()


@router.delete("/coding-ignore-rules/{rule_id}")
def delete_coding_ignore_rule(
    rule_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Deactivate a coding ignore rule so the term can re-enter review."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            result = session.run(
                DEACTIVATE_CODING_IGNORE_RULE,
                rule_id=rule_id,
            ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Ignore rule not found")
        return {"rule_id": result["rule_id"], "status": "deactivated"}
    finally:
        client.close()


_VALID_CATEGORIES = frozenset(
    {
        "NEGATED_EXISTENCE",
        "POSSIBLE_EXISTENCE",
        "HISTORICAL",
        "HYPOTHETICAL",
        "FAMILY",
        "DECLINED",
    }
)
_VALID_DIRECTIONS = frozenset({"FORWARD", "BACKWARD", "BIDIRECTIONAL"})


class ContextRuleRequest(BaseModel):
    literal: str
    category: str
    direction: str = "FORWARD"
    max_scope: int = 6
    description: str = ""
    example: str = ""
    created_by: str = "operations_ui"


@router.get("/context-rules")
def list_context_rules(
    active_only: bool = True,
    include_builtin: bool = True,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List ConText rules: user-defined (Neo4j) plus optionally the shipped built-ins.

    Custom rules are scoped to the caller's org; platform admins see all orgs.
    Built-in rules (source='builtin') are read-only and global.
    """
    from libs.ner.context_engine import get_builtin_rules

    org_id = None if scope.is_admin else scope.primary_org_id

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                GET_CONTEXT_RULES, active_only=active_only, org_id=org_id
            )
            custom = [{**dict(r), "source": "custom"} for r in rows]
    finally:
        client.close()

    builtin = get_builtin_rules() if include_builtin else []
    return {"rules": builtin + custom}


@router.post("/context-rules")
def create_context_rule(
    body: ContextRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new user-defined ConText rule, scoped to the caller's org.

    The rule is picked up by the coding worker on the next pipeline restart.
    Only platform admins may create rules (GAP-015).
    """
    if not body.literal.strip():
        raise HTTPException(status_code=422, detail="literal must not be empty")
    if len(body.literal) > 200:
        raise HTTPException(
            status_code=422, detail="literal must not exceed 200 characters"
        )
    if body.category not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of {sorted(_VALID_CATEGORIES)}",
        )
    if body.direction.upper() not in _VALID_DIRECTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"direction must be one of {sorted(_VALID_DIRECTIONS)}",
        )
    rule_id = str(uuid.uuid4())
    org_id = scope.primary_org_id  # None for platform admins (platform-wide rule)
    client = PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_CONTEXT_RULE,
                rule_id=rule_id,
                literal=body.literal.strip().lower(),
                category=body.category.upper(),
                direction=body.direction.upper(),
                max_scope=max(1, min(20, body.max_scope)),
                description=body.description.strip(),
                example=body.example.strip(),
                created_by=scope.email,
                org_id=org_id,
            )
        logger.info(
            "ContextRule created: %s %r -> %s by %s (org=%s)",
            rule_id[:8],
            body.literal,
            body.category,
            scope.email,
            org_id,
        )
        return {
            "rule_id": rule_id,
            "literal": body.literal,
            "category": body.category,
            "org_id": org_id,
        }
    finally:
        client.close()

    # Rebuild the ConText NLP pipeline so the new rule takes effect immediately.
    try:
        from libs.ner.context_engine import reload_nlp

        reload_nlp()
    except Exception:
        logger.warning(
            "ConText pipeline reload failed after rule creation (non-fatal)",
            exc_info=True,
        )


@router.patch("/context-rules/{rule_id}/deactivate")
def deactivate_context_rule(
    rule_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Soft-delete a user-defined ConText rule."""
    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(DEACTIVATE_CONTEXT_RULE, rule_id=rule_id).single()
        if not row:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id!r} not found")
        logger.info("ContextRule deactivated: %s", rule_id[:8])
        return {"rule_id": rule_id, "active": False}
    finally:
        client.close()

    # Rebuild the ConText NLP pipeline so the removed rule is no longer applied.
    try:
        from libs.ner.context_engine import reload_nlp

        reload_nlp()
    except Exception:
        logger.warning(
            "ConText pipeline reload failed after rule deactivation (non-fatal)",
            exc_info=True,
        )


@router.delete("/surface-forms/{normalized}/revoke")
def revoke_surface_form(
    normalized: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Revoke a surface form mapping and cascade to affected encounters.

    Steps:
    1. Remove the MAPS_TO relationship and mark SurfaceForm / SurfaceFormTask
       as 'revoked'.
    2. Query DOCUMENTS relationships coded via this concept after first use.
    3. Create a CodingReview node (type=revocation_cascade, priority=urgent)
       for each affected encounter so reviewers are alerted.

    Returns the count of affected encounters.
    """
    kg_client = KnowledgeGraphClient()
    pg_client = PatientGraphClient()
    try:
        with kg_client.session() as session:
            row = session.run(REVOKE_SURFACE_FORM, normalized=normalized).single()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No surface form found for {normalized!r}",
            )
        concept_id = ""
        first_used_at = row.get("first_used_at")

        with pg_client.session() as pg_session:
            enc_rows = pg_session.run(
                GET_ENCOUNTERS_FOR_REVOKED_CONCEPT,
                concept_id=concept_id,
                first_used_at=first_used_at,
            )
            encounter_ids = [r["encounter_id"] for r in enc_rows]

            for enc_id in encounter_ids:
                review_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"revoke:{normalized}:{enc_id}",
                    )
                )
                pg_session.run(
                    CREATE_REVOCATION_CASCADE_REVIEW,
                    review_id=review_id,
                    encounter_id=enc_id,
                    concept_id=concept_id,
                )

        logger.info(
            "SurfaceForm revoked: %r  cascade_encounters=%d  by=%s",
            normalized,
            len(encounter_ids),
            scope.email,
        )
        return {
            "normalized": normalized,
            "status": "revoked",
            "affected_encounters": len(encounter_ids),
        }
    finally:
        kg_client.close()
        pg_client.close()


@router.patch("/surface-forms/{normalized}/approve")
def approve_surface_form(
    normalized: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Promote a pending surface form to approved after second confirmation.

    Surface forms are created as 'pending' on first writeback. This endpoint
    confirms the mapping so the resolver treats it as a trusted Tier 1 match.
    """
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                APPROVE_SURFACE_FORM,
                normalized=normalized,
                reviewer=scope.email,
            ).single()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No pending surface form found for {normalized!r}",
            )
        logger.info("SurfaceForm approved: %s", normalized[:40])
        return {"normalized": row["normalized"], "status": row["status"]}
    finally:
        client.close()


@router.get("/surface-form-tasks")
def list_surface_form_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    status: str | None = Query(default="pending"),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    skip = (page - 1) * page_size
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = session.run(
                LIST_PENDING_SURFACE_FORM_TASKS,
                skip=skip,
                limit=page_size,
                status=status,
            )
            items = [dict(r) for r in rows]
            count_row = session.run(COUNT_SURFACE_FORM_TASKS, status=status).single()
        total = count_row["total"] if count_row else 0
        return {"items": items, "page": page, "page_size": page_size, "total": total}
    finally:
        client.close()


@router.get("/surface-form-tasks/stats")
def surface_form_task_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            pending = session.run(COUNT_SURFACE_FORM_TASKS, status="pending").single()
            resolved = session.run(COUNT_SURFACE_FORM_TASKS, status="approved").single()
        return {
            "pending": pending["total"] if pending else 0,
            "approved": resolved["total"] if resolved else 0,
        }
    finally:
        client.close()


@router.get("/surface-form-tasks/{task_id}")
def get_surface_form_task(
    task_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_SURFACE_FORM_TASK_BY_ID, task_id=task_id).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"SurfaceFormTask {task_id!r} not found"
            )
        return dict(row)
    finally:
        client.close()


@router.post("/surface-form-tasks/{task_id}/resolve")
def resolve_surface_form_task(
    task_id: str,
    body: ResolveSurfaceFormTaskRequest,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    if body.status not in {"approved", "rejected", "modified"}:
        raise HTTPException(
            status_code=422, detail="status must be approved|rejected|modified"
        )
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                RESOLVE_SURFACE_FORM_TASK,
                task_id=task_id,
                status=body.status,
                resolved_concept=body.resolved_concept or "",
                resolved_by=body.resolved_by or "operations_ui",
            ).single()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"SurfaceFormTask {task_id!r} not found"
            )
        return {"task_id": row["task_id"], "status": row["status"]}
    finally:
        client.close()
