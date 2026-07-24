"""HITL rule review endpoints for LLM-generated AppropriatenessRules.

Atlas trace:
  DO: DO-5B320DDC
  Also implements: DO-D6CE2AA5
  DI: DI-69C29EEF, DI-A3107424
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5B320DDC")

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
from app.services.guidance_rule_edit import (
    EditNotApplicable,
    LogicTreeValidationError,
    RuleUpdates,
    apply_rule_edit,
    reject_sibling_pending_rules,
)
from libs.auth.org_scope import CallerScope
from libs.auth.service_auth import get_service_auth_header

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
    headers = {**get_service_auth_header()}
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.request(method, url, json=json_body, headers=headers)

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


# Active-list staleness projection -- updated_at + reviewed_at + reviewer
# are written by _UPSERT_APPROPRIATENESS_RULE (ON MATCH SET rule.updatedAt
# = datetime()) and _UPDATE_RULE_STATUS (sets reviewedAt / reviewedBy on
# every approve / edit / reject). Surfacing them lets the FE sort the
# Active list "stalest first" so reviewers see the rules most overdue
# for re-validation at the top of the page (DI-LEO-AI-528 AC-001).
# updated_at falls back to created_at for rules that have never been
# edited; reviewed_at is null until the first decision.
_FETCH_RULES = """
MATCH (rule:AppropriatenessRule)
WHERE ($status IS NULL OR rule.status = $status)
  AND ($guideline_id IS NULL OR
       EXISTS {
         MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(rule)
       })
WITH rule
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)<-[:HAS_RECOMMENDATION]-(g:Guideline)
WITH rule, rec, g ORDER BY coalesce(rec.versionId, '') DESC
WITH rule, head(collect(rec)) AS rec, head(collect(g)) AS g
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)-[hc:HAS_CRITERIA]->(concept)
OPTIONAL MATCH (rule)-[:SUPERSEDES]->(pred:AppropriatenessRule)
WITH rule, rec, g, ch, pred,
     collect({
         predicate: hc.predicate,
         concept_id: coalesce(concept.id, concept.conceptId),
         preferred_term: coalesce(concept.preferred_term, concept.fsn, concept.term, concept.id, concept.conceptId)
     }) AS criteria
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(:ActionGroup)-[ha:HAS_ACTION]->()
WITH rule, rec, g, ch, pred, criteria,
     head([p IN collect(ha.priority) WHERE p IS NOT NULL | p]) AS action_priority,
     head([d IN collect(ha.dueDays) WHERE d IS NOT NULL | d]) AS action_due_days
RETURN rule.id AS rule_id,
       rule.name AS name,
       rule.strength AS strength,
       rule.status AS status,
       coalesce(rule.schemaVersion, 1) AS schema_version,
       rule.logicJson AS logic_json,
       rule.actionJson AS action_json,
       rule.verifierJson AS verifier_json,
       rule.createdAt AS created_at,
       coalesce(rule.updatedAt, rule.createdAt) AS updated_at,
       rule.reviewedAt AS reviewed_at,
       rule.reviewedBy AS reviewed_by,
       rule.previousRecommendationText AS previous_recommendation_text,
       rule.previousRecommendationNumber AS previous_recommendation_number,
       g.id AS guideline_id,
       g.ingestVersion AS guideline_version,
       ch.title AS chapter_title,
       rec.verbatim AS recommendation_text,
       rec.listStructureJson AS list_structure_json,
       criteria,
       action_priority,
       action_due_days,
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
        concept_id: coalesce(pred_concept.id, pred_concept.conceptId),
        preferred_term: coalesce(pred_concept.preferred_term, pred_concept.fsn, pred_concept.term, pred_concept.id, pred_concept.conceptId)
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
WITH rule
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)<-[:HAS_RECOMMENDATION]-(g:Guideline)
WITH rule, rec, g ORDER BY coalesce(rec.versionId, '') DESC
WITH rule, head(collect(rec)) AS rec, head(collect(g)) AS g
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)-[hc:HAS_CRITERIA]->(concept)
OPTIONAL MATCH (rule)-[:SUPERSEDES]->(pred:AppropriatenessRule)
WITH rule, rec, g, ch, pred,
     collect({
         predicate: hc.predicate,
         concept_id: coalesce(concept.id, concept.conceptId),
         preferred_term: coalesce(concept.preferred_term, concept.fsn, concept.term, concept.id, concept.conceptId)
     }) AS criteria
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(:ActionGroup)-[ha:HAS_ACTION]->()
WITH rule, rec, g, ch, pred, criteria,
     head([p IN collect(ha.priority) WHERE p IS NOT NULL | p]) AS action_priority,
     head([d IN collect(ha.dueDays) WHERE d IS NOT NULL | d]) AS action_due_days
