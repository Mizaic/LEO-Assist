"""Offline compiler: reads active AppropriatenessRules from Neo4j and builds bitmaps.

Atlas trace:
  DO: DO-E74B0605
  DI: DI-5E25E872
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-E74B0605")

The compile step is CPU-bound (pyroaring BitMap construction). It is run via
``asyncio.to_thread()`` so it does not block the async event loop.

Only rules with ``status: active`` are compiled. Rules with
``status: pending_review`` or ``status: rejected`` are silently excluded.

SNOMED hierarchy expansion
--------------------------
Each ``HAS_CRITERIA`` edge stores ``distanceChild`` and ``distanceParent`` hops.
When ``distanceChild > 0`` the compiler expands the criterion to include all
SNOMED descendant concepts within that many IS_A hops.  This means a rule coded
to "haematuria" will also fire when the patient record contains a more specific
child concept such as "microscopic haematuria".

Expansion requires SNOMED IS_A relationships to be present in the same Neo4j
instance.  If they are not, ``_closure_ids`` gracefully falls back to the exact
concept only — the bitmap still works, just without hierarchy widening.

Action metadata
---------------
The compiled rule output includes ``actions``, a list of
``{concept_id, name, strength, priority, due_days}`` dicts -- one per
``HAS_ACTION`` edge (a rule can recommend more than one procedure).
``action`` (singular) is kept as a read-only derived field equal to
``actions[0]`` (or ``None`` when empty) for one release as a back-compat
shim -- removable once ``libs/sbar`` is confirmed migrated to ``actions``.
Action metadata is read directly from the ``HAS_ACTION`` edge properties
written by the rule generator, so no Neo4j re-query is needed at
evaluation time.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from neo4j import GraphDatabase

from libs.lab_results.classifier import (
    LabConfigError,
    convert_value as convert_lab_value,
    get_lab_config,
)
from libs.units.observable_units import (
    UnitConversionError,
    UnknownObservableError,
    canonicalise_value_for_observation,
    is_known_observable,
    resolve_effective_canonical_unit,
)
from services.terminology_api.app.services.bitmap_store import BitmapStore

logger = logging.getLogger(__name__)

ScopeType = Literal["global", "guideline", "domain", "subdomain", "custom"]


@dataclass(frozen=True)
class CompileScope:
    scope_type: ScopeType = "global"
    scope_id: str = "default"

    @classmethod
    def from_values(
        cls,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> "CompileScope":
        st = str(scope_type or "global").strip().lower()
        sid = str(scope_id or "default").strip() or "default"
        if st not in {"global", "guideline", "domain", "subdomain", "custom"}:
            st = "global"
            sid = "default"
        if st == "global" and not sid:
            sid = "default"
        return cls(scope_type=st, scope_id=sid)


@dataclass(frozen=True)
class CompilePolicy:
    mode: Literal["advisory", "strict"] = "advisory"
    allowed_concept_ids: frozenset[str] = frozenset()
    enforce_action_scope: bool = False


# DUAL-GRAPH NOTE (DI-LEO-AI-528):
# Earlier versions of the rule generator wrote criteria / action / applies_to
# concepts as the legacy parallel label `(:SnomedConcept {conceptId})` with
# `term` / `semanticTag` properties. The canonical SNOMED loader writes
# `(:Concept {id})` with `preferred_term` / `fsn` / `semantic_tag`.
# Reads MUST tolerate either shape until the one-shot migration in
# scripts/migrations/2026_link_or_delete_orphan_snomed_concepts.py has run
# in every environment. Two safeguards keep that promise:
#   1. Concept matches are unlabeled -- the relationship type
#      (HAS_CRITERIA, HAS_ACTION, APPLIES_TO) is the only constraint, so
#      both `:Concept` and `:SnomedConcept` bind.
#   2. Property reads use coalesce(concept.id, concept.conceptId) for IDs
#      and coalesce(concept.preferred_term, concept.fsn, concept.term, ...)
#      for display text.
# Action targets used to require `:Procedure` (set by the generator's dual
# label MERGE). The `HAS_ACTION` relationship is itself the constraint --
# unlabeling `proc` lets new canonical writes (no `:Procedure` sub-label)
# bind without changing semantics.
_FETCH_ACTIVE_RULES = """
MATCH (g:Guideline)-[:HAS_RECOMMENDATION]->(rec:Recommendation)
    -[:HAS_RULE]->(rule:AppropriatenessRule {status: 'active'})
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (g)-[:IN_SUBCATEGORY]->(:TaxonomySubcategory)-[:IN_DOMAIN]->(dom:AuditDomain)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp:CriteriaGroup)
OPTIONAL MATCH (grp)-[hc:HAS_CRITERIA]->(concept)
RETURN
    rule.id              AS rule_id,
    rule.name            AS name,
    rule.strength        AS strength,
    coalesce(rule.schemaVersion, 1) AS schema_version,
    rule.logicJson       AS logic_json,
    rule.actionJson      AS action_json,
    rule.investigationPolicy AS investigation_policy,
    g.id                 AS guideline_id,
    g.title              AS guideline_title,
    coalesce(g.publisher, '') AS guideline_publisher,
    coalesce(g.source, '')    AS guideline_source,
    dom.id               AS guideline_domain_id,
    ch.title             AS chapter_title,
    rec.verbatim         AS recommendation_verbatim,
    grp.id               AS group_id,
    coalesce(grp.type, 'ALL') AS group_mode,
    hc.predicate         AS predicate,
    coalesce(concept.id, concept.conceptId)         AS concept_id,
    coalesce(hc.distanceChild,  0) AS distance_child,
    coalesce(hc.distanceParent, 0) AS distance_parent
ORDER BY rule.id, grp.id, coalesce(concept.id, concept.conceptId)
"""

# Separate query for APPLIES_TO demographic constraints -- fetched once per
# compile run and merged into the compiled rules by rule_id. Same dual-graph
# tolerance as _FETCH_ACTIVE_RULES (see DUAL-GRAPH NOTE above).
_FETCH_APPLIES_TO = """
MATCH (rule:AppropriatenessRule {status: 'active'})-[at:APPLIES_TO]->(concept)
OPTIONAL MATCH (:Recommendation)-[:HAS_RULE]->(rule)<-[:HAS_RECOMMENDATION]-(:Guideline)-[:IN_SUBCATEGORY]->(:TaxonomySubcategory)-[:IN_DOMAIN]->(dom:AuditDomain)
RETURN
    rule.id              AS rule_id,
    dom.id               AS guideline_domain_id,
    coalesce(concept.id, concept.conceptId)        AS concept_id,
    coalesce(concept.preferred_term, concept.fsn, concept.term, concept.id, concept.conceptId) AS preferred_term,
    coalesce(concept.semantic_tag, concept.semanticTag) AS semantic_tag,
    at.rawTerm           AS raw_term,
    at.operator          AS operator,
    at.value             AS value,
    at.unit              AS unit
ORDER BY rule.id, coalesce(concept.id, concept.conceptId)
"""

# Separate query for recommended actions (HAS_ACTION edges) -- fetched once
# per compile run and merged into the compiled rules by rule_id, mirroring
# _FETCH_APPLIES_TO above. Kept separate from _FETCH_ACTIVE_RULES so a rule
# with N criteria rows and M action rows does not produce an NxM cross-join.
# Same dual-graph tolerance as _FETCH_ACTIVE_RULES (see DUAL-GRAPH NOTE
# above): `proc` binds unlabeled so both `:Concept` and legacy
# `:SnomedConcept` action targets resolve.
_FETCH_ACTIONS = """
MATCH (rule:AppropriatenessRule {status: 'active'})
    -[:HAS_ACTION_GROUP]->(:ActionGroup)-[ha:HAS_ACTION]->(proc)
RETURN
    rule.id              AS rule_id,
    coalesce(proc.id, proc.conceptId)               AS concept_id,
    coalesce(proc.preferred_term, proc.fsn, proc.term, proc.id, proc.conceptId) AS name,
    ha.strength          AS strength,
    ha.priority          AS priority,
    ha.dueDays           AS due_days,
    coalesce(ha.actionKind, 'snomed_procedure')     AS action_kind,
    ha.actionText        AS action_text
