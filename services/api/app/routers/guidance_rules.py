"""HITL rule review endpoints for LLM-generated AppropriatenessRules.

Provides:
  POST /guidance/rules/generate                           -- trigger rule generation
  POST /guidance/rules/test/{recommendation_id}           -- dry-run extraction (no writes)
  GET  /guidance/rules/review                             -- list pending rules
  GET  /guidance/rules/review/{rule_id}                   -- rule detail
  POST /guidance/rules/review/{rule_id}/decision          -- approve / edit / reject
  POST /guidance/rules/review/{rule_id}/promote-to-domain -- add SNOMED to NICE domain
  POST /guidance/rules/review/approve-all                 -- bulk approve

All endpoints require the ai.admin role.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.db.neo4j_client import CodingGraphClient
from app.deps import require_admin
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/guidance", tags=["guidance-rules"])
PIPELINE_WORKER_BASE = os.getenv("PIPELINE_WORKER_URL", "http://localhost:8006").rstrip(
    "/"
)


def get_registry():
    from libs.pipeline_graph.registry import get_registry as _get_registry

    return _get_registry()


async def _proxy_pipeline_worker_json(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
) -> dict:
    url = f"{PIPELINE_WORKER_BASE}{path}"
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.request(method, url, json=json_body)

    if resp.status_code >= 400:
        try:
            payload = resp.json()
            detail = payload.get("detail", payload)
        except ValueError:
            detail = resp.text or f"Pipeline worker error ({resp.status_code})"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="Pipeline worker returned invalid JSON"
        ) from exc


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
       coalesce(rule.schemaVersion, 1) AS schema_version,
       rule.logicJson AS logic_json,
       rule.actionJson AS action_json,
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
    coalesce(pred.schemaVersion, 1) AS predecessor_schema_version,
    pred.logicJson AS predecessor_logic_json,
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
       coalesce(rule.schemaVersion, 1) AS schema_version,
       rule.logicJson AS logic_json,
       rule.actionJson AS action_json,
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
       coalesce(rule.schemaVersion, 1) AS schema_version,
       rule.logicJson AS logic_json,
       rule.actionJson AS action_json,
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
       coalesce(rule.schemaVersion, 1) AS schema_version,
       rule.logicJson AS logic_json,
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


_FETCH_SINGLE_RECOMMENDATION = """
MATCH (r:Recommendation {id: $rec_id})
OPTIONAL MATCH (r)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (ch)<-[:HAS_CHAPTER]-(g:Guideline)
RETURN r.id          AS id,
       r.verbatim    AS verbatim,
       r.title       AS title,
       r.urgency     AS urgency,
       r.strength    AS strength,
       r.sectionTitle AS section_title,
       r.isNormative  AS is_normative,
       ch.title       AS chapter_title,
       g.id           AS guideline_id,
       g.title        AS guideline_title
