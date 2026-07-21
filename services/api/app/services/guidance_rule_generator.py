"""LLM-based AppropriatenessRule generator with HITL gate.

Atlas trace:
  DO: DO-5B320DDC
  DI: DI-69C29EEF
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5B320DDC")

Pipeline
--------
For each normative Recommendation linked to the Guideline:

1. **guidance_rule_extraction** LangGraph subgraph (libs/pipeline_graph):
   - Loads the PromptConfig from Neo4j (per-guideline lookup, editable via
     /admin/prompts)
   - Calls the dual-model consensus pipeline (Haiku + GPT-5-mini, Sonnet
     arbitration)
   - Calls ``GET /terminology/search`` (Terminology API) with semantic_tag
     filtering to resolve each plain-text criterion and the recommended action
     to a SNOMED concept ID

2. **_write_rule** (this module) persists to Neo4j:
   - ``AppropriatenessRule`` (status = pending_review)
   - One ``CriteriaGroup`` node per ``criteria_groups`` entry with
     ``type = ANY | ALL | NOT`` and HAS_CRITERIA edges to SNOMED concept nodes
   - ``ActionGroup`` with HAS_ACTION edge to the recommended SNOMED procedure
   - ``GuidanceReviewTask`` (HITL gate)
   - ``SUPERSEDES`` link to any prior rule for the same verbatim text

CriteriaGroup semantics
-----------------------
- ``type="ALL"``  — ALL criteria must be present in the patient record
- ``type="ANY"``  — AT LEAST ONE criterion must be present
- ``type="NOT"``  — NO criterion may be present (exclusion / contraindication)

The bitmap compiler reads these type values to determine evaluation semantics.

All LLM call sites comply with llm-security.mdc:
  - INJECTION_GUARD prepended (in the subgraph)
  - sanitise_for_prompt() applied (in the subgraph)
  - cap_llm_response() applied (in the subgraph)
  - When extraction fails, a pending_review stub rule is still written so every
    recommendation appears in the HITL queue for manual authoring.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ── AuditEvent write ───────────────────────────────────────────────────────────
# Written for every recommendation processed (pass or fail) so that guidance
# rule generation costs appear in /admin/billing under "Platform spend".
# patient_id is NULL — these are knowledge-graph authoring calls, not patient
# pipeline runs.  The platform-spend query filters on ae.patient_id IS NULL.
_UPSERT_GUIDANCE_AUDIT_EVENT = """
MERGE (ae:AuditEvent {id: $id})
SET ae += $props,
    ae.created_at = datetime()
"""

# ── Cypher queries ─────────────────────────────────────────────────────────────

_FETCH_RECOMMENDATIONS = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE coalesce(r.isNormative, false) = true
OPTIONAL MATCH (r)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (r)-[:HAS_RULE]->(existing:AppropriatenessRule)
WITH r, ch, count(existing) AS rule_count
RETURN r.id          AS id,
       r.verbatim    AS verbatim,
       r.title       AS title,
       r.urgency     AS urgency,
       r.strength    AS strength,
       r.sectionTitle AS section_title,
       ch.title      AS chapter_title,
       ch.order      AS chapter_order,
       rule_count > 0 AS has_rule
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
    rule.compileScopeType  = 'guideline',
    rule.compileScopeId    = $compile_scope_id,
    rule.schemaVersion     = $schema_version,
    rule.logicJson         = $logic_json,
    rule.rawLogicJson      = $raw_logic_json,
    rule.verifierJson      = $verifier_json,
    rule.actionJson        = $action_json,
    rule.createdAt         = datetime()
ON MATCH SET
    rule.compileScopeType  = 'guideline',
    rule.compileScopeId    = $compile_scope_id,
    rule.schemaVersion     = $schema_version,
    rule.logicJson         = $logic_json,
    rule.rawLogicJson      = $raw_logic_json,
    rule.verifierJson      = $verifier_json,
    rule.actionJson        = $action_json,
    rule.updatedAt         = datetime()
MERGE (rec)-[:HAS_RULE]->(rule)
RETURN rule.id AS id
"""

