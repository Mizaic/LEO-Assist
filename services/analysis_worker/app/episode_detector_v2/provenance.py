"""Provenance store -- writes EpisodeProvenance records to Neo4j.

Atlas trace:
  DI: DI-8A5FCF4F

The persister is intentionally narrow: one Cypher MERGE per
(episode_id, encounter_id) pair. Idempotent so a re-run produces the
same node count. The runner calls ``persist_provenance`` after
boundaries are committed.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from .types import EpisodeProvenance

logger = logging.getLogger(__name__)


_PROVENANCE_MERGE = """
UNWIND $rows AS row
MATCH (e:Episode {episode_id: row.episode_id})
MATCH (enc:Encounter {encounter_id: row.encounter_id})
MERGE (p:EpisodeProvenance {
    episode_id: row.episode_id,
    encounter_id: row.encounter_id
})
SET p.generator = row.generator,
    p.score = row.score,
    p.supporting_signals = row.supporting_signals,
    p.alternatives_considered = row.alternatives_considered,
    p.detector_version = row.detector_version,
    p.last_updated = datetime()
MERGE (e)-[:HAS_PROVENANCE]->(p)
MERGE (p)-[:FOR_ENCOUNTER]->(enc)
"""


def persist_provenance(
    session: Any,
    *,
    records: Sequence[EpisodeProvenance],
) -> int:
    """Write provenance rows. Returns number of rows persisted."""
    if not records:
        return 0
    rows = [
        {
            "episode_id": r.episode_id,
            "encounter_id": r.encounter_id,
            "generator": r.generator,
            "score": r.score,
            "supporting_signals": _coerce_json(r.supporting_signals),
            "alternatives_considered": _coerce_json(r.alternatives_considered),
            "detector_version": r.detector_version,
        }
        for r in records
    ]
    try:
        session.run(_PROVENANCE_MERGE, rows=rows)
    except Exception:
        logger.exception(
            "Failed to persist EpisodeProvenance for %d records", len(rows)
        )
        return 0
    return len(rows)


def _coerce_json(value: list[dict[str, Any]]) -> list[str]:
    """Neo4j primitives only -- serialise nested dicts to repr strings."""
    return [str(item) for item in value]
