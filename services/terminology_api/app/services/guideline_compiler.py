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
import logging
import os
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase

from services.terminology_api.app.services.bitmap_store import BitmapStore

logger = logging.getLogger(__name__)

_FETCH_ACTIVE_RULES = """
MATCH (g:Guideline)-[:HAS_RECOMMENDATION]->(rec:Recommendation)
    -[:HAS_RULE]->(rule:AppropriatenessRule {status: 'active'})
    -[:HAS_CRITERIA_GROUP]->(grp:CriteriaGroup)
OPTIONAL MATCH (rec)<-[:HAS_RECOMMENDATION]-(ch:Chapter)
OPTIONAL MATCH (grp)-[hc:HAS_CRITERIA]->(concept)
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(ag:ActionGroup)-[ha:HAS_ACTION]->(proc:Procedure)
RETURN
    rule.id              AS rule_id,
    rule.name            AS name,
    rule.strength        AS strength,
    g.id                 AS guideline_id,
    g.title              AS guideline_title,
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

# Separate query for APPLIES_TO demographic constraints — fetched once per
# compile run and merged into the compiled rules by rule_id.
_FETCH_APPLIES_TO = """
MATCH (rule:AppropriatenessRule {status: 'active'})-[at:APPLIES_TO]->(concept:SnomedConcept)
RETURN
    rule.id              AS rule_id,
    concept.conceptId    AS concept_id,
    concept.term         AS preferred_term,
    concept.semanticTag  AS semantic_tag,
    at.rawTerm           AS raw_term,
    at.operator          AS operator,
    at.value             AS value,
    at.unit              AS unit
ORDER BY rule.id, concept.conceptId
"""

# SNOMED IS_A closure query — returns the target concept plus all descendants
# within ``d_child`` hops and all ancestors within ``d_parent`` hops.
# Gracefully returns only the target if no IS_A relationships are present.
_SNOMED_CLOSURE = """
MATCH (t:SnomedConcept {conceptId: $concept_id})
WITH t
OPTIONAL MATCH (d:SnomedConcept)-[:IS_A*1..%(dc)d]->(t)
OPTIONAL MATCH (t)-[:IS_A*1..%(dp)d]->(a:SnomedConcept)
WITH
    collect(DISTINCT t.conceptId) +
    collect(DISTINCT d.conceptId) +
    collect(DISTINCT a.conceptId) AS ids
