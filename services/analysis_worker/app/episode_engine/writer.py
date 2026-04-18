"""Stage 6: idempotent Neo4j writer for the episode engine.

Per-patient contract:
    1. DETACH DELETE every existing EpisodeOfCare for the patient (including
       its IS_PART_OF edges and HAS_EPISODE_OF_CARE link). This is
       intentional: the engine is the new owner of episode state; partial
       merges across runs would create silent drift.
    2. Write one EpisodeOfCare node per reconciled episode with the full
       milestone payload, treatment_type, evidence_quotes, confidence,
       provenance and trace_id.
    3. Re-attach (Encounter)-[:IS_PART_OF {milestone_type, treatment_type,
       evidence_quote, confidence}]-> (EpisodeOfCare).

A ``dry_run=True`` path runs all the deterministic id work but skips the
graph mutations -- used by the cohort dry-run before cutover.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from libs.neo4j_client.client import PatientGraphClient
from services.analysis_worker.app.episode_engine.schemas import (
    Episode,
    Milestone,
    Provenance,
    ReconciledEpisode,
)

logger = logging.getLogger(__name__)


# -- Cypher ---------------------------------------------------------------

_DELETE_EXISTING_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
DETACH DELETE ep
RETURN count(ep) AS deleted
"""

_WRITE_EPISODE_Q = """
MATCH (p:Patient {id: $patient_id})
MERGE (ep:EpisodeOfCare {episode_id: $episode_id})
SET ep.patient_id           = $patient_id,
    ep.condition_type       = $condition_type,
    ep.cancer_type          = $suspected_site,
    ep.episode_type         = $episode_type,
    ep.suspected_site       = $suspected_site,
    ep.start_date           = date($window_start),
    ep.end_date             = CASE WHEN $window_end IS NULL
                                   THEN null ELSE date($window_end) END,
    ep.first_seen_date      = CASE WHEN $first_seen_date IS NULL
                                   THEN null ELSE date($first_seen_date) END,
    ep.confidence           = $confidence,
    ep.reasoning            = $reasoning,
    ep.needs_human_review   = $needs_human_review,
    ep.merged_from_json     = $merged_from_json,
    ep.engine_version       = $engine_version,
    ep.engine_trace_id      = $trace_id,
    ep.engine_provenance_json = $provenance_json,
    ep.created_at           = coalesce(ep.created_at, datetime($created_at)),
    ep.updated_at           = datetime($created_at),
    ep.status               = $status,
    ep.domain_id            = $domain_id
MERGE (p)-[:HAS_EPISODE_OF_CARE]->(ep)
RETURN ep.episode_id AS episode_id
"""

_LINK_MILESTONE_Q = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
MATCH (e:Encounter {id: $encounter_id})
MERGE (e)-[r:IS_PART_OF {milestone_type: $milestone_type}]->(ep)
SET r.treatment_type = $treatment_type,
    r.evidence_quote = $evidence_quote,
    r.confidence     = $confidence,
    r.engine         = true,
    r.linked_by      = 'episode_engine',
    r.created_at     = coalesce(r.created_at, datetime($created_at))
RETURN type(r) AS rt
"""


# -- Engine version --------------------------------------------------------

ENGINE_VERSION = "haiku-engine-v1"


# -- Helpers --------------------------------------------------------------


def deterministic_episode_id(
    patient_id: str, suspected_site: str, window_start: str
) -> str:
    """Stable id so reruns of the same window keep the same episode_id (audit)."""
    raw = f"{patient_id}|{suspected_site.lower()}|{window_start}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:16]
    return f"ep-{digest}"


def _episode_status(ep: ReconciledEpisode) -> str:
    if ep.episode_type == "benign":
        return "benign_closed"
    types = {m.type for m in ep.milestones}
    if "treatment_completed" in types:
        return "completed"
    if ep.needs_human_review:
        return "review"
    return "active"


def _first_seen_date(ms: Iterable[Milestone]) -> str | None:
    for m in ms:
        if m.type == "first_seen":
            return m.date.isoformat()
    return None


def _condition_type(ep: ReconciledEpisode) -> str:
    return "cancer" if ep.episode_type in ("cancer", "multi_site") else ep.episode_type


# -- Public API ------------------------------------------------------------


def write_episodes(
    *,
    client: PatientGraphClient,
    patient_id: str,
    domain_id: str,
    episodes: list[ReconciledEpisode],
    provenance: Provenance,
    dry_run: bool = False,
) -> list[Episode]:
    """Write the engine output for one patient and return the materialised
    Episode list (with deterministic episode_ids).

    Idempotent: if you re-run the engine for the same patient, the previous
    episodes are wiped and rewritten. The patient's encounters are not
    touched.
    """

    now_iso = datetime.now(timezone.utc).isoformat()
    provenance_json = json.dumps(provenance.model_dump(), default=str)

    materialised: list[Episode] = []
    for ep in episodes:
        ep_id = deterministic_episode_id(
            patient_id, ep.suspected_site, ep.window_start.isoformat()
        )
        materialised.append(
            Episode(
                episode_id=ep_id,
                patient_id=patient_id,
                suspected_site=ep.suspected_site,
                episode_type=ep.episode_type,
                window_start=ep.window_start,
                window_end=ep.window_end,
                milestones=list(ep.milestones),
                confidence=ep.confidence,
                reasoning=ep.reasoning,
                needs_human_review=ep.needs_human_review,
                merged_from=list(ep.merged_from),
                provenance=provenance,
            )
        )

    if dry_run:
        logger.info(
            "[dry_run] writer would replace %d episodes for patient %s",
            len(materialised),
            patient_id,
        )
        return materialised

    deleted = client.run(_DELETE_EXISTING_Q, patient_id=patient_id) or []
    n_deleted = (deleted[0] or {}).get("deleted", 0) if deleted else 0
    logger.info(
        "writer: deleted %d existing episodes for patient %s", n_deleted, patient_id
    )

    for ep, final in zip(episodes, materialised):
        client.run(
            _WRITE_EPISODE_Q,
            patient_id=patient_id,
            episode_id=final.episode_id,
            condition_type=_condition_type(ep),
            suspected_site=ep.suspected_site,
            episode_type=ep.episode_type,
            window_start=ep.window_start.isoformat(),
            window_end=ep.window_end.isoformat() if ep.window_end else None,
            first_seen_date=_first_seen_date(ep.milestones),
            confidence=float(ep.confidence),
            reasoning=ep.reasoning,
            needs_human_review=bool(ep.needs_human_review),
            merged_from_json=json.dumps(list(ep.merged_from)),
            engine_version=ENGINE_VERSION,
            trace_id=provenance.trace_id,
            provenance_json=provenance_json,
            created_at=now_iso,
            status=_episode_status(ep),
            domain_id=domain_id,
        )

        for m in ep.milestones:
            try:
                client.run(
                    _LINK_MILESTONE_Q,
                    episode_id=final.episode_id,
                    encounter_id=m.encounter_id,
                    milestone_type=m.type,
                    treatment_type=m.treatment_type,
                    evidence_quote=m.evidence_quote,
                    confidence=float(m.confidence),
                    created_at=now_iso,
                )
            except Exception:
                logger.exception(
                    "Failed to link milestone %s for episode %s (encounter %s)",
                    m.type,
                    final.episode_id,
                    m.encounter_id,
                )

    return materialised


def episodes_to_dicts(eps: list[Episode]) -> list[dict[str, Any]]:
    return [e.model_dump() for e in eps]
