"""Reset tools delegated to core API side effects."""

from __future__ import annotations

from typing import Any

from services.neo4j_mcp._http import core_post


def reset_patient(patient_id: str) -> dict[str, Any]:
    return core_post(f"/patients/{patient_id}/reset")


def reset_review_queue(patient_id: str) -> dict[str, Any]:
    return core_post(f"/patients/{patient_id}/reset-review-queue")


def reset_and_recode_encounter(
    patient_id: str,
    encounter_id: str,
    dry_run: bool = False,
    rerun_episode_detector: bool = False,
) -> dict[str, Any]:
    return core_post(
        f"/patients/{patient_id}/encounters/{encounter_id}/reset-and-recode",
        json_body={
            "dry_run": dry_run,
            "rerun_episode_detector": rerun_episode_detector,
        },
    )


TOOLS = [
    {
        "name": "reset_patient",
        "description": "Reset patient documents from core API.",
        "inputSchema": {
            "type": "object",
            "properties": {"patient_id": {"type": "string"}},
            "required": ["patient_id"],
        },
        "fn": reset_patient,
    },
    {
        "name": "reset_review_queue",
        "description": "Reset patient review queue from core API.",
        "inputSchema": {
            "type": "object",
            "properties": {"patient_id": {"type": "string"}},
            "required": ["patient_id"],
        },
        "fn": reset_review_queue,
    },
    {
        "name": "reset_and_recode_encounter",
        "description": "Reset and queue encounter recode via core API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "encounter_id": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "rerun_episode_detector": {"type": "boolean", "default": False},
            },
            "required": ["patient_id", "encounter_id"],
        },
        "fn": reset_and_recode_encounter,
    },
]

