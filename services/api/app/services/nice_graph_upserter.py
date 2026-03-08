"""Idempotent Neo4j upsert for NICE guideline content.

Stores Guideline, Recommendation, and Section nodes in the knowledge graph.
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

_UPSERT_RECOMMENDATION = """
MATCH (g:Guideline {id: $guideline_id})
MERGE (r:Recommendation {id: $id})
ON CREATE SET
    r.verbatim      = $verbatim,
    r.title         = $title,
    r.urgency       = $urgency,
    r.strength      = $strength,
    r.source        = 'nice_syndication_api',
    r.status        = 'loaded',
    r.createdAt     = datetime()
ON MATCH SET
    r.verbatim      = $verbatim,
    r.updatedAt     = datetime()
MERGE (g)-[:HAS_RECOMMENDATION]->(r)
RETURN r.id AS id
"""

_UPSERT_SECTION = """
MATCH (g:Guideline {id: $guideline_id})
MERGE (s:Section {sectionId: $section_id})
ON CREATE SET
    s.title         = $title,
    s.text          = $text,
    s.source        = 'nice_syndication_api',
    s.createdAt     = datetime()
ON MATCH SET
    s.title         = $title,
    s.text          = $text,
    s.updatedAt     = datetime()
MERGE (g)-[:HAS_SECTION]->(s)
RETURN s.sectionId AS id
"""


def _kg_driver():
    """Return a synchronous Neo4j driver for the knowledge graph."""
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    return GraphDatabase.driver(uri, auth=(user, password))


class NiceGraphUpserter:
    """Idempotent MERGE operations for NICE guideline nodes in Neo4j.

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

    def upsert_recommendation(
        self, guideline_id: str, rec_id: str, rec: dict[str, Any]
    ) -> str:
        """Store a Recommendation node linked to its parent Guideline.

        Args:
            guideline_id: Parent guideline node ID.
            rec_id: Stable recommendation identifier.
            rec: Recommendation dict from the NICE API.

        Returns:
            The recommendation node ID.
        """
        params = {
            "guideline_id": guideline_id,
            "id": rec_id,
            "verbatim": rec.get("Text", rec.get("Title", "")),
            "title": rec.get("Title", ""),
            "urgency": _extract_urgency(rec),
            "strength": _extract_strength(rec),
        }
        driver = _kg_driver()
        try:
            with driver.session() as session:
                result = session.run(_UPSERT_RECOMMENDATION, **params)
                record = result.single()
                return record["id"] if record else rec_id
        finally:
            driver.close()

    def upsert_section(
        self, guideline_id: str, section: dict[str, Any], order: int
    ) -> None:
        """Store a Section node linked to its parent Guideline.

        Args:
            guideline_id: Parent guideline node ID.
            section: Section resource dict from the NICE API.
            order: Position of this section within the guideline.
        """
        section_id = f"{guideline_id}:S{order:03d}"
        params = {
            "guideline_id": guideline_id,
            "section_id": section_id,
            "title": section.get("Title", ""),
            "text": section.get("Text", section.get("Title", "")),
        }
        driver = _kg_driver()
        try:
            with driver.session() as session:
                session.run(_UPSERT_SECTION, **params)
        finally:
            driver.close()


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
    if "2-week" in title or "2ww" in title or "urgent" in title:
        return "urgent_2w"
    if "immediate" in title:
        return "immediate"
    return "routine"


def _extract_strength(rec: dict[str, Any]) -> str:
    """Extract recommendation strength from a recommendation dict."""
    title = rec.get("Title", "").lower()
    if "refer" in title:
        return "refer"
    if "consider" in title:
        return "consider"
    return "offer"