# SCHEMA UNIFICATION (DI-LEO-AI-528):
# Earlier versions of this generator wrote criteria / action / applies_to
# concepts as the legacy parallel label `(:SnomedConcept {conceptId})`,
# which sat alongside the canonical SNOMED loader's `(:Concept {id})` and
# caused two bugs:
#   1. `_VERIFY_CONCEPTS` in services/api/app/services/guidance_rule_edit.py
#      had to OR-match both labels (the dual-graph fallback documented in
#      DI-LEO-AI-508) -- a band-aid for a schema split.
#   2. `_closure_ids` in services/terminology_api/app/services/
#      guideline_compiler.py walked IS_A on `:SnomedConcept`, which the
#      generator NEVER wrote -- so descendant expansion silently fell back
#      to exact-match only for every guidance-only concept.
# We now write the canonical label + property names (`id`, `preferred_term`,
# `semantic_tag`) so both bugs disappear at the source. Existing data is
# rewired by scripts/migrations/2026_link_or_delete_orphan_snomed_concepts.py
# (idempotent; safe to re-run; never touches patient :SnomedConcept nodes
# connected via :DOCUMENTS).
# distanceChild=1 means the bitmap compiler will also match any SNOMED child
# concepts (one hop via IS_A) -- e.g. a rule for "haematuria" will fire even
# when the patient record contains a more specific haematuria subtype.
_UPSERT_CONCEPT_AND_CRITERIA = """
MATCH (grp:CriteriaGroup {id: $group_id})
MERGE (concept:Concept {id: $concept_id})
ON CREATE SET
    concept.preferred_term = $preferred_term,
    concept.semantic_tag   = $semantic_tag,
    concept.source         = 'guidance_rule_extraction',
    concept.createdAt      = datetime()
ON MATCH SET
    concept.preferred_term = coalesce($preferred_term, concept.preferred_term)
MERGE (grp)-[e:HAS_CRITERIA]->(concept)
ON CREATE SET
    e.predicate      = $predicate,
    e.distanceChild  = $distance_child,
    e.distanceParent = $distance_parent,
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
# ha.priority maps to "2ww" | "urgent" | "routine" — matches HCCP-Agents convention.
# ha.dueDays gives the maximum calendar days to complete the action (14 for 2WW, etc.)
_UPSERT_ACTION_GROUP = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
MERGE (ag:ActionGroup {id: $group_id})
ON CREATE SET
    ag.type      = 'RECOMMENDED',
    ag.createdAt = datetime()
MERGE (rule)-[:HAS_ACTION_GROUP]->(ag)
RETURN ag.id AS id
"""

# Action concepts now write the canonical (:Concept {id}) without the
# legacy :Procedure sub-label. The bitmap compiler binds action targets
# unlabeled (the HAS_ACTION relationship is the constraint -- see
# guideline_compiler._FETCH_ACTIVE_RULES), so dropping :Procedure has no
# read-side impact and removes one more pollution path on the canonical
# terminology graph (DI-LEO-AI-528).
_UPSERT_ACTION_CONCEPT = """
MATCH (ag:ActionGroup {id: $group_id})
MERGE (proc:Concept {id: $concept_id})
ON CREATE SET
    proc.preferred_term = $preferred_term,
    proc.semantic_tag   = 'procedure',
    proc.source         = 'guidance_rule_extraction',
    proc.createdAt      = datetime()
ON MATCH SET
    proc.preferred_term = coalesce($preferred_term, proc.preferred_term)
MERGE (ag)-[ha:HAS_ACTION]->(proc)
ON CREATE SET
    ha.rawTerm  = $raw_term,
    ha.priority = $priority,
    ha.dueDays  = $due_days,
    ha.strength = $strength
ON MATCH SET
    ha.priority = $priority,
    ha.dueDays  = $due_days,
    ha.strength = $strength
"""

_UPSERT_APPLIES_TO = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
MERGE (concept:Concept {id: $concept_id})
ON CREATE SET
    concept.preferred_term = $preferred_term,
    concept.semantic_tag   = $semantic_tag,
    concept.source         = 'guidance_rule_extraction',
    concept.createdAt      = datetime()
ON MATCH SET
    concept.preferred_term = coalesce($preferred_term, concept.preferred_term)