ORDER BY rule.id, coalesce(proc.id, proc.conceptId)
"""


def _kg_driver():
    """Return a synchronous Neo4j driver for the knowledge graph."""
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    return GraphDatabase.driver(uri, auth=(user, password))


class GuidelineCompiler:
    """Compiles active AppropriatenessRules from Neo4j into Redis bitmaps.

    The compiled ruleset is versioned and written to Redis. The active
    version pointer is updated separately via
    :meth:`BitmapStore.set_current_version`.
    """

    _DEFAULT_COMPILE_STATS: dict[str, int] = {
        "rules_seen": 0,
        "rules_included": 0,
        "rules_excluded": 0,
        "policy_violations": 0,
        "out_of_scope_concepts": 0,
        "out_of_scope_actions": 0,
        "cycle_warnings": 0,
    }

    def __init__(self, store: BitmapStore | None = None) -> None:
        self._store = store or BitmapStore()
        # Cache closure results so each (concept_id, d_child, d_parent) triple
        # is only queried once per compilation run.
        self._closure_cache: dict[tuple, list[str]] = {}
        # Always initialise with the full counter shape so callers that invoke
        # _build_ruleset directly (e.g. tests, ad-hoc tooling) don't trip over
        # KeyError when policy filters reject a concept.
        self._compile_stats: dict[str, Any] = dict(self._DEFAULT_COMPILE_STATS)

    async def compile_drafts(
        self,
        version: str,
        rules: list[dict[str, Any]],
        *,
        scope: CompileScope,
        policy_mode: Literal["advisory", "strict"] = "advisory",
        distance_child_override: int | None = None,
        distance_parent_override: int | None = None,
        ttl_seconds: int | None = None,
    ) -> dict:
        """Compile a hand-built list of v2 rules into a sandbox ruleset.

        Used by the rule editor's "Test against library" flow so a reviewer
        can replay saved test patients against an UNSAVED draft of a rule
        without round-tripping through Neo4j.

        SAFETY: Refuses to write to ``scope.scope_type == "global"`` so a
        draft compile can never overwrite the production ruleset. Use a
        ``custom`` scope (e.g. ``CompileScope("custom", "draft-<uuid>")``).
        Caller is responsible for cleaning up the sandbox via
        :meth:`BitmapStore.delete_scope` once the replay completes.

        Each entry in ``rules`` must be a schema v2 rule dict with at
        least ``rule_id``, ``name``, ``strength``, ``guideline_id``,
        ``guideline_title``, ``recommendation_verbatim``, and either a
        parsed ``logic_tree`` dict (the EditableLogicNode payload sent
        from the UI) or a ``logic_json`` string. ``action`` and
        ``applies_to`` are optional.
        """
        if scope.scope_type == "global":
            raise ValueError(
                "compile_drafts refuses to write to the global scope; "
                "use a custom scope so the draft cannot affect production."
            )
        self._closure_cache.clear()
        self._compile_stats = dict(self._DEFAULT_COMPILE_STATS)
        ruleset = await asyncio.to_thread(
            self._compile_drafts_sync,
            rules,
            policy_mode,
            distance_child_override,
            distance_parent_override,
        )
        ruleset["version"] = version
        ruleset["compile_timestamp"] = datetime.now(timezone.utc).isoformat()
        ruleset["scope_type"] = scope.scope_type
        ruleset["scope_id"] = scope.scope_id
        ruleset["policy_mode"] = policy_mode
        ruleset["compile_stats"] = dict(self._compile_stats)
        ruleset["draft"] = True

        self._store.write_ruleset(
            version,
            ruleset,
            scope_type=scope.scope_type,
            scope_id=scope.scope_id,
        )
        self._store.set_current_version(
            version,
            scope_type=scope.scope_type,
            scope_id=scope.scope_id,
        )
        if ttl_seconds and ttl_seconds > 0:
            try:
                self._store.set_scope_ttl(
                    scope.scope_type, scope.scope_id, ttl_seconds=ttl_seconds
                )
            except Exception as exc:
                logger.warning(
                    "compile_drafts: could not set TTL on sandbox scope %s/%s: %s",
                    scope.scope_type,
                    scope.scope_id,
                    exc,
                )
        logger.info(
            "Compiled DRAFT ruleset %s scope=%s/%s: %d/%d rules",
            version,
            scope.scope_type,
            scope.scope_id,
            len(ruleset.get("rules", [])),
            len(rules),
        )
        return {
            "version": version,
            "rule_count": len(ruleset.get("rules", [])),
            "draft_input_count": len(rules),
            "compile_timestamp": ruleset["compile_timestamp"],
            "scope_type": scope.scope_type,
            "scope_id": scope.scope_id,
            "policy_mode": policy_mode,
            "compile_stats": dict(self._compile_stats),
            "draft": True,
        }

    def _compile_drafts_sync(
        self,
        rules: list[dict[str, Any]],
        policy_mode: Literal["advisory", "strict"],
        distance_child_override: int | None,
        distance_parent_override: int | None,
    ) -> dict:
        """CPU-bound sandbox compile -- runs in thread pool.

        Opens its own Neo4j session because the SNOMED IS_A closure
        expansion (see ``_closure_ids``) reads from the knowledge graph.
        Without descendant expansion the bitmap would not match the same
        codes the production evaluator does, so the parity guarantee
        would break.
        """
        policy = CompilePolicy(mode=policy_mode)
        self._compile_stats["rules_seen"] = len(rules)
        compiled_rules: list[dict[str, Any]] = []
        driver = _kg_driver()
        try:
            with driver.session() as session:
                for rule_in in rules:
                    rule_data = self._normalise_draft_rule(rule_in)
                    if rule_data is None:
                        continue
                    compiled = self._compile_schema_v2_rule(
                        rule_data,
                        session,
                        policy=policy,
                        distance_child_override=distance_child_override,
                        distance_parent_override=distance_parent_override,
                    )
                    if compiled is None:
                        continue
                    compiled_rules.append(compiled)
        finally:
            driver.close()
        self._compile_stats["rules_included"] = len(compiled_rules)
        self._compile_stats["rules_excluded"] = max(0, len(rules) - len(compiled_rules))
        self._detect_rule_fired_cycles(compiled_rules)
        return {"rules": compiled_rules}

    @staticmethod
    def _normalise_action_item(item: dict[str, Any]) -> dict[str, Any] | None:
        """Coerce one draft action item into the compiled action shape.

        Accepts either a ``RuleAction``-shaped item (``{criterion: {...},
        strength: ...}``) or a flat legacy action dict (``{snomed_concept_id
        | concept_id, preferred_term | term | name, priority, due_days,
        strength}``). Returns ``None`` when no SNOMED concept id is present.
        """
        criterion = item.get("criterion")
        if not isinstance(criterion, dict):
            criterion = item
        concept_id = (
            item.get("concept_id")
            or criterion.get("snomed_concept_id")
            or criterion.get("concept_id")
        )
        if not concept_id:
            return None
        name = (
            item.get("name")
            or criterion.get("preferred_term")
            or criterion.get("term")
            or criterion.get("name")
        )
        from libs.terminology.local_concepts import validate_action_kind

        action_kind = validate_action_kind(
            item.get("action_kind") or criterion.get("action_kind")
        )
        action_text = item.get("action_text") or criterion.get("action_text")
        return {
            "concept_id": str(concept_id),
            "name": name,
            "strength": item.get("strength")
            or criterion.get("strength")
            or "unspecified",
            "priority": item.get("priority") or criterion.get("priority") or "routine",
            "due_days": item.get("due_days", criterion.get("due_days")),
            "action_kind": action_kind,
            "action_text": action_text,
        }

    @staticmethod
    def _normalise_draft_actions(rule_in: dict[str, Any]) -> list[dict[str, Any]]:
        """Build the draft-compile ``actions`` list from either shape.

        Prefers the new ``rule_in["actions"]`` array; falls back to the
        legacy singular ``action``/``action_concept_id``/``action_name``
        fields so pre-Phase-3 UI builds keep compiling correctly.
        """
        actions_in = rule_in.get("actions")
        if isinstance(actions_in, list) and actions_in:
            normalised = [
                GuidelineCompiler._normalise_action_item(item)
                for item in actions_in
                if isinstance(item, dict)
            ]
            return [a for a in normalised if a]

        legacy_action = rule_in.get("action") or {}
        legacy_item = {
            "concept_id": rule_in.get("action_concept_id"),
            "name": rule_in.get("action_name"),
            "priority": rule_in.get("action_priority"),
            "due_days": rule_in.get("action_due_days"),
            "criterion": legacy_action,
        }
        normalised_legacy = GuidelineCompiler._normalise_action_item(legacy_item)
        return [normalised_legacy] if normalised_legacy else []

    @staticmethod
    def _normalise_draft_rule(rule_in: dict[str, Any]) -> dict[str, Any] | None:
        """Coerce a UI-side draft rule dict into _compile_schema_v2_rule shape."""
        if not isinstance(rule_in, dict):
            logger.warning("compile_drafts: ignoring non-dict rule entry")
            return None
        rule_id = rule_in.get("rule_id") or rule_in.get("id")
        if not rule_id:
            logger.warning("compile_drafts: ignoring rule with no rule_id")
            return None
        logic_tree = rule_in.get("logic_tree") or rule_in.get("logicJson")
        if isinstance(logic_tree, str):
            logic_json = logic_tree
        else:
            logic_json = json.dumps(logic_tree) if logic_tree else None
        if not logic_json:
            logger.warning(
                "compile_drafts: rule %s has no logic_tree/logicJson", rule_id
            )
            return None
        return {
            "rule_id": str(rule_id),
            "name": rule_in.get("name") or "",
            "strength": rule_in.get("strength") or "unspecified",
            "schema_version": 2,
            "logic_json": logic_json,
            "guideline_id": rule_in.get("guideline_id") or "",
            "guideline_title": rule_in.get("guideline_title") or "",
            "guideline_publisher": rule_in.get("guideline_publisher") or "",
            "guideline_source": rule_in.get("guideline_source") or "",
            "guideline_domain_id": rule_in.get("guideline_domain_id"),
            "chapter_title": rule_in.get("chapter_title"),
            "recommendation_verbatim": rule_in.get("recommendation_verbatim")
            or rule_in.get("recommendation_text")
            or "",
            "actions": GuidelineCompiler._normalise_draft_actions(rule_in),
            "action_priority": rule_in.get("action_priority"),
            "action_due_days": rule_in.get("action_due_days"),
            "action_json": rule_in.get("action_json"),
            "applies_to": list(rule_in.get("applies_to") or []),
            "investigation_policy": rule_in.get("investigation_policy")
            or rule_in.get("investigationPolicy"),
        }

    async def compile_and_store(
        self,
        version: str,
        *,
        scope: CompileScope | None = None,
        policy_mode: Literal["advisory", "strict"] = "advisory",
        include_rule_statuses: list[str] | None = None,
        policy_domain_id: str | None = None,
        policy_subdomain_name: str | None = None,
        policy_include_descendants: bool = True,
        policy_depth: int = 3,
        enforce_action_scope: bool = False,
        distance_child_override: int | None = None,
        distance_parent_override: int | None = None,
        activate: bool = False,
    ) -> dict:
        """Compile all active rules and store as a versioned ruleset.

        CPU-bound work runs in a thread pool to avoid blocking the event loop.

        By default ``activate=False`` so the new version is a candidate
        only. Callers must activate explicitly (DI-8DD23CE2).

        Args:
            version: Version label for the new ruleset (e.g. ``v20260308-1``).
            activate: When True, flip the scope current pointer to this version.

        Returns:
            Summary dict with ``version``, ``rule_count``, and ``compile_timestamp``.
        """
        scope = scope or CompileScope()
        statuses = include_rule_statuses or ["active"]
        self._closure_cache.clear()
        self._compile_stats = dict(self._DEFAULT_COMPILE_STATS)

        ruleset = await asyncio.to_thread(
            self._compile_ruleset,
            scope,
            statuses,
            policy_mode,
            policy_domain_id,
            policy_subdomain_name,
            policy_include_descendants,
            policy_depth,
            enforce_action_scope,
            distance_child_override,
            distance_parent_override,
        )
        ruleset["version"] = version
        ruleset["compile_timestamp"] = datetime.now(timezone.utc).isoformat()
        ruleset["scope_type"] = scope.scope_type
        ruleset["scope_id"] = scope.scope_id
        ruleset["policy_mode"] = policy_mode
        ruleset["compile_stats"] = dict(self._compile_stats)
        ruleset["activated_on_compile"] = bool(activate)

        self._store.write_ruleset(
            version,
            ruleset,
            scope_type=scope.scope_type,
            scope_id=scope.scope_id,
        )
        if activate:
            self._store.set_current_version(
                version,
                scope_type=scope.scope_type,
                scope_id=scope.scope_id,
            )
        logger.info(
            "Compiled ruleset %s scope=%s/%s policy=%s activate=%s: %d rules",
            version,
            scope.scope_type,
            scope.scope_id,
            policy_mode,
            activate,
            len(ruleset.get("rules", [])),
        )
        return {
            "version": version,
            "rule_count": len(ruleset.get("rules", [])),
            "compile_timestamp": ruleset["compile_timestamp"],
            "scope_type": scope.scope_type,
            "scope_id": scope.scope_id,
            "policy_mode": policy_mode,
            "compile_stats": dict(self._compile_stats),
            "activated": bool(activate),
        }

    def _compile_ruleset(
        self,
        scope: CompileScope,
        statuses: list[str],
        policy_mode: Literal["advisory", "strict"],
        policy_domain_id: str | None,
        policy_subdomain_name: str | None,
        policy_include_descendants: bool,
        policy_depth: int,
        enforce_action_scope: bool,
        distance_child_override: int | None,
        distance_parent_override: int | None,
    ) -> dict:
        """Synchronous ruleset compilation -- runs in thread pool."""
        driver = _kg_driver()
        try:
            with driver.session() as session:
                records = list(
                    session.run(
                        self._build_fetch_active_rules_query(scope),
                        statuses=statuses,
                        scope_id=scope.scope_id,
                        scope_domain_id=(
                            scope.scope_id.split(":", 1)[0]
                            if scope.scope_type == "subdomain"
                            else scope.scope_id
                        ),
                    )
                )
                applies_to_records = list(
                    session.run(
                        self._build_fetch_applies_to_query(scope),
                        statuses=statuses,
                        scope_id=scope.scope_id,
                        scope_domain_id=(
                            scope.scope_id.split(":", 1)[0]
                            if scope.scope_type == "subdomain"
                            else scope.scope_id
                        ),
                    )
                )
                action_records = list(
                    session.run(
                        self._build_fetch_actions_query(scope),
                        statuses=statuses,
                        scope_id=scope.scope_id,
                        scope_domain_id=(
                            scope.scope_id.split(":", 1)[0]
                            if scope.scope_type == "subdomain"
                            else scope.scope_id
                        ),
                    )
                )
                policy = self._build_policy(
                    session,
                    scope,
                    policy_mode=policy_mode,
                    policy_domain_id=policy_domain_id,
                    policy_subdomain_name=policy_subdomain_name,
                    include_descendants=policy_include_descendants,
                    depth=policy_depth,
                    enforce_action_scope=enforce_action_scope,
                )
                return self._build_ruleset(
                    records,
                    session,
                    applies_to_records,
                    action_records,
                    policy=policy,
                    distance_child_override=distance_child_override,
                    distance_parent_override=distance_parent_override,
                )
        finally:
            driver.close()

    def _build_fetch_active_rules_query(self, scope: CompileScope) -> str:
        where = ["coalesce(rule.status, 'active') IN $statuses"]
        if scope.scope_type == "guideline":
            where.append("g.id = $scope_id")
        elif scope.scope_type in {"domain", "subdomain"}:
            where.append("dom.id = $scope_domain_id")
        where_clause = " AND ".join(where)
        # Dual-graph tolerance: see DUAL-GRAPH NOTE above _FETCH_ACTIVE_RULES.
        return f"""