UNWIND ids AS x
WITH DISTINCT x WHERE x IS NOT NULL
RETURN x AS concept_id
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

    def __init__(self, store: BitmapStore | None = None) -> None:
        self._store = store or BitmapStore()
        # Cache closure results so each (concept_id, d_child, d_parent) triple
        # is only queried once per compilation run.
        self._closure_cache: dict[tuple, list[str]] = {}

    async def compile_and_store(self, version: str) -> dict:
        """Compile all active rules and store as a versioned ruleset.

        CPU-bound work runs in a thread pool to avoid blocking the event loop.

        Args:
            version: Version label for the new ruleset (e.g. ``v20260308-1``).

        Returns:
            Summary dict with ``version``, ``rule_count``, and ``compile_timestamp``.
        """
        self._closure_cache.clear()
        ruleset = await asyncio.to_thread(self._compile_ruleset)
        ruleset["version"] = version
        ruleset["compile_timestamp"] = datetime.now(timezone.utc).isoformat()
        self._store.write_ruleset(version, ruleset)
        self._store.set_current_version(version)
        logger.info(
            "Compiled ruleset %s: %d rules", version, len(ruleset.get("rules", []))
        )
        return {
            "version": version,
            "rule_count": len(ruleset.get("rules", [])),
            "compile_timestamp": ruleset["compile_timestamp"],
        }

    def _compile_ruleset(self) -> dict:
        """Synchronous ruleset compilation -- runs in thread pool."""
        driver = _kg_driver()
        try:
            with driver.session() as session:
                records = list(session.run(_FETCH_ACTIVE_RULES))
                applies_to_records = list(session.run(_FETCH_APPLIES_TO))
                return self._build_ruleset(records, session, applies_to_records)
        finally:
            driver.close()

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
            parts.append(
                f"OPTIONAL MATCH (d:SnomedConcept)-[:IS_A*1..{dc}]->(t)"
            )
            collect_parts.append("collect(DISTINCT d.conceptId)")
        if dp > 0:
            parts.append(
                f"OPTIONAL MATCH (t)-[:IS_A*1..{dp}]->(a:SnomedConcept)"
            )
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
                concept_id, dc, dp, exc,
            )
            result = [concept_id]

        self._closure_cache[cache_key] = result
        return result

    def _build_ruleset(
        self,
        records: list[Any],
        session,
        applies_to_records: list[Any] | None = None,
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
        by_rule: dict[str, dict] = {}
        by_group: dict[str, dict] = {}  # group_id → {rule_id, mode, int_ids}

        for row in records:
            rule_id = str(row["rule_id"])
            group_id = str(row["group_id"]) if row.get("group_id") else None
            concept_id = row.get("concept_id")

            if rule_id not in by_rule:
                by_rule[rule_id] = {
                    "rule_id":                 rule_id,
                    "name":                    row["name"],
                    "strength":                row["strength"],
                    "guideline_id":            row["guideline_id"],
                    "guideline_title":         row["guideline_title"],
                    "chapter_title":           row.get("chapter_title"),
                    "recommendation_verbatim": row.get("recommendation_verbatim", ""),
                    "group_ids_ordered":       [],  # preserves insertion order
                    "applies_to":              [],
                    "action_concept_id": row.get("action_concept_id"),
                    "action_name":       row.get("action_name"),
                    "action_priority":   row.get("action_priority", "routine"),
                    "action_due_days":   row.get("action_due_days"),
                }
            else:
                rule = by_rule[rule_id]
                if not rule["action_concept_id"] and row.get("action_concept_id"):
                    rule["action_concept_id"] = row["action_concept_id"]
                    rule["action_name"]        = row.get("action_name")
                    rule["action_priority"]    = row.get("action_priority", "routine")
                    rule["action_due_days"]    = row.get("action_due_days")

            if not group_id:
                continue

            if group_id not in by_group:
                raw_mode  = str(row.get("group_mode") or "ALL").upper()
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

            d_child  = int(row.get("distance_child")  or 0)
            d_parent = int(row.get("distance_parent") or 0)
            closure  = self._closure_ids(session, str(concept_id), d_child, d_parent)
            int_ids  = [self._store.get_or_assign_int_id(cid) for cid in closure]
            by_group[group_id]["int_ids"].extend(int_ids)

        # Merge APPLIES_TO demographic constraints into their rules
        for row in (applies_to_records or []):
            rule_id = str(row["rule_id"])
            if rule_id not in by_rule:
                continue
            concept_id = row.get("concept_id")
            operator   = row.get("operator")
            value      = row.get("value")
            if not concept_id or not operator:
                continue
            by_rule[rule_id]["applies_to"].append({
                "concept_id":    concept_id,
                "preferred_term": row.get("preferred_term", ""),
                "semantic_tag":  row.get("semantic_tag", ""),
                "raw_term":      row.get("raw_term", ""),
                "operator":      operator,
                "value":         float(value) if value is not None else None,
                "unit":          row.get("unit"),
            })

        compiled_rules = []
        for rule_data in by_rule.values():
            groups = []
            for gid in rule_data["group_ids_ordered"]:
                g = by_group[gid]
                int_ids = sorted(set(g["int_ids"]))
                if int_ids:
                    bitmap_id = self._store.put_bitmap(int_ids)
                    groups.append({"mode": g["mode"], "bitmap_id": bitmap_id})

            if groups or rule_data["applies_to"]:
                compiled_rules.append(self._compile_one_rule(rule_data, groups))
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

        return {"rules": compiled_rules}

    def _compile_one_rule(self, rule_data: dict, groups: list[dict]) -> dict:
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
            action = {
                "concept_id": rule_data["action_concept_id"],
                "name":       rule_data.get("action_name"),
                "priority":   rule_data.get("action_priority") or "routine",
                "due_days":   rule_data.get("action_due_days"),
            }

        return {
            "rule_id":                 rule_data["rule_id"],
            "name":                    rule_data["name"],
            "strength":                rule_data["strength"],
            "guideline_id":            rule_data["guideline_id"],
            "guideline_title":         rule_data["guideline_title"],
            "chapter_title":           rule_data.get("chapter_title"),
            "recommendation_verbatim": rule_data["recommendation_verbatim"],
            "criteria_groups":         groups,
            "action":                  action,
            "applies_to":              rule_data.get("applies_to") or [],
        }
