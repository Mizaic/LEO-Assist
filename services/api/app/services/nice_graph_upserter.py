"""Idempotent Neo4j upsert for NICE guideline content.

Atlas trace:
  DO: DO-24AA8840
  DI: DI-693FFEEA
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-24AA8840")

Versioning model
----------------
Every ingest of a guideline creates a new **ingest version** (v1, v2 ...).
Version-scoped IDs ensure old nodes are never overwritten:

    Chapter:        ``NG12:v1:CH000``
    Recommendation: ``NG12:v1:CH000:R000``

When a guideline is re-ingested:

  1. Pending (not yet approved) AppropriatenessRule nodes are marked
     ``superseded`` and a copy of their parent recommendation text is
     stored on the rule so that diffs can be computed without traversing
     the old recommendation node. Approved (``active``) rules are NEVER
     superseded by ingest -- they stay active and are only flagged
     (``guidelineTextChanged=true``) with the same previous-text copy, so
     a human explicitly decides whether to re-approve, edit, or retire
     them. See ``clear_guideline_content()``.
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

import json
import logging
import os
import uuid
from typing import Any

from app.services.nice_api_client import parse_nice_ms_date

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

# ── Guideline ──────────────────────────────────────────────────────────────

_UPSERT_GUIDELINE = """
MERGE (g:Guideline {id: $id})
ON CREATE SET
    g.code             = $code,
    g.title            = $title,
    g.guidanceNumber   = $guidance_number,
    g.type             = $guidance_type,
    g.publicationDate  = $pub_date,
    g.lastModifiedDate = $last_modified_date,
    g.source           = 'nice_syndication_api',
    g.ingestVersion    = 1,
    g.createdAt        = datetime()
ON MATCH SET
    g.title            = $title,
    g.publicationDate  = $pub_date,
    g.lastModifiedDate = $last_modified_date,
    g.ingestVersion    = coalesce(g.ingestVersion, 0) + 1,
    g.updatedAt        = datetime()
RETURN g.id AS id, g.ingestVersion AS version
"""

# ── Versioning: supersede old rules, detach old content links ─────────────

# Only PENDING (not-yet-approved) rules are ever superseded by an ingest.
# An APPROVED (status='active') rule represents a human clinical sign-off;
# a guideline re-ingest must never retire it silently. See
# _FLAG_ACTIVE_RULES_FOR_REVIEW / _SELECTIVE_FLAG_ACTIVE_RULES below --
# active rules whose recommendation changed stay active (still enforced,
# no coverage gap) and are only *flagged* so a human can choose to
# re-approve, edit, or explicitly retire them.
# Atlas: DI-C2DE7FDF / DO-F8CDEBBA / R-02B6E3E3 / VT-34F3B9C2
_SUPERSEDE_EXISTING_RULES = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
      -[:HAS_RULE]->(rule:AppropriatenessRule)
WHERE rule.status = 'pending_review'
SET rule.status                        = 'superseded',
    rule.supersededAt                   = datetime(),
    rule.supersededByGuidelineId        = $guideline_id,
    rule.previousRecommendationText     = r.verbatim,
    rule.previousRecommendationNumber   = r.number
RETURN count(rule) AS superseded_count
"""

# Smart variant: only supersede rules for recommendations whose text changed.
_SELECTIVE_SUPERSEDE_RULES = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
      -[:HAS_RULE]->(rule:AppropriatenessRule)
WHERE r.number IN $changed_numbers
  AND rule.status = 'pending_review'
SET rule.status                      = 'superseded',
    rule.supersededAt                 = datetime(),
    rule.supersededByGuidelineId      = $guideline_id,
    rule.previousRecommendationText   = r.verbatim,
    rule.previousRecommendationNumber = r.number
RETURN count(rule) AS superseded_count
"""

# An already-approved rule is never superseded by ingest. Instead it is
# flagged (status stays 'active', so it keeps being compiled/enforced)
# so a reviewer can see the guideline text moved underneath it and
# decide whether to re-approve, edit, or explicitly retire it.
_FLAG_ACTIVE_RULES_FOR_REVIEW = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
      -[:HAS_RULE]->(rule:AppropriatenessRule)
WHERE rule.status = 'active'
SET rule.guidelineTextChanged          = true,
    rule.guidelineChangeDetectedAt     = datetime(),
    rule.guidelineChangeGuidelineId    = $guideline_id,
    rule.previousRecommendationText    = r.verbatim,
    rule.previousRecommendationNumber  = r.number
RETURN count(rule) AS flagged_count
"""

