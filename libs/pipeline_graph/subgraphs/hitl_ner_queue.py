"""Queue extraction issues for human review and training."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class HitlNerQueueState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict[str, Any]]
    llm_check_changes: list[dict[str, Any]]
    relation_changes: list[dict[str, Any]]
    encounter_status: str
    training_labels_written: int
    errors: list[str]


def _candidate_id(text: str, idx: int) -> str:
    return hashlib.sha256(f"{text}|{idx}".encode()).hexdigest()


def _reason_and_guidance(change: dict[str, Any]) -> tuple[str, str]:
    change_type = str(change.get("type") or "")
    reason = str(change.get("reason") or "")
    if reason == "ner_false_positive" or change_type == "drop":
        return (
            "ner_false_positive",
            "LEO picked up non-clinical text. Remove it or add a negative example.",
        )
    if change_type == "assertion_corrected":
        return (
            "assertion_corrected",
            "LEO got status wrong. Add a corrected example for this context.",
        )
    if change_type == "label_corrected":
        return (
            "label_corrected",
            "LEO used the wrong semantic type. Add a corrected label example.",
        )
    if change_type == "added":
        return (
            "missed_entity",
            "LEO missed this finding. Add a positive training example.",
        )
    if change_type == "relation_corrected":
        return (
            "relation_corrected",
            "LEO linked the wrong body site or qualifier. Add corrected relation examples.",
        )
    if change_type == "relation_missed":
        return (
            "relation_missed",
            "LEO missed a relation. Add examples showing this relation type.",
        )
    return (
        "extraction_review",
        "Review this extraction change and update training data if needed.",
    )


def queue_hitl_ner(state: HitlNerQueueState) -> dict[str, Any]:
    changes = list(state.get("llm_check_changes") or [])
    relation_changes = list(state.get("relation_changes") or [])
    entities = list(state.get("entities") or [])
    encounter_text = str(state.get("encounter_text") or "")
    errors = list(state.get("errors") or [])
    all_changes = changes + relation_changes
    if not all_changes:
        return {"training_labels_written": 0, "encounter_status": "auto_ready"}
    try:
        from libs.cypher.training_candidate_queries import UPSERT_TRAINING_CANDIDATE
        from libs.neo4j_client.client import KnowledgeGraphClient

        written = 0
        client = KnowledgeGraphClient()
        try:
            with client.session() as session:
                for idx, change in enumerate(all_changes):
                    reason, guidance = _reason_and_guidance(change)
                    candidate = {
                        "change": change,
                        "entities": entities,
                    }
                    session.run(
                        UPSERT_TRAINING_CANDIDATE,
                        candidate_id=_candidate_id(encounter_text, idx),
                        text=encounter_text,
                        entities_json=json.dumps(entities),
                        relation_changes=json.dumps(relation_changes),
                        source="pipeline_hitl_ner",
                        status="pending",
                        hitl_reason=reason,
                        hitl_guidance=guidance,
                        schema_version="v5",
                    )
                    written += 1
                    logger.debug("Queued NER HITL candidate: %s", candidate)
        finally:
            client.close()
        return {
            "training_labels_written": written,
            "encounter_status": "pending_ner_review",
            "errors": errors,
        }
    except Exception as exc:
        errors.append(f"hitl_ner_queue: {exc}")
        return {"training_labels_written": 0, "encounter_status": "queue_failed", "errors": errors}


def build_hitl_ner_queue_subgraph() -> CompiledStateGraph:
    g = StateGraph(HitlNerQueueState)
    g.add_node("queue_hitl_ner", queue_hitl_ner)
    g.add_edge(START, "queue_hitl_ner")
    g.add_edge("queue_hitl_ner", END)
    return g.compile()
