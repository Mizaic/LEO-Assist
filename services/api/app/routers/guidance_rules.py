"""HITL rule review endpoints for LLM-generated AppropriatenessRules.

Provides:
  POST /guidance/rules/generate                           -- trigger rule generation
  GET  /guidance/rules/review                             -- list pending rules
  GET  /guidance/rules/review/{rule_id}                   -- rule detail
  POST /guidance/rules/review/{rule_id}/decision          -- approve / edit / reject
  POST /guidance/rules/review/{rule_id}/promote-to-domain -- add SNOMED to NICE domain
  POST /guidance/rules/review/approve-all                 -- bulk approve

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
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)-[hc:HAS_CRITERIA]->(concept)
OPTIONAL MATCH (rule)-[:SUPERSEDES]->(pred:AppropriatenessRule)
RETURN rule.id AS rule_id,
       rule.name AS name,
       rule.strength AS strength,
       rule.status AS status,
       rule.createdAt AS created_at,
       g.id AS guideline_id,
       g.ingestVersion AS guideline_version,
       ch.title AS chapter_title,
       rec.verbatim AS recommendation_text,
       collect({
           predicate: hc.predicate,
           concept_id: concept.conceptId,
           preferred_term: coalesce(concept.term, concept.conceptId)
       }) AS criteria,
       pred.id IS NOT NULL AS has_predecessor,
       pred.id AS predecessor_id
ORDER BY rule.createdAt DESC
LIMIT $limit
"""

_FETCH_RULE_DIFF = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
OPTIONAL MATCH (rule)-[:SUPERSEDES]->(pred:AppropriatenessRule)
OPTIONAL MATCH (pred)-[:HAS_CRITERIA_GROUP]->(pred_grp)-[pred_hc:HAS_CRITERIA]->(pred_concept)
OPTIONAL MATCH (pred)-[:HAS_AUDIT_EVENT]->(audit:GuidanceAuditEvent)
RETURN
    pred.id AS predecessor_id,
    pred.name AS predecessor_name,
    pred.status AS predecessor_status,
    pred.previousRecommendationText AS predecessor_recommendation_text,
    pred.previousRecommendationNumber AS predecessor_recommendation_number,
    pred.supersededAt AS superseded_at,
    collect(DISTINCT {
        predicate: pred_hc.predicate,
        concept_id: pred_concept.conceptId,
        preferred_term: coalesce(pred_concept.term, pred_concept.conceptId)
    }) AS predecessor_criteria,
    collect(DISTINCT {
        action: audit.action,
        reviewer: audit.reviewer,
        timestamp: toString(audit.timestamp),
        reason: audit.reason
    }) AS predecessor_decisions
"""

_FETCH_RULE_BY_ID = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)<-[:HAS_RECOMMENDATION]-(g:Guideline)
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)-[hc:HAS_CRITERIA]->(concept)
OPTIONAL MATCH (rule)-[:SUPERSEDES]->(pred:AppropriatenessRule)
RETURN rule.id AS rule_id,
       rule.name AS name,
       rule.strength AS strength,
       rule.status AS status,
       rule.createdAt AS created_at,
       g.id AS guideline_id,
       g.ingestVersion AS guideline_version,
       ch.title AS chapter_title,
       rec.verbatim AS recommendation_text,
       collect({
           predicate: hc.predicate,
           concept_id: concept.conceptId,
           preferred_term: coalesce(concept.term, concept.conceptId)
       }) AS criteria,
       pred.id IS NOT NULL AS has_predecessor,
       pred.id AS predecessor_id
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

_FETCH_RULE_FOR_PROMOTION = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
OPTIONAL MATCH (rule)<-[:HAS_RULE]-()<-[:HAS_RECOMMENDATION]-(g:Guideline)
OPTIONAL MATCH (g)<-[:CLASSIFIES_GUIDELINE]-(sub:TaxonomySubcategory)-[:HAS_DOMAIN]->(domain:AuditDomain {source: 'nice'})
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)-[:HAS_CRITERIA]->(concept)
RETURN rule.status AS status,
       g.id AS guideline_id,
       domain.id AS domain_id,
       domain.name AS domain_name,
       collect(DISTINCT {concept_id: concept.conceptId, term: coalesce(concept.term, concept.conceptId)}) AS concepts
"""

