"""Queue coding issues for human review and training.

Atlas trace:
  DO: DO-93E086B0
  DI: DI-F2C18D2E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-93E086B0")
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class HitlCodingQueueState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict[str, Any]]
    llm_check_changes: list[dict[str, Any]]
    encounter_status: str
    training_labels_written: int
    errors: list[str]


def _candidate_id(text: str, idx: int) -> str:
    return hashlib.sha256(f"{text}|coding|{idx}".encode()).hexdigest()


def _reason_and_guidance(change: dict[str, Any]) -> tuple[str, str]:
    if str(change.get("type") or "") == "force_review":
        return (
            "coding_ambiguous",
            "Code looks possible but context is unclear. Confirm code and add terminology guidance.",
        )
    if str(change.get("reason") or "") == "coding_mismatch":
        return (
            "coding_mismatch",
            "Code does not match text. Review terminology lookup and synonyms.",
        )
    return (
        "coding_review",
        "Review coding quality issue and update terminology/training if needed.",
    )


def queue_hitl_coding(state: HitlCodingQueueState) -> dict[str, Any]:
    changes = list(state.get("llm_check_changes") or [])
    entities = list(state.get("entities") or [])
    encounter_text = str(state.get("encounter_text") or "")
    errors = list(state.get("errors") or [])
    if not changes:
        return {"training_labels_written": 0, "encounter_status": "auto_ready"}
    try:
        from libs.cypher.training_candidate_queries import UPSERT_TRAINING_CANDIDATE
        from libs.neo4j_client.client import KnowledgeGraphClient

        written = 0
        client = KnowledgeGraphClient()
        try:
            with client.session() as session:
                for idx, change in enumerate(changes):
                    reason, guidance = _reason_and_guidance(change)
                    session.run(
                        UPSERT_TRAINING_CANDIDATE,
                        candidate_id=_candidate_id(encounter_text, idx),
                        text=encounter_text,
                        entities_json=json.dumps(entities),
                        relation_changes=json.dumps([]),
                        source="pipeline_hitl_coding",
                        status="pending",
                        hitl_reason=reason,
                        hitl_guidance=guidance,
                        schema_version="v5",
                    )
                    written += 1
        finally:
            client.close()
        return {
            "training_labels_written": written,
            "encounter_status": "pending_coding_review",
            "errors": errors,
        }
    except Exception as exc:
        errors.append(f"hitl_coding_queue: {exc}")
        return {"training_labels_written": 0, "encounter_status": "queue_failed", "errors": errors}


def build_hitl_coding_queue_subgraph() -> CompiledStateGraph:
    g = StateGraph(HitlCodingQueueState)
    g.add_node("queue_hitl_coding", queue_hitl_coding)
    g.add_edge(START, "queue_hitl_coding")
    g.add_edge("queue_hitl_coding", END)
    return g.compile()