MERGE (rule)-[at:APPLIES_TO {conceptId: $concept_id, rawTerm: $raw_term}]->(concept)
ON CREATE SET
    at.operator  = $operator,
    at.value     = $value,
    at.unit      = $unit
ON MATCH SET
    at.operator  = $operator,
    at.value     = $value,
    at.unit      = $unit
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


# ── Urgency → clinical priority mapping ────────────────────────────────────────

_URGENCY_TO_PRIORITY: dict[str, dict] = {
    "urgent_2w": {"priority": "2ww", "due_days": 14},
    "very_urgent_48h": {"priority": "urgent", "due_days": 2},
    "immediate": {"priority": "urgent", "due_days": 1},
    "urgent_1w": {"priority": "urgent", "due_days": 7},
    "routine": {"priority": "routine", "due_days": None},
}

# Default SNOMED closure distances used when writing HAS_CRITERIA edges.
#
# distanceChild controls how many IS_A hops DOWN the SNOMED hierarchy the
# bitmap compiler will expand a criterion concept.  GP coding software tends
# to land on parent/intermediate concepts (e.g. "Haemoptysis (finding)") while
# SNOMED has 3–5 levels of descendant specificity beneath them.  Setting this
# to 3 means a rule coded to "Haemoptysis" will also fire for any SNOMED
# descendant within 3 IS_A hops — catching the specific subtypes a coder
# might select without missing the rule entirely.
#
# distanceParent controls upward (ancestor) expansion.  Kept at 0 — expanding
# upward makes rules too broad (e.g. a rule for "haematuria" would also fire
# for any other child of "Abnormal urinary finding").
_DEFAULT_DISTANCE_CHILD = 3
_DEFAULT_DISTANCE_PARENT = 0


