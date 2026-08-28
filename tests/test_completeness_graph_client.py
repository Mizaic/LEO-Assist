"""The completeness domain lives on the patient graph, not the knowledge graph.

AuditDomain and ValueSet nodes are written by ensure_service_completeness_domain,
which uses PatientGraphClient. The quality_check subgraph must read from the
same graph so it finds the schema.

Atlas trace:
  DI: DI-F22160C3  (quality-check subgraph)
  DO: DO-69F520C9
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# -- helper -------------------------------------------------------------------

def _schema_row():
    """One completeness group as stored in the ValueSet."""
    return [
        {
            "completeness_schema": (
                '{"groups": [{'
                '"name": "Blood pressure",'
                '"required": true,'
                '"kind": "mandatory",'
                '"concept_ids": [75367002],'
                '"semantic_categories": [],'
                '"members": [],'
                '"if_group": null,'
                '"then_group": null'
                "}]}"
            )
        }
    ]


class _EmptyGlobalReport:
    def to_dict(self) -> dict:
        return {"total_checked": 0, "compliant_count": 0, "issues": []}


# -- red test: wrong client ---------------------------------------------------

def test_load_schema_uses_patient_graph_not_knowledge_graph():
    """_load_completeness_schema must open a PatientGraphClient.

    Before the fix it opens KnowledgeGraphClient, which connects to a separate
    URI that holds no tenant AuditDomain nodes. The schema is never found and
    every run reports configured=false.
    """
    from libs.pipeline_graph.subgraphs import quality_check

    patient_mock = MagicMock()
    patient_mock.run.return_value = _schema_row()
    patient_mock.__enter__ = lambda s: s
    patient_mock.__exit__ = MagicMock(return_value=False)

    knowledge_mock = MagicMock()
    knowledge_mock.run.return_value = []

    with (
        patch(
            "libs.pipeline_graph.subgraphs.quality_check.PatientGraphClient",
            return_value=patient_mock,
        ) as pat_cls,
        patch(
            "libs.pipeline_graph.subgraphs.quality_check.KnowledgeGraphClient",
            return_value=knowledge_mock,
        ) as kg_cls,
    ):
        schema = quality_check._load_completeness_schema("svc_7980224", "minimum_dataset")

    # The patient graph must have been queried.
    pat_cls.assert_called_once()
    patient_mock.run.assert_called_once()

    # The knowledge graph must NOT be queried for the schema.
    knowledge_mock.run.assert_not_called()

    # The schema must be returned.
    assert len(schema) == 1
    assert schema[0]["name"] == "Blood pressure"


# -- green: completeness result is configured when schema found ---------------

def test_quality_check_reports_configured_when_patient_graph_has_domain(monkeypatch):
    """End-to-end: state has domain/subdomain -> PatientGraphClient finds schema
    -> configured=True with groups evaluated."""
    from libs.pipeline_graph.subgraphs import quality_check

    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)

    patient_mock = MagicMock()
    patient_mock.run.return_value = _schema_row()

    with patch(
        "libs.pipeline_graph.subgraphs.quality_check.PatientGraphClient",
        return_value=patient_mock,
    ):
        result = quality_check.run_quality_checks(
            {
                "patient_id": "p-test",
                "completeness_domain": "svc_7980224",
                "completeness_subdomain": "minimum_dataset",
                "entities": [{"concept_id": "75367002", "semantic_tag": "observable_entity"}],
                "episodes": [{}],
            }
        )

    completeness = result.get("completeness_result") or {}
    assert completeness.get("configured") is True, (
        f"Expected configured=True, got: {completeness}"
    )
    # Blood pressure matched via concept_id 75367002.
    assert completeness.get("complete") is True
