from __future__ import annotations

from unittest.mock import patch

from libs.pipeline_graph.subgraphs.surface_form_validation import (
    _find_mismatches,
    build_surface_form_validation_subgraph,
)


def test_surface_form_validation_builds_graph() -> None:
    graph = build_surface_form_validation_subgraph()
    assert graph is not None


def test_surface_form_validation_creates_task_on_mismatch() -> None:
    mock_resolved = {"chest pain": []}
    with patch("libs.pipeline_graph.subgraphs.surface_form_validation.TerminologyClient.resolve", return_value=mock_resolved):
        out = _find_mismatches(
            {
                "entities": [{"text": "chest pain", "label": "finding", "snomed_concept_id": "1"}],
                "encounter_text": "chest pain for 2 days",
                "candidate_id": "cand1",
            }
        )
    assert len(out.get("surface_form_mismatches", [])) == 1

