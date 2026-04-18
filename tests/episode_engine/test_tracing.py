"""Unit VT for the tracing module (VT-LEO-AI-506)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from services.analysis_worker.app.episode_engine.schemas import StageTrace
from services.analysis_worker.app.episode_engine.tracing import (
    build_provenance,
    new_trace_id,
    persist_trace,
)


def _stages() -> list[StageTrace]:
    return [
        StageTrace(
            stage="segmenter",
            prompt_version="v1",
            model_id="haiku",
            tier="small",
            input_tokens=100,
            output_tokens=20,
            cached_input_tokens=30,
            cost_usd=0.001234,
            latency_ms=500,
        ),
        StageTrace(
            stage="reconciler",
            prompt_version="v1",
            model_id="sonnet",
            tier="big",
            input_tokens=200,
            output_tokens=40,
            cached_input_tokens=10,
            cost_usd=0.002,
            latency_ms=1500,
            ok=False,
            error="schema validation failed",
        ),
    ]


def test_new_trace_id_unique_and_prefixed():
    """VT-506-TC-001: trace ids are prefixed and unique per call."""

    a = new_trace_id()
    b = new_trace_id()
    assert a.startswith("eet-") and b.startswith("eet-")
    assert a != b


def test_build_provenance_aggregates_stage_totals():
    """VT-506-TC-002: provenance sums input/output tokens and latency."""

    prov = build_provenance(
        trace_id="eet-test",
        stages=_stages(),
        encounter_count=42,
    )
    assert prov.trace_id == "eet-test"
    assert prov.total_input_tokens == 300
    assert prov.total_output_tokens == 60
    assert prov.total_cached_input_tokens == 40
    assert prov.total_cost_usd == round(0.001234 + 0.002, 6)
    assert prov.total_latency_ms == 2000
    assert prov.timeline_encounter_count == 42
    assert len(prov.stages) == 2


def test_persist_trace_writes_node_with_serialised_stages():
    """VT-506-TC-003: persist_trace writes a node with stage + error JSON."""

    client = MagicMock()
    persist_trace(
        client=client,
        trace_id="eet-123",
        patient_id="p-1",
        stages=_stages(),
        encounter_count=42,
        episode_count=2,
        errors=["reconciler failed"],
        dry_run=False,
    )
    assert client.run.call_count == 1
    kwargs = client.run.call_args.kwargs
    assert kwargs["trace_id"] == "eet-123"
    assert kwargs["patient_id"] == "p-1"
    assert kwargs["episode_count"] == 2
    assert kwargs["dry_run"] is False
    assert kwargs["total_input_tokens"] == 300
    assert kwargs["total_output_tokens"] == 60
    assert kwargs["total_cached_input_tokens"] == 40
    assert kwargs["total_cost_usd"] == round(0.001234 + 0.002, 6)

    stages = json.loads(kwargs["stages_json"])
    assert {s["stage"] for s in stages} == {"segmenter", "reconciler"}

    errors = json.loads(kwargs["errors_json"])
    assert errors == ["reconciler failed"]


def test_persist_trace_swallows_exceptions(caplog):
    """VT-506-TC-004: failures inside persist_trace are logged, never raised."""

    client = MagicMock()
    client.run.side_effect = RuntimeError("neo4j unavailable")
    with caplog.at_level("ERROR"):
        persist_trace(
            client=client,
            trace_id="eet-x",
            patient_id="p-1",
            stages=_stages(),
            encounter_count=1,
            episode_count=0,
            errors=[],
            dry_run=True,
        )
    assert "Failed to persist EpisodeEngineTrace" in caplog.text