_SELECTIVE_FLAG_ACTIVE_RULES = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
      -[:HAS_RULE]->(rule:AppropriatenessRule)
WHERE r.number IN $changed_numbers
  AND rule.status = 'active'
SET rule.guidelineTextChanged          = true,
    rule.guidelineChangeDetectedAt     = datetime(),
    rule.guidelineChangeGuidelineId    = $guideline_id,
    rule.previousRecommendationText    = r.verbatim,
    rule.previousRecommendationNumber  = r.number
RETURN count(rule) AS flagged_count
"""

# Re-attach rules from old recommendation nodes to new ones for unchanged recs.
_REATTACH_UNCHANGED_RULES = """
MATCH (old_rec:Recommendation {guidelineId: $guideline_id, versionId: $old_version_id})
      -[old_link:HAS_RULE]->(rule:AppropriatenessRule)
WHERE old_rec.number IN $unchanged_numbers
  AND rule.status IN ['active', 'pending_review']
MATCH (new_rec:Recommendation {guidelineId: $guideline_id, versionId: $new_version_id,
                                number: old_rec.number})
MERGE (new_rec)-[:HAS_RULE]->(rule)
DELETE old_link
RETURN count(rule) AS reattached_count
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
    r.verbatim          = $verbatim,
    r.title             = $title,
    r.number            = $number,
    r.urgency           = $urgency,
    r.strength          = $strength,
    r.sectionTitle      = $section_title,
    r.isNormative       = $is_normative,
    r.guidelineId       = $guideline_id,
    r.versionId         = $version_id,
    r.listStructureJson = $list_structure_json,
    r.companionPanelsJson = $companion_panels_json,
    r.recommendationKey = $recommendation_key,
    r.renumberedFrom    = $renumbered_from,
    r.source            = 'nice_syndication_api',
    r.status            = 'loaded',
    r.createdAt         = datetime()
ON MATCH SET
    r.verbatim          = $verbatim,
    r.title             = $title,
    r.number            = $number,
    r.sectionTitle      = $section_title,
    r.isNormative       = $is_normative,
    r.listStructureJson = $list_structure_json,
    r.companionPanelsJson = $companion_panels_json,
    r.updatedAt         = datetime()
