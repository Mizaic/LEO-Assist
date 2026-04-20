"""Encounter loader subgraph.

Atlas trace:
  DO: DO-A26CD350
  DI: DI-705C806B
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A26CD350")

Loads encounter text from the patient graph at runtime so clinical text is not
transported in queue payloads.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class EncounterLoaderState(TypedDict, total=False):
    patient_id: str
    encounter_id: str
    encounter_text: str


def load_encounter(state: EncounterLoaderState) -> dict[str, Any]:
    # Short-circuit: text already provided inline (e.g. dry-run / test-run payloads).
    existing_text = str(state.get("encounter_text") or "").strip()
    if existing_text:
        return {"encounter_text": existing_text}

    encounter_id = str(state.get("encounter_id") or "").strip()
    if not encounter_id:
        raise ValueError("encounter_id is required for encounter_loader")

    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (e:Encounter {id: $encounter_id}) RETURN coalesce(e.text, '') AS text",
            encounter_id=encounter_id,
        )
    finally:
        client.close()

    text = str((rows or [{}])[0].get("text") or "").strip()
    if not text:
        raise ValueError(f"No encounter text found for encounter_id={encounter_id}")
    return {"encounter_text": text}


def build_encounter_loader_subgraph() -> CompiledStateGraph:
    graph = StateGraph(EncounterLoaderState)
    graph.add_node("load_encounter", load_encounter)
    graph.add_edge(START, "load_encounter")
    graph.add_edge("load_encounter", END)
    return graph.compile()
