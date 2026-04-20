"""Writeback layer: persist pre_done overrides + delete with TOCTOU.

Atlas trace:
  DO: DO-D7005C41
  DI: DI-0FFA05BB
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D7005C41")

DI-LEO-AI-208 / DO-LEO-AI-205 / R-LEO-AI-197.

Two writers, both defended by the GET_TRAINING_CANDIDATE_BY_ID
TOCTOU re-check so a row whose live status flipped to 'completed'
between the AI pass and the write is never modified or deleted.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from libs.cypher.training_candidate_queries import (
    DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS,
    GET_TRAINING_CANDIDATE_BY_ID,
    UPSERT_AI_FIRST_PASS_ENTITIES,
)

from ._types import CodingOutcome, ExtractedEntity

logger = logging.getLogger(__name__)


def _entity_payload(
    entity: ExtractedEntity,
    coding: CodingOutcome | None,
    *,
    run_id: str,
) -> dict[str, Any]:
    """Render one entity as the dict we persist to entities_json.

    The 'ai_first_pass' field is the marker the UI looks for to render
    the 'AI suggested' chip.
    """
    payload = entity.to_dict()
    payload["ai_first_pass"] = True
    payload["ai_first_pass_run_id"] = run_id
    if coding is not None:
        payload["snomed_concept_id"] = coding.snomed_concept_id
        payload["snomed_term"] = coding.snomed_term
        payload["snomed_score"] = round(float(coding.score or 0.0), 3)
        payload["coding_accepted"] = bool(coding.accepted)
        if coding.rejection_reason:
            payload["coding_rejection_reason"] = coding.rejection_reason
        if coding.alt_query_used:
            payload["coding_alt_query_used"] = coding.alt_query_used
    return payload


def build_pre_done_entities_payload(
    entities: Sequence[ExtractedEntity],
    codings: Sequence[CodingOutcome],
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    """Pair entities with codings (by index) and render the persisted list."""
    out: list[dict[str, Any]] = []
    for i, ent in enumerate(entities):
        coding = codings[i] if i < len(codings) else None
        out.append(_entity_payload(ent, coding, run_id=run_id))
    return out


def writeback_pre_done(
    client: Any,
    *,
    candidate_id: str,
    entities_payload: Sequence[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Atomically overwrite entities_json + stash the original audit copy.

    Returns the row payload from the upsert query. If the candidate's
    live status is 'completed' the upsert query's WHERE clause returns
    nothing (zero rows) and we surface a structured 'skipped_completed'
    outcome instead of writing.
    """
    if not candidate_id:
        return {"action": "error", "error": "empty_candidate_id"}

    serialised = json.dumps(list(entities_payload), ensure_ascii=True)

    with client.session() as session:
        # TOCTOU defence layer 1: explicit status check before any write.
        row = session.run(
            GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id
        ).single()
        if not row:
            return {"action": "not_found", "candidate_id": candidate_id}
        live_status = str(dict(row).get("status") or "")
        if live_status == "completed":
            return {
                "action": "skipped_completed",
                "candidate_id": candidate_id,
            }

        # TOCTOU defence layer 2: the Cypher's own WHERE c.status <> 'completed'.
        result = session.run(
            UPSERT_AI_FIRST_PASS_ENTITIES,
            candidate_id=candidate_id,
            entities_json=serialised,
            run_id=run_id,
        ).single()

        if not result:
            return {
                "action": "skipped_completed",
                "candidate_id": candidate_id,
            }

        payload = dict(result)
        payload["action"] = "upserted_pre_done"
        return payload


def execute_delete(
    client: Any,
    candidate_id: str,
) -> dict[str, Any]:
    """Delete one candidate after a TOCTOU re-fetch.

    Mirrors services.api.app.services.candidate_prune.execute_prune for
    the single-id case, with the cascade counts surfaced.
    """
    if not candidate_id:
        return {"action": "error", "error": "empty_candidate_id"}

    with client.session() as session:
        row = session.run(
            GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id
        ).single()
        if not row:
            return {"action": "not_found", "candidate_id": candidate_id}
        if str(dict(row).get("status") or "") == "completed":
            return {
                "action": "skipped_completed",
                "candidate_id": candidate_id,
            }
        del_row = session.run(
            DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS, candidate_id=candidate_id
        ).single()
        if not del_row:
            return {"action": "not_found", "candidate_id": candidate_id}
        d = dict(del_row)
        return {
            "action": "deleted",
            "candidate_id": candidate_id,
            "gold_labels_deleted": int(d.get("gold_labels_deleted") or 0),
            "surface_form_tasks_deleted": int(
                d.get("surface_form_tasks_deleted") or 0
            ),
        }
