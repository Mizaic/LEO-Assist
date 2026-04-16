"""Episode tools for patient graph and analytics API operations."""

from __future__ import annotations

from typing import Any

from services.neo4j_mcp._client import patient_run
from services.neo4j_mcp._http import analytics_patch, analytics_post


LIST_PATIENT_EPISODES = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e:Encounter)-[:IS_PART_OF]->(ep)
RETURN ep.episode_id AS episode_id,
       ep.status AS status,
       ep.primary_cancer_type AS primary_cancer_type,
       ep.first_encounter_date AS first_encounter_date,
       ep.last_encounter_date AS last_encounter_date,
       count(DISTINCT e) AS encounter_count
ORDER BY coalesce(ep.last_encounter_date, ep.first_encounter_date) DESC
"""

GET_EPISODE = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
OPTIONAL MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep)
RETURN ep.episode_id AS episode_id,
       ep.status AS status,
       ep.primary_cancer_type AS primary_cancer_type,
       ep.first_encounter_date AS first_encounter_date,
       ep.last_encounter_date AS last_encounter_date,
       ep.needs_review AS needs_review,
       toString(p.id) AS patient_id,
       collect(DISTINCT {
           encounter_id: toString(e.id),
           encounter_date: toString(e.date),
           milestone_type: r.milestone_type
       }) AS encounters
LIMIT 1
"""


def get_patient_episodes(patient_id: str) -> dict[str, Any]:
    rows = patient_run(LIST_PATIENT_EPISODES, patient_id=patient_id)
    return {"items": rows, "count": len(rows)}


def get_episode(episode_id: str) -> dict[str, Any]:
    rows = patient_run(GET_EPISODE, episode_id=episode_id)
    return {"item": rows[0] if rows else None}


def close_episode(episode_id: str, reason: str, status: str = "closed") -> dict[str, Any]:
    return analytics_patch(
        f"/analytics/episodes/{episode_id}/status",
        json_body={"status": status, "reason": reason},
    )


def rebuild_patient_episodes(
    patient_id: str,
    delete_existing: bool = True,
) -> dict[str, Any]:
    return analytics_post(
        "/analytics/episodes/rebuild",
        json_body={"patient_id": patient_id, "delete_existing": delete_existing},
    )


def merge_episodes(
    primary_episode_id: str,
    secondary_episode_ids: list[str],
    reason: str,
) -> dict[str, Any]:
    return analytics_post(
        "/analytics/episodes/merge",
        json_body={
            "primary_episode_id": primary_episode_id,
            "secondary_episode_ids": secondary_episode_ids,
            "reason": reason,
        },
    )


TOOLS = [
    {
        "name": "get_patient_episodes",
        "description": "List episode records for one patient.",
        "inputSchema": {
            "type": "object",
            "properties": {"patient_id": {"type": "string"}},
            "required": ["patient_id"],
        },
        "fn": get_patient_episodes,
    },
    {
        "name": "get_episode",
        "description": "Get one episode with linked encounters.",
        "inputSchema": {
            "type": "object",
            "properties": {"episode_id": {"type": "string"}},
            "required": ["episode_id"],
        },
        "fn": get_episode,
    },
    {
        "name": "close_episode",
        "description": "Close or complete an episode via analytics API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "episode_id": {"type": "string"},
                "status": {"type": "string", "default": "closed"},
                "reason": {"type": "string"},
            },
            "required": ["episode_id", "reason"],
        },
        "fn": close_episode,
    },
    {
        "name": "rebuild_patient_episodes",
        "description": "Rebuild patient episodes via analytics API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "delete_existing": {"type": "boolean", "default": True},
            },
            "required": ["patient_id"],
        },
        "fn": rebuild_patient_episodes,
    },
    {
        "name": "merge_episodes",
        "description": "Merge episodes via analytics API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "primary_episode_id": {"type": "string"},
                "secondary_episode_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "reason": {"type": "string"},
            },
            "required": ["primary_episode_id", "secondary_episode_ids", "reason"],
        },
        "fn": merge_episodes,
    },
]