RETURN rule.id AS rule_id,
       rule.name AS name,
       rule.strength AS strength,
       rule.status AS status,
       coalesce(rule.schemaVersion, 1) AS schema_version,
       rule.logicJson AS logic_json,
       rule.actionJson AS action_json,
       rule.verifierJson AS verifier_json,
       rule.createdAt AS created_at,
       coalesce(rule.updatedAt, rule.createdAt) AS updated_at,
       rule.reviewedAt AS reviewed_at,
       rule.reviewedBy AS reviewed_by,
       rule.previousRecommendationText AS previous_recommendation_text,
       rule.previousRecommendationNumber AS previous_recommendation_number,
       g.id AS guideline_id,
       g.ingestVersion AS guideline_version,
       ch.title AS chapter_title,
       rec.verbatim AS recommendation_text,
       rec.listStructureJson AS list_structure_json,
       criteria,
       action_priority,
       action_due_days,
       pred.id IS NOT NULL AS has_predecessor,
       pred.id AS predecessor_id
"""

_FETCH_RULE_DETAIL = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)<-[:HAS_RECOMMENDATION]-(g:Guideline)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)-[hc:HAS_CRITERIA]->(concept)
WITH rule, rec, g,
     collect({
         predicate: hc.predicate,
         concept_id: coalesce(concept.id, concept.conceptId),
         preferred_term: coalesce(concept.preferred_term, concept.fsn, concept.term, concept.id, concept.conceptId)
     }) AS criteria
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(:ActionGroup)-[ha:HAS_ACTION]->()
WITH rule, rec, g, criteria,
     head([p IN collect(ha.priority) WHERE p IS NOT NULL | p]) AS action_priority,
     head([d IN collect(ha.dueDays) WHERE d IS NOT NULL | d]) AS action_due_days
RETURN rule.id AS rule_id,
       rule.name AS name,
       rule.strength AS strength,
       rule.status AS status,
       coalesce(rule.schemaVersion, 1) AS schema_version,
       rule.logicJson AS logic_json,
       rule.actionJson AS action_json,
       rule.verifierJson AS verifier_json,
       rule.createdAt AS created_at,
       coalesce(rule.updatedAt, rule.createdAt) AS updated_at,
       rule.reviewedAt AS reviewed_at,
       rule.reviewedBy AS reviewed_by,
       g.id AS guideline_id,
       g.title AS guideline_title,
       rec.verbatim AS recommendation_text,
       rec.listStructureJson AS list_structure_json,
       criteria,
       action_priority,
       action_due_days
"""

