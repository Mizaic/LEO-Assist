"""Tests for `services/neo4j_mcp/_client.py`.

Atlas trace:
  DO: DO-5F438C17
  DI: DI-5700882E

We mock the underlying graph clients so the tiny dict-coercion helper
and the run() wrappers can be tested without a live Neo4j.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.neo4j_mcp._client import (
    _as_dict_rows,
    knowledge_run,
    patient_run,
)


class TestAsDictRows:
    def test_mapping_rows_converted_to_dict(self):
        rows = [{"a": 1, "b": 2}]
        out = _as_dict_rows(rows)
        assert out == [{"a": 1, "b": 2}]
        assert isinstance(out[0], dict)

    def test_neo4j_record_like_uses_data_method(self):
        record = MagicMock()
        record.data.return_value = {"x": 9}
        # Mapping-check is True for MagicMock by accident in some cases,
        # so guarantee mapping returns False:
        record.__class__ = type("R", (), {"data": record.data})
        out = _as_dict_rows([record])
        assert out == [{"x": 9}]

    def test_empty_input_returns_empty_list(self):
        assert _as_dict_rows([]) == []


class TestPatientRun:
    @patch("services.neo4j_mcp._client.PatientGraphClient")
    def test_runs_query_and_closes_client(self, MockClient):
        instance = MockClient.return_value
        instance.run.return_value = [{"n": 1}]
        out = patient_run("MATCH (n) RETURN n", limit=1)
        assert out == [{"n": 1}]
        instance.run.assert_called_once_with("MATCH (n) RETURN n", limit=1)
        instance.close.assert_called_once()

    @patch("services.neo4j_mcp._client.PatientGraphClient")
    def test_close_runs_even_if_query_raises(self, MockClient):
        instance = MockClient.return_value
        instance.run.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            patient_run("MATCH (n) RETURN n")
        instance.close.assert_called_once()


class TestKnowledgeRun:
    @patch("services.neo4j_mcp._client.KnowledgeGraphClient")
    def test_runs_query_and_closes_client(self, MockClient):
        instance = MockClient.return_value
        instance.run.return_value = [{"k": "v"}]
        out = knowledge_run("MATCH (m:Measure) RETURN m")
        assert out == [{"k": "v"}]
        instance.close.assert_called_once()
