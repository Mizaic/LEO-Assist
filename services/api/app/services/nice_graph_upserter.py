"""Idempotent Neo4j upsert for NICE guideline content.

Stores Guideline, Chapter, and Recommendation nodes in the knowledge graph,
preserving the chapter hierarchy from the NICE Syndication API.

Graph model:
    (Guideline)-[:HAS_CHAPTER]->(Chapter)-[:HAS_RECOMMENDATION]->(Recommendation)
    (Guideline)-[:HAS_RECOMMENDATION]->(Recommendation)   # shortcut for backwards-compat queries

No LLM. All data comes directly from the NICE Syndication API JSON.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

_UPSERT_GUIDELINE = """
MERGE (g:Guideline {id: $id})
ON CREATE SET
    g.code          = $code,
    g.title         = $title,
    g.guidanceNumber = $guidance_number,
    g.type          = $guidance_type,
    g.publicationDate = $pub_date,
    g.source        = 'nice_syndication_api',
    g.createdAt     = datetime()
ON MATCH SET
    g.title         = $title,
    g.updatedAt     = datetime()
RETURN g.id AS id
"""

_CLEAR_GUIDELINE_CONTENT = """
MATCH (g:Guideline {id: $guideline_id})
OPTIONAL MATCH (g)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (g)-[:HAS_RECOMMENDATION]->(r:Recommendation)
OPTIONAL MATCH (r)-[:HAS_RULE]->(rule:AppropriatenessRule)
OPTIONAL MATCH (rule)-[:HAS_CRITERIA_GROUP]->(grp)
OPTIONAL MATCH (g)-[:HAS_SECTION]->(s:Section)
DETACH DELETE ch, r, s, rule, grp
"""

_UPSERT_CHAPTER = """
MATCH (g:Guideline {id: $guideline_id})
MERGE (ch:Chapter {id: $id})
ON CREATE SET
    ch.title     = $title,
    ch.order     = $order,
    ch.source    = 'nice_syndication_api',
    ch.createdAt = datetime()
ON MATCH SET
    ch.title     = $title,
    ch.updatedAt = datetime()
MERGE (g)-[:HAS_CHAPTER]->(ch)
RETURN ch.id AS id
"""

_UPSERT_RECOMMENDATION = """
MATCH (g:Guideline {id: $guideline_id})
MERGE (r:Recommendation {id: $id})
ON CREATE SET
    r.verbatim      = $verbatim,
    r.title         = $title,
    r.number        = $number,
    r.urgency       = $urgency,
    r.strength      = $strength,
    r.source        = 'nice_syndication_api',
    r.status        = 'loaded',
    r.createdAt     = datetime()
ON MATCH SET
    r.verbatim      = $verbatim,
    r.title         = $title,
    r.number        = $number,
    r.updatedAt     = datetime()
MERGE (g)-[:HAS_RECOMMENDATION]->(r)
WITH r
FOREACH (ch_id IN CASE WHEN $chapter_id IS NOT NULL THEN [$chapter_id] ELSE [] END |
    MERGE (ch:Chapter {id: ch_id})
    MERGE (ch)-[:HAS_RECOMMENDATION]->(r)
)
RETURN r.id AS id
"""

_UPSERT_TAXONOMY_CATEGORY = """
MERGE (c:TaxonomyCategory {id: $id})
ON CREATE SET
    c.title     = $title,
    c.source    = 'nice_api',
    c.syncedAt  = datetime()
ON MATCH SET
    c.title     = $title,
    c.syncedAt  = datetime()
RETURN c.id AS id
"""

_UPSERT_TAXONOMY_SUBCATEGORY = """
MERGE (s:TaxonomySubcategory {id: $id})
ON CREATE SET
    s.title          = $title,
    s.niceUri        = $nice_uri,
    s.categoryId     = $category_id,
    s.source         = 'nice_api',
    s.guidelineCodes = $guideline_codes,
    s.syncedAt       = datetime()
ON MATCH SET
    s.title          = $title,
    s.guidelineCodes = $guideline_codes,
    s.syncedAt       = datetime()
WITH s
MATCH (c:TaxonomyCategory {id: $category_id})
MERGE (c)-[:HAS_SUBCATEGORY]->(s)
RETURN s.id AS id
"""

_UPSERT_NICE_AUDIT_DOMAIN = """
MERGE (d:AuditDomain {id: $id})
ON CREATE SET
    d.name              = $name,
    d.description       = $description,
    d.source            = 'nice',
    d.niceSubcategoryId = $subcategory_id,
    d.createdAt         = datetime()