MATCH (g:Guideline)-[:HAS_RECOMMENDATION]->(rec:Recommendation)-[:HAS_RULE]->(rule:AppropriatenessRule)
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (g)-[:IN_SUBCATEGORY]->(:TaxonomySubcategory)-[:IN_DOMAIN]->(dom:AuditDomain)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp:CriteriaGroup)
OPTIONAL MATCH (grp)-[hc:HAS_CRITERIA]->(concept)
WITH g, rec, rule, ch, dom, grp, hc, concept
WHERE {where_clause}
RETURN
    rule.id              AS rule_id,
    rule.name            AS name,
    rule.strength        AS strength,
    coalesce(rule.schemaVersion, 1) AS schema_version,
    rule.logicJson       AS logic_json,
    rule.actionJson      AS action_json,
    rule.investigationPolicy AS investigation_policy,
    g.id                 AS guideline_id,
    g.title              AS guideline_title,
    coalesce(g.publisher, '') AS guideline_publisher,
    coalesce(g.source, '')    AS guideline_source,
    dom.id               AS guideline_domain_id,
    ch.title             AS chapter_title,
    rec.verbatim         AS recommendation_verbatim,
    grp.id               AS group_id,
    coalesce(grp.type, 'ALL') AS group_mode,
    hc.predicate         AS predicate,
    coalesce(concept.id, concept.conceptId)         AS concept_id,
    coalesce(hc.distanceChild,  0) AS distance_child,
    coalesce(hc.distanceParent, 0) AS distance_parent
