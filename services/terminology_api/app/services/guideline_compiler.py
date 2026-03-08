"""Offline compiler: reads active AppropriatenessRules from Neo4j and builds bitmaps.

The compile step is CPU-bound (pyroaring BitMap construction). It is run via
``asyncio.to_thread()`` so it does not block the async event loop.

Only rules with ``status: active`` are compiled. Rules with
``status: pending_review`` or ``status: rejected`` are silently excluded.
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
OPTIONAL MATCH (grp)-[hc:HAS_CRITERIA]->(concept)
OPTIONAL MATCH (rule)-[:HAS_ACTION_GROUP]->(ag:ActionGroup)-[ha:HAS_ACTION]->(proc:Procedure)
RETURN
    rule.id              AS rule_id,
    rule.name            AS name,
    rule.strength        AS strength,
    g.id                 AS guideline_id,
    g.title              AS guideline_title,
    rec.verbatim         AS recommendation_verbatim,
    grp.id               AS group_id,
    coalesce(grp.type, 'ALL') AS group_mode,
    hc.predicate         AS predicate,
    concept.conceptId    AS concept_id
ORDER BY rule.id, grp.id, concept.conceptId
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

    async def compile_and_store(self, version: str) -> dict:
        """Compile all active rules and store as a versioned ruleset.

        CPU-bound work runs in a thread pool to avoid blocking the event loop.

        Args:
            version: Version label for the new ruleset (e.g. ``v20260308-1``).

        Returns:
            Summary dict with ``version``, ``rule_count``, and ``compile_timestamp``.
        """
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
        finally:
            driver.close()

        return self._build_ruleset(records)

    def _build_ruleset(self, records: list[Any]) -> dict:
        """Transform raw Neo4j records into a serialisable ruleset.

        Args:
            records: Raw records from the Cypher query.

        Returns:
            Dict with a ``rules`` list, each rule containing bitmap IDs
            for ``req_all`` and ``forbid`` groups.
        """
        by_rule: dict[str, dict] = {}

        for row in records:
            rule_id = str(row["rule_id"])
            concept_id = row["concept_id"]
            if not concept_id:
                continue

            if rule_id not in by_rule:
                by_rule[rule_id] = {
                    "rule_id": rule_id,
                    "name": row["name"],
                    "strength": row["strength"],
                    "guideline_id": row["guideline_id"],
                    "guideline_title": row["guideline_title"],
                    "recommendation_verbatim": row.get("recommendation_verbatim", ""),
                    "req_all": [],
                    "forbid": [],
                }

            int_id = self._store.get_or_assign_int_id(str(concept_id))
            predicate = row.get("predicate", "PRESENT")
            if predicate == "ABSENT":
                by_rule[rule_id]["forbid"].append(int_id)
            else:
                by_rule[rule_id]["req_all"].append(int_id)

        compiled_rules = []
        for rule_data in by_rule.values():
            compiled = self._compile_one_rule(rule_data)
            compiled_rules.append(compiled)

        return {"rules": compiled_rules}

    def _compile_one_rule(self, rule_data: dict) -> dict:
        """Build bitmap IDs for a single rule.

        Args:
            rule_data: Intermediate rule dict with ``req_all`` and ``forbid``
                       integer ID lists.

        Returns:
            Rule dict with ``req_all_bitmap_id`` and ``forbid_bitmap_id`` set.
        """
        req_all_ids = sorted(set(rule_data["req_all"]))
        forbid_ids = sorted(set(rule_data["forbid"]))

        req_bitmap_id = self._store.put_bitmap(req_all_ids) if req_all_ids else None
        forbid_bitmap_id = self._store.put_bitmap(forbid_ids) if forbid_ids else None

        return {
            "rule_id": rule_data["rule_id"],
            "name": rule_data["name"],
            "strength": rule_data["strength"],
            "guideline_id": rule_data["guideline_id"],
            "guideline_title": rule_data["guideline_title"],
            "recommendation_verbatim": rule_data["recommendation_verbatim"],
            "req_all_bitmap_id": req_bitmap_id,
            "forbid_bitmap_id": forbid_bitmap_id,
        }
