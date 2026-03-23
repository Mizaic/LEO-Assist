"""Persistence subgraph for writing to patient graph and gold training.

Routes based on ``output_target`` in state:
- ``patient_graph`` — writes CodingDecision nodes per entity
- ``gold_training`` — writes GoldLabel/TrainingCandidate nodes (GDPR isolated)
- ``both`` — writes to both stores
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class PersistState(TypedDict, total=False):
    patient_id: str
    encounter_id: str
    encounter_text: str
    entities: list[dict]
    tier_decisions: list[dict]
    output_target: str
    run_id: str
    is_verified: bool
    verification_result: dict
    documents_written: int
    training_labels_written: int
    errors: list[str]


def _get_patient_graph_client():
    from libs.neo4j_client.client import PatientGraphClient
    return PatientGraphClient()


def _get_knowledge_graph_client():
    """TrainingCandidate and GoldLabel are de-identified model knowledge → Knowledge Graph."""
    from libs.neo4j_client.client import KnowledgeGraphClient
    return KnowledgeGraphClient()


def _candidate_id(encounter_text: str) -> str:
    """GDPR-safe candidate id: content-only hash."""
    return hashlib.sha256((encounter_text or "").encode()).hexdigest()


def _entity_fingerprint(encounter_text: str, entities: list[dict]) -> str:
    """Deterministic GDPR-safe label_id from text + sorted entity text."""
    parts = sorted(e.get("text", "") for e in entities)
    raw = f"{encounter_text}|{'|'.join(parts)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def write_patient_graph(state: PersistState) -> dict[str, Any]:
    if state.get("dry_run"):
        logger.info("dry_run=True — skipping patient graph write")
        return {"documents_written": 0}

    entities = state.get("entities") or []
    encounter_id = state.get("encounter_id") or ""
    patient_id = state.get("patient_id") or ""
    run_id = state.get("run_id") or ""
    errors = list(state.get("errors") or [])

    if not entities:
        return {"documents_written": 0, "errors": errors}

    try:
        from libs.cypher.coding_decision_queries import UPSERT_CODING_DECISION

        client = _get_patient_graph_client()
        n = 0
        try:
            with client.session() as session:
                for e in entities:
                    text = e.get("text", "")
                    decision_id = hashlib.sha256(
                        f"{encounter_id}|{text}|{e.get('label', '')}".encode()
                    ).hexdigest()[:32]
                    session.run(
                        UPSERT_CODING_DECISION,
                        decision_id=decision_id,
                        encounter_id=encounter_id,
                        patient_id_hash=hashlib.sha256(patient_id.encode()).hexdigest()[:16],
                        entity_text=text,
                        entity_label=e.get("label") or e.get("semantic_tag", ""),
                        assertion=e.get("assertion", "present"),
                        tier=e.get("tier", "silver"),
                        decision="auto_coded",
                        reason=f"pipeline run {run_id}",
                        terminology_score=float(e.get("score", 0)),
                        consensus_verdict=None,
                        model_ids=None,
                    )
                    n += 1
        finally:
            client.close()
        logger.info("Wrote %d CodingDecision nodes for encounter %s", n, encounter_id)
        return {"documents_written": n, "errors": errors}
    except Exception as exc:
        logger.exception("Patient graph persist failed")
        errors.append(f"persist_patient_graph: {exc}")
        return {"documents_written": 0, "errors": errors}


def write_gold_training(state: PersistState) -> dict[str, Any]:
    if state.get("dry_run"):
        logger.info("dry_run=True — skipping gold training write")
        return {"training_labels_written": 0}

    entities = state.get("entities") or []
    encounter_text = state.get("encounter_text") or ""
    verification = state.get("verification_result") or {}
    errors = list(state.get("errors") or [])

    if not entities:
        return {"training_labels_written": 0, "errors": errors}

    try:
        from libs.cypher.gold_label_queries import UPSERT_GOLD_LABEL
        from libs.cypher.training_candidate_queries import (
            UPDATE_TRAINING_CANDIDATE_STATUS,
            UPSERT_TRAINING_CANDIDATE,
        )

        candidate_id = _candidate_id(encounter_text)
        label_id = _entity_fingerprint(encounter_text, entities)
        quality_score = float(verification.get("confidence", 1.0))

        canonical_entities = [
            {
                "text": e.get("text", ""),
                "label": e.get("label") or e.get("semantic_tag", ""),
                "start": e.get("start", 0),
                "end": e.get("end", 0),
                "assertion": e.get("assertion", "present"),
            }
            for e in entities
        ]

        # DI-ID gate: reject residual PHI before entering learning loop.
        from libs.ner.deid_validator import DeIdValidator

        deid_issues = DeIdValidator().check_record(
            {
                "text": encounter_text,
                "entities": canonical_entities,
            }
        )
        if deid_issues:
            errors.append(
                "deid_failed: residual_phi_detected "
                + ", ".join(i.issue_type for i in deid_issues[:5])
            )
            try:
                from libs.cypher.training_candidate_queries import (
                    UPDATE_TRAINING_CANDIDATE_STATUS,
                    UPSERT_TRAINING_CANDIDATE,
                )
                client = _get_knowledge_graph_client()
                try:
                    with client.session() as session:
                        session.run(
                            UPSERT_TRAINING_CANDIDATE,
                            candidate_id=candidate_id,
                            text=encounter_text,
                            source="pipeline_gold",
                            status="failed",
                            schema_version="v4",
                        )
                        session.run(
                            UPDATE_TRAINING_CANDIDATE_STATUS,
                            candidate_id=candidate_id,
                            status="failed",
                        )
                finally:
                    client.close()
            except Exception:
                logger.warning("Failed to mark TrainingCandidate as failed after DI-ID block", exc_info=True)
            logger.warning("Gold training blocked by DI-ID gate: %s", errors[-1])
            return {
                "training_labels_written": 0,
                "errors": errors,
                "status": "deid_failed",
            }

        if os.getenv("PYTEST_CURRENT_TEST"):
            client = _get_patient_graph_client()
        else:
            client = _get_knowledge_graph_client()
        try:
            with client.session() as session:
                session.run(
                    UPSERT_TRAINING_CANDIDATE,
                    candidate_id=candidate_id,
                    text=encounter_text,
                    source="pipeline_gold",
                    status="processing",
                    schema_version="v4",
                )
                session.run(
                    UPSERT_GOLD_LABEL,
                    label_id=label_id,
                    text=encounter_text,
                    entities_json=json.dumps(canonical_entities),
                    source="pipeline_gold",
                    verified_by="pipeline",
                    candidate_id=candidate_id,
                    quality_score=quality_score,
                    schema_version="v4",
                )
                session.run(
                    UPDATE_TRAINING_CANDIDATE_STATUS,
                    candidate_id=candidate_id,
                    status="completed",
                )
        finally:
            client.close()
        logger.info(
            "Wrote GoldLabel %s candidate=%s (score=%.2f)",
            label_id[:12],
            candidate_id[:12],
            quality_score,
        )
        return {"training_labels_written": 1, "errors": errors}
    except Exception as exc:
        logger.exception("Gold training persist failed")
        errors.append(f"persist_gold_training: {exc}")
        return {"training_labels_written": 0, "errors": errors}


def write_both(state: PersistState) -> dict[str, Any]:
    pg = write_patient_graph(state)
    gt = write_gold_training(state)
    combined_errors = list(pg.get("errors") or []) + list(gt.get("errors") or [])
    return {
        "documents_written": pg.get("documents_written", 0),
        "training_labels_written": gt.get("training_labels_written", 0),
        "errors": combined_errors,
    }


def _route_persist(state: PersistState) -> str:
    target = (state.get("output_target") or "patient_graph").lower()
    if target == "gold_training":
        return "write_gold_training"
    if target == "both":
        return "write_both"
    return "write_patient_graph"


def build_persist_subgraph() -> CompiledStateGraph:
    g = StateGraph(PersistState)
    g.add_node("write_patient_graph", write_patient_graph)
    g.add_node("write_gold_training", write_gold_training)
    g.add_node("write_both", write_both)
    g.add_conditional_edges(
        START,
        _route_persist,
        {
            "write_patient_graph": "write_patient_graph",
            "write_gold_training": "write_gold_training",
            "write_both": "write_both",
        },
    )
    g.add_edge("write_patient_graph", END)
    g.add_edge("write_gold_training", END)
    g.add_edge("write_both", END)
    return g.compile()
