"""LLM-based AppropriatenessRule generator with HITL gate.

Uses the existing dual-model consensus pipeline (AWS Bedrock Haiku +
Azure GPT-5-mini, with Sonnet arbitration) to generate candidate clinical
decision criteria from NICE Recommendation nodes in Neo4j.

All LLM call sites comply with llm-security.mdc:
  - INJECTION_GUARD prepended to every system prompt
  - sanitise_for_prompt() applied to all clinical text
  - cap_llm_response() applied before parsing
  - fail_verdict = None (conservative -- no rule written on LLM failure)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import httpx

from libs.llm_client.consensus import run_consensus
from libs.llm_client.prompt_safety import (
    INJECTION_GUARD,
    cap_llm_response,
    sanitise_for_prompt,
)

logger = logging.getLogger(__name__)

_TERMINOLOGY_URL = os.getenv("TERMINOLOGY_API_URL", "http://terminology-api:8001")

_SYSTEM_PROMPT = (
    INJECTION_GUARD
    + "You are a clinical decision-support analyst. "
    "Your task is to identify the clinical criteria that determine "
    "when a NICE recommendation applies to a patient. "
    "Output ONLY a JSON object with two keys: "
    '"present" (list of clinical terms that must be present) and '
    '"absent" (list of clinical terms that must be absent). '
    "Use plain clinical terms, not SNOMED IDs. "
    "Maximum 5 terms per list. "
    "If you cannot determine clear criteria, return {\"present\": [], \"absent\": []}."
)

_UPSERT_RULE = """
MATCH (rec:Recommendation {id: $recommendation_id})
MERGE (rule:AppropriatenessRule {id: $rule_id})
ON CREATE SET
    rule.name              = $name,
    rule.strength          = $strength,
    rule.status            = 'pending_review',
    rule.generatedBy       = 'llm_consensus',
    rule.createdAt         = datetime()
ON MATCH SET
    rule.updatedAt         = datetime()
MERGE (rec)-[:HAS_RULE]->(rule)
RETURN rule.id AS id
"""

_UPSERT_CRITERIA_GROUP = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
MERGE (grp:CriteriaGroup {id: $group_id})
ON CREATE SET
    grp.type = $group_type,
    grp.createdAt = datetime()
MERGE (rule)-[:HAS_CRITERIA_GROUP]->(grp)
RETURN grp.id AS id
"""

_UPSERT_CRITERIA_EDGE = """
MATCH (grp:CriteriaGroup {id: $group_id})
MATCH (concept {conceptId: $concept_id})
MERGE (grp)-[e:HAS_CRITERIA]->(concept)
ON CREATE SET
    e.predicate       = $predicate,
    e.distanceChild   = 0,
    e.distanceParent  = 0
"""

_CREATE_REVIEW_TASK = """
MERGE (task:GuidanceReviewTask {id: $task_id})
ON CREATE SET
    task.ruleId       = $rule_id,
    task.guidelineId  = $guideline_id,
    task.status       = 'pending',
    task.createdAt    = datetime()
"""

_FETCH_RECOMMENDATIONS = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
RETURN r.id AS id,
       r.verbatim AS verbatim,
       r.title AS title,
       r.urgency AS urgency,
       r.strength AS strength