_PROMOTE_CONCEPT_TO_DOMAIN = """
MATCH (domain:AuditDomain {id: $domain_id})
MERGE (vs:ValueSet {id: $valueset_id})
ON CREATE SET
    vs.name        = $domain_name + ' concepts',
    vs.domainId    = $domain_id,
    vs.createdAt   = datetime()
MERGE (domain)-[:HAS_VALUESET]->(vs)
WITH vs
UNWIND $concepts AS c
MERGE (concept:SnomedConcept {conceptId: c.concept_id})
ON CREATE SET concept.term = c.term
MERGE (vs)-[r:INCLUDES_CONCEPT]->(concept)
ON CREATE SET r.addedAt    = datetime(),
              r.ruleId     = $rule_id,
              r.source     = 'guidance_promotion'
RETURN count(concept) AS added
"""

_WRITE_PROMOTION_AUDIT = """
MERGE (audit:GuidanceAuditEvent {id: $event_id})
ON CREATE SET
    audit.type       = 'domain_promotion',
    audit.ruleId     = $rule_id,
    audit.domainId   = $domain_id,
    audit.conceptIds = $concept_ids,
    audit.reviewer   = $reviewer,
    audit.timestamp  = datetime(),
    audit.immutable  = true
WITH audit
MATCH (rule:AppropriatenessRule {id: $rule_id})
MERGE (rule)-[:HAS_AUDIT_EVENT]->(audit)
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


@router.get("/rules/review/{rule_id}/diff")
def get_rule_diff(
    rule_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Return the version diff for a rule that supersedes a previous one.

    When a guideline is re-ingested and rules re-generated, each new
    ``AppropriatenessRule`` is linked to its predecessor via ``[:SUPERSEDES]``.
    This endpoint exposes:

    - The predecessor rule's criteria (what the AI decided last time).
    - The previous human decisions (GuidanceAuditEvent nodes) — who approved
      or rejected the old rule and why.
    - A computed diff showing which criteria were **added**, **removed**, or
      **unchanged** relative to the predecessor.

    If the rule has no predecessor, returns ``{"has_predecessor": false}``.

    This is the primary endpoint for the HITL review diff view, giving
    reviewers full context to make informed decisions about new rule versions.
    """
    client = _kg_client()
    try:
        current_records = client.run(_FETCH_RULE_BY_ID, rule_id=rule_id)
        if not current_records:
            raise HTTPException(status_code=404, detail="Rule not found")
        rule = _format_rule(current_records[0])

        if not rule.get("has_predecessor"):
            return {"has_predecessor": False}

        # Fetch predecessor info and previous decisions
        diff_records = client.run(_FETCH_RULE_DIFF, rule_id=rule_id)
        if not diff_records:
            return {"has_predecessor": False}

        row = diff_records[0]
        pred_id = row.get("predecessor_id")
        if not pred_id:
            return {"has_predecessor": False}

        pred_criteria_raw = [
            c for c in (row.get("predecessor_criteria") or []) if c.get("concept_id")
        ]
        pred_present = [c for c in pred_criteria_raw if c.get("predicate") == "PRESENT"]
        pred_absent = [c for c in pred_criteria_raw if c.get("predicate") == "ABSENT"]

        pred_decisions = [
            d for d in (row.get("predecessor_decisions") or []) if d.get("action")
        ]

        new_criteria = rule["present_criteria"] + rule["absent_criteria"]
        diff = _compute_diff(new_criteria, pred_criteria_raw)

        return {
            "has_predecessor": True,
            "predecessor": {
                "rule_id": pred_id,
                "name": row.get("predecessor_name"),
                "status": row.get("predecessor_status"),
                "recommendation_text": row.get("predecessor_recommendation_text"),
                "recommendation_number": row.get("predecessor_recommendation_number"),
                "superseded_at": str(row.get("superseded_at", "")),
                "plain_english": _plain_english_criteria(pred_present, pred_absent),
                "present_criteria": pred_present,
                "absent_criteria": pred_absent,
                "decisions": pred_decisions,
            },
            "diff": diff,
            "diff_summary": {
                "added_count": len(diff["added"]),
                "removed_count": len(diff["removed"]),
                "unchanged_count": len(diff["unchanged"]),
            },
        }
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


