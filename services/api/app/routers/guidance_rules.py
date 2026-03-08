"""HITL rule review endpoints for LLM-generated AppropriatenessRules.

Provides:
  POST /guidance/rules/generate            -- trigger rule generation for a guideline
  GET  /guidance/rules/review              -- list pending rules
  GET  /guidance/rules/review/{rule_id}    -- rule detail with plain-English summary
  POST /guidance/rules/review/{rule_id}/decision -- approve / edit / reject
  POST /guidance/rules/review/approve-all  -- bulk approve all pending rules

All endpoints require the ai.admin role.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.neo4j_client import CodingGraphClient
from app.deps import require_admin
from app.services.guidance_rule_generator import GuidanceRuleGenerator
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/guidance", tags=["guidance-rules"])

_generate_jobs: dict[str, dict] = {}

_FETCH_RULES = """
MATCH (rule:AppropriatenessRule)
WHERE ($status IS NULL OR rule.status = $status)
  AND ($guideline_id IS NULL OR
       EXISTS {
         MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(rule)
       })
WITH rule
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)<-[:HAS_RECOMMENDATION]-(g:Guideline)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)-[hc:HAS_CRITERIA]->(concept)
RETURN rule.id AS rule_id,
       rule.name AS name,
       rule.strength AS strength,
       rule.status AS status,
       rule.createdAt AS created_at,
       g.id AS guideline_id,
       rec.verbatim AS recommendation_text,
       collect({
           predicate: hc.predicate,
           concept_id: concept.conceptId,
           preferred_term: coalesce(concept.term, concept.conceptId)
       }) AS criteria
ORDER BY rule.createdAt DESC
LIMIT $limit
"""

_FETCH_RULE_DETAIL = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)<-[:HAS_RECOMMENDATION]-(g:Guideline)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)-[hc:HAS_CRITERIA]->(concept)
RETURN rule.id AS rule_id,
       rule.name AS name,
       rule.strength AS strength,
       rule.status AS status,
       rule.createdAt AS created_at,
       g.id AS guideline_id,
       g.title AS guideline_title,
       rec.verbatim AS recommendation_text,
       collect({
           predicate: hc.predicate,
           concept_id: concept.conceptId,
           preferred_term: coalesce(concept.term, concept.conceptId)
       }) AS criteria
"""

_UPDATE_RULE_STATUS = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
SET rule.status = $status,
    rule.reviewedAt = datetime(),
    rule.reviewedBy = $reviewer
MERGE (audit:GuidanceAuditEvent {id: $event_id})
ON CREATE SET
    audit.ruleId      = $rule_id,
    audit.action      = $action,
    audit.reviewer    = $reviewer,
    audit.reason      = $reason,
    audit.timestamp   = datetime(),
    audit.immutable   = true
MERGE (rule)-[:HAS_AUDIT_EVENT]->(audit)
RETURN rule.id AS id
"""

_FETCH_PENDING_IDS = """
MATCH (rule:AppropriatenessRule {status: 'pending_review'})
WHERE ($guideline_id IS NULL OR
       EXISTS {
         MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(rule)
       })