MERGE (g)-[:HAS_RECOMMENDATION]->(r)
WITH r
FOREACH (ch_id IN CASE WHEN $chapter_id IS NOT NULL THEN [$chapter_id] ELSE [] END |
    MERGE (ch:Chapter {id: ch_id})
    MERGE (ch)-[:HAS_RECOMMENDATION]->(r)
)
RETURN r.id AS id
"""

_FETCH_RECS_FOR_KEY_MATCHING = """
MATCH (r:Recommendation {guidelineId: $guideline_id, versionId: $version_id})
WHERE r.recommendationKey IS NOT NULL
RETURN r.number AS number, r.verbatim AS text, r.recommendationKey AS recommendation_key
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
        meta = guidance_json.get("MetadataApplicationProfile") or {}
        params = {
            "id": code,
            "code": code,
            "title": guidance_json.get("Title", ""),
            "guidance_number": guidance_json.get("GuidanceNumber", code),
            "guidance_type": guidance_json.get(
                "GuidanceType", guidance_json.get("Type", "")
            ),
            "pub_date": parse_nice_ms_date(meta.get("Issued") or ""),
            "last_modified_date": parse_nice_ms_date(
                guidance_json.get("LastModified") or meta.get("Modified") or ""
            ),
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

    def clear_guideline_content(
        self,
        guideline_id: str,
        changed_numbers: list[str] | None = None,
    ) -> dict[str, int]:
        """Archive stale content while never silently retiring an approval.

        Only ``pending_review`` rules (not yet approved by a human) are
        marked ``superseded``. An ``active`` (approved) rule is never
        touched by ingest -- it stays ``active`` (so it keeps firing, no
        coverage gap) and is instead *flagged* via
        ``guidelineTextChanged=true`` so a reviewer can see their approval
        may be stale and choose to re-approve, edit, or explicitly retire
        it themselves.

        When *changed_numbers* is supplied (smart ingest mode) only rules
        attached to those specific recommendations are affected. Rules for
        unchanged recommendations are left untouched entirely.

        When *changed_numbers* is ``None`` (full ingest / default) every
        pending rule is superseded and every active rule is flagged.

        Args:
            guideline_id: Guideline node ID (e.g. ``NG12``).
            changed_numbers: Rec numbers whose text changed, or ``None`` for
                a full sweep.

        Returns:
            ``{"superseded": N, "flagged_active": M}`` -- N is the count of
            not-yet-approved rules archived; M is the count of approved
            rules left active but flagged for re-review.
        """
        driver = _kg_driver()
        try:
            with driver.session() as session:
                if changed_numbers is not None:
                    superseded = self._run_count(
                        session,
                        _SELECTIVE_SUPERSEDE_RULES,
                        "superseded_count",
                        guideline_id=guideline_id,
                        changed_numbers=changed_numbers,
                    )
                    flagged = self._run_count(
                        session,
                        _SELECTIVE_FLAG_ACTIVE_RULES,
                        "flagged_count",
                        guideline_id=guideline_id,
                        changed_numbers=changed_numbers,
                    )
                else:
                    superseded = self._run_count(
                        session,
                        _SUPERSEDE_EXISTING_RULES,
                        "superseded_count",
                        guideline_id=guideline_id,
                    )
                    flagged = self._run_count(
                        session,
                        _FLAG_ACTIVE_RULES_FOR_REVIEW,
                        "flagged_count",
                        guideline_id=guideline_id,
                    )
                session.run(_DETACH_GUIDELINE_CONTENT_LINKS, guideline_id=guideline_id)
        finally:
            driver.close()
        logger.info(
            "Guideline %s: archived content (%d pending rule(s) superseded, "
            "%d approved rule(s) flagged for re-review, mode=%s)",
            guideline_id,
            superseded,
            flagged,
            "selective" if changed_numbers is not None else "full",
        )
        return {"superseded": superseded, "flagged_active": flagged}

    @staticmethod
    def _run_count(session: Any, query: str, count_key: str, **params: Any) -> int:
        record = session.run(query, **params).single()
        return int(record[count_key]) if record else 0

    def reattach_unchanged_rules(
        self,
        guideline_id: str,
        old_version_id: str,
        new_version_id: str,
        unchanged_numbers: list[str],
    ) -> int:
        """Move active/pending rules from old rec nodes to new rec nodes.

        Called after a smart ingest to preserve rules for recommendations
        whose text did not change.  Each rule is linked from the new-version
        Recommendation node so the bitmap compiler and review queue see it
        without the reviewer needing to re-approve unchanged work.

        Args:
            guideline_id: Guideline ID (e.g. ``NG12``).
            old_version_id: Version ID of the previous ingest (e.g. ``NG12:v1``).
            new_version_id: Version ID of the new ingest (e.g. ``NG12:v2``).
            unchanged_numbers: Recommendation numbers whose text is identical.

        Returns:
            Number of rules re-attached.
        """
        if not unchanged_numbers:
            return 0
        driver = _kg_driver()
        try:
            with driver.session() as session:
                result = session.run(
                    _REATTACH_UNCHANGED_RULES,
                    guideline_id=guideline_id,
                    old_version_id=old_version_id,
                    new_version_id=new_version_id,
                    unchanged_numbers=unchanged_numbers,
                )
                record = result.single()
                return int(record["reattached_count"]) if record else 0
        finally:
            driver.close()

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
        recommendation_key: str | None = None,
        renumbered_from: str | None = None,
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

        ``listStructureJson`` captures the recommendation's own nested list
        markup (see ``nice_list_parser.parse_recommendation_list_structure``)
        as a JSON string, read from ``rec["ListStructure"]``. ``None`` (not
        written / cleared to null) when the recommendation has no list
        structure -- most recommendations are a single plain sentence.

        ``recommendationKey`` / ``renumberedFrom`` are the LEO-internal
        stable identity resolved by ``recommendation_key_matcher.py`` --
        set only ``ON CREATE`` so a re-run of the exact same ingest version
        (same ``rec_id``) never overwrites the identity already resolved for
        it. The caller is responsible for resolving these (see
        ``_async_ingest`` in ``nice_guidance.py``): pass a freshly minted
        UUID for a genuinely new recommendation, or the previous version's
        key when continuity was established.

        Args:
            guideline_id: Parent guideline node ID.
            rec_id: Version-scoped identifier (e.g. ``NG12:v2:CH000:R003``).
            rec: Recommendation dict from the NICE API chapter Items.
            chapter_id: Optional parent chapter node ID.
            version_id: Version string for provenance (e.g. ``NG12:v2``).
            recommendation_key: Stable LEO-internal identity, independent of
                ``rec_id`` and ``number``. Required for correct cross-version
                continuity; only enforced ``ON CREATE``.
            renumbered_from: The previous version's recommendation number,
                set only when ``recommendation_key`` was carried forward via
                the text-similarity fallback (not an exact number match).

        Returns:
            The recommendation node ID.
        """
        verbatim = rec.get("Text", rec.get("Title", ""))
        title = rec.get("Title", "")
        section_title = rec.get("SectionTitle", "")
        is_normative = bool(rec.get("isNormative", False))
        # ListStructure (nice_list_parser.parse_recommendation_list_structure)
        # is a static parse artifact, not something requiring its own graph
        # traversal -- stored as a JSON string, same precedent as
        # AppropriatenessRule.logicJson, rather than exploded into nodes.
        list_structure = rec.get("ListStructure")
        list_structure_json = json.dumps(list_structure) if list_structure else None
        companion_panels = rec.get("CompanionPanels")
        companion_panels_json = (
            json.dumps(companion_panels) if companion_panels else None
        )
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
                    list_structure_json=list_structure_json,
                    companion_panels_json=companion_panels_json,
                    recommendation_key=recommendation_key or str(uuid.uuid4()),
                    renumbered_from=renumbered_from,
                )
                record = result.single()
                return record["id"] if record else rec_id
        finally:
            driver.close()

    def fetch_recommendations_for_key_matching(
        self, guideline_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        """Return ``{number, text, recommendation_key}`` for every
        recommendation in one specific previous ingest version.

        Feeds ``recommendation_key_matcher.match_recommendation_keys()`` so
        a re-ingest can resolve stable identity for the new version's
        recommendations before any of them are written. Returns an empty
        list for a first-ever ingest (no previous version to match against).
        """
        driver = _kg_driver()
        try:
            with driver.session() as session:
                result = session.run(
                    _FETCH_RECS_FOR_KEY_MATCHING,
                    guideline_id=guideline_id,
                    version_id=version_id,
                )
                return [dict(record) for record in result]
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
    """Map free-text NICE wording to Recommendation.urgency.

    Order matters: ``very urgent`` / ``48 hours`` must win over a bare
    ``urgent`` substring (NG12 1.10.9), and ``non-urgent`` must not be
    treated as a 2WW. ``immediate`` covers same-day specialist
    assessment (e.g. NG12 1.10.2).
    """
    combined = (rec.get("Title", "") + " " + rec.get("Text", "")).lower()
    if "immediate" in combined:
        return "immediate"
    if (
        "very urgent" in combined
        or "48 hour" in combined
        or "48-hour" in combined
        or "within 48" in combined
    ):
        return "very_urgent_48h"
    if "non-urgent" in combined or "non urgent" in combined:
        return "routine"
    if (
        "2-week" in combined
        or "2 week" in combined
        or "2ww" in combined
        or "suspected cancer pathway" in combined
    ):
        return "urgent_2w"
    if "urgent" in combined:
        return "urgent_2w"
    return "routine"


def _extract_strength(rec: dict[str, Any]) -> str:
    combined = (rec.get("Title", "") + " " + rec.get("Text", "")).lower()
    if "refer" in combined:
        return "refer"
    if "consider" in combined:
        return "consider"
    return "offer"