"""


_EXTRACTION_TIMEOUT_S = int(os.getenv("RULE_EXTRACTION_TIMEOUT_S", "120"))


@router.post("/rules/test/{recommendation_id:path}", status_code=200)
async def test_rule_extraction(
    recommendation_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Dry-run the rule extraction pipeline on a single recommendation.

    Runs the full ``guidance_rule_extraction`` LangGraph subgraph -- prompt
    resolution, dual-model consensus LLM, Terminology API SNOMED coding --
    but does **not** write anything to Neo4j or Redis.

    Use this to preview what criteria and action the AI would extract before
    committing to a full rule generation run.

    Times out after ``RULE_EXTRACTION_TIMEOUT_S`` seconds (default 120) and
    returns HTTP 504 so callers are never left waiting indefinitely.

    Args:
        recommendation_id: Neo4j Recommendation node ID
            (e.g. ``NG12:v1:CH000:SEC000:R000``).

    Returns:
        ``{recommendation, raw_criteria, coded_criteria, errors}`` where:
        - ``recommendation`` -- the stored verbatim text and metadata
        - ``raw_criteria`` -- plain-text LLM output ``{criteria_groups, action}``
        - ``coded_criteria`` -- SNOMED-resolved ``{criteria_groups, action, applies_to}``
          ``{present: [{term, snomed_concept_id, preferred_term, semantic_tag}], ...}``
        - ``errors`` -- any pipeline warnings
    """
    loop = asyncio.get_running_loop()

    client = _kg_client()
    try:
        rows = await loop.run_in_executor(
            None,
            lambda: client.run(_FETCH_SINGLE_RECOMMENDATION, rec_id=recommendation_id),
        )
    finally:
        client.close()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Recommendation {recommendation_id!r} not found in Neo4j.",
        )

    row = rows[0]
    rec = {
        "id": row["id"],
        "verbatim": row.get("verbatim", ""),
        "title": row.get("title", ""),
        "urgency": row.get("urgency", ""),
        "strength": row.get("strength", ""),
        "section_title": row.get("section_title", ""),
        "chapter_title": row.get("chapter_title", ""),
    }
    guideline_id = row.get("guideline_id", "")

    if not rec["verbatim"]:
        raise HTTPException(
            status_code=422,
            detail="Recommendation has no verbatim text stored -- re-ingest the guideline first.",
        )

    if not row.get("is_normative"):
        raise HTTPException(
            status_code=422,
            detail=(
                "This recommendation is marked as a cross-reference entry "
                "(isNormative=false) and would not be used for rule generation. "
                "Only canonical numbered recommendations are eligible."
            ),
        )

    # Run the subgraph dry-run in a thread so the event loop stays free, and
    # cap execution time so a slow LLM or Terminology API cannot block the
    # server indefinitely.
    try:
        subgraph = get_registry().build("guidance_rule_extraction")
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: subgraph.invoke(
                    {
                        "recommendation": rec,
                        "guideline_id": guideline_id,
                    }
                ),
            ),
            timeout=float(_EXTRACTION_TIMEOUT_S),
        )
    except asyncio.TimeoutError:
        logger.error(
            "Rule extraction test timed out after %ss for %s",
            _EXTRACTION_TIMEOUT_S,
            recommendation_id,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"Rule extraction timed out after {_EXTRACTION_TIMEOUT_S}s. "
                "The LLM or Terminology API may be overloaded -- try again shortly."
            ),
        )
    except Exception as exc:
        logger.exception("Rule extraction test failed for %s", recommendation_id)
        raise HTTPException(status_code=500, detail=f"Extraction pipeline error: {exc}")

    errors = result.get("errors") or []
    coded = result.get("coded_criteria")
    raw = result.get("raw_criteria")
    llm_tokens: dict = result.get("llm_tokens") or {}

    response_body = {
        "recommendation": {
            **rec,
            "guideline_id": guideline_id,
            "guideline_title": row.get("guideline_title", ""),
        },
        "raw_criteria": raw,
        "coded_criteria": coded,
        "errors": errors,
        # LLM token usage for this dry run (all consensus calls combined).
        "llm_tokens": llm_tokens,
        # Indicates whether this result would be written to Neo4j by the rule
        # generator.  False when any term failed to SNOMED-code (partial results).
        "would_write": coded is not None
        and not any("terminology_api_unavailable" in e for e in errors)
        and not bool((coded or {}).get("no_rule_expected")),
    }

    if coded is None:
        if errors:
            logger.warning(
                "Rule extraction test returned warnings for %s without coded output: %s",
                recommendation_id,
                errors,
            )
            return response_body
        # Pipeline produced no coded output at all — hard failure.
        logger.error(
            "Rule extraction test FAILED for %s — coded_criteria is None. Errors: %s",
            recommendation_id,
            errors,
        )
        return JSONResponse(status_code=422, content=response_body)

    if errors:
        # Partial results — coded_criteria exists but some terms failed or
        # Azure was offline.  Return 200 with warnings in the body so the UI
        # can show what DID get coded plus highlight the failures.
        logger.warning(
            "Rule extraction test PARTIAL for %s — coded_criteria returned with warnings: %s",
            recommendation_id,
            errors,
        )

    return response_body


@router.post("/rules/generate", status_code=202)
async def generate_rules(
    req: GenerateRulesRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Trigger LLM rule generation for a loaded NICE guideline.

    Returns a job ID immediately. Rule generation runs in the background.
    Rules will appear in the review queue once complete.
    Poll GET /rules/generate/{job_id} to track progress.
    """
    _ = scope
    return await _proxy_pipeline_worker_json(
        "POST",
        "/guidance/generate",
        json_body=req.model_dump(),
    )


@router.get("/rules/generate/{job_id}")
async def get_generate_job_status(
    job_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Poll the status of a rule generation job.

    Returns ``{job_id, guideline_id, status, started_at, completed_at, rule_ids, error}``
    where ``status`` is one of ``running | done | error``.
    """
    _ = scope
    return await _proxy_pipeline_worker_json("GET", f"/guidance/generate/{job_id}")


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

        pred_logic_tree = (
            _parse_logic_json(row.get("predecessor_logic_json"))
            if int(row.get("predecessor_schema_version") or 1) == 2
            else None
        )
        pred_criteria_raw = (
            _logic_tree_concepts(pred_logic_tree)
            if pred_logic_tree is not None
            else [
                c
                for c in (row.get("predecessor_criteria") or [])
                if c.get("concept_id")
            ]
        )
        pred_present = [c for c in pred_criteria_raw if c.get("predicate") == "PRESENT"]
        pred_absent = [c for c in pred_criteria_raw if c.get("predicate") == "ABSENT"]

        pred_decisions = [
            d for d in (row.get("predecessor_decisions") or []) if d.get("action")
        ]

        new_criteria = (
            rule.get("criteria_concepts")
            if int(rule.get("schema_version") or 1) == 2
            else rule["present_criteria"] + rule["absent_criteria"]
        )
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
                "schema_version": int(row.get("predecessor_schema_version") or 1),
                "plain_english": (
                    _plain_english_logic(pred_logic_tree)
                    if pred_logic_tree is not None
                    else _plain_english_criteria(pred_present, pred_absent)
                ),
                "present_criteria": pred_present,
                "absent_criteria": pred_absent,
                "logic_tree": pred_logic_tree,
                "criteria_concepts": pred_criteria_raw,
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
    reviewer: str = Query(
        ..., min_length=2, description="Email of the admin promoting this rule"
    ),
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

        logic_tree = (
            _parse_logic_json(row.get("logic_json"))
            if int(row.get("schema_version") or 1) == 2
            else None
        )
        concepts = (
            _logic_tree_concepts(logic_tree)
            if logic_tree is not None
            else [c for c in (row.get("concepts") or []) if c.get("concept_id")]
        )
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
        pending = client.run(_FETCH_PENDING_IDS, guideline_id=guideline_id)
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


def _compute_diff(new_criteria: list[dict], pred_criteria: list[dict]) -> dict:
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
        "added": [c for c in valid_new if _key(c) not in pred_keys],
        "removed": [c for c in valid_pred if _key(c) not in new_keys],
        "unchanged": [c for c in valid_new if _key(c) in pred_keys],
    }