ORDER BY rule.id, grp.id, coalesce(concept.id, concept.conceptId)
"""

    def _build_fetch_applies_to_query(self, scope: CompileScope) -> str:
        where = ["coalesce(rule.status, 'active') IN $statuses"]
        if scope.scope_type == "guideline":
            where.append("g.id = $scope_id")
        elif scope.scope_type in {"domain", "subdomain"}:
            where.append("dom.id = $scope_domain_id")
        where_clause = " AND ".join(where)
        # Dual-graph tolerance: see DUAL-GRAPH NOTE above _FETCH_ACTIVE_RULES.
        return f"""
MATCH (rule:AppropriatenessRule)-[at:APPLIES_TO]->(concept)
OPTIONAL MATCH (rec:Recommendation)-[:HAS_RULE]->(rule)<-[:HAS_RECOMMENDATION]-(g:Guideline)-[:IN_SUBCATEGORY]->(:TaxonomySubcategory)-[:IN_DOMAIN]->(dom:AuditDomain)
WITH rule, at, concept, dom, g
WHERE {where_clause}
RETURN
    rule.id              AS rule_id,
    dom.id               AS guideline_domain_id,
    coalesce(concept.id, concept.conceptId)        AS concept_id,
    coalesce(concept.preferred_term, concept.fsn, concept.term, concept.id, concept.conceptId) AS preferred_term,
    coalesce(concept.semantic_tag, concept.semanticTag) AS semantic_tag,
    at.rawTerm           AS raw_term,
    at.operator          AS operator,
    at.value             AS value,
    at.unit              AS unit
ORDER BY rule.id, coalesce(concept.id, concept.conceptId)
"""

    def _build_fetch_actions_query(self, scope: CompileScope) -> str:
        """Same scope filter as the other fetch queries; see _FETCH_ACTIONS."""
        where = ["coalesce(rule.status, 'active') IN $statuses"]
        if scope.scope_type == "guideline":
            where.append("g.id = $scope_id")
        elif scope.scope_type in {"domain", "subdomain"}:
            where.append("dom.id = $scope_domain_id")
        where_clause = " AND ".join(where)
        # Dual-graph tolerance: see DUAL-GRAPH NOTE above _FETCH_ACTIVE_RULES.
        return f"""
MATCH (rule:AppropriatenessRule)-[:HAS_ACTION_GROUP]->(:ActionGroup)-[ha:HAS_ACTION]->(proc)
OPTIONAL MATCH (rec:Recommendation)-[:HAS_RULE]->(rule)<-[:HAS_RECOMMENDATION]-(g:Guideline)-[:IN_SUBCATEGORY]->(:TaxonomySubcategory)-[:IN_DOMAIN]->(dom:AuditDomain)
WITH rule, ha, proc, dom, g
WHERE {where_clause}
RETURN
    rule.id              AS rule_id,
    coalesce(proc.id, proc.conceptId)               AS concept_id,
    coalesce(proc.preferred_term, proc.fsn, proc.term, proc.id, proc.conceptId) AS name,
    ha.strength          AS strength,
    ha.priority          AS priority,
    ha.dueDays           AS due_days