_CREATE_BLANK_RULE = """
MATCH (rec:Recommendation {id: $rec_id})
WHERE NOT coalesce(rec.likelyIncorrect, false)
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (ch)<-[:HAS_CHAPTER]-(g:Guideline)
WITH rec, ch, g
CREATE (rule:AppropriatenessRule {
    id: $rule_id,
    name: coalesce(rec.title, $rec_id),
    status: 'pending_review',
    schemaVersion: 2,
    logicJson: '{}',
    actionJson: null,
    verifierJson: null,
    createdAt: datetime(),
    guidelineId: coalesce(g.id, '')
})
MERGE (rec)-[:HAS_RULE]->(rule)
RETURN rule.id AS rule_id,
       rule.name AS name,
       rule.status AS status,
       coalesce(rule.schemaVersion, 2) AS schema_version,
       rule.logicJson AS logic_json,
       rule.createdAt AS created_at,
       rec.verbatim AS recommendation_text,
       rec.listStructureJson AS list_structure_json,
       g.id AS guideline_id,
       ch.title AS chapter_title
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

_FETCH_INCORRECT_RECOMMENDATIONS = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(rec:Recommendation)
WHERE coalesce(rec.likelyIncorrect, false)
  AND ($recommendation_ids IS NULL OR rec.id IN $recommendation_ids)
RETURN rec.id AS rec_id
LIMIT 1
"""

_FETCH_RULE_FOR_PROMOTION = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
OPTIONAL MATCH (rule)<-[:HAS_RULE]-()<-[:HAS_RECOMMENDATION]-(g:Guideline)
OPTIONAL MATCH (g)<-[:CLASSIFIES_GUIDELINE]-(sub:TaxonomySubcategory)-[:HAS_DOMAIN]->(domain:AuditDomain {source: 'nice'})
OPTIONAL MATCH (g)-[:HAS_DOMAIN]->(local_domain:AuditDomain)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)-[:HAS_CRITERIA]->(concept)
RETURN rule.status AS status,
       coalesce(rule.schemaVersion, 1) AS schema_version,
       rule.logicJson AS logic_json,
       g.id AS guideline_id,
       coalesce(local_domain.id, domain.id) AS domain_id,
       coalesce(local_domain.name, domain.name) AS domain_name,
       collect(DISTINCT {concept_id: coalesce(concept.id, concept.conceptId), term: coalesce(concept.preferred_term, concept.fsn, concept.term, concept.id, concept.conceptId)}) AS concepts
"""

# Promotion writes the canonical (:Concept {id}) so the new ValueSet
# concepts share the same node identity as terminology search results
# and as the rule's own criteria nodes. See DI-LEO-AI-528 for the
# wider schema-unification rationale.
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
MERGE (concept:Concept {id: c.concept_id})
ON CREATE SET concept.preferred_term = c.term
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
    only_without_rules: bool = False
    recommendation_ids: list[str] | None = None


class CreateBlankRuleRequest(BaseModel):
    rec_id: str


class RuleDecisionRequest(BaseModel):
    action: Literal["approve", "reject", "edit"]
    reviewer: str = Field(min_length=2)
    reason: str = Field(min_length=3)
    edited_name: str | None = None
    # Populated only for action == "edit" when the reviewer changed the rule
    # content. When absent on an edit, the call falls back to the legacy
    # "approve with note" behaviour for backward compatibility.
    updates: RuleUpdates | None = None


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
        # Partial results -- coded_criteria exists but some terms failed or
        # Azure was offline.  Return 200 with warnings in the body so the UI
        # can show what DID get coded plus highlight the failures.
        logger.warning(
            "Rule extraction test PARTIAL for %s -- coded_criteria returned"
            " with warnings: %s",
            recommendation_id,
            errors,
        )

    _write_dry_run_audit_event(
        recommendation_id=recommendation_id,
        guideline_id=guideline_id,
        coded=coded,
        errors=list(errors),
        llm_tokens=dict(llm_tokens),
    )

    return response_body


# ---------------------------------------------------------------------------
# AI-assisted re-draft endpoint (rule editor "Draft from NICE text" feature)
# ---------------------------------------------------------------------------

_FETCH_REC_FOR_RULE = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)
WITH rule, rec ORDER BY coalesce(rec.versionId, '') DESC
WITH rule, head(collect(rec)) AS rec
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (ch)<-[:HAS_CHAPTER]-(g:Guideline)
RETURN rec.id        AS rec_id,
       rec.verbatim  AS verbatim,
       rec.title     AS title,
       rec.urgency   AS urgency,
       rec.strength  AS strength,
       rec.sectionTitle AS section_title,
       ch.title      AS chapter_title,
       coalesce(g.id, rule.guidelineId, '') AS guideline_id
"""