def _format_rule(r: dict) -> dict:
    """Format a Neo4j rule record into a plain-English API response."""
    schema_version = int(r.get("schema_version") or 1)
    criteria = [c for c in (r.get("criteria") or []) if c.get("concept_id")]
    present = [c for c in criteria if c.get("predicate") == "PRESENT"]
    absent = [c for c in criteria if c.get("predicate") == "ABSENT"]
    logic_tree = _parse_logic_json(r.get("logic_json")) if schema_version == 2 else None
    logic_concepts = _logic_tree_concepts(logic_tree) if logic_tree else []
    display_plain_english = (
        _plain_english_logic(logic_tree)
        if logic_tree is not None
        else _plain_english_criteria(present, absent)
    )
    return {
        "rule_id": r.get("rule_id"),
        "name": r.get("name"),
        "status": r.get("status"),
        "strength": r.get("strength"),
        "schema_version": schema_version,
        "guideline_id": r.get("guideline_id"),
        "guideline_version": r.get("guideline_version"),
        "chapter_title": r.get("chapter_title"),
        "recommendation_text": r.get("recommendation_text"),
        "plain_english": display_plain_english,
        "present_criteria": present,
        "absent_criteria": absent,
        "logic_tree": logic_tree,
        "criteria_concepts": logic_concepts,
        "created_at": str(r.get("created_at", "")),
        "has_predecessor": bool(r.get("has_predecessor")),
        "predecessor_id": r.get("predecessor_id"),
    }


def _plain_english_criteria(present: list[dict], absent: list[dict]) -> str:
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


def _parse_logic_json(value: str | None) -> dict | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _logic_tree_concepts(node: dict | None) -> list[dict]:
    if not node:
        return []
    kind = str(node.get("kind") or "").lower()
    if kind == "concept":
        criterion = dict(node.get("criterion") or {})
        concept_id = criterion.get("snomed_concept_id")
        if not concept_id:
            return []
        return [
            {
                "predicate": "LOGIC",
                "concept_id": concept_id,
                "preferred_term": criterion.get("preferred_term")
                or criterion.get("term")
                or concept_id,
            }
        ]
    items: list[dict] = []
    for child in node.get("children") or []:
        if isinstance(child, dict):
            items.extend(_logic_tree_concepts(child))
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for item in items:
        key = (str(item.get("predicate") or ""), str(item.get("concept_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _plain_english_logic(node: dict | None) -> str:
    if not node:
        return "No criteria defined yet."
    return "Triggers when: " + _logic_node_to_text(node)


def _logic_node_to_text(node: dict) -> str:
    kind = str(node.get("kind") or "").upper()
    if kind == "CONCEPT":
        criterion = dict(node.get("criterion") or {})
        return str(
            criterion.get("preferred_term")
            or criterion.get("term")
            or "unknown concept"
        )
    if kind == "DEMOGRAPHIC":
        field = node.get("field")
        operator = node.get("operator")
        value = node.get("value")
        unit = node.get("unit")
        suffix = f" {unit}" if unit else ""
        return f"{field} {operator} {value}{suffix}".strip()
    child_texts = [
        _logic_node_to_text(child)
        for child in (node.get("children") or [])
        if isinstance(child, dict)
    ]
    if not child_texts:
        return "unknown condition"
    if kind == "AND":
        return " AND ".join(f"({text})" for text in child_texts)
    if kind == "OR":
        return " OR ".join(f"({text})" for text in child_texts)
    if kind == "NOT":
        return f"NOT ({child_texts[0]})"
    if kind == "AT_LEAST":
        return f"at least {int(node.get('min') or 1)} of: " + ", ".join(child_texts)
    return "unknown condition"