ORDER BY rule.id, coalesce(proc.id, proc.conceptId)
"""

    def _build_policy(
        self,
        session,
        scope: CompileScope,
        *,
        policy_mode: Literal["advisory", "strict"],
        policy_domain_id: str | None,
        policy_subdomain_name: str | None,
        include_descendants: bool,
        depth: int,
        enforce_action_scope: bool,
    ) -> CompilePolicy:
        domain_id = policy_domain_id
        subdomain_name = policy_subdomain_name
        if scope.scope_type == "subdomain":
            parts = scope.scope_id.split(":", 1)
            if len(parts) == 2:
                domain_id = domain_id or parts[0]
                subdomain_name = subdomain_name or parts[1]
        if policy_mode == "advisory" and not domain_id:
            return CompilePolicy(
                mode="advisory",
                allowed_concept_ids=frozenset(),
                enforce_action_scope=False,
            )
        if not domain_id or not subdomain_name:
            return CompilePolicy(
                mode=policy_mode,
                allowed_concept_ids=frozenset(),
                enforce_action_scope=False,
            )
        allowed = self._load_allowed_concepts(
            session,
            domain_id,
            subdomain_name,
            include_descendants=include_descendants,
            depth=depth,
        )
        return CompilePolicy(
            mode=policy_mode,
            allowed_concept_ids=frozenset(allowed),
            enforce_action_scope=bool(enforce_action_scope),
        )

    def _load_allowed_concepts(
        self,
        session,
        domain_id: str,
        subdomain_name: str,
        *,
        include_descendants: bool,
        depth: int,
    ) -> set[str]:
        vs_id = f"ncda-{subdomain_name.replace('_', '-')}"
        rows = session.run(
            "MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet {id: $vs_id}) "
            "RETURN v.rawJson AS raw_json",
            {"domain_id": domain_id, "vs_id": vs_id},
        )
        row = rows.single()
        if not row:
            logger.warning(
                "Compile policy source not found for domain=%s subdomain=%s; no allowlist loaded.",
                domain_id,
                subdomain_name,
            )
            return set()
        raw_json = row.get("raw_json")
        if not raw_json:
            return set()
        try:
            data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        except Exception:
            logger.warning("Invalid rawJson on ValueSet %s", vs_id)
            return set()
        allowed: set[str] = set()
        for include in (data.get("compose") or {}).get("include") or []:
            for concept in include.get("concept") or []:
                code = str(concept.get("code") or "").strip()
                if not code:
                    continue
                allowed.add(code)
                if include_descendants:
                    for cid in self._closure_ids(
                        session, code, max(0, int(depth or 0)), 0
                    ):
                        allowed.add(str(cid))
        return allowed

    def _closure_ids(
        self,
        session,
        concept_id: str,
        distance_child: int,
        distance_parent: int,
    ) -> list[str]:
        """Return the SNOMED closure for a concept (target + descendants + ancestors).

        Queries the knowledge graph for IS_A relationships.  Falls back silently
        to ``[concept_id]`` when SNOMED hierarchy is not loaded — the bitmap still
        works with exact-match semantics.

        Args:
            session: Active Neo4j session (same driver as the rule fetch).
            concept_id: SNOMED concept ID string.
            distance_child: Max IS_A hops downward (descendants).
            distance_parent: Max IS_A hops upward (ancestors).

        Returns:
            List of concept ID strings including the seed and any found relatives.
        """
        dc = max(0, int(distance_child or 0))
        dp = max(0, int(distance_parent or 0))

        cache_key = (concept_id, dc, dp)
        if cache_key in self._closure_cache:
            return self._closure_cache[cache_key]

        # Exact match only when both distances are zero
        if dc == 0 and dp == 0:
            result = [concept_id]
            self._closure_cache[cache_key] = result
            return result

        # Dual-graph closure (DI-LEO-AI-528):
        # The canonical SNOMED loader writes (:Concept {id})-[:IS_A]->(:Concept)
        # for every active concept; the legacy guidance generator wrote
        # (:SnomedConcept {conceptId}) WITHOUT IS_A edges, so descendant
        # expansion only ever worked through the canonical graph anyway.
        # We bind the seed unlabeled (so `:Concept` and `:SnomedConcept`
        # both match), follow IS_A on `:Concept` only -- that is the only
        # graph that actually has hierarchy -- and fall back silently to
        # `[concept_id]` when neither label is present, mirroring the
        # previous exact-match behaviour for missing concepts.
        parts = [
            "MATCH (t) WHERE (t:Concept AND t.id = $concept_id) "
            "OR (t:SnomedConcept AND t.conceptId = $concept_id)",
            "WITH t",
        ]
        collect_parts = ["collect(DISTINCT coalesce(t.id, t.conceptId))"]
        if dc > 0:
            parts.append(f"OPTIONAL MATCH (d:Concept)-[:IS_A*1..{dc}]->(t)")
            collect_parts.append("collect(DISTINCT d.id)")
        if dp > 0:
            parts.append(f"OPTIONAL MATCH (t)-[:IS_A*1..{dp}]->(a:Concept)")
            collect_parts.append("collect(DISTINCT a.id)")

        q = "\n".join(parts)
        q += f"\nWITH {' + '.join(collect_parts)} AS ids"
        q += "\nUNWIND ids AS x\nWITH DISTINCT x WHERE x IS NOT NULL\nRETURN x AS concept_id"

        try:
            rows = session.run(q, {"concept_id": concept_id})
            ids = [str(r["concept_id"]) for r in rows if r.get("concept_id")]
            result = ids if ids else [concept_id]
        except Exception as exc:
            logger.warning(
                "SNOMED closure query FAILED for concept %s (d_child=%d, d_parent=%d) -- "
                "falling back to exact-match only. IS_A hierarchy expansion is DISABLED "
                "for this concept. Rules using it will only fire on exact code matches, "
                "not descendant concepts. Error: %s",
                concept_id,
                dc,
                dp,
                exc,
            )
            result = [concept_id]

        self._closure_cache[cache_key] = result
        return result

    @staticmethod
    def _merge_legacy_row_action(rule_data: dict[str, Any], row: Any) -> None:
        """Back-compat: populate ``actions`` from a joined per-row column.

        Pre-Phase-4 callers (and any row shape that still carries
        ``action_concept_id`` directly, e.g. hand-built test fixtures) do not
        supply a separate ``action_records`` result set. When that is the
        case, this reproduces the old "keep the first action seen" merge so
        those callers keep working unchanged. Once ``action_records`` (from
        ``_FETCH_ACTIONS``) is supplied, real rows never carry these columns
        and this is a no-op.
        """
        if rule_data["actions"]:
            return
        concept_id = row.get("action_concept_id")
        if not concept_id:
            return
        rule_data["actions"].append(
            {
                "concept_id": concept_id,
                "name": row.get("action_name"),
                "strength": row.get("action_strength") or "unspecified",
                "priority": row.get("action_priority") or "routine",
                "due_days": row.get("action_due_days"),
            }
        )

    def _build_ruleset(
        self,
        records: list[Any],
        session,
        applies_to_records: list[Any] | None = None,
        action_records: list[Any] | None = None,
        *,
        policy: CompilePolicy | None = None,
        distance_child_override: int | None = None,
        distance_parent_override: int | None = None,
    ) -> dict:
        """Transform raw Neo4j records into a serialisable ruleset.

        One record per criterion (one row per concept per group).  The method
        groups rows by rule_id → group_id, expands each criterion to its SNOMED
        closure, and builds one bitmap per CriteriaGroup.

        Compiled rule format::

            {
              "criteria_groups": [
                {"mode": "ALL", "bitmap_id": "bm:abc..."},
                {"mode": "ANY", "bitmap_id": "bm:def..."},
                {"mode": "NOT", "bitmap_id": "bm:ghi..."},
              ],
              "actions": [{"concept_id": ..., "name": ..., "strength": ...,
                           "priority": ..., "due_days": ...}, ...],
              "action": {...} | None,  # actions[0], back-compat shim
              "applies_to": [...],
            }

        Backward compat with old Neo4j data (CriteriaGroup.type="ANY" +
        predicate="ABSENT"): mapped to mode="NOT" so old rules still evaluate
        correctly with the new evaluator.

        Args:
            records: Raw records from the ``_FETCH_ACTIVE_RULES`` Cypher query.
            session: Active Neo4j session (for SNOMED closure queries).
            applies_to_records: Raw records from ``_FETCH_APPLIES_TO``.
            action_records: Raw records from ``_FETCH_ACTIONS``. When omitted,
                per-row ``action_concept_id`` columns are used instead (see
                ``_merge_legacy_row_action``).
        """
        policy = policy or CompilePolicy()
        by_rule: dict[str, dict] = {}
        by_group: dict[str, dict] = {}  # group_id → {rule_id, mode, int_ids}
        self._compile_stats["rules_seen"] = len(
            {str(r["rule_id"]) for r in records if r.get("rule_id")}
        )

        for row in records:
            rule_id = str(row["rule_id"])
            group_id = str(row["group_id"]) if row.get("group_id") else None
            concept_id = row.get("concept_id")

            if rule_id not in by_rule:
                action_json = row.get("action_json")
                by_rule[rule_id] = {
                    "rule_id": rule_id,
                    "name": row["name"],
                    "strength": row["strength"],
                    "schema_version": int(row.get("schema_version") or 1),
                    "logic_json": row.get("logic_json"),
                    "action_json": (
                        json.loads(action_json)
                        if isinstance(action_json, str) and action_json
                        else None
                    ),
                    "guideline_id": row["guideline_id"],
                    "guideline_title": row["guideline_title"],
                    "guideline_publisher": row.get("guideline_publisher") or "",
                    "guideline_source": row.get("guideline_source") or "",
                    "chapter_title": row.get("chapter_title"),
                    "recommendation_verbatim": row.get("recommendation_verbatim", ""),
                    "group_ids_ordered": [],  # preserves insertion order
                    "applies_to": [],
                    "actions": [],
                    "action_priority": row.get("action_priority"),
                    "action_due_days": row.get("action_due_days"),
                    "guideline_domain_id": row.get("guideline_domain_id"),
                    "investigation_policy": row.get("investigation_policy"),
                }

            self._merge_legacy_row_action(by_rule[rule_id], row)

            if not group_id:
                continue

            if group_id not in by_group:
                raw_mode = str(row.get("group_mode") or "ALL").upper()
                predicate = str(row.get("predicate") or "PRESENT")
                # Backward compat: old data writes type="ANY" + predicate="ABSENT"
                # to mean "none of these may be present" → NOT semantics.
                if raw_mode == "ANY" and predicate == "ABSENT":
                    mode = "NOT"
                else:
                    mode = raw_mode  # ALL, ANY, or NOT
                by_group[group_id] = {"rule_id": rule_id, "mode": mode, "int_ids": []}
                by_rule[rule_id]["group_ids_ordered"].append(group_id)

            if not concept_id:
                continue

            if (
                policy.allowed_concept_ids
                and str(concept_id) not in policy.allowed_concept_ids
            ):
                self._compile_stats["policy_violations"] += 1
                self._compile_stats["out_of_scope_concepts"] += 1
                if policy.mode == "strict":
                    continue

            d_child = int(
                distance_child_override
                if distance_child_override is not None
                else row.get("distance_child") or 0
            )
            d_parent = int(
                distance_parent_override
                if distance_parent_override is not None
                else row.get("distance_parent") or 0
            )
            closure = self._closure_ids(session, str(concept_id), d_child, d_parent)
            if policy.allowed_concept_ids:
                closure = [
                    cid for cid in closure if str(cid) in policy.allowed_concept_ids
                ]
                if not closure:
                    self._compile_stats["policy_violations"] += 1
                    self._compile_stats["out_of_scope_concepts"] += 1
                    if policy.mode == "strict":
                        continue
                    closure = [str(concept_id)]
            int_ids = [self._store.get_or_assign_int_id(cid) for cid in closure]
            by_group[group_id]["int_ids"].extend(int_ids)

        # Merge APPLIES_TO demographic constraints into their rules
        for row in applies_to_records or []:
            rule_id = str(row["rule_id"])
            if rule_id not in by_rule:
                continue
            concept_id = row.get("concept_id")
            operator = row.get("operator")
            value = row.get("value")
            if not concept_id or not operator:
                continue
            by_rule[rule_id]["applies_to"].append(
                {
                    "concept_id": concept_id,
                    "preferred_term": row.get("preferred_term", ""),
                    "semantic_tag": row.get("semantic_tag", ""),
                    "raw_term": row.get("raw_term", ""),
                    "operator": operator,
                    "value": float(value) if value is not None else None,
                    "unit": row.get("unit"),
                }
            )

        # Merge recommended actions (HAS_ACTION edges) into their rules.
        # Fetched as a separate per-rule-id query (_FETCH_ACTIONS) so a rule
        # with multiple criteria rows AND multiple action rows does not
        # cross-join; this mirrors the APPLIES_TO merge above.
        for row in action_records or []:
            rule_id = str(row["rule_id"])
            if rule_id not in by_rule:
                continue
            concept_id = row.get("concept_id")
            if not concept_id:
                continue
            by_rule[rule_id]["actions"].append(
                {
                    "concept_id": concept_id,
                    "name": row.get("name"),
                    "strength": row.get("strength") or "unspecified",
                    "priority": row.get("priority") or "routine",
                    "due_days": row.get("due_days"),
                    "action_kind": row.get("action_kind") or "snomed_procedure",
                    "action_text": row.get("action_text"),
                }
            )

        compiled_rules = []
        for rule_data in by_rule.values():
            if int(rule_data.get("schema_version") or 1) == 2 and rule_data.get(
                "logic_json"
            ):
                compiled = self._compile_schema_v2_rule(
                    rule_data,
                    session,
                    policy=policy,
                    distance_child_override=distance_child_override,
                    distance_parent_override=distance_parent_override,
                )
                if compiled is not None:
                    compiled_rules.append(compiled)
                continue

            groups = []
            for gid in rule_data["group_ids_ordered"]:
                g = by_group[gid]
                int_ids = sorted(set(g["int_ids"]))
                if int_ids:
                    bitmap_id = self._store.put_bitmap(int_ids)
                    groups.append({"mode": g["mode"], "bitmap_id": bitmap_id})

            if groups or rule_data["applies_to"]:
                compiled_rules.append(
                    self._compile_one_rule(
                        rule_data,
                        groups,
                        policy=policy,
                        session=session,
                    )
                )
            else:
                logger.error(
                    "Active rule %r (%s, guideline=%s) has NO bitmap groups AND no "
                    "APPLIES_TO constraints — it will NOT be included in the compiled "
                    "ruleset and will NEVER fire for any patient. "
                    "This means all SNOMED criteria were unresolved when the rule was generated "
                    "(Terminology API was likely unavailable). "
                    "Re-generate and re-approve this rule.",
                    rule_data["rule_id"],
                    rule_data.get("name", ""),
                    rule_data.get("guideline_id", ""),
                )

        self._compile_stats["rules_included"] = len(compiled_rules)
        self._compile_stats["rules_excluded"] = max(
            0,
            int(self._compile_stats.get("rules_seen") or 0) - len(compiled_rules),
        )
        self._detect_rule_fired_cycles(compiled_rules)
        return {"rules": compiled_rules}

    def _seeds_from_criterion(self, criterion: dict[str, Any]) -> list[dict[str, Any]]:
        """Resolve the synonym-set seeds for a CONCEPT criterion (UN-LEO-AI-093).

        Backwards compatible: when ``seeds`` is empty / missing, we synthesise
        a single seed from the legacy ``snomed_concept_id`` so the rest of
        the compile path is uniform. ``include_descendants`` defaults to
        True to match historical behaviour where descendants were always
        swept up to ``distance_child`` levels.
        """
        seeds_in = list(criterion.get("seeds") or [])
        if seeds_in:
            return [
                {
                    "snomed_concept_id": str(s["snomed_concept_id"]),
                    "include_descendants": bool(s.get("include_descendants", True)),
                    "distance_child": s.get("distance_child"),
                }
                for s in seeds_in
                if s.get("snomed_concept_id")
            ]
        cid = criterion.get("snomed_concept_id")
        if not cid:
            return []
        return [
            {
                "snomed_concept_id": str(cid),
                "include_descendants": True,
                "distance_child": criterion.get("distance_child"),
            }
        ]

    def _compile_concept_leaf(
        self,
        node: dict[str, Any],
        session,
        *,
        policy: CompilePolicy,
        distance_child_override: int | None = None,
        distance_parent_override: int | None = None,
    ) -> dict[str, Any] | None:
        """Compile one CONCEPT leaf into a bitmap echo dict.

        Implements DI-LEO-AI-509: union of every seed's IS_A closure, minus
        ``excluded_concept_ids``. When the criterion is the legacy single-seed
        shape, the int-id set passed to ``put_bitmap`` is identical to the
        pre-change behaviour (no clinical-output drift on migration).
        """
        criterion = dict(node.get("criterion") or {})
        seeds = self._seeds_from_criterion(criterion)
        if not seeds:
            logger.error(
                "Schema v2 concept leaf %r has no SNOMED code -- rule will be excluded from compilation.",
                criterion.get("node_id"),
            )
            return None

        excluded_ids = {
            str(x) for x in (criterion.get("excluded_concept_ids") or []) if x
        }
        primary_id = str(
            criterion.get("primary_concept_id")
            or criterion.get("snomed_concept_id")
            or seeds[0]["snomed_concept_id"]
        )

        union_ids: set[str] = set()
        for seed in seeds:
            seed_id = seed["snomed_concept_id"]
            if seed["include_descendants"]:
                rule_default = (
                    distance_child_override
                    if distance_child_override is not None
                    else (
                        seed["distance_child"]
                        if seed["distance_child"] is not None
                        else 3
                    )
                )
                dc = max(0, int(rule_default))
            else:
                dc = 0
            dp = int(
                distance_parent_override
                if distance_parent_override is not None
                else (criterion.get("distance_parent") or 0)
            )
            try:
                closure = self._closure_ids(session, seed_id, dc, dp)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Synonym seed %s closure lookup failed; falling back to exact-match for this seed only. err=%s",
                    seed_id,
                    exc,
                )
                closure = [seed_id]
            for cid in closure:
                union_ids.add(str(cid))

        unreachable = excluded_ids - union_ids
        if unreachable:
            logger.warning(
                "Concept leaf %r has %d excluded id(s) that are not in any seed closure (no-op): %s",
                criterion.get("node_id"),
                len(unreachable),
                sorted(unreachable),
            )

        union_ids -= excluded_ids

        if policy.allowed_concept_ids:
            union_ids = {cid for cid in union_ids if cid in policy.allowed_concept_ids}
            if not union_ids:
                if policy.mode == "strict":
                    return None
                # Fallback to the primary id so the leaf still compiles to a bitmap.
                union_ids = {primary_id}

        if not union_ids:
            # Defensive: every seed's closure was empty AND every id was excluded.
            # Fall back to the primary id so the rule does not silently disappear.
            union_ids = {primary_id}

        sorted_ids = sorted(union_ids)
        int_ids = sorted({self._store.get_or_assign_int_id(cid) for cid in sorted_ids})
        bitmap_id = self._store.put_bitmap(int_ids)

        echo_seeds = [
            {
                "snomed_concept_id": s["snomed_concept_id"],
                "include_descendants": s["include_descendants"],
                "distance_child": s["distance_child"],
            }
            for s in seeds
        ]
        return {
            "kind": "concept",
            "node_id": criterion.get("node_id"),
            "bitmap_id": bitmap_id,
            "criterion": {
                "term": criterion.get("term"),
                "snomed_concept_id": primary_id,
                "preferred_term": criterion.get("preferred_term"),
                "semantic_tag": criterion.get("semantic_tag"),
                "primary_concept_id": primary_id,
                "seeds": echo_seeds,
                "excluded_concept_ids": sorted(excluded_ids),
                "soft_qualifiers": list(criterion.get("soft_qualifiers") or []),
            },
            "seed_concept_ids": sorted_ids,
        }

    def _compile_observation_leaf(self, node: dict[str, Any]) -> dict[str, Any] | None:
        """Compile an OBSERVATION leaf into the evaluator wire shape.

        Phase 5c. Responsibilities:

          1. Resolve the comparison unit -- from the curated registry when
             present, otherwise from the unit the rule author supplied
             (absolute-threshold mode only).
          2. Canonicalise the rule's threshold value(s) to that unit so
             the evaluator compares like-with-like at runtime.

        Curated registry entries are still required for reference_range,
        trend, temporal, and aggregate modes (they need conversion aliases
        or reference bands). Absolute thresholds (>= 10 ug/g) work for any
        SNOMED observable entity when the author declares a unit.

        Returns None (excludes the leaf) on validation / unit errors.
        """
        nested = node.get("observation")
        if isinstance(nested, dict) and nested:
            observation = dict(nested)
        else:
            observation = {
                k: node.get(k)
                for k in (
                    "observable_id",
                    "observable_term",
                    "operator",
                    "value",
                    "unit",
                    "within_days",
                    "temporal",
                    "reference_range",
                    "trend",
                    "aggregation",
                )
                if node.get(k) is not None
            }
        if not observation:
            logger.error(
                "OBSERVATION leaf %r is missing its payload "
                "-- rule will be excluded from compilation.",
                node.get("node_id"),
            )
            return None

        observable_id = str(observation.get("observable_id") or "").strip()
        if not observable_id:
            logger.error(
                "OBSERVATION leaf %r has no observable_id -- rule will be "
                "excluded from compilation.",
                node.get("node_id"),
            )
            return None

        wire_unit = str(observation.get("unit") or "").strip()
        advanced_mode = any(
            observation.get(key)
            for key in ("temporal", "reference_range", "trend", "aggregation")
        )
        lab_config = get_lab_config(observable_id)
        if advanced_mode and not (lab_config or is_known_observable(observable_id)):
            logger.error(
                "OBSERVATION leaf %r uses advanced mode on unregistered "
                "observable %s -- add Knowledge Graph lab config or use "
                "absolute threshold mode only.",
                node.get("node_id"),
                observable_id,
            )
            return None

        try:
            canonical_unit = (
                lab_config.canonical_unit
                if lab_config is not None
                else resolve_effective_canonical_unit(observable_id, wire_unit)
            )
        except UnknownObservableError:
            logger.error(
                "OBSERVATION leaf %r references unregistered observable %s "
                "with no unit -- add a unit on the rule (for example ug/g) "
                "or register the observable in the unit registry.",
                node.get("node_id"),
                observable_id,
            )
            return None

        if not wire_unit:
            wire_unit = canonical_unit

        operator = str(observation.get("operator") or "").strip()
        try:
            canonical_value = self._canonicalise_threshold(
                observable_id,
                operator,
                observation.get("value"),
                wire_unit,
                rule_canonical_unit=canonical_unit,
            )
        except (LabConfigError, UnitConversionError, ValueError) as exc:
            logger.error(
                "OBSERVATION leaf %r failed unit canonicalisation "
                "(observable=%s, unit=%s): %s",
                node.get("node_id"),
                observable_id,
                wire_unit,
                exc,
            )
            return None

        return {
            "kind": "observation",
            "node_id": node.get("node_id"),
            "observable_id": observable_id,
            "observable_term": observation.get("observable_term") or "",
            "operator": operator,
            "value": canonical_value,
            "unit": canonical_unit,
            "wire_unit": wire_unit,
            "within_days": int(observation.get("within_days") or 365),
            "temporal": observation.get("temporal"),
            "reference_range": observation.get("reference_range"),
            "trend": observation.get("trend"),
            "aggregation": observation.get("aggregation"),
        }

    @staticmethod
    def _canonicalise_threshold(
        observable_id: str,
        operator: str,
        value: Any,
        unit: str,
        *,
        rule_canonical_unit: str,
    ) -> float | list[float]:
        """Convert a leaf's threshold value(s) to the comparison unit."""
        if operator == "between":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError(
                    "OBSERVATION 'between' operator requires a [low, "
                    "high] value pair."
                )
            low = GuidelineCompiler._canonicalise_scalar_threshold(
                observable_id, float(value[0]), unit, rule_canonical_unit
            )
            high = GuidelineCompiler._canonicalise_scalar_threshold(
                observable_id, float(value[1]), unit, rule_canonical_unit
            )
            if low > high:
                raise ValueError(
                    "OBSERVATION 'between' canonicalised range is "
                    f"inverted (low={low}, high={high})."
                )
            return [low, high]
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"OBSERVATION operator {operator!r} requires a scalar "
                f"value; got {type(value).__name__}."
            )
        return GuidelineCompiler._canonicalise_scalar_threshold(
            observable_id, float(value), unit, rule_canonical_unit
        )

    @staticmethod
    def _canonicalise_scalar_threshold(
        observable_id: str,
        value: float,
        unit: str,
        rule_canonical_unit: str,
    ) -> float:
        config = get_lab_config(observable_id)
        if config is not None:
            return convert_lab_value(config, value, unit or config.canonical_unit)
        return canonicalise_value_for_observation(
            observable_id,
            value,
            unit,
            rule_canonical_unit=rule_canonical_unit,
        )

    @staticmethod
    def _compile_medication_leaf(node: dict[str, Any]) -> dict[str, Any] | None:
        """Compile a MEDICATION leaf -- validates required fields.

        Atlas trace: DO-0EC3A9CB / DI-2199E670
        Fails closed (returns None) when drug_class is missing.
        """
        drug_class = (node.get("drug_class") or "").strip()
        if not drug_class:
            logger.error(
                "MEDICATION leaf %r is missing required drug_class -- rule excluded.",
                node.get("node_id"),
            )
            return None
        return {
            "kind": "MEDICATION",
            "node_id": node.get("node_id"),
            "drug_class": drug_class,
            "concept_id": node.get("concept_id"),
            "term": node.get("term", ""),
        }

    @staticmethod
    def _compile_allergy_leaf(node: dict[str, Any]) -> dict[str, Any] | None:
        """Compile an ALLERGY leaf -- validates required fields.

        Atlas trace: DO-0EC3A9CB / DI-2199E670
        Fails closed (returns None) when substance_concept_id is missing.
        """
        substance_concept_id = (node.get("substance_concept_id") or "").strip()
        if not substance_concept_id:
            logger.error(
                "ALLERGY leaf %r is missing required substance_concept_id -- rule excluded.",
                node.get("node_id"),
            )
            return None
        return {
            "kind": "ALLERGY",
            "node_id": node.get("node_id"),
            "substance_concept_id": substance_concept_id,
            "allergy_class": node.get("allergy_class"),
            "term": node.get("term", ""),
        }

    @staticmethod
    def _compile_treatment_history_leaf(
        node: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Compile a TREATMENT_HISTORY leaf -- validates required fields.

        Atlas trace: DO-0EC3A9CB / DI-2199E670
        Fails closed (returns None) when treatment_class is missing.
        """
        treatment_class = (node.get("treatment_class") or "").strip()
        if not treatment_class:
            logger.error(
                "TREATMENT_HISTORY leaf %r is missing required treatment_class"
                " -- rule excluded.",
                node.get("node_id"),
            )
            return None
        min_duration = node.get("min_duration_days")
        if min_duration is not None:
            try:
                min_duration = int(min_duration)
                if min_duration < 1:
                    raise ValueError("min_duration_days must be >= 1")
            except (TypeError, ValueError) as exc:
                logger.error(
                    "TREATMENT_HISTORY leaf %r has invalid min_duration_days %r: %s"
                    " -- rule excluded.",
                    node.get("node_id"),
                    min_duration,
                    exc,
                )
                return None
        return {
            "kind": "TREATMENT_HISTORY",
            "node_id": node.get("node_id"),
            "treatment_class": treatment_class,
            "concept_id": node.get("concept_id"),
            "min_duration_days": min_duration,
            "term": node.get("term", ""),
        }

    @staticmethod
    def _collect_rule_fired_deps(node: dict[str, Any]) -> list[str]:
        """Return all referenced_rule_id values found in RULE_FIRED leaves."""
        kind = str(node.get("kind") or "").upper()
        if kind == "RULE_FIRED":
            ref = node.get("referenced_rule_id")
            return [ref] if ref else []
        deps: list[str] = []
        for child in node.get("children") or []:
            deps.extend(GuidelineCompiler._collect_rule_fired_deps(child))
        return deps

    def _detect_rule_fired_cycles(self, compiled_rules: list[dict[str, Any]]) -> None:
        """DFS cycle detection across RULE_FIRED dependency edges.

        Logs a warning in compile_stats for every cycle found. The evaluator's
        _in_progress guard is the runtime safety net; this is an early-warning
        signal for administrators. Atlas trace: DO-274E5A61 / DI-8899D4F3.
        """
        adj: dict[str, list[str]] = {}
        for rule in compiled_rules:
            rule_id = rule.get("rule_id", "")
            tree = rule.get("logic_tree") or {}
            adj[rule_id] = self._collect_rule_fired_deps(tree)

        visited: set[str] = set()
        in_stack: set[str] = set()

        def _dfs(node_id: str) -> bool:
            if node_id in in_stack:
                return True
            if node_id in visited:
                return False
            visited.add(node_id)
            in_stack.add(node_id)
            for neighbour in adj.get(node_id, []):
                if _dfs(neighbour):
                    return True
            in_stack.discard(node_id)
            return False

        for rule_id in list(adj):
            if rule_id not in visited:
                if _dfs(rule_id):
                    self._compile_stats["cycle_warnings"] = (
                        int(self._compile_stats.get("cycle_warnings") or 0) + 1
                    )
                    logger.warning(
                        "RULE_FIRED cycle detected involving rule %r -- "
                        "affected rules will return False (fail-closed) at evaluation time.",
                        rule_id,
                    )

    def _compile_logic_tree_node(
        self,
        node: dict[str, Any] | None,
        session,
        *,
        policy: CompilePolicy,
        distance_child_override: int | None = None,
        distance_parent_override: int | None = None,
    ) -> dict[str, Any] | None:
        if not node:
            return None
        kind = str(node.get("kind") or "").lower()
        if kind == "concept":
            return self._compile_concept_leaf(
                node,
                session,
                policy=policy,
                distance_child_override=distance_child_override,
                distance_parent_override=distance_parent_override,
            )
        if kind == "demographic":
            return {
                "kind": "demographic",
                "node_id": node.get("node_id"),
                "field": node.get("field"),
                "operator": node.get("operator"),
                "value": node.get("value"),
                "unit": node.get("unit"),
                "raw_term": node.get("raw_term"),
            }
        if kind == "observation":
            return self._compile_observation_leaf(node)
        if kind == "medication":
            return self._compile_medication_leaf(node)
        if kind == "allergy":
            return self._compile_allergy_leaf(node)
        if kind == "treatment_history":
            return self._compile_treatment_history_leaf(node)
        if kind == "rule_fired":
            return {
                "kind": "RULE_FIRED",
                "node_id": node.get("node_id"),
                "referenced_rule_id": node.get("referenced_rule_id"),
                "outcome": node.get("outcome", "fired"),
                "display_name": node.get("display_name"),
            }

        children = []
        for child in node.get("children") or []:
            compiled_child = self._compile_logic_tree_node(
                child,
                session,
                policy=policy,
                distance_child_override=distance_child_override,
                distance_parent_override=distance_parent_override,
            )
            if compiled_child is None:
                return None
            children.append(compiled_child)
        return {
            "kind": str(node.get("kind") or "").upper(),
            "node_id": node.get("node_id"),
            "min": node.get("min"),
            "children": children,
        }

    @staticmethod
    def _actions_from_action_json(rule_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Fallback source for rules with no HAS_ACTION edges (human-edit path).

        ``action_json`` tolerates both the legacy single-object shape and
        the new JSON-array shape written by ``guidance_rule_edit.py``
        (``{term, snomed_concept_id, preferred_term, semantic_tag,
        strength, verification_status}`` per item). Rule-level
        ``action_priority``/``action_due_days`` are reused for every item
        since actionJson-only rules have no per-action priority source.
        """
        action_json = rule_data.get("action_json")
        if isinstance(action_json, list):
            items = [a for a in action_json if isinstance(a, dict)]
        elif isinstance(action_json, dict):
            items = [action_json]
        else:
            items = []
        priority = rule_data.get("action_priority") or "routine"
        due_days = rule_data.get("action_due_days")
        out: list[dict[str, Any]] = []
        for item in items:
            concept_id = item.get("snomed_concept_id")
            if not concept_id:
                continue
            out.append(
                {
                    "concept_id": concept_id,
                    "name": item.get("preferred_term") or item.get("term"),
                    "strength": item.get("strength") or "unspecified",
                    "priority": priority,
                    "due_days": due_days,
                    "already_done_evidence_ids": item.get("already_done_evidence_ids")
                    or [],
                }
            )
        return out

    def _build_compiled_actions(
        self,
        rule_data: dict[str, Any],
        policy: CompilePolicy,
        session=None,
    ) -> list[dict[str, Any]]:
        """Build the compiled ``actions`` list for one rule.

        Prefers ``rule_data["actions"]`` (from HAS_ACTION edges, merged in
        by ``_build_ruleset``). Falls back to ``action_json`` only when no
        HAS_ACTION-sourced actions exist at all -- matches the previous
        singular-action if/elif precedence (a filtered/out-of-scope action
        does not fall through to the actionJson source).
        """
        source = rule_data.get("actions") or self._actions_from_action_json(rule_data)
        from libs.guidelines.investigation_family_catalog import load_family_index

        families = load_family_index(session) if session is not None else {}
        actions: list[dict[str, Any]] = []
        for item in source:
            concept_id = item.get("concept_id")
            if not concept_id:
                continue
            if (
                policy.allowed_concept_ids
                and policy.enforce_action_scope
                and str(concept_id) not in policy.allowed_concept_ids
            ):
                self._compile_stats["policy_violations"] += 1
                self._compile_stats["out_of_scope_actions"] += 1
                if policy.mode != "strict":
                    logger.warning(
                        "Action concept %s for rule %s is outside policy scope.",
                        concept_id,
                        rule_data.get("rule_id"),
                    )
                continue
            actions.append(
                self._compiled_action_item(
                    item,
                    str(concept_id),
                    session=session,
                    families=families,
                )
            )
        return actions

    @staticmethod
    def _snomed_related_dict(concept_id: str, session) -> dict[str, Any] | None:
        """Return SNOMED ontology neighbours for concept_id in investigation_family format.

        Returns the raw Neo4j row dict (keys: has_components, interpreted_by_findings,
        etc.) so it can be passed directly to evidence_ids_for_action(related=...).
        Returns None on any failure so callers degrade gracefully.
        """
        from services.terminology_api.app.queries.terminology import (
            RELATED_CONCEPTS_QUERY,
        )

        try:
            rows = list(session.run(RELATED_CONCEPTS_QUERY, concept_id=concept_id))
            if not rows:
                return None
            row = rows[0]
            return dict(row) if not isinstance(row, dict) else row
        except Exception:
            logger.warning(
                "_snomed_related_dict: lookup failed for concept %s",
                concept_id,
                exc_info=True,
            )
            return None

    @staticmethod
    def _compiled_action_item(
        item: dict[str, Any],
        concept_id: str,
        session=None,
        families=None,
    ) -> dict[str, Any]:
        """Build one compiled action, including already-done evidence ids.

        When a Neo4j session is supplied the evidence ids are enriched with
        SNOMED ontology neighbours (HAS_COMPONENT observables and
        INTERPRETED_BY findings) so the already-done check fires even when
        the patient has a result *finding* rather than the procedure code.
        """
        from libs.guidelines.investigation_family import evidence_ids_for_action

        related = (
            GuidelineCompiler._snomed_related_dict(concept_id, session)
            if session is not None
            else None
        )
        evidence = evidence_ids_for_action(
            concept_id, related=related, families=families
        )
        for extra in item.get("already_done_evidence_ids") or []:
            text = str(extra).strip()
            if text:
                evidence.add(text)
        return {
            "concept_id": concept_id,
            "name": item.get("name"),
            "strength": item.get("strength") or "unspecified",
            "priority": item.get("priority") or "routine",
            "due_days": item.get("due_days"),
            "already_done_evidence_ids": sorted(evidence),
        }

    def _compile_schema_v2_rule(
        self,
        rule_data: dict[str, Any],
        session,
        *,
        policy: CompilePolicy,
        distance_child_override: int | None = None,
        distance_parent_override: int | None = None,
    ) -> dict[str, Any] | None:
        try:
            logic_tree = (
                json.loads(rule_data["logic_json"])
                if isinstance(rule_data.get("logic_json"), str)
                else rule_data.get("logic_json")
            )
        except Exception as exc:
            logger.error(
                "Invalid schema v2 logicJson for rule %s: %s", rule_data["rule_id"], exc
            )
            return None
        compiled_tree = self._compile_logic_tree_node(
            logic_tree,
            session,
            policy=policy,
            distance_child_override=distance_child_override,
            distance_parent_override=distance_parent_override,
        )
        if compiled_tree is None:
            logger.error(
                "Schema v2 rule %s could not be compiled because one or more leaf concepts were unresolved.",
                rule_data["rule_id"],
            )
            return None

        actions = self._build_compiled_actions(rule_data, policy, session=session)

        return {
            "rule_id": rule_data["rule_id"],
            "name": rule_data["name"],
            "strength": rule_data["strength"],
            "schema_version": 2,
            "guideline_id": rule_data["guideline_id"],
            "guideline_title": rule_data["guideline_title"],
            "guideline_publisher": rule_data.get("guideline_publisher") or "",
            "guideline_source": rule_data.get("guideline_source") or "",
            "guideline_domain_id": rule_data.get("guideline_domain_id"),
            "chapter_title": rule_data.get("chapter_title"),
            "recommendation_verbatim": rule_data["recommendation_verbatim"],
            "logic_tree": compiled_tree,
            "actions": actions,
            # Back-compat shim for one release -- removable once libs/sbar
            # (Phase 4b) is confirmed migrated to reading "actions".
            "action": actions[0] if actions else None,
            "investigation_policy": rule_data.get("investigation_policy") or None,
        }

    def _compile_one_rule(
        self,
        rule_data: dict,
        groups: list[dict],
        *,
        policy: CompilePolicy,
        session=None,
    ) -> dict:
        """Build the compiled rule dict for a single rule.

        Args:
            rule_data: Intermediate rule dict with action metadata and applies_to.
            groups: List of ``{mode, bitmap_id}`` dicts, one per CriteriaGroup.

        Returns:
            Compiled rule dict with ``criteria_groups``, ``actions``,
            ``action`` (back-compat shim), and ``applies_to`` fields
            consumed by the evaluator.
        """
        actions = self._build_compiled_actions(rule_data, policy, session=session)

        return {
            "rule_id": rule_data["rule_id"],
            "name": rule_data["name"],
            "strength": rule_data["strength"],
            "schema_version": 1,
            "guideline_id": rule_data["guideline_id"],
            "guideline_title": rule_data["guideline_title"],
            "guideline_publisher": rule_data.get("guideline_publisher") or "",
            "guideline_source": rule_data.get("guideline_source") or "",
            "guideline_domain_id": rule_data.get("guideline_domain_id"),
            "chapter_title": rule_data.get("chapter_title"),
            "recommendation_verbatim": rule_data["recommendation_verbatim"],
            "criteria_groups": groups,
            "actions": actions,
            # Back-compat shim for one release -- removable once libs/sbar
            # (Phase 4b) is confirmed migrated to reading "actions".
            "action": actions[0] if actions else None,
            "applies_to": rule_data.get("applies_to") or [],
            "investigation_policy": rule_data.get("investigation_policy") or None,
        }