RETURN rule.id AS rule_id
"""


class GenerateRulesRequest(BaseModel):
    guideline_id: str


class RuleDecisionRequest(BaseModel):
    action: Literal["approve", "reject", "edit"]
    reviewer: str = Field(min_length=2)
    reason: str = Field(min_length=3)
    edited_name: str | None = None


def _kg_client() -> CodingGraphClient:
    return CodingGraphClient()


@router.post("/rules/generate", status_code=202)
def generate_rules(
    req: GenerateRulesRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Trigger LLM rule generation for a loaded NICE guideline.

    Returns a job ID immediately. Rule generation runs in the background.
    Rules will appear in the review queue once complete.
    """
    job_id = str(uuid.uuid4())
    _generate_jobs[job_id] = {
        "job_id": job_id,
        "guideline_id": req.guideline_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "rule_ids": [],
        "error": None,
    }
    thread = threading.Thread(
        target=_run_generation,
        args=(job_id, req.guideline_id),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@router.get("/rules/review")
def list_pending_rules(
    guideline_id: str | None = Query(default=None),
    status: str | None = Query(default="pending_review"),
    limit: int = Query(default=50, ge=1, le=200),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """List rules awaiting human review, in plain English."""
    client = _kg_client()
    try:
        records = client.run(
            _FETCH_RULES,
            status=status,
            guideline_id=guideline_id,
            limit=limit,
        )
        return [_format_rule(r) for r in records]
    finally:
        client.close()


@router.get("/rules/review/{rule_id}")
def get_rule_detail(
    rule_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Return detail for a single rule including plain-English criteria."""
    client = _kg_client()
    try:
        records = client.run(_FETCH_RULE_DETAIL, rule_id=rule_id)
        if not records:
            raise HTTPException(status_code=404, detail="Rule not found")
        return _format_rule(records[0])
    finally:
        client.close()


@router.post("/rules/review/{rule_id}/decision")
def decide_rule(
    rule_id: str,
    body: RuleDecisionRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Approve, edit, or reject a generated rule.

    Approving sets the rule to ``active`` so it will be included in the
    next bitmap compilation. Rejecting removes it from the review queue.
    All decisions are recorded in an immutable audit trail.
    """
    client = _kg_client()
    try:
        new_status = "active" if body.action in ("approve", "edit") else "rejected"
        records = client.run(
            _UPDATE_RULE_STATUS,
            rule_id=rule_id,
            status=new_status,
            reviewer=body.reviewer,
            action=body.action,
            reason=body.reason,
            event_id=str(uuid.uuid4()),
        )
        if not records:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"rule_id": rule_id, "status": new_status}
    finally:
        client.close()


@router.post("/rules/review/approve-all")
def approve_all_rules(
    guideline_id: str | None = Query(default=None),
    reviewer: str = Query(..., min_length=2),
    reason: str = Query(default="Bulk approval"),
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Bulk-approve all pending rules for a guideline.

    All rules change to ``active`` in a single operation.
    A ConfirmDialog in the UI must gate this action.
    """
    client = _kg_client()
    try:
        pending = client.run(
            _FETCH_PENDING_IDS, guideline_id=guideline_id
        )
        approved = []
        for row in pending:
            rid = row["rule_id"]
            client.run(
                _UPDATE_RULE_STATUS,
                rule_id=rid,
                status="active",
                reviewer=reviewer,
                action="approve",
                reason=reason,
                event_id=str(uuid.uuid4()),
            )
            approved.append(rid)
        return {"approved_count": len(approved), "rule_ids": approved}
    finally:
        client.close()


def _format_rule(r: dict) -> dict:
    """Format a Neo4j rule record into a plain-English API response."""
    criteria = r.get("criteria") or []
    present = [c for c in criteria if c.get("predicate") == "PRESENT"]
    absent = [c for c in criteria if c.get("predicate") == "ABSENT"]
    return {
        "rule_id": r.get("rule_id"),
        "name": r.get("name"),
        "status": r.get("status"),
        "strength": r.get("strength"),
        "guideline_id": r.get("guideline_id"),
        "recommendation_text": r.get("recommendation_text"),
        "plain_english": _plain_english_criteria(present, absent),
        "present_criteria": present,
        "absent_criteria": absent,
        "created_at": str(r.get("created_at", "")),
    }


def _plain_english_criteria(
    present: list[dict], absent: list[dict]
) -> str:
    """Return a plain-English description of rule criteria.

    Designed for reading age 11.
    """
    parts = []
    for c in present:
        term = c.get("preferred_term", c.get("concept_id", "unknown"))
        parts.append(f"patient HAS {term}")
    for c in absent:
        term = c.get("preferred_term", c.get("concept_id", "unknown"))
        parts.append(f"patient does NOT HAVE {term}")
    if not parts:
        return "No criteria defined yet."
    return "Triggers when: " + " AND ".join(parts)


def _run_generation(job_id: str, guideline_id: str) -> None:
    """Background thread: run LLM rule generation."""
    try:
        client = _kg_client()
        generator = GuidanceRuleGenerator(client._driver)
        rule_ids = generator.generate_rules_for_guideline(guideline_id)
        _generate_jobs[job_id].update({
            "status": "done",
            "rule_ids": rule_ids,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        client.close()
    except Exception as exc:
        logger.exception("Rule generation failed for %s", guideline_id)
        _generate_jobs[job_id].update({
            "status": "error",
            "error": str(exc),
        })
