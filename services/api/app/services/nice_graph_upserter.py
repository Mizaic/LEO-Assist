"""Idempotent Neo4j upsert for NICE guideline content.

Versioning model
----------------
Every ingest of a guideline creates a new **ingest version** (v1, v2 ...).
Version-scoped IDs ensure old nodes are never overwritten:

    Chapter:        ``NG12:v1:CH000``
    Recommendation: ``NG12:v1:CH000:R000``

When a guideline is re-ingested:

  1. Active/pending AppropriatenessRule nodes are marked ``superseded`` and
     a copy of their parent recommendation text is stored on the rule so that
     diffs can be computed without traversing the old recommendation node.
  2. The ``Guideline→HAS_CHAPTER`` and ``Guideline→HAS_RECOMMENDATION``
     shortcut edges are *detached* (not deleted) so old Chapter and
     Recommendation nodes remain reachable for audit queries.
  3. Old ``GuidanceAuditEvent`` nodes are **never touched** — they are
     permanently linked to the specific AppropriatenessRule version on which
     the human decision was made.
  4. New Chapter and Recommendation nodes (v2 …) are created with the
     shortcut edges re-attached.

This means:
  - The bitmap compiler (``Guideline→HAS_RECOMMENDATION→Recommendation``)
    always sees only the *current* version.
  - Audit queries can reach old decisions through the ``SUPERSEDES`` chain.

Graph model
-----------
::

    (:Guideline {ingestVersion: N, currentVersionId: "NG12:vN"})
      -[:HAS_CHAPTER]->  (:Chapter {id: "NG12:vN:CH000"})          # current
      -[:HAS_RECOMMENDATION]-> (:Recommendation {id: "NG12:vN:CH000:R000"})  # current shortcut

    (:Chapter {id: "NG12:vN:CH000"})
      -[:HAS_RECOMMENDATION]-> (:Recommendation {id: "NG12:vN:CH000:R000"})

    (:Recommendation {id: "NG12:vN:CH000:R000"})
      -[:HAS_RULE]-> (:AppropriatenessRule {status: 'pending_review'})
                       -[:SUPERSEDES]-> (:AppropriatenessRule {status: 'superseded'})
                                          -[:HAS_AUDIT_EVENT]-> (:GuidanceAuditEvent)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

# ── Guideline ──────────────────────────────────────────────────────────────

_UPSERT_GUIDELINE = """
MERGE (g:Guideline {id: $id})
ON CREATE SET
    g.code            = $code,
    g.title           = $title,
    g.guidanceNumber  = $guidance_number,
    g.type            = $guidance_type,
    g.publicationDate = $pub_date,
    g.source          = 'nice_syndication_api',
    g.ingestVersion   = 1,
    g.createdAt       = datetime()
ON MATCH SET
    g.title           = $title,
    g.ingestVersion   = coalesce(g.ingestVersion, 0) + 1,
    g.updatedAt       = datetime()
RETURN g.id AS id, g.ingestVersion AS version
"""

# ── Versioning: supersede old rules, detach old content links ─────────────

_SUPERSEDE_EXISTING_RULES = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
      -[:HAS_RULE]->(rule:AppropriatenessRule)
WHERE rule.status IN ['active', 'pending_review']
SET rule.status                        = 'superseded',
    rule.supersededAt                   = datetime(),
    rule.supersededByGuidelineId        = $guideline_id,
    rule.previousRecommendationText     = r.verbatim,
    rule.previousRecommendationNumber   = r.number
RETURN count(rule) AS superseded_count
"""

_DETACH_GUIDELINE_CONTENT_LINKS = """
MATCH (g:Guideline {id: $guideline_id})
OPTIONAL MATCH (g)-[hch:HAS_CHAPTER]->(ch)
OPTIONAL MATCH (g)-[hr:HAS_RECOMMENDATION]->(r)
DELETE hch, hr
"""

# ── Chapter ────────────────────────────────────────────────────────────────

