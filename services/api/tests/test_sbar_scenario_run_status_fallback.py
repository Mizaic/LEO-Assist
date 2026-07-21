"""Regression tests for the scenario-run status fallback in sbar.py.

DurableStepRunner is the only writer of :PipelineRun/:PipelineStageRun nodes,
but it is gated behind DURABLE_ENGINE_ENABLED which defaults to "false" and
is unset everywhere in this repo's env config. With the flag off (the
default in every environment today), referral runs -- including AI
Summarisation scenario runs launched from /admin/knowledge?tab=ai-summarisation
-- execute via the legacy WorkflowEngine, which only ever writes
:AuditEvent nodes (audit-{run_id} from engine.py, audit-{run_id}:sbar from
sbar_orchestrator.py).

Before this fix, `_normalise_child_run` always defaulted every child case to
status "queued" whenever no :PipelineRun node existed (i.e. always, in
practice), while `_child_counts` counted that same "queued" status as
"running" for the parent rollup -- so the Scenario Runs panel showed a
"Running" parent chip sitting forever above "Queued" child rows, even after
the pipeline had actually completed. See the user-reported symptom: "UI
just says running and queued at the same time."
"""

from __future__ import annotations

from app.routers.sbar import (
    _child_counts,
    _derive_parent_status,
    _normalise_audit_fallback,
    _normalise_child_run,
)


def test_normalise_audit_fallback_returns_none_without_any_audit_event() -> None:
    assert _normalise_audit_fallback("run-1", []) is None


def test_normalise_audit_fallback_maps_completed_status() -> None:
    audit_rows = [
        {
            "id": "audit-run-1",
            "status": "completed",
            "patient_id": "pat-1",
            "encounter_id": "enc-1",
            "assessment_id": None,
            "created_at": "2026-07-03T15:59:37Z",
            "error_count": 0,
            "first_error": None,
        }
    ]
    result = _normalise_audit_fallback("run-1", audit_rows)
    assert result is not None
    assert result["status"] == "completed"
    assert result["patient_id"] == "pat-1"
    assert result["encounter_id"] == "enc-1"
    assert result["completed_at"] == "2026-07-03T15:59:37Z"


def test_normalise_audit_fallback_maps_error_status_to_failed() -> None:
    audit_rows = [
        {
            "id": "audit-run-2",
            "status": "error",
            "patient_id": "pat-2",
            "encounter_id": "enc-2",
            "assessment_id": None,
            "created_at": "2026-07-03T15:59:37Z",
            "error_count": 1,
            "first_error": "boom",
        }
    ]
    result = _normalise_audit_fallback("run-2", audit_rows)
    assert result is not None
    assert result["status"] == "failed"


def test_normalise_audit_fallback_merges_assessment_id_from_sbar_audit_event() -> None:
    audit_rows = [
        {
            "id": "audit-run-3",
            "status": "completed",
            "patient_id": "pat-3",
            "encounter_id": "enc-3",
            "assessment_id": None,
            "created_at": "2026-07-03T15:59:37Z",
            "error_count": 0,
            "first_error": None,
        },
        {
            "id": "audit-run-3:sbar",
            "status": "completed",
            "patient_id": "pat-3",
            "encounter_id": "enc-3",
            "assessment_id": "assessment-xyz",
            "created_at": "2026-07-03T15:59:20Z",
            "error_count": 0,
            "first_error": None,
        },
    ]
    result = _normalise_audit_fallback("run-3", audit_rows)
    assert result is not None
    assert result["assessment_id"] == "assessment-xyz"


def test_normalise_child_run_falls_back_to_audit_event_when_no_pipeline_run_node() -> (
    None
):
    """No :PipelineRun node exists (DURABLE_ENGINE_ENABLED=false), but the
    legacy engine's :AuditEvent shows the run actually completed -- the
    child should reflect "completed", not the old hard-coded "queued"."""
    audit_rows = [
        {
            "id": "audit-run-4",
            "status": "completed",
            "patient_id": "pat-4",
            "encounter_id": "enc-4",
            "assessment_id": None,
            "created_at": "2026-07-03T15:59:37Z",
            "error_count": 0,
            "first_error": None,
        }
    ]
    child = _normalise_child_run("case-1", "run-4", [], [], audit_rows)
    assert child["status"] == "completed"
    assert child["patient_id"] == "pat-4"


def test_normalise_child_run_stays_queued_with_no_pipeline_run_and_no_audit_event() -> (
    None
):
    """A run that has genuinely not started yet still shows "queued"."""
    child = _normalise_child_run("case-1", "run-5", [], [], [])
    assert child["status"] == "queued"


def test_normalise_child_run_prefers_pipeline_run_node_over_audit_fallback() -> None:
    """When DurableStepRunner *is* enabled, the real :PipelineRun node wins."""
    run_rows = [
        {
            "run_id": "run-6",
            "status": "running",
            "patient_id": "pat-6",
            "encounter_id": "enc-6",
            "assessment_id": None,
            "created_at": None,
            "updated_at": None,
            "completed_at": None,
            "completion_event_json": None,
        }
    ]
    audit_rows = [
        {
            "id": "audit-run-6",
            "status": "completed",
            "patient_id": "pat-6",
            "encounter_id": "enc-6",
            "assessment_id": None,
            "created_at": "2026-07-03T15:59:37Z",
            "error_count": 0,
            "first_error": None,
        }
    ]
    child = _normalise_child_run("case-1", "run-6", run_rows, [], audit_rows)
    assert child["status"] == "running"


def test_child_counts_and_parent_status_reflect_completed_audit_fallback() -> None:
    """End-to-end of the reported bug: once every child completes via the
    audit fallback, the parent must report "completed", not "running"."""
    children = [
        _normalise_child_run(
            "case-1",
            "run-7",
            [],
            [],
            [
                {
                    "id": "audit-run-7",
                    "status": "completed",
                    "patient_id": "pat-7",
                    "encounter_id": "enc-7",
                    "assessment_id": None,
                    "created_at": "2026-07-03T15:59:37Z",
                    "error_count": 0,
                    "first_error": None,
                }
            ],
        )
    ]
    counts = _child_counts(children)
    assert counts == {"completed": 1, "failed": 0, "running": 0}
    assert _derive_parent_status(counts, total=1, current="running") == "completed"
