"""Unit tests for the encounter_loader subgraph.

Covers the short-circuit path (encounter_text already in state) and the
guard clause for missing encounter_id.  The Neo4j path is not exercised
here; it is covered by integration tests that require a live patient graph.
"""

from __future__ import annotations

import pytest

from libs.pipeline_graph.subgraphs.encounter_loader import load_encounter


def test_short_circuit_when_text_present() -> None:
    """If encounter_text is already in state, Neo4j must not be called."""
    state = {
        "encounter_text": "Patient has hypertension.",
        "encounter_id": "test-encounter",
        "patient_id": "test-patient",
    }
    result = load_encounter(state)
    assert result == {"encounter_text": "Patient has hypertension."}


def test_short_circuit_strips_whitespace() -> None:
    """Whitespace-only encounter_text falls through to the Neo4j path."""
    state = {
        "encounter_text": "   ",
        "encounter_id": "",
        "patient_id": "test-patient",
    }
    with pytest.raises(ValueError, match="encounter_id is required"):
        load_encounter(state)


def test_missing_encounter_id_raises() -> None:
    """When no text and no encounter_id, a clear ValueError is raised."""
    state: dict = {"patient_id": "test-patient"}
    with pytest.raises(ValueError, match="encounter_id is required"):
        load_encounter(state)


def test_empty_state_raises() -> None:
    """An entirely empty state raises on the encounter_id guard."""
    with pytest.raises(ValueError, match="encounter_id is required"):
        load_encounter({})