_UPSERT_CHAPTER = """
MATCH (g:Guideline {id: $guideline_id})
MERGE (ch:Chapter {id: $id})
ON CREATE SET
    ch.title          = $title,
    ch.order          = $order,
    ch.guidelineId    = $guideline_id,
    ch.versionId      = $version_id,
    ch.source         = 'nice_syndication_api',
    ch.createdAt      = datetime()
ON MATCH SET
    ch.title          = $title,
    ch.updatedAt      = datetime()
MERGE (g)-[:HAS_CHAPTER]->(ch)
RETURN ch.id AS id
"""

# ── Recommendation ─────────────────────────────────────────────────────────

_UPSERT_RECOMMENDATION = """
MATCH (g:Guideline {id: $guideline_id})
MERGE (r:Recommendation {id: $id})
ON CREATE SET
    r.verbatim        = $verbatim,
    r.title           = $title,
    r.number          = $number,
    r.urgency         = $urgency,
    r.strength        = $strength,
    r.sectionTitle    = $section_title,
    r.isNormative     = $is_normative,
    r.guidelineId     = $guideline_id,
    r.versionId       = $version_id,
    r.source          = 'nice_syndication_api',
    r.status          = 'loaded',
    r.createdAt       = datetime()
ON MATCH SET
    r.verbatim        = $verbatim,
    r.title           = $title,
    r.number          = $number,
    r.sectionTitle    = $section_title,
    r.isNormative     = $is_normative,
    r.updatedAt       = datetime()
MERGE (g)-[:HAS_RECOMMENDATION]->(r)
WITH r
FOREACH (ch_id IN CASE WHEN $chapter_id IS NOT NULL THEN [$chapter_id] ELSE [] END |
    MERGE (ch:Chapter {id: ch_id})
    MERGE (ch)-[:HAS_RECOMMENDATION]->(r)
)
RETURN r.id AS id
"""

# ── Taxonomy ───────────────────────────────────────────────────────────────