ON MATCH SET
    d.syncedAt          = datetime()
WITH d
MATCH (s:TaxonomySubcategory {id: $subcategory_id})
MERGE (s)-[:HAS_DOMAIN]->(d)
RETURN d.id AS id
"""

_LINK_GUIDELINE_TO_SUBCATEGORY = """
MATCH (s:TaxonomySubcategory {id: $subcategory_id})
MATCH (g:Guideline {id: $guideline_code})
MERGE (s)-[:CLASSIFIES_GUIDELINE]->(g)
"""


def _kg_driver():
    """Return a synchronous Neo4j driver for the knowledge graph."""
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    return GraphDatabase.driver(uri, auth=(user, password))


class NiceGraphUpserter:
    """Idempotent MERGE operations for NICE guideline nodes in Neo4j.

    Preserves the NICE API chapter hierarchy:
        Guideline → Chapter → Recommendation

    A shortcut Guideline→Recommendation edge is also created so existing
    Cypher queries that traverse HAS_RECOMMENDATION from the guideline continue
    to work without modification.

    All operations are safe to call multiple times -- duplicate calls
    update the existing node rather than creating a second one.
    """

    def upsert_guideline(self, guidance_json: dict[str, Any]) -> str:
        """Store a Guideline node from the NICE API document JSON.

        Args:
            guidance_json: Top-level guidance document dict from the NICE API.

        Returns:
            The guideline node ID (normalised NICE code, upper-case).
        """
        code = _extract_code(guidance_json)
        params = {
            "id": code,
            "code": code,
            "title": guidance_json.get("Title", ""),
            "guidance_number": guidance_json.get("GuidanceNumber", code),
            "guidance_type": guidance_json.get("Type", ""),
            "pub_date": guidance_json.get("PublicationDate", ""),
        }
        driver = _kg_driver()
        try:
            with driver.session() as session:
                result = session.run(_UPSERT_GUIDELINE, **params)
                record = result.single()
                return record["id"] if record else code
        finally:
            driver.close()

    def clear_guideline_content(self, guideline_id: str) -> None:
        """Delete all Chapter, Recommendation, Section, and derived Rule nodes.

        Called before re-ingesting to avoid stale data. Cascade-deletes:
        - Chapter nodes (and their HAS_RECOMMENDATION edges)
        - Recommendation nodes (and any linked AppropriatenessRule + CriteriaGroup)
        - Legacy Section nodes from the old flat schema

        The Guideline node itself is preserved.

        Args:
            guideline_id: Guideline node ID (e.g. ``NG12``).
        """
        driver = _kg_driver()
        try:
            with driver.session() as session:
                session.run(_CLEAR_GUIDELINE_CONTENT, guideline_id=guideline_id)
        finally:
            driver.close()
        logger.info("Cleared existing content for guideline %s", guideline_id)

    def upsert_chapter(
        self, guideline_id: str, chapter_id: str, title: str, order: int
    ) -> str:
        """Store a Chapter node linked to its parent Guideline.

        Chapters correspond to top-level resources (rel=chapter) in the NICE
        API document. Each chapter becomes a first-class node so that
        Recommendations can be scoped to their clinical context.

        Args:
            guideline_id: Parent guideline node ID.
            chapter_id: Stable chapter identifier (e.g. ``NG12:CH000``).
            title: Chapter title from the NICE API.
            order: Position of this chapter within the guideline.

        Returns:
            The chapter node ID.
        """
        params = {
            "guideline_id": guideline_id,
            "id": chapter_id,
            "title": title,
            "order": order,
        }
        driver = _kg_driver()
        try:
            with driver.session() as session:
                result = session.run(_UPSERT_CHAPTER, **params)
                record = result.single()
                return record["id"] if record else chapter_id
        finally:
            driver.close()

    def upsert_recommendation(
        self,
        guideline_id: str,
        rec_id: str,
        rec: dict[str, Any],
        chapter_id: str | None = None,
    ) -> str:
        """Store a Recommendation node linked to its Guideline and Chapter.

        Creates two edges:
        - ``(Guideline)-[:HAS_RECOMMENDATION]->(Recommendation)`` — always
        - ``(Chapter)-[:HAS_RECOMMENDATION]->(Recommendation)`` — when chapter_id given

        Args:
            guideline_id: Parent guideline node ID.
            rec_id: Stable recommendation identifier (e.g. ``NG12:CH000:R003``).
            rec: Recommendation dict from the NICE API chapter Items.
            chapter_id: Optional parent chapter node ID.

        Returns:
            The recommendation node ID.
        """
        # NICE leaf items: Title holds the recommendation number (e.g. "1.1.1.1"),
        # Text holds the full recommendation wording.
        verbatim = rec.get("Text", rec.get("Title", ""))
        title = rec.get("Title", "")
        params = {
            "guideline_id": guideline_id,
            "id": rec_id,
            "verbatim": verbatim,
            "title": title,
            "number": title,  # recommendation number (e.g. "1.1.1.1")
            "urgency": _extract_urgency(rec),
            "strength": _extract_strength(rec),
            "chapter_id": chapter_id,
        }
        driver = _kg_driver()
        try:
            with driver.session() as session:
                result = session.run(_UPSERT_RECOMMENDATION, **params)
                record = result.single()
                return record["id"] if record else rec_id
        finally:
            driver.close()

    def upsert_taxonomy(self, taxonomy_entries: list[dict[str, Any]]) -> dict[str, int]:
        """Persist NICE taxonomy hierarchy as Neo4j nodes.

        Creates or updates TaxonomyCategory, TaxonomySubcategory, and AuditDomain
        (source='nice') nodes from the flat list returned by
        :meth:`NiceApiClient.fetch_taxonomy`.

        Args:
            taxonomy_entries: Flat list of taxonomy dicts each containing
                ``category_id``, ``category_title``, ``subcategory_id``,
                ``subcategory_title``, ``subcategory_uri``, and
                ``guideline_codes`` keys.

        Returns:
            Dict with ``categories``, ``subcategories``, and ``domains`` counts.
        """
        seen_cats: set[str] = set()
        counts: dict[str, int] = {"categories": 0, "subcategories": 0, "domains": 0}
        driver = _kg_driver()
        try:
            with driver.session() as session:
                for entry in taxonomy_entries:
                    cat_id = entry["category_id"]
                    cat_title = entry["category_title"]
                    sub_id = entry["subcategory_id"]
                    sub_title = entry["subcategory_title"]
                    sub_uri = entry.get("subcategory_uri", "")
                    guideline_codes = entry.get("guideline_codes", [])

                    if cat_id not in seen_cats:
                        session.run(
                            _UPSERT_TAXONOMY_CATEGORY,
                            id=cat_id,
                            title=cat_title,
                        )
                        seen_cats.add(cat_id)
                        counts["categories"] += 1

                    session.run(
                        _UPSERT_TAXONOMY_SUBCATEGORY,
                        id=sub_id,
                        title=sub_title,
                        nice_uri=sub_uri,
                        category_id=cat_id,
                        guideline_codes=guideline_codes,
                    )
                    counts["subcategories"] += 1

                    domain_id = f"nice:{sub_id}"
                    session.run(
                        _UPSERT_NICE_AUDIT_DOMAIN,
                        id=domain_id,
                        name=sub_title,
                        description=f"NICE guidelines area: {cat_title} > {sub_title}",
                        subcategory_id=sub_id,
                    )
                    counts["domains"] += 1

                    for code in guideline_codes:
                        try:
                            session.run(
                                _LINK_GUIDELINE_TO_SUBCATEGORY,
                                subcategory_id=sub_id,
                                guideline_code=code,
                            )
                        except Exception:
                            logger.debug(
                                "Could not link guideline %s to subcategory %s",
                                code,
                                sub_id,
                            )
        finally:
            driver.close()

        logger.info(
            "Taxonomy upsert: %d categories, %d subcategories, %d domains",
            counts["categories"],
            counts["subcategories"],
            counts["domains"],
        )
        return counts


def _extract_code(guidance_json: dict[str, Any]) -> str:
    """Return the normalised NICE code from a guidance document."""
    return (
        guidance_json.get("GuidanceNumber")
        or guidance_json.get("Code")
        or "UNKNOWN"
    ).upper()


def _extract_urgency(rec: dict[str, Any]) -> str:
    """Extract urgency label from a recommendation dict."""
    title = rec.get("Title", "").lower()
    text = rec.get("Text", "").lower()
    combined = title + " " + text
    if "2-week" in combined or "2ww" in combined or "urgent" in combined:
        return "urgent_2w"
    if "immediate" in combined:
        return "immediate"
    return "routine"


def _extract_strength(rec: dict[str, Any]) -> str:
    """Extract recommendation strength from a recommendation dict."""
    title = rec.get("Title", "").lower()
    text = rec.get("Text", "").lower()
    combined = title + " " + text
    if "refer" in combined:
        return "refer"
    if "consider" in combined:
        return "consider"
    return "offer"