"""


def _parse_criteria_response(raw: str) -> dict[str, list[str]] | None:
    """Parse LLM response into present/absent criteria lists.

    Args:
        raw: Raw LLM response text.

    Returns:
        Dict with ``present`` and ``absent`` lists, or ``None`` on any error.
    """
    capped = cap_llm_response(raw, max_chars=2000)
    if not capped:
        return None
    try:
        start = capped.find("{")
        end = capped.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        data = json.loads(capped[start:end])
        return {
            "present": [str(t) for t in data.get("present", [])[:5]],
            "absent": [str(t) for t in data.get("absent", [])[:5]],
        }
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


async def _snomed_lookup(term: str) -> dict[str, str] | None:
    """Look up a SNOMED concept for a clinical term via the terminology API.

    Args:
        term: Plain-language clinical term.

    Returns:
        Dict with ``concept_id`` and ``preferred_term``, or ``None`` on failure.
    """
    url = f"{_TERMINOLOGY_URL}/terminology/search"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"q": term, "limit": 3})
            resp.raise_for_status()
            results = resp.json()
            if not results:
                return None
            best = results[0]
            return {
                "concept_id": str(best.get("conceptId", "")),
                "preferred_term": best.get("term", term),
            }
    except Exception as exc:
        logger.debug("SNOMED lookup failed for %r: %s", term, exc)
        return None


class GuidanceRuleGenerator:
    """Generates AppropriatenessRule candidates from Recommendation nodes.

    Uses the existing dual-model consensus pipeline. Generated rules are
    stored with status ``pending_review`` and cannot affect patients until
    a human approves them via the HITL review queue.
    """

    def __init__(self, neo4j_driver) -> None:
        self._driver = neo4j_driver

    def generate_rules_for_guideline(self, guideline_id: str) -> list[str]:
        """Generate rule candidates for all recommendations of a guideline.

        Args:
            guideline_id: Knowledge-graph Guideline node ID (e.g. ``NG151``).

        Returns:
            List of generated rule IDs (all with status ``pending_review``).
        """
        recs = self._fetch_recommendations(guideline_id)
        generated = []
        for rec in recs:
            rule_id = self._generate_one(guideline_id, rec)
            if rule_id:
                generated.append(rule_id)
        return generated

    def _fetch_recommendations(self, guideline_id: str) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            result = session.run(_FETCH_RECOMMENDATIONS, guideline_id=guideline_id)
            return [dict(r) for r in result]

    def _generate_one(self, guideline_id: str, rec: dict[str, Any]) -> str | None:
        """Generate a single rule for one recommendation.

        Returns the rule ID on success, None on LLM failure.
        """
        verbatim = rec.get("verbatim") or rec.get("title") or ""
        if not verbatim.strip():
            return None

        user_msg = (
            f"NICE recommendation:\n"
            f"{sanitise_for_prompt(verbatim, max_chars=2000)}\n\n"
            f"Urgency: {rec.get('urgency', 'unspecified')}\n"
            f"Strength: {rec.get('strength', 'unspecified')}\n\n"
            "Extract the clinical decision criteria as JSON."
        )

        result = run_consensus(
            system_prompt=_SYSTEM_PROMPT,
            user_msg=user_msg,
            parse_fn=_parse_criteria_response,
            fail_verdict=None,
            max_tokens=800,
        )

        if result.verdict is None:
            logger.info("No criteria extracted for rec %s", rec["id"])
            return None

        criteria = result.verdict
        return self._write_rule(guideline_id, rec, criteria)

    def _write_rule(
        self,
        guideline_id: str,
        rec: dict[str, Any],
        criteria: dict[str, list[str]],
    ) -> str:
        """Write AppropriatenessRule, CriteriaGroups, and ReviewTask to Neo4j.

        Args:
            guideline_id: Parent guideline ID.
            rec: Recommendation record dict.
            criteria: Parsed ``{present, absent}`` criteria dict.

        Returns:
            The new rule node ID.
        """
        rule_id = f"rule:{rec['id']}:{str(uuid.uuid4())[:8]}"
        task_id = str(uuid.uuid4())

        with self._driver.session() as session:
            session.run(
                _UPSERT_RULE,
                recommendation_id=rec["id"],
                rule_id=rule_id,
                name=f"Rule: {(rec.get('title') or '')[:80]}",
                strength=rec.get("strength", "unspecified"),
            )
            self._write_criteria_group(
                session, rule_id, criteria.get("present", []), "ALL", "PRESENT"
            )
            self._write_criteria_group(
                session, rule_id, criteria.get("absent", []), "ANY", "ABSENT"
            )
            session.run(
                _CREATE_REVIEW_TASK,
                task_id=task_id,
                rule_id=rule_id,
                guideline_id=guideline_id,
            )
        return rule_id

    def _write_criteria_group(
        self,
        session,
        rule_id: str,
        terms: list[str],
        group_type: str,
        predicate: str,
    ) -> None:
        """Write a CriteriaGroup and link it to SNOMED concept nodes.

        Terms without a SNOMED match are skipped silently.
        """
        if not terms:
            return
        group_id = f"{rule_id}:{predicate}"
        session.run(
            _UPSERT_CRITERIA_GROUP,
            rule_id=rule_id,
            group_id=group_id,
            group_type=group_type,
        )
        for term in terms:
            snomed = _snomed_lookup_sync(session, term)
            if not snomed:
                continue
            session.run(
                _UPSERT_CRITERIA_EDGE,
                group_id=group_id,
                concept_id=snomed["concept_id"],
                predicate=predicate,
            )


def _snomed_lookup_sync(session, term: str) -> dict[str, str] | None:
    """Synchronous SNOMED lookup against the knowledge graph."""
    cypher = (
        "CALL db.index.fulltext.queryNodes('concept_text_index', $term) "
        "YIELD node, score "
        "WHERE score > 0.5 "
        "RETURN node.conceptId AS conceptId, node.term AS term "
        "ORDER BY score DESC LIMIT 1"
    )
    try:
        result = session.run(cypher, term=term)
        record = result.single()
        if not record:
            return None
        return {"concept_id": str(record["conceptId"]), "preferred_term": record["term"]}
    except Exception as exc:
        logger.debug("Knowledge graph SNOMED lookup failed for %r: %s", term, exc)
        return None
