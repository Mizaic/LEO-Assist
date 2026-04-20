"""Safety net detection subgraph.

Atlas trace:
  DO: DO-B711D180
  DI: DI-CE0A08E5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B711D180")
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from services.analysis_worker.app.analyzers.abnormal_results import (
    detect_abnormal_results,
)
from services.analysis_worker.app.analyzers.safety_net_detector import (
    detect_safety_net_signals,
)
from services.analysis_worker.app.analyzers.safety_net_persistence import (
    persist_safety_net_alerts,
)

logger = logging.getLogger(__name__)


class SafetyNetState(TypedDict, total=False):
    patient_id: str
    org_id: str
    episodes: list[dict[str, Any]]
    encounter_text: str
    abnormal_results: list[dict[str, Any]]
    safety_net_alerts: list[dict[str, Any]]
    errors: list[str]


def detect_safety_net(state: SafetyNetState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Detecting safety net for patient %s", patient_id)
    errors = list(state.get("errors") or [])
    alerts: list[dict[str, Any]] = []

    episode_ids = [
        str(ep.get("episode_id") or ep.get("id") or "")
        for ep in state.get("episodes") or []
    ]
    episode_ids = [episode_id for episode_id in episode_ids if episode_id]
    if episode_ids:
        try:
            from libs.neo4j_client.client import (
                KnowledgeGraphClient,
                PatientGraphClient,
            )

            patient_client = PatientGraphClient()
            knowledge_client = KnowledgeGraphClient()
            try:
                detected = detect_safety_net_signals(
                    patient_id,
                    episode_ids,
                    patient_client,
                    knowledge_client,
                )
                alerts.extend(detected)
                # DI-LEO-AI-127: persist signals as SafetyNetAlert nodes
                # with a Patient (and optional EpisodeOfCare) edge so
                # the safety-netting worklist can surface them.
                if detected:
                    persist_safety_net_alerts(
                        patient_id,
                        detected,
                        patient_client,
                    )
            finally:
                patient_client.close()
                knowledge_client.close()
        except Exception as exc:
            errors.append(str(exc))

    if not alerts:
        encounter_text = str(state.get("encounter_text") or "").strip()
        if encounter_text:

            class _Client:
                def run(self, *_args, **_kwargs):
                    return [
                        {
                            "encounter_id": state.get("encounter_id"),
                            "text": encounter_text,
                            "date": state.get("encounter_date"),
                        }
                    ]

            alerts.extend(
                detect_abnormal_results(
                    patient_id=patient_id,
                    start_date=str(state.get("window_start") or ""),
                    end_date=str(state.get("window_end") or ""),
                    patient_client=_Client(),
                    org_id=str(state.get("org_id") or "") or None,
                )
            )

    return {
        "abnormal_results": [
            a for a in alerts if a.get("severity") in {"warning", "critical"}
        ],
        "safety_net_alerts": alerts,
        "errors": errors,
    }


def build_safety_net_subgraph() -> CompiledStateGraph:
    g = StateGraph(SafetyNetState)
    g.add_node("detect_safety_net", detect_safety_net)
    g.add_edge(START, "detect_safety_net")
    g.add_edge("detect_safety_net", END)
    return g.compile()
