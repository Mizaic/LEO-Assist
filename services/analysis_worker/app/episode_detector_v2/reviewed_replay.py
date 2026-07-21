"""Replay curator-reviewed episodes as detector output.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Reviewed EpisodeOfCare rows are the clinical source of truth. The v2
detector must not regenerate or reshape them during calibration or later
pipeline runs.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .types import ResolvedEpisode

_REVIEWED_EPISODES_QUERY = """
MATCH (p:Patient {id: $patient_id})-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.reviewed_at IS NOT NULL
OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(ep)
RETURN ep.episode_id AS episode_id,
       coalesce(ep.site_key, ep.primary_cancer_type, ep.cancer_type,
                ep.suspected_site) AS site_key,
       coalesce(ep.suspected_site, ep.site_key, ep.cancer_type,
                ep.primary_cancer_type) AS suspected_site,
       ep.status AS status,
       ep.intent AS intent,
       ep.start_date AS start_date,
       ep.end_date AS end_date,
       collect(DISTINCT enc.id) AS encounter_ids
ORDER BY coalesce(ep.start_date, ep.end_date), ep.episode_id
"""


def load_reviewed_episode_replay(
    patient_client: Any,
    *,
    patient_id: str,
) -> list[ResolvedEpisode]:
    """Return reviewed episodes for patient_id, or an empty list."""
    if patient_client is None:
        return []
    rows = patient_client.run(_REVIEWED_EPISODES_QUERY, patient_id=patient_id)
    return [_row_to_episode(row) for row in rows]


def _row_to_episode(row: Any) -> ResolvedEpisode:
    status = _row_value(row, "status") or "reviewed"
    return ResolvedEpisode(
        episode_id=str(_row_value(row, "episode_id")),
        site_key=str(_row_value(row, "site_key") or "unknown"),
        encounter_ids=list(_row_value(row, "encounter_ids") or []),
        start_date=_as_date(_row_value(row, "start_date")),
        end_date=_as_date(_row_value(row, "end_date")),
        suspected_site=str(_row_value(row, "suspected_site") or "unknown"),
        role="reviewed_episode",
        intent=str(_row_value(row, "intent") or _intent_from_status(status)),
        status=str(status),
        confidence_tier="auto",
        needs_human_review=False,
        review_reasons=[],
        vote_count=1,
        supporting_signals=[],
        alternatives_considered=[],
        generator_consensus=["reviewed_episode_replay"],
    )


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key]


def _as_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _intent_from_status(status: str) -> str:
    if status in {"closed_benign", "benign_closure"}:
        return "ruled_out"
    if status in {"completed", "active"}:
        return "confirmed"
    return "suspected"
