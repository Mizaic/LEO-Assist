"""LLM-based AppropriatenessRule generator with HITL gate.

Pipeline
--------
For each normative Recommendation linked to the Guideline:

1. **guidance_rule_extraction** LangGraph subgraph (libs/pipeline_graph):
   - Loads the ``guidance_rule_extraction`` PromptConfig from Neo4j (editable
     at runtime via /admin/prompts)
   - Calls the dual-model consensus pipeline (Haiku + GPT-5-mini, Sonnet
     arbitration)
   - Calls ``GET /terminology/search`` (Terminology API) with semantic_tag
     filtering to resolve each plain-text criterion and the recommended action
     to a SNOMED concept ID

2. **_write_rule** (this module) persists to Neo4j:
   - ``AppropriatenessRule`` (status = pending_review)
   - ``CriteriaGroup`` PRESENT (ALL) and ABSENT (ANY) with HAS_CRITERIA edges
     to SNOMED concept nodes — these are what the bitmap compiler reads
   - ``ActionGroup`` with HAS_ACTION edge to the recommended SNOMED procedure
   - ``GuidanceReviewTask`` (HITL gate)
   - ``SUPERSEDES`` link to any prior rule for the same verbatim text

SNOMED coding
-------------
The Terminology API (``GET /terminology/search``) is used with semantic_tag
filters:
- Criteria (present/absent): finding, disorder, observable entity, situation
- Action: procedure

This replaces the previous approach of querying the knowledge graph's full-text
index directly (``concept_text_index``), which was unfiltered and could return
concepts of the wrong clinical type.

Concept nodes are MERGED into Neo4j during the write step using the
``snomed_concept_id`` string returned by the Terminology API.  The bitmap
compiler reads ``concept.conceptId`` — the same string — so the link between
the rule criteria and the bitmap integer IDs is consistent.

All LLM call sites comply with llm-security.mdc:
  - INJECTION_GUARD prepended (in the subgraph)
  - sanitise_for_prompt() applied (in the subgraph)
  - cap_llm_response() applied (in the subgraph)
  - fail_verdict = None (conservative — no rule written on LLM failure)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ── Cypher queries ─────────────────────────────────────────────────────────────

_FETCH_RECOMMENDATIONS = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE coalesce(r.isNormative, false) = true
OPTIONAL MATCH (r)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
RETURN r.id          AS id,
       r.verbatim    AS verbatim,
       r.title       AS title,
       r.urgency     AS urgency,
       r.strength    AS strength,
       r.sectionTitle AS section_title,
       ch.title      AS chapter_title,
       ch.order      AS chapter_order
"""

_UPSERT_RULE = """
MATCH (rec:Recommendation {id: $recommendation_id})
MERGE (rule:AppropriatenessRule {id: $rule_id})
ON CREATE SET
    rule.name              = $name,
    rule.strength          = $strength,
    rule.status            = 'pending_review',
    rule.generatedBy       = 'llm_consensus',
    rule.promptConfigName  = 'guidance_rule_extraction',
    rule.promptConfigVer   = 1,
    rule.createdAt         = datetime()
ON MATCH SET
    rule.updatedAt         = datetime()
MERGE (rec)-[:HAS_RULE]->(rule)
RETURN rule.id AS id
"""

# Merge the SNOMED concept node (creates it if not yet in the graph) then link
# to the criteria group.  Using MERGE on conceptId ensures idempotency.
_UPSERT_CONCEPT_AND_CRITERIA = """
MATCH (grp:CriteriaGroup {id: $group_id})
MERGE (concept:SnomedConcept {conceptId: $concept_id})
ON CREATE SET
    concept.term        = $preferred_term,
    concept.semanticTag = $semantic_tag,
    concept.source      = 'guidance_rule_extraction',
    concept.createdAt   = datetime()
ON MATCH SET
    concept.term        = $preferred_term
MERGE (grp)-[e:HAS_CRITERIA]->(concept)
ON CREATE SET
    e.predicate      = $predicate,
    e.distanceChild  = 0,
    e.distanceParent = 0,
    e.rawTerm        = $raw_term
"""

_UPSERT_CRITERIA_GROUP = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
MERGE (grp:CriteriaGroup {id: $group_id})
ON CREATE SET
    grp.type      = $group_type,
    grp.createdAt = datetime()
MERGE (rule)-[:HAS_CRITERIA_GROUP]->(grp)
RETURN grp.id AS id
"""

# Action: SNOMED procedure concept linked through an ActionGroup
_UPSERT_ACTION_GROUP = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
MERGE (ag:ActionGroup {id: $group_id})
ON CREATE SET
    ag.type      = 'RECOMMENDED',
    ag.createdAt = datetime()
MERGE (rule)-[:HAS_ACTION_GROUP]->(ag)
RETURN ag.id AS id
"""

_UPSERT_ACTION_CONCEPT = """
MATCH (ag:ActionGroup {id: $group_id})
MERGE (proc:SnomedConcept:Procedure {conceptId: $concept_id})
ON CREATE SET
    proc.term        = $preferred_term,
    proc.semanticTag = 'procedure',
    proc.source      = 'guidance_rule_extraction',
    proc.createdAt   = datetime()
ON MATCH SET
    proc.term        = $preferred_term
MERGE (ag)-[ha:HAS_ACTION]->(proc)
ON CREATE SET
    ha.rawTerm = $raw_term
"""

