"""Per-stage validation entity snapshots on AuditEvent.validation_output."""

from __future__ import annotations

from libs.workflow.engine import WorkflowEngine, _VALIDATION_SNAPSHOT_SUBGRAPHS


def test_record_validation_stage_snapshot_captures_entities() -> None:
    state: dict = {
        "capture_validation_output": True,
        "entities": [
            {"text": "Hb"},
            {"text": "seizure"},
        ],
    }
    WorkflowEngine._record_validation_stage_snapshot(state, "extraction")
    snapshots = state["validation_stage_snapshots"]
    assert snapshots["extraction"]["entity_count"] == 2
    assert snapshots["extraction"]["terms"] == ["Hb", "seizure"]


def test_record_validation_stage_snapshot_ignores_non_validation_subgraphs() -> None:
    state: dict = {
        "capture_validation_output": True,
        "entities": [{"text": "fever"}],
    }
    WorkflowEngine._record_validation_stage_snapshot(state, "terminology")
    assert "validation_stage_snapshots" not in state


def test_record_validation_stage_snapshot_skips_without_flag() -> None:
    state: dict = {"entities": [{"text": "fever"}]}
    WorkflowEngine._record_validation_stage_snapshot(state, "extraction")
    assert "validation_stage_snapshots" not in state


def test_validation_snapshot_subgraphs_match_plan() -> None:
    assert _VALIDATION_SNAPSHOT_SUBGRAPHS == frozenset(
        {
            "extraction",
            "post_processing",
            "relation_linking",
            "extraction_check",
        }
    )


def test_validation_output_json_includes_stage_snapshots_key() -> None:
    from pathlib import Path

    source = Path("libs/workflow/engine.py").read_text(encoding="utf-8")
    assert '"stage_snapshots": stage_snapshots' in source
    assert "_record_validation_stage_snapshot" in source
    assert "_validation_terms_from_entities" in source
    assert '"semantic_tag": tag' in source
