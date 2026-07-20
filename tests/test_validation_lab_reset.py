"""Purge coverage for the Validation Lab reset (empty-Lab) flow.

Atlas: DI-724CD8A5
"""

from __future__ import annotations

from typing import Any

from libs.validation_lab.reset import (
    PATIENT_GRAPH_SOURCES,
    reset_knowledge_graph,
    reset_patient_graph,
    reset_validation_lab,
)


class _FakeClient:
    def __init__(self, deleted_count: int = 3) -> None:
        self.deleted_count = deleted_count
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((" ".join(query.split()), params))
        return [{"deleted_count": self.deleted_count}]


def test_reset_knowledge_graph_purges_test_patients_and_replays():
    client = _FakeClient(deleted_count=5)
    test_patients, ruleset_replays = reset_knowledge_graph(client)
    assert test_patients == 5
    assert ruleset_replays == 5
    assert len(client.calls) == 2
    assert "TestPatient" in client.calls[0][0]
    assert "RulesetReplay" in client.calls[1][0]


def test_reset_patient_graph_binds_to_each_source():
    client = _FakeClient(deleted_count=2)
    counts = reset_patient_graph(client)
    assert counts == {source: 2 for source in PATIENT_GRAPH_SOURCES}
    for _, params in client.calls:
        assert params["source"] in PATIENT_GRAPH_SOURCES


def test_reset_patient_graph_never_targets_a_bare_match():
    """Every purge query in this module must bind `source` -- never a bare MATCH."""
    client = _FakeClient()
    reset_patient_graph(client)
    for query, params in client.calls:
        assert "$source" in query
        assert params.get("source")


def test_reset_validation_lab_returns_full_report():
    knowledge_client = _FakeClient(deleted_count=1)
    patient_client = _FakeClient(deleted_count=4)
    report = reset_validation_lab(knowledge_client, patient_client)
    assert report.test_patients == 1
    assert report.ruleset_replays == 1
    assert report.validation_cases == 4
    assert report.patient_graph_by_source == {
        source: 4 for source in PATIENT_GRAPH_SOURCES
    }
    as_dict = report.to_dict()
    assert as_dict["validation_cases"] == 4
