"""Cypher writes for episode-aware coding artefacts.

Atlas trace:
  DI: DI-885930F8 (canonical episode code)
  DI: DI-E8FE404D (cross-encounter QA)

Three audit nodes:

- ``EpisodeCanonicalCode`` -- the per-episode canonical SNOMED.
- ``EpisodeCodingQAResult`` -- the QA run summary for a bundle.
- ``EpisodeCodingQAFlag`` -- one per cross-encounter flag.

All MERGEs are idempotent on (episode_id, concept_id) for the
canonical code and on (episode_id, qa_run_id) for the QA result so
re-runs are safe.

A small ``schema_constraints`` helper exposes the indexes / uniqueness
rules so the analytics worker boot can call ``ensure_episode_coding_indexes``.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)


WRITE_CANONICAL_CODE = """
MATCH (e:Episode {episode_id: $episode_id})
MERGE (c:EpisodeCanonicalCode {episode_id: $episode_id})
SET c.concept_id = $concept_id,
    c.display_name = $display_name,
    c.intent = $intent,
    c.modifiers = $modifiers,
    c.confidence = $confidence,
    c.derivation_trace = $derivation_trace,
    c.derived_at = datetime()
MERGE (e)-[:HAS_CANONICAL_CODE]->(c)
RETURN c.episode_id AS episode_id, c.concept_id AS concept_id
"""


WRITE_QA_RESULT = """
MATCH (e:Episode {episode_id: $episode_id})
MERGE (r:EpisodeCodingQAResult {
    episode_id: $episode_id,
    qa_run_id: $qa_run_id
})
SET r.run_at = datetime(),
    r.flag_count = $flag_count,
    r.severity_max = $severity_max,
    r.summary = $summary
MERGE (e)-[:HAS_CODING_QA_RUN]->(r)
WITH r
UNWIND $flags AS flag
MERGE (f:EpisodeCodingQAFlag {
    episode_id: $episode_id,
    qa_run_id: $qa_run_id,
    flag_id: flag.flag_id
})
SET f.code = flag.code,
    f.severity = flag.severity,
    f.summary = flag.summary,
    f.encounter_ids = flag.encounter_ids,
    f.citation = flag.citation,
    f.created_at = datetime()
MERGE (r)-[:HAS_FLAG]->(f)
RETURN r.qa_run_id AS qa_run_id, count(f) AS flag_count
"""


def ensure_episode_coding_indexes(session) -> None:
    """Create the indexes used by episode coding queries.

    Called from the analysis worker boot path -- safe to run multiple
    times because Neo4j IF NOT EXISTS makes each statement idempotent.
    """
    statements = [
        (
            "CREATE CONSTRAINT episode_canonical_code_unique IF NOT EXISTS "
            "FOR (c:EpisodeCanonicalCode) REQUIRE c.episode_id IS UNIQUE"
        ),
        (
            "CREATE CONSTRAINT episode_qa_result_unique IF NOT EXISTS "
            "FOR (r:EpisodeCodingQAResult) "
            "REQUIRE (r.episode_id, r.qa_run_id) IS UNIQUE"
        ),
        (
            "CREATE INDEX episode_qa_flag_episode IF NOT EXISTS "
            "FOR (f:EpisodeCodingQAFlag) ON (f.episode_id)"
        ),
    ]
    for stmt in statements:
        try:
            session.run(stmt)
        except Exception:
            logger.exception("Failed to ensure index/constraint: %s", stmt)


def write_canonical_code(
    session,
    *,
    episode_id: str,
    concept_id: str,
    display_name: str,
    intent: str,
    modifiers: Iterable[str],
    confidence: float,
    derivation_trace: Iterable[str],
) -> dict[str, Any] | None:
    """Persist a canonical episode code. Returns the row dict or None."""
    try:
        result = session.run(
            WRITE_CANONICAL_CODE,
            episode_id=episode_id,
            concept_id=concept_id,
            display_name=display_name,
            intent=intent,
            modifiers=list(modifiers),
            confidence=float(confidence),
            derivation_trace=list(derivation_trace),
        )
        row = result.single() if hasattr(result, "single") else None
        return dict(row) if row else None
    except Exception:
        logger.exception("Failed to write canonical episode code for %s", episode_id)
        return None


def write_qa_result(
    session,
    *,
    episode_id: str,
    qa_run_id: str,
    flags: list[dict[str, Any]],
    summary: str = "",
) -> dict[str, Any] | None:
    """Persist a QA run plus per-flag detail."""
    severity_rank = {"low": 1, "medium": 2, "high": 3}
    severity_max = "low"
    if flags:
        worst = max(flags, key=lambda f: severity_rank.get(f.get("severity", ""), 0))
        severity_max = worst.get("severity", "low")
    try:
        result = session.run(
            WRITE_QA_RESULT,
            episode_id=episode_id,
            qa_run_id=qa_run_id,
            flags=flags,
            flag_count=len(flags),
            severity_max=severity_max,
            summary=summary,
        )
        row = result.single() if hasattr(result, "single") else None
        return dict(row) if row else None
    except Exception:
        logger.exception("Failed to write QA result for episode %s", episode_id)
        return None
