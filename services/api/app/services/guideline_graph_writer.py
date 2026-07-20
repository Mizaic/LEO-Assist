"""Versioned Neo4j writer for locally curated clinical guidelines."""

from __future__ import annotations

import os
from typing import Any

from neo4j import GraphDatabase

from app.schemas.local_guideline import LocalGuidelineDraft

_UPSERT_GUIDELINE = """
MERGE (g:Guideline {id: $id})
ON CREATE SET g.createdAt = datetime(), g.ingestVersion = 1
ON MATCH SET g.ingestVersion = coalesce(g.ingestVersion, 0) + 1, g.updatedAt = datetime()
SET g.code = $id, g.title = $title, g.source = 'local_guideline',
    g.type = 'local_guideline', g.publicationDate = $publication_date,
    g.versionLabel = $version_label
RETURN g.id AS id, g.ingestVersion AS version
"""

_DETACH_CONTENT = """
MATCH (g:Guideline {id: $guideline_id})
OPTIONAL MATCH (g)-[chapter_link:HAS_CHAPTER]->()
OPTIONAL MATCH (g)-[recommendation_link:HAS_RECOMMENDATION]->()
DELETE chapter_link, recommendation_link
"""

_UPSERT_CHAPTER = """
MATCH (g:Guideline {id: $guideline_id})
MERGE (ch:Chapter {id: $id})
ON CREATE SET ch.createdAt = datetime()
SET ch.title = $title, ch.order = $order, ch.guidelineId = $guideline_id,
    ch.versionId = $version_id, ch.source = 'local_guideline'
MERGE (g)-[:HAS_CHAPTER]->(ch)
"""

_UPSERT_RECOMMENDATION = """
MATCH (g:Guideline {id: $guideline_id})
MATCH (ch:Chapter {id: $chapter_id})
MERGE (r:Recommendation {id: $id})
ON CREATE SET r.createdAt = datetime()
SET r.title = $title, r.verbatim = $verbatim, r.number = $stable_key,
    r.guidelineId = $guideline_id, r.versionId = $version_id,
    r.source = 'local_guideline', r.isNormative = true, r.status = 'loaded',
    r.likelyIncorrect = $verification_flag
MERGE (g)-[:HAS_RECOMMENDATION]->(r)
MERGE (ch)-[:HAS_RECOMMENDATION]->(r)
"""

# Clean delete for local guidelines only. Does not delete AuditDomain nodes;
# HAS_DOMAIN edges are removed when the Guideline is DETACH DELETEd.
_DELETE_LOCAL_GUIDELINE = """
MATCH (g:Guideline {id: $guideline_id, source: 'local_guideline'})
OPTIONAL MATCH (ch:Chapter {guidelineId: $guideline_id})
OPTIONAL MATCH (rec:Recommendation {guidelineId: $guideline_id})
OPTIONAL MATCH (rec)-[:HAS_RULE]->(rule:AppropriatenessRule)
OPTIONAL MATCH (rule)-[:HAS_AUDIT_EVENT]->(audit)
WITH g,
     [n IN collect(DISTINCT ch) WHERE n IS NOT NULL | n] AS chapters,
     [n IN collect(DISTINCT rec) WHERE n IS NOT NULL | n] AS recommendations,
     [n IN collect(DISTINCT rule) WHERE n IS NOT NULL | n] AS rules,
     [n IN collect(DISTINCT audit) WHERE n IS NOT NULL | n] AS audits
FOREACH (n IN audits | DETACH DELETE n)
FOREACH (n IN rules | DETACH DELETE n)
FOREACH (n IN recommendations | DETACH DELETE n)
FOREACH (n IN chapters | DETACH DELETE n)
DETACH DELETE g
RETURN $guideline_id AS guideline_id,
       size(chapters) AS chapters,
       size(recommendations) AS recommendations,
       size(rules) AS rules
"""


def _driver():
    """Return the shared knowledge graph driver."""
    return GraphDatabase.driver(
        os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688"),
        auth=(
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j"),
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", ""),
        ),
    )


class GuidelineGraphWriter:
    """Write local guideline drafts without overwriting prior versions."""

    def upsert_local_guideline(self, draft: LocalGuidelineDraft) -> dict[str, Any]:
        """Persist a verified draft and return import counts."""
        metadata = draft.metadata
        driver = _driver()
        try:
            with driver.session() as session:
                record = session.run(
                    _UPSERT_GUIDELINE,
                    id=metadata.short_code,
                    title=metadata.title,
                    publication_date=metadata.publication_date,
                    version_label=metadata.version_label,
                ).single()
                version = int(record["version"]) if record else 1
                session.run(_DETACH_CONTENT, guideline_id=metadata.short_code)
                counts = self._write_content(session, draft, version)
        finally:
            driver.close()
        return {
            "guideline_id": metadata.short_code,
            "ingest_version": version,
            **counts,
        }

    def delete_local_guideline(self, guideline_id: str) -> dict[str, Any] | None:
        """Remove a local guideline and its chapters, recommendations, and rules.

        Shared AuditDomain nodes are left intact. Returns None when the
        guideline is missing or not a local_guideline source.
        """
        driver = _driver()
        try:
            with driver.session() as session:
                record = session.run(
                    _DELETE_LOCAL_GUIDELINE, guideline_id=guideline_id
                ).single()
        finally:
            driver.close()
        if not record:
            return None
        return {
            "guideline_id": record["guideline_id"],
            "chapters_deleted": int(record["chapters"] or 0),
            "recommendations_deleted": int(record["recommendations"] or 0),
            "rules_deleted": int(record["rules"] or 0),
        }

    def _write_content(
        self, session: Any, draft: LocalGuidelineDraft, version: int
    ) -> dict[str, int]:
        """Write the version-scoped chapter and recommendation nodes."""
        guideline_id = draft.metadata.short_code
        version_id = f"{guideline_id}:v{version}"
        recommendation_count = 0
        for chapter in draft.chapters:
            chapter_id = f"{version_id}:CH{chapter.order:03d}"
            session.run(
                _UPSERT_CHAPTER,
                guideline_id=guideline_id,
                id=chapter_id,
                title=chapter.title,
                order=chapter.order,
                version_id=version_id,
            )
            recommendation_count += self._write_recommendations(
                session, guideline_id, chapter_id, version_id, chapter.recommendations
            )
        return {
            "chapter_count": len(draft.chapters),
            "recommendation_count": recommendation_count,
        }

    def _write_recommendations(
        self,
        session: Any,
        guideline_id: str,
        chapter_id: str,
        version_id: str,
        recommendations: list[Any],
    ) -> int:
        """Write recommendations preserving their curator-assigned stable key."""
        for index, recommendation in enumerate(recommendations):
            session.run(
                _UPSERT_RECOMMENDATION,
                guideline_id=guideline_id,
                chapter_id=chapter_id,
                id=f"{chapter_id}:R{index:03d}",
                title=recommendation.title or recommendation.stable_key,
                verbatim=recommendation.verbatim,
                stable_key=recommendation.stable_key,
                verification_flag=recommendation.verification_flag,
                version_id=version_id,
            )
        return len(recommendations)
