"""Tests for Validation Lab trace events and inspector API."""

from __future__ import annotations

from typing import Any

import pytest

from libs.validation_lab import inspector as lab_inspector
from libs.validation_lab.trace_events import build_trace_event, keys_from_state


def test_build_trace_event_normalises_fields() -> None:
    event = build_trace_event(
        "durable_step_started",
        "run-1",
        action_id="act-ref-extract",
        input_keys=["entities", "patient_id"],
    )
    assert event["type"] == "durable_step_started"
    assert event["run_id"] == "run-1"
    assert event["schema_version"] == "1"
    assert event["input_keys"] == ["entities", "patient_id"]


def test_keys_from_state_caps_and_sorts() -> None:
    keys = keys_from_state({"z": 1, "a": 2, "entities": []})
    assert keys == ["a", "entities", "z"]


class _InspectorClient:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.stages: dict[str, list[dict[str, Any]]] = {}
        self.cases: dict[str, dict[str, Any]] = {}
        self.lab_runs: dict[str, dict[str, Any]] = {}

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        q = " ".join(query.split())
        if "plan_raw_json" in q and "PipelineRun {id: $run_id}" in q:
            row = self.runs.get(params["run_id"])
            return [row] if row else []
        if "input_json AS input_json" in q and "ORDER BY" in q:
            return list(self.stages.get(params["run_id"]) or [])
        if "s.input_json AS input_json" in q and "step_id = $step_id" in q:
            for row in self.stages.get(params["run_id"]) or []:
                if row.get("step_id") == params["step_id"]:
                    return [row]
            return []
        return []


def test_parse_plan_edges_from_related_action() -> None:
    raw = """
    {
      "action": [
        {"id": "act-a"},
        {
          "id": "act-b",
          "relatedAction": [{"actionId": "act-a", "relationship": "after-end"}]
        }
      ]
    }
    """
    edges = lab_inspector._parse_plan_edges(raw)
    assert edges == [
        {
            "source": "act-a",
            "target": "act-b",
            "relationship": "after-end",
        }
    ]


def test_get_run_inspector_returns_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _InspectorClient()
    client.cases["case-1"] = {"id": "case-1", "plan_id": "pd-referral-assessment"}
    client.lab_runs["run-1"] = {
        "id": "run-1",
        "status": "running",
        "plan_id": "pd-referral-assessment",
    }
    client.runs["run-1"] = {
        "pipeline_status": "running",
        "plan_id": "pd-referral-assessment",
        "execution_manifest_json": '{"schema_version":"1.0"}',
        "plan_raw_json": (
            '{"action":['
            '{"id":"act-ref-durable-start","_dynamicValues":{"params":{"nodeType":"trigger","subgraphId":"trigger"}}},'
            '{"id":"act-ref-extract","relatedAction":[{"actionId":"act-ref-durable-start","relationship":"after-end"}],'
            '"_dynamicValues":{"params":{"subgraphId":"extraction"}}}'
            "]}"
        ),
    }
    client.stages["run-1"] = [
        {
            "step_id": "act-ref-extract",
            "event_type": "extraction",
            "status": "running",
            "worker_id": "worker-1",
            "started_at": "2026-08-06T10:00:00+00:00",
            "completed_at": "",
            "attempt": 1,
            "input_json": '{"patient_id":"p-1"}',
            "output_json": "{}",
        }
    ]
    monkeypatch.setattr(
        "libs.validation_lab.inspector.resolve_pipeline_run_id",
        lambda *args, **kwargs: "run-1",
    )
    monkeypatch.setattr(
        "libs.validation_lab.service.get_run",
        lambda c, case_id, run_id: {
            "run": client.lab_runs[run_id],
            "case": client.cases[case_id],
        },
    )
    payload = lab_inspector.get_run_inspector(client, case_id="case-1", run_id="run-1")
    assert payload["pipeline_run_id"] == "run-1"
    assert len(payload["spans"]) == 1
    assert payload["spans"][0]["input_keys"] == ["patient_id"]
    assert payload["plan_steps"][0]["action_id"] == "act-ref-durable-start"
    assert payload["plan_edges"][0]["target"] == "act-ref-extract"