def _urgency_to_priority(urgency: str | None) -> dict:
    """Map a Recommendation.urgency value to bitmap action priority metadata."""
    return _URGENCY_TO_PRIORITY.get(
        urgency or "routine", {"priority": "routine", "due_days": None}
    )


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
            logger.error(
                "CRITICAL: guidance_rule_extraction subgraph could not be loaded — "
                "rule generation is DISABLED until this is fixed. "
                "No rules will be written for any recommendation. Error: %s",
                exc,
                exc_info=True,
            )
            self._subgraph = None

    def generate_rules_for_guideline(
        self,
        guideline_id: str,
        *,
        only_without_rules: bool = False,
        recommendation_ids: list[str] | None = None,
    ) -> list[str]:
        """Generate rule candidates for normative recommendations.

        Args:
            guideline_id: Knowledge-graph Guideline node ID (e.g. ``NG12``).
            only_without_rules: When true, skip recommendations that already
                have any AppropriatenessRule linked.
            recommendation_ids: Optional allow-list of recommendation node ids.

        Returns:
            List of generated rule IDs (all with status ``pending_review``).
        """
        recs = self._fetch_recommendations(guideline_id)
        if only_without_rules:
            recs = [rec for rec in recs if not rec.get("has_rule")]
        if recommendation_ids:
            allowed = {str(rid) for rid in recommendation_ids}
            recs = [rec for rec in recs if str(rec.get("id") or "") in allowed]
        generated: list[str] = []
        for rec in recs:
            rule_id = self._generate_one(guideline_id, rec)
            if rule_id:
                generated.append(rule_id)
        logger.info(
            "Generated or stubbed %d/%d rules for guideline %s",
            len(generated),
            len(recs),
            guideline_id,
        )
        return generated

    def _fetch_recommendations(self, guideline_id: str) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            result = session.run(_FETCH_RECOMMENDATIONS, guideline_id=guideline_id)
            return [dict(r) for r in result]

    def _generate_one(self, guideline_id: str, rec: dict[str, Any]) -> str | None:
        """Run the extraction subgraph for a single recommendation.

        Returns the rule ID on success or stub write. Returns None only when
        the recommendation has no verbatim text to extract from.
        """
        verbatim = rec.get("verbatim") or rec.get("title") or ""
        if not verbatim.strip():
            return None

        from libs.guidance.recommendation_triage import triage_recommendation

        triage = triage_recommendation(verbatim)
        if triage == "no_rule":
            logger.info(
                "Recommendation %s triaged no_rule -- stubbing without LLM extract",
                rec.get("id"),
            )
            return self._write_generation_stub(
                guideline_id,
                rec,
                outcome="no_rule_expected",
                errors=["triage:no_rule"],
                coded={
                    "no_rule_expected": True,
                    "reason": "triaged_information_or_advice_only",
                    "triage": triage,
                },
            )

        if self._subgraph is None:
            logger.error(
                "Cannot extract rule for recommendation %s — "
                "guidance_rule_extraction subgraph is unavailable. "
                "Fix the load error above and restart the service.",
                rec.get("id"),
            )
            return self._write_generation_stub(
                guideline_id,
                rec,
                outcome="subgraph_unavailable",
                errors=["guidance_rule_extraction subgraph unavailable"],
            )

        import time as _time

        t0 = _time.monotonic()

        result = self._subgraph.invoke(
            {
                "recommendation": rec,
                "guideline_id": guideline_id,
            }
        )
        duration_ms = int((_time.monotonic() - t0) * 1000)
        raw = result.get("raw_criteria")
        coded = result.get("coded_criteria")
        llm_tokens: dict[str, int] = result.get("llm_tokens") or {}

        _CRITICAL_KEYWORDS = (
            "prompt_missing",
            "extraction_blocked",
            "snomed_coding_error",
            "llm_error",
        )
        errors_out = result.get("errors") or []
        for err in errors_out:
            if any(kw in err for kw in _CRITICAL_KEYWORDS):
                logger.error(
                    "Rule extraction pipeline FAILURE for %s: %s",
                    rec.get("id"),
                    err,
                )
            elif "terminology_api_unavailable" in err:
                logger.error(
                    "Rule extraction TERMINOLOGY FAILURE for %s: %s",
                    rec.get("id"),
                    err,
                )
            else:
                logger.warning(
                    "Rule extraction warning for %s: %s",
                    rec.get("id"),
                    err,
                )

        if coded is None:
            logger.error(
                "Rule extraction returned no coded_criteria for recommendation %s — "
                "writing pending_review stub for manual authoring. Errors: %s",
                rec["id"],
                errors_out,
            )
            self._write_guidance_audit_event(
                rec=rec,
                guideline_id=guideline_id,
                status="failed",
                llm_tokens=llm_tokens,
                duration_ms=duration_ms,
                errors=errors_out,
            )
            return self._write_generation_stub(
                guideline_id,
                rec,
                outcome="extraction_failed",
                errors=errors_out,
                raw=raw,
            )

        if bool(coded.get("no_rule_expected")):
            logger.info(
                "Recommendation %s marked no_rule_expected (%s) — "
                "writing stub for reviewer confirmation.",
                rec["id"],
                coded.get("reason") or "non_codable_service_recommendation",
            )
            self._write_guidance_audit_event(
                rec=rec,
                guideline_id=guideline_id,
                status="skipped_non_codable",
                llm_tokens=llm_tokens,
                duration_ms=duration_ms,
                errors=errors_out,
            )
            reason = str(coded.get("reason") or "non_codable_service_recommendation")
            return self._write_generation_stub(
                guideline_id,
                rec,
                outcome="no_rule_expected",
                errors=[f"no_rule_expected:{reason}", *errors_out],
                raw=raw,
                coded=coded,
            )

        if any("terminology_api_unavailable" in e for e in errors_out):
            logger.error(
                "Rule for recommendation %s has terminology gaps — "
                "writing partial rule for manual review.",
                rec["id"],
            )
            coded = {**coded, "needs_human_review": True}
            rule_id = self._write_rule(guideline_id, rec, raw, coded, errors=errors_out)
            self._write_guidance_audit_event(
                rec=rec,
                guideline_id=guideline_id,
                status="terminology_failed",
                llm_tokens=llm_tokens,
                duration_ms=duration_ms,
                errors=errors_out,
                rule_id=rule_id,
            )
            return rule_id

        rule_id = self._write_rule(guideline_id, rec, raw, coded, errors=errors_out)
        status = (
            "partial" if bool((coded or {}).get("needs_human_review")) else "success"
        )
        self._write_guidance_audit_event(
            rec=rec,
            guideline_id=guideline_id,
            status=status,
            llm_tokens=llm_tokens,
            duration_ms=duration_ms,
            errors=errors_out,
            rule_id=rule_id,
        )
        return rule_id

    @staticmethod
    def _resolve_actions(coded: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the recommended actions for a rule as a list.

        Prefers ``coded["actions"]`` (the multi-action shape). Falls back
        to a 1-item list from the legacy singular ``coded["action"]`` so
        this generator keeps working unchanged until the extraction
        pipeline (Phase 6) emits ``actions`` directly.
        """
        actions = coded.get("actions")
        if isinstance(actions, list) and actions:
            return actions
        legacy = coded.get("action")
        return [legacy] if legacy else []

    def _empty_logic_tree(
        self, rec: dict[str, Any], coded: dict[str, Any] | None = None
    ) -> dict:
        """Minimal v2 tree so failed extractions still open in the rule editor."""
        label = str(
            (coded or {}).get("name")
            or rec.get("name")
            or rec.get("title")
            or rec.get("recommendation_text", "")[:120]
        )
        return {
            "kind": "AND",
            "label": label,
            "children": [],
        }

    def _write_generation_stub(
        self,
        guideline_id: str,
        rec: dict[str, Any],
        *,
        outcome: str,
        errors: list[str],
        raw: dict[str, Any] | None = None,
        coded: dict[str, Any] | None = None,
    ) -> str:
        """Write a pending_review placeholder so every rec appears in HITL."""
        rule_id = f"rule:{rec['id']}:{str(uuid.uuid4())[:8]}"
        task_id = str(uuid.uuid4())
        logic_tree = self._empty_logic_tree(rec, coded)
        raw_tree = (raw or {}).get("logic_tree")
        verifier: dict[str, Any] = {
            "generation_outcome": outcome,
            "needs_human_review": True,
            "errors": errors[:20],
        }
        if coded:
            verifier["partial_coded"] = {
                k: coded[k]
                for k in (
                    "name",
                    "reason",
                    "no_rule_expected",
                    "present_criteria",
                    "absent_criteria",
                )
                if k in coded
            }
        title = (rec.get("title") or rec.get("recommendation_text") or "")[:80]
        with self._driver.session() as session:
            session.run(
                _UPSERT_RULE,
                recommendation_id=rec["id"],
                rule_id=rule_id,
                name=f"Rule: {title}",
                strength=rec.get("strength", "unspecified"),
                compile_scope_id=guideline_id,
                schema_version=2,
                logic_json=json.dumps(logic_tree),
                raw_logic_json=(json.dumps(raw_tree) if raw_tree is not None else None),
                verifier_json=json.dumps(verifier),
                action_json=None,
            )
            session.run(
                _CREATE_REVIEW_TASK,
                task_id=task_id,
                rule_id=rule_id,
                guideline_id=guideline_id,
            )
            session.run(
                _LINK_SUPERSEDES,
                rule_id=rule_id,
                guideline_id=guideline_id,
                verbatim=rec.get("verbatim") or rec.get("title") or "",
            )
        logger.info(
            "Wrote generation stub %s for recommendation %s (outcome=%s)",
            rule_id,
            rec["id"],
            outcome,
        )
        return rule_id

    # ── Neo4j write ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_verifier_payload(
        coded: dict[str, Any], errors: list[str] | None = None
    ) -> dict[str, Any] | None:
        """Merge the LLM verifier verdict with pipeline-level review signals.

        ``coded["verifier"]`` is the raw code-verifier LLM output (only
        ``overall_status`` / ``leaf_decisions`` / ``action_decision`` --
        see guidance_rule_code_verifier_output_schema.py). It never carries
        ``needs_human_review``. Writing it to Neo4j unmerged, as this method
        used to do, silently dropped every ``needs_human_review`` /
        ``hitl_terms`` flag that assemble_result() set (including the
        sex-constraint safety check), so the UI's "Needs review" chip never
        lit up for those rules even though the pipeline had already flagged
        them for a reviewer.
        """
        verifier = dict(coded.get("verifier") or {})
        needs_review = bool(coded.get("needs_human_review")) or bool(
            coded.get("hitl_terms")
        )
        if not verifier and not needs_review and not errors:
            return None
        if needs_review:
            verifier["needs_human_review"] = True
        if coded.get("hitl_terms"):
            verifier["hitl_terms"] = coded["hitl_terms"]
        if errors:
            verifier["errors"] = list(errors)[:20]
        return verifier

    def _write_rule(
        self,
        guideline_id: str,
        rec: dict[str, Any],
        raw: dict[str, Any] | None,
        coded: dict[str, Any],
        *,
        errors: list[str] | None = None,
    ) -> str:
        """Write AppropriatenessRule, CriteriaGroups, ActionGroup, ReviewTask.

        One CriteriaGroup node is written per entry in ``coded["criteria_groups"]``,
        with ``type`` set to the group mode (ANY / ALL / NOT).  Only criteria with
        a resolved ``snomed_concept_id`` are written to bitmap-eligible HAS_CRITERIA
        edges; unresolved terms are skipped with a debug log.
        """
        rule_id = f"rule:{rec['id']}:{str(uuid.uuid4())[:8]}"
        task_id = str(uuid.uuid4())
        verbatim = rec.get("verbatim") or rec.get("title") or ""

        urgency = rec.get("urgency") or "routine"
        priority_meta = _urgency_to_priority(urgency)
        actions = self._resolve_actions(coded)
        verifier_payload = self._build_verifier_payload(coded, errors)

        with self._driver.session() as session:
            session.run(
                _UPSERT_RULE,
                recommendation_id=rec["id"],
                rule_id=rule_id,
                name=f"Rule: {(rec.get('title') or '')[:80]}",
                strength=rec.get("strength", "unspecified"),
                compile_scope_id=guideline_id,
                schema_version=int(coded.get("schema_version") or 1),
                logic_json=(
                    json.dumps(coded.get("logic_tree"))
                    if coded.get("logic_tree") is not None
                    else None
                ),
                raw_logic_json=(
                    json.dumps((raw or {}).get("logic_tree"))
                    if (raw or {}).get("logic_tree") is not None
                    else None
                ),
                verifier_json=(
                    json.dumps(verifier_payload)
                    if verifier_payload is not None
                    else None
                ),
                action_json=(json.dumps(actions) if actions else None),
            )

            if int(coded.get("schema_version") or 1) != 2:
                for idx, group in enumerate(coded.get("criteria_groups") or []):
                    mode = str(group.get("mode", "ALL")).upper()
                    predicate = "ABSENT" if mode == "NOT" else "PRESENT"
                    self._write_criteria_group(
                        session,
                        rule_id,
                        group.get("coded_terms") or [],
                        group_type=mode,
                        predicate=predicate,
                        group_suffix=str(idx),
                    )

            self._write_action_groups(session, rule_id, actions, priority_meta)

            if int(coded.get("schema_version") or 1) != 2:
                for constraint in coded.get("applies_to") or []:
                    self._write_applies_to(session, rule_id, constraint)

            session.run(
                _CREATE_REVIEW_TASK,
                task_id=task_id,
                rule_id=rule_id,
                guideline_id=guideline_id,
            )
            session.run(
                _LINK_SUPERSEDES,
                rule_id=rule_id,
                guideline_id=guideline_id,
                verbatim=verbatim,
            )

        return rule_id

    def _write_criteria_group(
        self,
        session,
        rule_id: str,
        criteria: list[dict[str, Any]],
        group_type: str,
        predicate: str,
        group_suffix: str = "",
        distance_child: int = _DEFAULT_DISTANCE_CHILD,
        distance_parent: int = _DEFAULT_DISTANCE_PARENT,
    ) -> None:
        """Write CriteriaGroup and link resolved SNOMED concepts.

        Args:
            group_type: CriteriaGroup.type — "ALL", "ANY", or "NOT".
            predicate:  HAS_CRITERIA edge predicate — "PRESENT" or "ABSENT".
            group_suffix: Appended to the group_id to make each group unique
                when a rule has multiple groups of the same type.
            distance_child: SNOMED IS_A hops downward for bitmap closure.
                A value of 3 means the bitmap compiler will match any descendant
                within 3 IS_A hops (e.g. "haematuria" → subtypes).
            distance_parent: SNOMED IS_A hops upward (default 0 — exact match
                toward parents would be too broad for clinical rules).
        """
        resolved = [c for c in criteria if c.get("snomed_concept_id")]
        if not resolved:
            logger.error(
                "No SNOMED-coded criteria for %s group (suffix=%s) of rule %s — "
                "group NOT written to Neo4j. This likely means the Terminology API was "
                "unavailable during extraction or no SNOMED match was found. "
                "Re-generate this rule when the Terminology API is healthy.",
                predicate,
                group_suffix,
                rule_id,
            )
            return

        group_id = (
            f"{rule_id}:{predicate}:{group_suffix}"
            if group_suffix
            else f"{rule_id}:{predicate}"
        )
        session.run(
            _UPSERT_CRITERIA_GROUP,
            rule_id=rule_id,
            group_id=group_id,
            group_type=group_type,
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
                distance_child=distance_child,
                distance_parent=distance_parent,
            )

    def _write_applies_to(
        self,
        session,
        rule_id: str,
        constraint: dict[str, Any],
    ) -> None:
        """Write an APPLIES_TO edge from the rule to a demographic SNOMED concept.

        Used for continuous-value criteria such as age that cannot be represented
        as discrete SNOMED bitmap bits.  The ``operator``, ``value``, and ``unit``
        properties on the edge are used by the bitmap evaluator at runtime to
        compare against the patient's actual demographic values.

        Args:
            constraint: ``AppliesToConstraint`` dict from the extraction subgraph.
        """
        concept_id = constraint.get("concept_id")
        if not concept_id:
            logger.debug(
                "APPLIES_TO constraint has no concept_id — skipping: %s", constraint
            )
            return
        session.run(
            _UPSERT_APPLIES_TO,
            rule_id=rule_id,
            concept_id=concept_id,
            preferred_term=constraint.get("preferred_term", ""),
            semantic_tag=constraint.get("semantic_tag", ""),
            raw_term=constraint.get("raw_term", ""),
            operator=constraint.get("operator", ">="),
            value=constraint.get("value"),
            unit=constraint.get("unit"),
        )
        logger.debug(
            "Wrote APPLIES_TO: rule=%s concept=%s %s %s %s",
            rule_id,
            concept_id,
            constraint.get("operator"),
            constraint.get("value"),
            constraint.get("unit"),
        )

    def _write_action_groups(
        self,
        session,
        rule_id: str,
        actions: list[dict[str, Any]],
        priority_meta: dict[str, Any] | None = None,
    ) -> None:
        """Write one HAS_ACTION edge per recommended action.

        All actions for a rule share one ``ActionGroup`` -- the
        ``(ActionGroup)-[:HAS_ACTION]->(Concept)`` pattern already supports
        multiple distinct edges from one ActionGroup, so this is a loop
        over the existing per-action MERGE, not a schema change. Actions
        with no resolved SNOMED code are skipped with an error log (same
        conservative-fail behaviour as the previous singular-action path).
        """
        for action in actions or []:
            if action and action.get("snomed_concept_id"):
                self._write_action_group(session, rule_id, action, priority_meta)
            elif action:
                logger.error(
                    "Action %r for rule %s has no SNOMED code -- action group NOT written. "
                    "HCCP-Agents will receive a rule match with no recommended procedure. "
                    "This likely means the Terminology API was unavailable during extraction. "
                    "Re-generate this rule when the Terminology API is healthy.",
                    action.get("term"),
                    rule_id,
                )

    def _write_action_group(
        self,
        session,
        rule_id: str,
        action: dict[str, Any],
        priority_meta: dict[str, Any] | None = None,
    ) -> None:
        """Write ActionGroup linked to the recommended SNOMED procedure concept.

        Args:
            priority_meta: Dict with ``priority`` (``"2ww"`` | ``"urgent"`` |
                ``"routine"``) and ``due_days`` (int or None) derived from the
                Recommendation's urgency field.  Stored on the HAS_ACTION edge so
                the bitmap evaluator can surface it without re-querying Neo4j.
        """
        if priority_meta is None:
            priority_meta = {"priority": "routine", "due_days": None}
        group_id = f"{rule_id}:ACTION"
        session.run(
            _UPSERT_ACTION_GROUP,
            rule_id=rule_id,
            group_id=group_id,
        )
        session.run(
            _UPSERT_ACTION_CONCEPT,
            group_id=group_id,
            concept_id=action["snomed_concept_id"],
            preferred_term=action["preferred_term"],
            raw_term=action["term"],
            priority=priority_meta["priority"],
            due_days=priority_meta["due_days"],
            strength=action.get("strength") or "unspecified",
        )

    # ── Billing audit ───────────────────────────────────────────────────────────

    def _write_guidance_audit_event(
        self,
        *,
        rec: dict[str, Any],
        guideline_id: str,
        status: str,
        llm_tokens: dict[str, int],
        duration_ms: int,
        errors: list[str],
        rule_id: str | None = None,
    ) -> None:
        """Write an AuditEvent node to Neo4j for /admin/billing platform-spend.

        ``patient_id`` is intentionally absent (NULL) so that the platform-spend
        query (which filters on ``ae.patient_id IS NULL``) picks these up while
        they are excluded from per-patient billing aggregations.

        Token counts cover ALL LLM calls in the consensus run for this
        recommendation (small model A + small model B + optional Sonnet
        arbitrator).  Cost is computed from the environment's pricing env-vars
        so the billing page can display the real USD figure.
        """
        try:
            from libs.llm_usage import LLMUsage, LLMCostConfig

            usage = LLMUsage(
                input_tokens=int(llm_tokens.get("input_tokens", 0)),
                output_tokens=int(llm_tokens.get("output_tokens", 0)),
                cached_input_tokens=int(llm_tokens.get("cached_input_tokens", 0)),
                llm_calls=int(llm_tokens.get("llm_calls", 0)),
            )
            try:
                cost_cfg = LLMCostConfig.from_env()
                cost_usd = usage.cost_usd(cost_cfg)
            except Exception:
                cost_usd = 0.0

            audit_id = f"audit-guidance-{rec.get('id', uuid.uuid4())}"
            props = {
                # DI-LEO-AI-518: align with the unified AuditEvent wire
                # format so guidance rule generation costs aggregate
                # alongside SBAR / coding / episode-engine spend in
                # /admin/billing without UI changes. The legacy
                # ``GuidanceRuleExtraction`` value is preserved as a
                # ``subtype`` discriminator.
                "type": "PipelineRun",
                "subtype": "guidance_rule_extraction",
                "plan_definition_id": "guidance_rule_extraction",
                "event_type": "guidance_rule_extraction",
                "extraction_prompt_name": "guidance_rule_extraction",
                "extraction_prompt_version": 1,
                "extraction_provider": "bedrock",
                "extraction_model_tier": "small",
                "guideline_id": guideline_id,
                "recommendation_id": rec.get("id", ""),
                "rule_id": rule_id or "",
                "status": status,
                "total_duration_ms": duration_ms,
                "llm_input_tokens": usage.input_tokens,
                "llm_output_tokens": usage.output_tokens,
                "llm_cached_tokens": usage.cached_input_tokens,
                "llm_calls": usage.llm_calls,
                "llm_cost_usd": round(cost_usd, 6),
                "error_count": len(errors),
                "errors": str(errors[:10]),
                # patient_id intentionally omitted -- platform spend, not patient spend
            }
            with self._driver.session() as session:
                session.run(_UPSERT_GUIDANCE_AUDIT_EVENT, id=audit_id, props=props)
            logger.debug(
                "AuditEvent written for %s: status=%s tokens=%d+%d cost=$%.4f",
                rec.get("id"),
                status,
                usage.input_tokens,
                usage.output_tokens,
                cost_usd,
            )
        except Exception as exc:
            # Billing is non-critical — log and continue; never block rule generation.
            logger.warning(
                "Failed to write guidance AuditEvent for %s: %s",
                rec.get("id"),
                exc,
            )