@router.post("/rules/review/{rule_id}/ai-redraft", status_code=200)
async def ai_redraft_rule(
    rule_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Re-run the guidance rule extraction subgraph for a rule's linked
    NICE recommendation and return the proposed ``logic_tree`` JSON.

    This is advisory only: nothing is written to Neo4j.  The UI shows
    the proposed tree for the reviewer to accept, edit, or discard.

    Returns:
        ``{"logic_tree": {...}, "errors": [...]}``

    Raises:
        404 if rule or its recommendation is not found.
        422 if the recommendation has no verbatim text.
        504 on extraction timeout.
    """
    loop = asyncio.get_running_loop()

    client = _kg_client()
    try:
        rows = await loop.run_in_executor(
            None,
            lambda: client.run(_FETCH_REC_FOR_RULE, rule_id=rule_id),
        )
    finally:
        client.close()

    if not rows or not rows[0].get("verbatim"):
        raise HTTPException(
            status_code=404,
            detail=(
                "Rule not found or has no linked recommendation text. "
                "Re-ingest the guideline to attach recommendation text."
            ),
        )

    row = rows[0]
    rec = {
        "id": row.get("rec_id", ""),
        "verbatim": row.get("verbatim", ""),
        "title": row.get("title", ""),
        "urgency": row.get("urgency", ""),
        "strength": row.get("strength", ""),
        "section_title": row.get("section_title", ""),
        "chapter_title": row.get("chapter_title", ""),
    }
    guideline_id = row.get("guideline_id", "")

    try:
        subgraph = get_registry().build("guidance_rule_extraction")
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: subgraph.invoke(
                    {"recommendation": rec, "guideline_id": guideline_id}
                ),
            ),
            timeout=float(_EXTRACTION_TIMEOUT_S),
        )
    except asyncio.TimeoutError:
        logger.error(
            "AI redraft timed out after %ss for rule %s",
            _EXTRACTION_TIMEOUT_S,
            rule_id,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"AI redraft timed out after {_EXTRACTION_TIMEOUT_S}s. "
                "Try again shortly."
            ),
        )
    except Exception as exc:
        logger.exception("AI redraft failed for rule %s", rule_id)
        raise HTTPException(status_code=500, detail=f"Extraction pipeline error: {exc}")

    errors = result.get("errors") or []
    coded = result.get("coded_criteria") or {}
    logic_tree = coded.get("logic_tree")

    if logic_tree is None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "AI could not extract a rule structure.",
                "errors": errors,
            },
        )

    return {"logic_tree": logic_tree, "errors": errors}


# DI-LEO-AI-518: persist a PipelineRun :AuditEvent for guidance dry-run
# invocations so /admin/billing surfaces the cost of the rule editor's
# "Test extraction" button. Best-effort -- never raises, never blocks.
_DRY_RUN_AUDIT_EVENT = """
MERGE (ae:AuditEvent {id: $id})
SET ae.type                          = 'PipelineRun',
    ae.subtype                       = 'guidance_rule_dry_run',
    ae.plan_definition_id            = 'guidance_rule_extraction',
    ae.event_type                    = 'guidance_rule_dry_run',
    ae.guideline_id                  = $guideline_id,
    ae.recommendation_id             = $recommendation_id,
    ae.status                        = $status,
    ae.error_count                   = $error_count,
    ae.first_error                   = $first_error,
    ae.llm_input_tokens              = $llm_input_tokens,
    ae.llm_output_tokens             = $llm_output_tokens,
    ae.llm_cached_tokens             = $llm_cached_tokens,
    ae.llm_calls                     = $llm_calls,
    ae.llm_cost_usd                  = $llm_cost_usd,
    ae.extraction_prompt_name        = 'guidance_rule_extraction',
    ae.extraction_prompt_version     = 1,
    ae.extraction_provider           = 'bedrock',
    ae.extraction_model_tier         = 'small',
    ae.would_write                   = $would_write,
    ae.created_at                    = datetime()
RETURN ae.id AS id
"""


def _write_dry_run_audit_event(
    *,
    recommendation_id: str,
    guideline_id: str,
    coded,
    errors: list[str],
    llm_tokens: dict,
) -> None:
    """Persist guidance rule dry-run telemetry as a PipelineRun event.

    Mirrors guidance_rule_generator._write_guidance_audit_event but
    runs in the request handler. The wire format is intentionally a
    superset (adds ``would_write``) so the dashboards can distinguish
    dry-run cost from production rule generation cost.
    """

    try:
        from libs.llm_usage import LLMCostConfig, LLMUsage

        usage = LLMUsage(
            input_tokens=int(llm_tokens.get("input_tokens", 0)),
            output_tokens=int(llm_tokens.get("output_tokens", 0)),
            cached_input_tokens=int(llm_tokens.get("cached_input_tokens", 0)),
            llm_calls=int(llm_tokens.get("llm_calls", 0)),
        )
        try:
            cost_usd = usage.cost_usd(LLMCostConfig.from_env())
        except Exception:
            cost_usd = 0.0

        status = (
            "completed"
            if coded is not None and not errors
            else ("partial" if coded is not None else "failed")
        )
        first_error = errors[0][:400] if errors else None

        client = CodingGraphClient()
        try:
            client.run(
                _DRY_RUN_AUDIT_EVENT,
                id=f"audit-guidance-dryrun-{recommendation_id}-{uuid.uuid4().hex[:8]}",
                guideline_id=guideline_id,
                recommendation_id=recommendation_id,
                status=status,
                error_count=len(errors),
                first_error=first_error,
                llm_input_tokens=int(usage.input_tokens),
                llm_output_tokens=int(usage.output_tokens),
                llm_cached_tokens=int(usage.cached_input_tokens),
                llm_calls=int(usage.llm_calls),
                llm_cost_usd=round(cost_usd, 6),
                would_write=bool(
                    coded is not None
                    and not any("terminology_api_unavailable" in e for e in errors)
                ),
            )
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception:
        logger.warning(
            "Failed to write guidance dry-run AuditEvent for %s",
            recommendation_id,
            exc_info=True,
        )


@router.post("/rules/generate", status_code=202)
async def generate_rules(
    req: GenerateRulesRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Trigger LLM rule generation for a loaded NICE guideline.

    Returns a job ID immediately. Rule generation runs in the background.
    Rules will appear in the review queue once complete.
    Poll GET /rules/generate/{job_id} to track progress.

    Pass ``recommendation_ids`` to restrict generation to a subset of
    recommendations (already supported by the pipeline worker).
    """
    _ = scope
    _reject_likely_incorrect_recommendations(req)
    return await _proxy_pipeline_worker_json(
        "POST",
        "/guidance/generate",
        json_body=req.model_dump(exclude_none=True),
    )


def _reject_likely_incorrect_recommendations(req: GenerateRulesRequest) -> None:
    """Prevent AI rule generation from an unverified local recommendation."""
    client = _kg_client()
    try:
        rows = client.run(
            _FETCH_INCORRECT_RECOMMENDATIONS,
            guideline_id=req.guideline_id,
            recommendation_ids=req.recommendation_ids,
        )
    finally:
        client.close()
    if rows:
        raise HTTPException(
            status_code=422,
            detail="Fix guideline verification issues before generating rules.",
        )


@router.post("/rules/create-blank", status_code=201)
def create_blank_rule(
    req: CreateBlankRuleRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Create an empty AppropriatenessRule stub for a recommendation.

    Used by the "Build by hand" flow in the recommendation picker dialog.
    Returns the new rule detail so the frontend can open EditRuleDialog
    immediately without a separate fetch.
    """
    _ = scope
    rule_id = f"rule:{uuid.uuid4()}"
    client = _kg_client()
    try:
        records = client.run(
            _CREATE_BLANK_RULE,
            rec_id=req.rec_id,
            rule_id=rule_id,
        )
        if not records:
            blocked = client.run(
                "MATCH (rec:Recommendation {id: $rec_id}) "
                "WHERE coalesce(rec.likelyIncorrect, false) "
                "RETURN rec.id AS id LIMIT 1",
                rec_id=req.rec_id,
            )
            if blocked:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Fix guideline verification issues before creating a rule."
                    ),
                )
            raise HTTPException(
                status_code=404,
                detail=f"Recommendation not found: {req.rec_id}",
            )
        row = records[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("create_blank_rule Neo4j error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Could not create rule stub."
        ) from exc
    finally:
        client.close()

    return {
        "rule_id": row["rule_id"],
        "rule": {
            "rule_id": row["rule_id"],
            "name": row["name"],
            "status": row["status"],
            "schema_version": row["schema_version"],
            "logic_json": row["logic_json"],
            "action_json": None,
            "verifier_json": None,
            "created_at": str(row["created_at"]) if row.get("created_at") else None,
            "updated_at": None,
            "reviewed_at": None,
            "reviewed_by": None,
            "guideline_id": row.get("guideline_id"),
            "guideline_version": None,
            "chapter_title": row.get("chapter_title"),
            "recommendation_text": row.get("recommendation_text"),
            "recommendation_structure": _parse_list_structure_json(
                row.get("list_structure_json")
            ),
            "criteria": [],
            "has_predecessor": False,
            "predecessor_id": None,
        },
    }


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

    - ``approve`` sets the rule to ``active`` so it will be included in the
      next bitmap compilation.
    - ``reject`` removes the rule from the review queue.
    - ``edit`` with no ``updates`` payload behaves like approve-with-note
      (kept for backward compatibility).
    - ``edit`` with an ``updates`` payload writes a NEW versioned rule
      carrying the reviewer's changes, supersedes the original, and links
      them via ``[:SUPERSEDES]``. Both the original and the new rule retain
      their audit events. See ``guidance_rule_edit.apply_rule_edit``.

    All decisions are recorded in an immutable audit trail.
    """
    if body.action == "edit" and body.updates is not None:
        return _decide_rule_with_edits(rule_id, body)

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
        if new_status == "active":
            reject_sibling_pending_rules(
                client,
                rule_id=rule_id,
                reviewer=body.reviewer,
            )
        return {"rule_id": rule_id, "status": new_status}
    finally:
        client.close()


def _decide_rule_with_edits(rule_id: str, body: RuleDecisionRequest) -> dict:
    """Persist a reviewer-edited rule version via the edit service."""
    client = _kg_client()
    try:
        try:
            result = apply_rule_edit(
                client,
                predecessor_rule_id=rule_id,
                updates=body.updates,  # type: ignore[arg-type]
                reviewer=body.reviewer,
                reason=body.reason,
            )
        except LogicTreeValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except EditNotApplicable as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {
            "rule_id": result["rule_id"],
            "predecessor_id": result["predecessor_id"],
            "status": "active",
        }
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
                    "No domain is linked to this guideline. "
                    "Link a domain before promoting this rule."
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
    verifier = _parse_verifier_json(r.get("verifier_json"))
    actions = _parse_actions_json(r.get("action_json"))
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
        # Structured NICE HTML list tree (lead text + <li> items, offsets
        # into recommendation_text) when the recommendation is a list
        # rather than a plain sentence. Lets the highlight-to-build
        # wizard's StepPathwaySplit prefer the real HTML structure over
        # the "or"-boundary heuristic. None for plain-sentence recs.
        "recommendation_structure": _parse_list_structure_json(
            r.get("list_structure_json")
        ),
        "plain_english": display_plain_english,
        "present_criteria": present,
        "absent_criteria": absent,
        "logic_tree": logic_tree,
        # "action" is a read-only derived flat criterion (actions[0].criterion)
        # kept for FE code that has not yet migrated to the actions[] list.
        # See DI-42246DA7 acceptance criteria (multi-action support).
        "action": actions[0]["criterion"] if actions else None,
        "actions": actions,
        # Rule-level clinical priority from HAS_ACTION edges. Surfaced so
        # the EditRuleDialog PriorityPanel can show and edit urgency
        # without a second round-trip.
        "action_priority": r.get("action_priority") or None,
        "action_due_days": r.get("action_due_days"),
        "criteria_concepts": logic_concepts,
        "generation_outcome": verifier.get("generation_outcome"),
        "needs_human_review": bool(verifier.get("needs_human_review")),
        "generation_errors": verifier.get("errors") or [],
        "created_at": str(r.get("created_at", "")),
        # updated_at + reviewed_at + reviewed_by are surfaced so the FE
        # can sort the Active list "stalest first" and show authors when
        # each rule was last touched (DI-LEO-AI-528 AC-001 / AC-002).
        # updated_at coalesces to created_at for rules that were never
        # edited; reviewed_at / reviewed_by are null until the first
        # decision and serialised as empty strings to keep the JSON
        # shape stable for FE consumers.
        "updated_at": str(r.get("updated_at") or r.get("created_at") or ""),
        "reviewed_at": str(r.get("reviewed_at") or ""),
        "reviewed_by": str(r.get("reviewed_by") or ""),
        "has_predecessor": bool(r.get("has_predecessor")),
        "predecessor_id": r.get("predecessor_id"),
        "previous_recommendation_text": r.get("previous_recommendation_text") or None,
        "previous_recommendation_number": r.get("previous_recommendation_number")
        or None,
    }


def _parse_verifier_json(raw: object) -> dict:
    """Parse stored verifierJson for generation outcome metadata."""
    if not raw:
        return {}
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_list_structure_json(raw: object) -> dict | None:
    """Parse the recommendation's stored ``listStructureJson``.

    Lets the highlight-to-build wizard prefer the NICE HTML list tree
    over the "or"-boundary heuristic when it renders a recommendation
    for pathway splitting (see ``pathwayTextSplit.ts``). Returns
    ``None`` for plain-sentence recommendations that have no list.
    """
    if not raw:
        return None
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _format_action_item(payload: dict) -> dict:
    """Format one stored action dict into the nested RuleAction API shape."""
    snomed_id = payload.get("snomed_concept_id")
    preferred = payload.get("preferred_term") or payload.get("term") or ""
    return {
        "criterion": {
            "snomed_concept_id": str(snomed_id) if snomed_id else None,
            "preferred_term": str(preferred),
            "semantic_tag": str(payload.get("semantic_tag") or ""),
            "term": str(payload.get("term") or preferred),
        },
        "strength": str(payload.get("strength") or "unspecified"),
    }


def _parse_actions_json(raw: object) -> list[dict]:
    """Parse the stored actionJson into the structured ``actions`` list.

    Surfacing this lets the EditRuleDialog show -- and let reviewers
    correct -- the SNOMED-coded recommended procedures that fire when
    the rule matches a patient (DI-LEO-AI-170, DI-42246DA7).

    Handles both the current array shape (``[{...}, ...]``, one or more
    recommended actions) and the legacy single-object shape written
    before multi-action support existed -- the latter is wrapped in a
    one-item list so old rows never need a backfill migration.

    Returns an empty list when the rule has no action coded or the
    stored JSON is malformed; otherwise a list of nested RuleAction
    dicts each with ``criterion`` (snomed_concept_id, preferred_term,
    semantic_tag, term) and ``strength`` keys.
    """
    if not raw:
        return []
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    if isinstance(payload, list):
        items = [p for p in payload if isinstance(p, dict)]
    elif isinstance(payload, dict):
        items = [payload]
    else:
        return []
    return [_format_action_item(p) for p in items]


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