@router.post("/rules/review/{rule_id}/promote-to-domain")
def promote_rule_to_domain(
    rule_id: str,
    reviewer: str = Query(..., min_length=2, description="Email of the admin promoting this rule"),
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Add the SNOMED codes from an approved rule into its NICE domain.

    The rule must be ``active`` (approved by a human reviewer). This action:

    1. Finds the NICE ``AuditDomain`` linked to the guideline's taxonomy subcategory.
    2. MERGEs each SNOMED concept from the rule's criteria into a ``ValueSet``
       under that domain.
    3. Writes an immutable ``GuidanceAuditEvent`` recording who did this and when.

    Returns the domain ID, name, and number of concepts added.
    """
    client = _kg_client()
    try:
        records = client.run(_FETCH_RULE_FOR_PROMOTION, rule_id=rule_id)
        if not records:
            raise HTTPException(status_code=404, detail="Rule not found")

        row = records[0]
        status = row.get("status")
        if status != "active":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Rule must be active before it can be added to a domain. "
                    f"Current status: '{status}'. "
                    "Please approve the rule first."
                ),
            )

        domain_id = row.get("domain_id")
        domain_name = row.get("domain_name", "")
        if not domain_id:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No NICE domain is linked to this guideline. "
                    "Run a catalogue sync first to build the NICE taxonomy."
                ),
            )

        concepts = [c for c in (row.get("concepts") or []) if c.get("concept_id")]
        if not concepts:
            return {
                "domain_id": domain_id,
                "domain_name": domain_name,
                "concepts_added": 0,
                "message": "Rule has no SNOMED criteria to promote.",
            }

        valueset_id = f"{domain_id}:vs"
        concept_ids = [c["concept_id"] for c in concepts]

        client.run(
            _PROMOTE_CONCEPT_TO_DOMAIN,
            domain_id=domain_id,
            valueset_id=valueset_id,
            domain_name=domain_name,
            concepts=concepts,
            rule_id=rule_id,
        )

        client.run(
            _WRITE_PROMOTION_AUDIT,
            event_id=str(uuid.uuid4()),
            rule_id=rule_id,
            domain_id=domain_id,
            concept_ids=concept_ids,
            reviewer=reviewer,
        )

        return {
            "domain_id": domain_id,
            "domain_name": domain_name,
            "concepts_added": len(concepts),
        }
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


def _compute_diff(
    new_criteria: list[dict], pred_criteria: list[dict]
) -> dict:
    """Compute what changed between new rule criteria and its predecessor's.

    Matches on (predicate, concept_id) pairs. Terms whose concept_id is None
    are excluded (NULL rows from Cypher OPTIONAL MATCH with no concepts).

    Returns:
        Dict with ``added``, ``removed``, and ``unchanged`` lists, each
        containing criterion dicts.
    """
    def _key(c: dict) -> tuple:
        return (c.get("predicate", ""), c.get("concept_id", ""))

    valid_new = [c for c in new_criteria if c.get("concept_id")]
    valid_pred = [c for c in pred_criteria if c.get("concept_id")]

    new_keys = {_key(c) for c in valid_new}
    pred_keys = {_key(c) for c in valid_pred}

    return {
        "added":     [c for c in valid_new  if _key(c) not in pred_keys],
        "removed":   [c for c in valid_pred if _key(c) not in new_keys],
        "unchanged": [c for c in valid_new  if _key(c) in pred_keys],
    }


def _format_rule(r: dict) -> dict:
    """Format a Neo4j rule record into a plain-English API response."""
    criteria = [c for c in (r.get("criteria") or []) if c.get("concept_id")]
    present = [c for c in criteria if c.get("predicate") == "PRESENT"]
    absent = [c for c in criteria if c.get("predicate") == "ABSENT"]
    return {
        "rule_id": r.get("rule_id"),
        "name": r.get("name"),
        "status": r.get("status"),
        "strength": r.get("strength"),
        "guideline_id": r.get("guideline_id"),
        "guideline_version": r.get("guideline_version"),
        "chapter_title": r.get("chapter_title"),
        "recommendation_text": r.get("recommendation_text"),
        "plain_english": _plain_english_criteria(present, absent),
        "present_criteria": present,
        "absent_criteria": absent,
        "created_at": str(r.get("created_at", "")),
        "has_predecessor": bool(r.get("has_predecessor")),
        "predecessor_id": r.get("predecessor_id"),
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
