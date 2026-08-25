"""Resolve the letter for an extraction quality review.

Covers encounter notes and document-chunk referrals.

Atlas trace:
  DI: DI-4A012A59
  DO: DO-E7824FED
"""

from __future__ import annotations

import json
from typing import Any

from libs.pipeline.document_chunk_loader import (
    chunk_ids_from_state,
    load_document_chunks_from_neo4j,
)
from libs.validation_lab.source_text import letter_from_extract_input


def resolve_review_letter(
    *,
    client: Any,
    task: dict[str, Any],
    state: dict[str, Any] | None,
) -> str:
    persisted = str((task or {}).get("source_text") or "").strip()
    if persisted:
        return persisted
    text = _letter_from_blob(client, state or {})
    if text:
        return text
    text = _letter_from_blob(client, _paused_stage_state(client, task or {}))
    if text:
        return text
    return _letter_from_encounter(client, task or {}, state or {})


def _letter_from_blob(client: Any, blob: dict[str, Any]) -> str:
    text = letter_from_extract_input(blob)
    if text:
        return text
    return _letter_from_chunks(client, blob)


def letter_from_pause_output(output: dict[str, Any] | None) -> str:
    return letter_from_extract_input(output or {})


def _letter_from_chunks(client: Any, state: dict[str, Any]) -> str:
    chunk_ids = chunk_ids_from_state(state)
    if not chunk_ids or client is None:
        return ""
    loaded = load_document_chunks_from_neo4j(client, chunk_ids)
    return str(loaded.get("encounter_text") or "").strip()


def _letter_from_encounter(
    client: Any,
    task: dict[str, Any],
    state: dict[str, Any],
) -> str:
    encounter_id = str(
        state.get("encounter_id") or task.get("encounter_id") or ""
    ).strip()
    if not encounter_id:
        encounter_id = _encounter_id_from_run(client, task)
    if not encounter_id or client is None:
        return ""
    rows = client.run(
        "MATCH (e:Encounter {id: $encounter_id}) "
        "RETURN coalesce(e.text, '') AS text",
        encounter_id=encounter_id,
    )
    return str((rows or [{}])[0].get("text") or "").strip()


def _encounter_id_from_run(client: Any, task: dict[str, Any]) -> str:
    run_id = str(task.get("run_id") or "").strip()
    if not run_id or client is None:
        return ""
    rows = client.run(
        "MATCH (r:PipelineRun {id: $run_id}) "
        "RETURN coalesce(r.encounter_id, '') AS encounter_id",
        run_id=run_id,
    )
    return str((rows or [{}])[0].get("encounter_id") or "").strip()


def _paused_stage_state(client: Any, task: dict[str, Any]) -> dict[str, Any]:
    run_id = str(task.get("run_id") or "").strip()
    step_id = str(task.get("step_id") or "").strip()
    if not run_id or not step_id or client is None:
        return {}
    from libs.cypher.pipeline_stage_queries import GET_PIPELINE_STAGE_DETAIL

    rows = client.run(GET_PIPELINE_STAGE_DETAIL, run_id=run_id, step_id=step_id)
    row = (rows or [{}])[0] if rows else {}
    merged: dict[str, Any] = {}
    for raw in (row.get("input_json"), row.get("output_json")):
        parsed = _as_dict(raw)
        for key, value in parsed.items():
            if value in (None, "", [], {}):
                continue
            merged[key] = value
    return merged


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw or not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