_UPSERT_TAXONOMY_CATEGORY = """
MERGE (c:TaxonomyCategory {id: $id})
ON CREATE SET
    c.title    = $title,
    c.source   = 'nice_api',
    c.syncedAt = datetime()
ON MATCH SET
    c.title    = $title,
    c.syncedAt = datetime()
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

    Versioning contract
    -------------------
    ``upsert_guideline()`` returns ``(guideline_id, version_number)``.
    Callers must embed ``version_number`` in all subsequent Chapter and
    Recommendation IDs so that each ingest produces distinct nodes.

    ``clear_guideline_content()`` preserves historical nodes:
    - AppropriatenessRule nodes are marked ``superseded`` (never deleted).
    - GuidanceAuditEvent nodes are untouched.
    - Chapter and Recommendation nodes are detached from the Guideline
      shortcut edges but remain in the graph for audit queries.
    """

    def upsert_guideline(self, guidance_json: dict[str, Any]) -> tuple[str, int]:
        """Store a Guideline node and return its ID and new ingest version.

        The ``ingestVersion`` counter on the Guideline node increments on every
        ingest so callers can construct version-scoped IDs for child nodes.

        Args:
            guidance_json: Top-level guidance document dict from the NICE API.

        Returns:
            Tuple of ``(guideline_id, ingest_version)`` where ``ingest_version``
            is the new version number (1 for first ingest, 2 for re-ingest …).
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
                if record:
                    return str(record["id"]), int(record["version"])
                return code, 1
        finally:
            driver.close()

    def clear_guideline_content(self, guideline_id: str) -> int:
        """Archive existing content so old audit decisions are preserved.

        Two-step approach:
          1. Mark active/pending AppropriatenessRule nodes as ``superseded``.
             Copies the parent recommendation verbatim text onto the rule so
             that diffs can be computed later without needing the old node.
          2. Detach ``HAS_CHAPTER`` and ``HAS_RECOMMENDATION`` edges from the
             Guideline node.  The Chapter and Recommendation nodes remain in
             the graph — they are the authoritative context for every
             GuidanceAuditEvent that referenced them.

        Args:
            guideline_id: Guideline node ID (e.g. ``NG12``).

        Returns:
            Number of AppropriatenessRule nodes marked superseded.
        """
        driver = _kg_driver()
        try:
            with driver.session() as session:
                result = session.run(
                    _SUPERSEDE_EXISTING_RULES, guideline_id=guideline_id
                )
                record = result.single()
                superseded = int(record["superseded_count"]) if record else 0
                session.run(_DETACH_GUIDELINE_CONTENT_LINKS, guideline_id=guideline_id)
        finally:
            driver.close()
        logger.info(
            "Guideline %s: archived content for re-ingest (%d rule(s) superseded)",
            guideline_id,
            superseded,
        )
        return superseded

    def upsert_chapter(
        self,
        guideline_id: str,
        chapter_id: str,
        title: str,
        order: int,
        version_id: str = "",
    ) -> str:
        """Store a Chapter node linked to its parent Guideline.

        Args:
            guideline_id: Parent guideline node ID.
            chapter_id: Version-scoped identifier (e.g. ``NG12:v2:CH000``).
            title: Chapter title from the NICE API.
            order: Position of this chapter within the guideline.
            version_id: Version string for provenance (e.g. ``NG12:v2``).

        Returns:
            The chapter node ID.
        """
        driver = _kg_driver()
        try:
            with driver.session() as session:
                result = session.run(
                    _UPSERT_CHAPTER,
                    guideline_id=guideline_id,
                    id=chapter_id,
                    title=title,
                    order=order,
                    version_id=version_id,
                )
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
        version_id: str = "",
    ) -> str:
        """Store a Recommendation node linked to Guideline and Chapter.

        Creates two edges:
        - ``(Guideline)-[:HAS_RECOMMENDATION]->(Recommendation)`` — shortcut for
          the bitmap compiler.
        - ``(Chapter)-[:HAS_RECOMMENDATION]->(Recommendation)`` — when
          ``chapter_id`` is supplied.

        The ``sectionTitle`` property captures the cancer-site / topic label from
        the NICE section heading (e.g. "Lung cancer", "Oesophageal cancer").
        This is read from ``rec["SectionTitle"]`` when present.

        Args:
            guideline_id: Parent guideline node ID.
            rec_id: Version-scoped identifier (e.g. ``NG12:v2:CH000:R003``).
            rec: Recommendation dict from the NICE API chapter Items.
            chapter_id: Optional parent chapter node ID.
            version_id: Version string for provenance (e.g. ``NG12:v2``).

        Returns:
            The recommendation node ID.
        """
        verbatim = rec.get("Text", rec.get("Title", ""))
        title = rec.get("Title", "")
        section_title = rec.get("SectionTitle", "")
        is_normative = bool(rec.get("isNormative", False))
        driver = _kg_driver()
        try:
            with driver.session() as session:
                result = session.run(
                    _UPSERT_RECOMMENDATION,
                    guideline_id=guideline_id,
                    id=rec_id,
                    verbatim=verbatim,
                    title=title,
                    number=title,
                    urgency=_extract_urgency(rec),
                    strength=_extract_strength(rec),
                    section_title=section_title,
                    is_normative=is_normative,
                    chapter_id=chapter_id,
                    version_id=version_id,
                )
                record = result.single()
                return record["id"] if record else rec_id
        finally:
            driver.close()

    def upsert_taxonomy(self, taxonomy_entries: list[dict[str, Any]]) -> dict[str, int]:
        """Persist NICE taxonomy hierarchy as Neo4j nodes.

        Args:
            taxonomy_entries: Flat list of taxonomy dicts from
                :meth:`NiceApiClient.fetch_taxonomy`.

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
    return (
        guidance_json.get("GuidanceNumber") or guidance_json.get("Code") or "UNKNOWN"
    ).upper()


def _extract_urgency(rec: dict[str, Any]) -> str:
    combined = (rec.get("Title", "") + " " + rec.get("Text", "")).lower()
    if "2-week" in combined or "2ww" in combined or "urgent" in combined:
        return "urgent_2w"
    if "immediate" in combined:
        return "immediate"
    return "routine"


def _extract_strength(rec: dict[str, Any]) -> str:
    combined = (rec.get("Title", "") + " " + rec.get("Text", "")).lower()
    if "refer" in combined:
        return "refer"
    if "consider" in combined:
        return "consider"
    return "offer"
