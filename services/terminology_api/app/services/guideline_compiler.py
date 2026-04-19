"""Offline compiler: reads active AppropriatenessRules from Neo4j and builds bitmaps.

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
The compiled rule output includes ``action`` with ``concept_id``, ``name``,
``priority`` ("2ww" | "urgent" | "routine"), and ``due_days`` (int | None).
This is read directly from the ``HAS_ACTION`` edge properties written by the
rule generator, so no Neo4j re-query is needed at evaluation time.
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


# DUAL-GRAPH NOTE (DI-LEO-AI-512):
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
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(ag:ActionGroup)-[ha:HAS_ACTION]->(proc)
RETURN
    rule.id              AS rule_id,
    rule.name            AS name,
    rule.strength        AS strength,
    coalesce(rule.schemaVersion, 1) AS schema_version,
    rule.logicJson       AS logic_json,
    rule.actionJson      AS action_json,
    g.id                 AS guideline_id,
    g.title              AS guideline_title,
    dom.id               AS guideline_domain_id,
    ch.title             AS chapter_title,
    rec.verbatim         AS recommendation_verbatim,
    grp.id               AS group_id,
    coalesce(grp.type, 'ALL') AS group_mode,
    hc.predicate         AS predicate,
    coalesce(concept.id, concept.conceptId)         AS concept_id,
    coalesce(hc.distanceChild,  0) AS distance_child,
    coalesce(hc.distanceParent, 0) AS distance_parent,
    coalesce(proc.id, proc.conceptId)               AS action_concept_id,
    coalesce(proc.preferred_term, proc.fsn, proc.term, proc.id, proc.conceptId) AS action_name,
    ha.priority          AS action_priority,
    ha.dueDays           AS action_due_days
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
        self._compile_stats["rules_excluded"] = max(
            0, len(rules) - len(compiled_rules)
        )
        return {"rules": compiled_rules}

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
        action = rule_in.get("action") or {}
        action_concept_id = (
            rule_in.get("action_concept_id")
            or action.get("snomed_concept_id")
            or action.get("concept_id")
        )
        action_name = (
            rule_in.get("action_name")
            or action.get("preferred_term")
            or action.get("term")
            or action.get("name")
        )
        return {
            "rule_id": str(rule_id),
            "name": rule_in.get("name") or "",
            "strength": rule_in.get("strength") or "unspecified",
            "schema_version": 2,
            "logic_json": logic_json,
            "guideline_id": rule_in.get("guideline_id") or "",
            "guideline_title": rule_in.get("guideline_title") or "",
            "guideline_domain_id": rule_in.get("guideline_domain_id"),
            "chapter_title": rule_in.get("chapter_title"),
            "recommendation_verbatim": rule_in.get("recommendation_verbatim")
            or rule_in.get("recommendation_text")
            or "",
            "action_concept_id": action_concept_id,
            "action_name": action_name,
            "action_priority": rule_in.get("action_priority")
            or action.get("priority")
            or "routine",
            "action_due_days": rule_in.get("action_due_days")
            or action.get("due_days"),
            "action_json": rule_in.get("action_json"),
            "applies_to": list(rule_in.get("applies_to") or []),
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
    ) -> dict:
        """Compile all active rules and store as a versioned ruleset.

        CPU-bound work runs in a thread pool to avoid blocking the event loop.

        Args:
            version: Version label for the new ruleset (e.g. ``v20260308-1``).

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
        logger.info(
            "Compiled ruleset %s scope=%s/%s policy=%s: %d rules",
            version,
            scope.scope_type,
            scope.scope_id,
            policy_mode,
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
        return f"""
MATCH (g:Guideline)-[:HAS_RECOMMENDATION]->(rec:Recommendation)-[:HAS_RULE]->(rule:AppropriatenessRule)
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (g)-[:IN_SUBCATEGORY]->(:TaxonomySubcategory)-[:IN_DOMAIN]->(dom:AuditDomain)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp:CriteriaGroup)
OPTIONAL MATCH (grp)-[hc:HAS_CRITERIA]->(concept)
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(ag:ActionGroup)-[ha:HAS_ACTION]->(proc:Procedure)
WITH g, rec, rule, ch, dom, grp, hc, concept, ag, ha, proc
WHERE {where_clause}
RETURN
    rule.id              AS rule_id,
    rule.name            AS name,
    rule.strength        AS strength,
    coalesce(rule.schemaVersion, 1) AS schema_version,
    rule.logicJson       AS logic_json,
    rule.actionJson      AS action_json,
    g.id                 AS guideline_id,
    g.title              AS guideline_title,
    dom.id               AS guideline_domain_id,
    ch.title             AS chapter_title,
    rec.verbatim         AS recommendation_verbatim,
    grp.id               AS group_id,
    coalesce(grp.type, 'ALL') AS group_mode,
    hc.predicate         AS predicate,
    concept.conceptId    AS concept_id,
    coalesce(hc.distanceChild,  0) AS distance_child,
    coalesce(hc.distanceParent, 0) AS distance_parent,
    proc.conceptId       AS action_concept_id,
    proc.term            AS action_name,
    ha.priority          AS action_priority,
    ha.dueDays           AS action_due_days
ORDER BY rule.id, grp.id, concept.conceptId
"""

    def _build_fetch_applies_to_query(self, scope: CompileScope) -> str:
        where = ["coalesce(rule.status, 'active') IN $statuses"]
        if scope.scope_type == "guideline":
            where.append("g.id = $scope_id")
        elif scope.scope_type in {"domain", "subdomain"}:
            where.append("dom.id = $scope_domain_id")
        where_clause = " AND ".join(where)
        return f"""
MATCH (rule:AppropriatenessRule)-[at:APPLIES_TO]->(concept:SnomedConcept)
OPTIONAL MATCH (rec:Recommendation)-[:HAS_RULE]->(rule)<-[:HAS_RECOMMENDATION]-(g:Guideline)-[:IN_SUBCATEGORY]->(:TaxonomySubcategory)-[:IN_DOMAIN]->(dom:AuditDomain)
WITH rule, at, concept, dom, g
WHERE {where_clause}
RETURN
    rule.id              AS rule_id,
    dom.id               AS guideline_domain_id,
    concept.conceptId    AS concept_id,
    concept.term         AS preferred_term,
    concept.semanticTag  AS semantic_tag,
    at.rawTerm           AS raw_term,
    at.operator          AS operator,
    at.value             AS value,
    at.unit              AS unit
ORDER BY rule.id, concept.conceptId
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

        # Build parameterised closure query — variable-length paths must be
        # literal in Cypher, so we interpolate the hop counts into the template.
        parts = ["MATCH (t:SnomedConcept {conceptId: $concept_id})", "WITH t"]
        collect_parts = ["collect(DISTINCT t.conceptId)"]
        if dc > 0:
            parts.append(f"OPTIONAL MATCH (d:SnomedConcept)-[:IS_A*1..{dc}]->(t)")
            collect_parts.append("collect(DISTINCT d.conceptId)")
        if dp > 0:
            parts.append(f"OPTIONAL MATCH (t)-[:IS_A*1..{dp}]->(a:SnomedConcept)")
            collect_parts.append("collect(DISTINCT a.conceptId)")

        q = "\n".join(parts)
        q += f"\nWITH {' + '.join(collect_parts)} AS ids"
        q += "\nUNWIND ids AS x\nWITH DISTINCT x WHERE x IS NOT NULL\nRETURN x AS concept_id"

        try:
            rows = session.run(q, {"concept_id": concept_id})
            ids = [str(r["concept_id"]) for r in rows if r.get("concept_id")]
            result = ids if ids else [concept_id]
        except Exception as exc:
            logger.warning(
                "SNOMED closure query FAILED for concept %s (d_child=%d, d_parent=%d) — "
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

    def _build_ruleset(
        self,
        records: list[Any],
        session,
        applies_to_records: list[Any] | None = None,
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
              "action": {...} | None,
              "applies_to": [...],
            }

        Backward compat with old Neo4j data (CriteriaGroup.type="ANY" +
        predicate="ABSENT"): mapped to mode="NOT" so old rules still evaluate
        correctly with the new evaluator.

        Args:
            records: Raw records from the ``_FETCH_ACTIVE_RULES`` Cypher query.
            session: Active Neo4j session (for SNOMED closure queries).
            applies_to_records: Raw records from ``_FETCH_APPLIES_TO``.
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
                    "chapter_title": row.get("chapter_title"),
                    "recommendation_verbatim": row.get("recommendation_verbatim", ""),
                    "group_ids_ordered": [],  # preserves insertion order
                    "applies_to": [],
                    "action_concept_id": row.get("action_concept_id"),
                    "action_name": row.get("action_name"),
                    "action_priority": row.get("action_priority", "routine"),
                    "action_due_days": row.get("action_due_days"),
                    "guideline_domain_id": row.get("guideline_domain_id"),
                }
            else:
                rule = by_rule[rule_id]
                if not rule["action_concept_id"] and row.get("action_concept_id"):
                    rule["action_concept_id"] = row["action_concept_id"]
                    rule["action_name"] = row.get("action_name")
                    rule["action_priority"] = row.get("action_priority", "routine")
                    rule["action_due_days"] = row.get("action_due_days")

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
        return {"rules": compiled_rules}

    def _seeds_from_criterion(
        self, criterion: dict[str, Any]
    ) -> list[dict[str, Any]]:
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

        excluded_ids = {str(x) for x in (criterion.get("excluded_concept_ids") or []) if x}
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
                    else (seed["distance_child"] if seed["distance_child"] is not None else 3)
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
            },
            "seed_concept_ids": sorted_ids,
        }

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

        action = None
        if rule_data.get("action_concept_id"):
            if (
                policy.allowed_concept_ids
                and policy.enforce_action_scope
                and str(rule_data["action_concept_id"])
                not in policy.allowed_concept_ids
            ):
                self._compile_stats["policy_violations"] += 1
                self._compile_stats["out_of_scope_actions"] += 1
                if policy.mode != "strict":
                    logger.warning(
                        "Action concept %s for rule %s is outside policy scope.",
                        rule_data["action_concept_id"],
                        rule_data["rule_id"],
                    )
            else:
                action = {
                    "concept_id": rule_data["action_concept_id"],
                    "name": rule_data.get("action_name"),
                    "priority": rule_data.get("action_priority") or "routine",
                    "due_days": rule_data.get("action_due_days"),
                }
        elif rule_data.get("action_json"):
            action_json = dict(rule_data["action_json"])
            if action_json.get("snomed_concept_id"):
                action = {
                    "concept_id": action_json["snomed_concept_id"],
                    "name": action_json.get("preferred_term")
                    or action_json.get("term"),
                    "priority": rule_data.get("action_priority") or "routine",
                    "due_days": rule_data.get("action_due_days"),
                }

        return {
            "rule_id": rule_data["rule_id"],
            "name": rule_data["name"],
            "strength": rule_data["strength"],
            "schema_version": 2,
            "guideline_id": rule_data["guideline_id"],
            "guideline_title": rule_data["guideline_title"],
            "guideline_domain_id": rule_data.get("guideline_domain_id"),
            "chapter_title": rule_data.get("chapter_title"),
            "recommendation_verbatim": rule_data["recommendation_verbatim"],
            "logic_tree": compiled_tree,
            "action": action,
        }

    def _compile_one_rule(
        self,
        rule_data: dict,
        groups: list[dict],
        *,
        policy: CompilePolicy,
    ) -> dict:
        """Build the compiled rule dict for a single rule.

        Args:
            rule_data: Intermediate rule dict with action metadata and applies_to.
            groups: List of ``{mode, bitmap_id}`` dicts, one per CriteriaGroup.

        Returns:
            Compiled rule dict with ``criteria_groups``, ``action``, and
            ``applies_to`` fields consumed by the evaluator.
        """
        action: dict | None = None
        if rule_data.get("action_concept_id"):
            if (
                policy.allowed_concept_ids
                and policy.enforce_action_scope
                and str(rule_data["action_concept_id"])
                not in policy.allowed_concept_ids
            ):
                self._compile_stats["policy_violations"] += 1
                self._compile_stats["out_of_scope_actions"] += 1
            else:
                action = {
                    "concept_id": rule_data["action_concept_id"],
                    "name": rule_data.get("action_name"),
                    "priority": rule_data.get("action_priority") or "routine",
                    "due_days": rule_data.get("action_due_days"),
                }

        return {
            "rule_id": rule_data["rule_id"],
            "name": rule_data["name"],
            "strength": rule_data["strength"],
            "schema_version": 1,
            "guideline_id": rule_data["guideline_id"],
            "guideline_title": rule_data["guideline_title"],
            "guideline_domain_id": rule_data.get("guideline_domain_id"),
            "chapter_title": rule_data.get("chapter_title"),
            "recommendation_verbatim": rule_data["recommendation_verbatim"],
            "criteria_groups": groups,
            "action": action,
            "applies_to": rule_data.get("applies_to") or [],
        }
