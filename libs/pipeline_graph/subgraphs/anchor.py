"""Anchor detection subgraph."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors as detect_patient_anchors

logger = logging.getLogger(__name__)


class AnchorState(TypedDict, total=False):
    patient_id: str
    org_id: str
    entities: list[dict[str, Any]]
    encounter_id: str
    encounter_date: str
    anchors: list[dict[str, Any]]
    anchor_result: dict[str, Any]
    errors: list[str]


def _entity_rows(state: AnchorState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity in state.get("entities") or []:
        concept_id = (
            entity.get("concept_id")
            or entity.get("resolved_code")
            or entity.get("code")
            or (entity.get("coding") or {}).get("code")
        )
        rows.append(
            {
                "encounter_id": entity.get("encounter_id") or state.get("encounter_id") or "",
                "encounter_date": entity.get("encounter_date") or state.get("encounter_date") or "",
                "concept_id": concept_id,
                "concept_name": entity.get("concept_name") or entity.get("text") or entity.get("label") or "",
                "source": entity.get("source") or "pipeline",
                "confidence": entity.get("confidence", 1.0),
                "evidence": entity.get("evidence") or "",
            }
        )
    return rows


def _flatten_anchor_result(anchor_result) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for milestone_type, rows in (
        ("referral", anchor_result.referral_anchors),
        ("diagnosis", anchor_result.diagnosis_anchors),
        ("treatment_start", anchor_result.treatment_anchors),
        ("specialist_visit", anchor_result.specialist_visit_anchors),
    ):
        for row in rows:
            anchor = dict(row)
            anchor["milestone_type"] = milestone_type
            anchors.append(anchor)
    return anchors


def detect_anchors(state: AnchorState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Detecting anchors for patient %s", patient_id)
    errors = list(state.get("errors") or [])

    try:
        entity_rows = _entity_rows(state)
        if entity_rows:
            class _Client:
                def run(self, *_args, **_kwargs):
                    return entity_rows

            anchor_result = detect_patient_anchors(
                patient_id=patient_id,
                start_date=str(state.get("window_start") or ""),
                end_date=str(state.get("window_end") or ""),
                patient_client=_Client(),
            )
        else:
            from libs.neo4j_client.client import PatientGraphClient

            client = PatientGraphClient()
            try:
                anchor_result = detect_patient_anchors(
                    patient_id=patient_id,
                    start_date=str(state.get("window_start") or ""),
                    end_date=str(state.get("window_end") or ""),
                    patient_client=client,
                )
            finally:
                client.close()
        anchors = _flatten_anchor_result(anchor_result)
        return {
            "anchors": anchors,
            "anchor_result": {
                "referral_anchors": anchor_result.referral_anchors,
                "diagnosis_anchors": anchor_result.diagnosis_anchors,
                "treatment_anchors": anchor_result.treatment_anchors,
                "specialist_visit_anchors": anchor_result.specialist_visit_anchors,
                "detection_method": anchor_result.detection_method,
                "expanded_start": anchor_result.expanded_start,
                "expanded_end": anchor_result.expanded_end,
            },
            "errors": errors + list(anchor_result.errors),
        }
    except Exception as exc:
        logger.exception("Anchor detection failed for patient %s", patient_id)
        return {"anchors": [], "anchor_result": {}, "errors": errors + [str(exc)]}


def build_anchor_subgraph() -> CompiledStateGraph:
    g = StateGraph(AnchorState)
    g.add_node("detect_anchors", detect_anchors)
    g.add_edge(START, "detect_anchors")
    g.add_edge("detect_anchors", END)
    return g.compile()