_CREATE_REVIEW_TASK = """
MERGE (task:GuidanceReviewTask {id: $task_id})
ON CREATE SET
    task.ruleId       = $rule_id,
    task.guidelineId  = $guideline_id,
    task.status       = 'pending',
    task.createdAt    = datetime()
"""

_LINK_SUPERSEDES = """
MATCH (new_rule:AppropriatenessRule {id: $rule_id})
OPTIONAL MATCH (pred:AppropriatenessRule {
    status:                     'superseded',
    supersededByGuidelineId:    $guideline_id,
    previousRecommendationText: $verbatim
})
FOREACH (p IN CASE WHEN pred IS NOT NULL THEN [pred] ELSE [] END |
    MERGE (new_rule)-[:SUPERSEDES]->(p)
)
RETURN new_rule.id AS id
"""


# ── Generator class ────────────────────────────────────────────────────────────

class GuidanceRuleGenerator:
    """Generates AppropriatenessRule candidates from Recommendation nodes.

    Uses the ``guidance_rule_extraction`` LangGraph subgraph which:
    1. Loads the prompt from Neo4j (editable via /admin/prompts)
    2. Runs dual-model consensus LLM extraction
    3. Resolves each term to SNOMED via the Terminology API

    Generated rules are stored with status ``pending_review`` and cannot
    affect patients until a human approves them via the HITL review queue.
    """

    def __init__(self, neo4j_driver) -> None:
        self._driver = neo4j_driver
        # Build the subgraph once — it is stateless and thread-safe
        try:
            from libs.pipeline_graph.registry import get_registry
            self._subgraph = get_registry().build("guidance_rule_extraction")
        except Exception as exc:
            logger.warning(
                "Could not load guidance_rule_extraction subgraph from registry "
                "— will fall back to inline extraction: %s", exc
            )
            self._subgraph = None

    def generate_rules_for_guideline(self, guideline_id: str) -> list[str]:
        """Generate rule candidates for all normative recommendations.

        Args:
            guideline_id: Knowledge-graph Guideline node ID (e.g. ``NG12``).

        Returns:
            List of generated rule IDs (all with status ``pending_review``).
        """
        recs = self._fetch_recommendations(guideline_id)
        generated: list[str] = []
        for rec in recs:
            rule_id = self._generate_one(guideline_id, rec)
            if rule_id:
                generated.append(rule_id)
        logger.info(
            "Generated %d/%d rules for guideline %s",
            len(generated), len(recs), guideline_id,
        )
        return generated

    def _fetch_recommendations(self, guideline_id: str) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            result = session.run(_FETCH_RECOMMENDATIONS, guideline_id=guideline_id)
            return [dict(r) for r in result]

    def _generate_one(self, guideline_id: str, rec: dict[str, Any]) -> str | None:
        """Run the extraction subgraph for a single recommendation.

        Returns the rule ID on success, None on LLM failure or empty criteria.
        """
        verbatim = rec.get("verbatim") or rec.get("title") or ""
        if not verbatim.strip():
            return None

        if self._subgraph is not None:
            result = self._subgraph.invoke({
                "recommendation": rec,
                "guideline_id": guideline_id,
            })
            coded = result.get("coded_criteria")
            if result.get("errors"):
                for err in result["errors"]:
                    logger.warning("Rule extraction error for %s: %s", rec.get("id"), err)
        else:
            # Inline fallback: legacy direct consensus call (no Terminology API)
            coded = self._inline_extract(rec)

        if coded is None:
            logger.info("No criteria extracted for recommendation %s", rec["id"])
            return None

        return self._write_rule(guideline_id, rec, coded)

    # ── Inline fallback (used only when the subgraph fails to load) ────────────

    def _inline_extract(self, rec: dict[str, Any]) -> dict | None:
        """Minimal inline extraction without the full subgraph."""
        from libs.llm_client.consensus import run_consensus
        from libs.llm_client.prompt_safety import (
            INJECTION_GUARD,
            cap_llm_response,
            sanitise_for_prompt,
        )
        import json as _json

        system = (
            INJECTION_GUARD
            + "You are a clinical decision-support analyst. "
            "Extract patient criteria from this NICE recommendation as JSON: "
            '{"present": [...], "absent": [...], "action": "..." or null}. '
            "Use plain clinical terms, maximum 5 per list."
        )
        verbatim = rec.get("verbatim") or rec.get("title") or ""
        user_msg = (
            f"Section: {rec.get('section_title', '')}\n"
            f"Recommendation {rec.get('title', '')}: "
            f"{sanitise_for_prompt(verbatim, max_chars=2000)}\n"
            f"Urgency: {rec.get('urgency', 'unspecified')}\n"
            f"Strength: {rec.get('strength', 'unspecified')}\n"
            "Extract JSON criteria."
        )

        def _parse(raw: str) -> dict | None:
            capped = cap_llm_response(raw, max_chars=2000) or ""
            s, e = capped.find("{"), capped.rfind("}") + 1
            if s == -1 or e == 0:
                return None
            try:
                d = _json.loads(capped[s:e])
                return {
                    "present": [str(t) for t in (d.get("present") or [])[:5]],
                    "absent":  [str(t) for t in (d.get("absent")  or [])[:5]],
                    "action":  str(d["action"]) if d.get("action") else None,
                }
            except Exception:
                return None

        result = run_consensus(
            system_prompt=system, user_msg=user_msg,
            parse_fn=_parse, fail_verdict=None, max_tokens=800,
        )
        if result.verdict is None:
            return None
        # Inline fallback does NOT call Terminology API — wrap terms without codes
        raw = result.verdict
        return {
            "present": [{"term": t, "snomed_concept_id": None, "preferred_term": t, "semantic_tag": ""} for t in raw["present"]],
            "absent":  [{"term": t, "snomed_concept_id": None, "preferred_term": t, "semantic_tag": ""} for t in raw["absent"]],
            "action":  {"term": raw["action"], "snomed_concept_id": None, "preferred_term": raw["action"], "semantic_tag": "procedure"} if raw.get("action") else None,
        }

    # ── Neo4j write ────────────────────────────────────────────────────────────

    def _write_rule(
        self,
        guideline_id: str,
        rec: dict[str, Any],
        coded: dict[str, Any],
    ) -> str:
        """Write AppropriatenessRule, CriteriaGroups, ActionGroup, ReviewTask.

        Only criteria with a resolved ``snomed_concept_id`` are written to the
        bitmap-eligible HAS_CRITERIA edges.  Unresolved terms are skipped with a
        debug log — they remain visible in the LLM extraction output stored on
        the rule node but do not participate in bitmap matching.
        """
        rule_id = f"rule:{rec['id']}:{str(uuid.uuid4())[:8]}"
        task_id = str(uuid.uuid4())
        verbatim = rec.get("verbatim") or rec.get("title") or ""

        with self._driver.session() as session:
            # Create the AppropriatenessRule node
            session.run(
                _UPSERT_RULE,
                recommendation_id=rec["id"],
                rule_id=rule_id,
                name=f"Rule: {(rec.get('title') or '')[:80]}",
                strength=rec.get("strength", "unspecified"),
            )

            # PRESENT criteria (ALL must match)
            self._write_criteria_group(
                session, rule_id,
                coded.get("present", []),
                group_type="ALL", predicate="PRESENT",
            )
            # ABSENT criteria (ANY present disqualifies)
            self._write_criteria_group(
                session, rule_id,
                coded.get("absent", []),
                group_type="ANY", predicate="ABSENT",
            )
            # Recommended action (SNOMED procedure)
            action = coded.get("action")
            if action and action.get("snomed_concept_id"):
                self._write_action_group(session, rule_id, action)
            elif action:
                logger.debug(
                    "Action %r for rule %s has no SNOMED code — skipping action group",
                    action.get("term"), rule_id,
                )

            # HITL gate
            session.run(
                _CREATE_REVIEW_TASK,
                task_id=task_id, rule_id=rule_id, guideline_id=guideline_id,
            )
            # Link to superseded predecessor for diff view
            session.run(
                _LINK_SUPERSEDES,
                rule_id=rule_id, guideline_id=guideline_id, verbatim=verbatim,
            )

        return rule_id

    def _write_criteria_group(
        self,
        session,
        rule_id: str,
        criteria: list[dict[str, Any]],
        group_type: str,
        predicate: str,
    ) -> None:
        """Write CriteriaGroup and link resolved SNOMED concepts."""
        # Only include criteria that the Terminology API resolved to a SNOMED code
        resolved = [c for c in criteria if c.get("snomed_concept_id")]
        if not resolved:
            logger.debug(
                "No resolved SNOMED criteria for %s group of rule %s — group not written",
                predicate, rule_id,
            )
            return

        group_id = f"{rule_id}:{predicate}"
        session.run(
            _UPSERT_CRITERIA_GROUP,
            rule_id=rule_id, group_id=group_id, group_type=group_type,
        )
        for criterion in resolved:
            session.run(
                _UPSERT_CONCEPT_AND_CRITERIA,
                group_id=group_id,
                concept_id=criterion["snomed_concept_id"],
                preferred_term=criterion["preferred_term"],
                semantic_tag=criterion.get("semantic_tag", ""),
                predicate=predicate,
                raw_term=criterion["term"],
            )

    def _write_action_group(
        self,
        session,
        rule_id: str,
        action: dict[str, Any],
    ) -> None:
        """Write ActionGroup linked to the recommended SNOMED procedure concept."""
        group_id = f"{rule_id}:ACTION"
        session.run(
            _UPSERT_ACTION_GROUP,
            rule_id=rule_id, group_id=group_id,
        )
        session.run(
            _UPSERT_ACTION_CONCEPT,
            group_id=group_id,
            concept_id=action["snomed_concept_id"],
            preferred_term=action["preferred_term"],
            raw_term=action["term"],
        )
