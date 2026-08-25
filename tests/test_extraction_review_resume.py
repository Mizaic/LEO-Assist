"""VT for DI-4A012A59 -- persist HITL task and resume once."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.cypher.extraction_review_queries import (
    CANCEL_EXTRACTION_REVIEW_TASK,
    CANCEL_PAUSED_EXTRACTION_STAGE,
    CREATE_EXTRACTION_REVIEW_TASK,
    UNLOCK_PAUSED_EXTRACTION_STAGE,
)
from libs.pipeline.document_quality import score_document_quality
from libs.pipeline.extraction_quality_gate import (
    TASK_TYPE,
    generic_hitl_resolve_allowed,
)
from libs.pipeline.extraction_review_store import (
    PersistReviewRequest,
    cancel_extraction_review,
    load_extraction_review_detail,
    persist_extraction_review_task,
    plan_extraction_resume,
    resume_extraction_review,
)


def _quality():
    return score_document_quality(
        "Section A: Gynaecological Cancer type suspected\nOvary [ ] Cervix [X]",
        few_shot_max_similarity=0.10,
        known_fingerprints={},
    )


def _req(**overrides):
    payload = {
        "run_id": "run-1",
        "patient_id": "p1",
        "plan_definition_id": "pd-referral-assessment",
        "step_id": "act-ref-extract",
        "next_action_id": "act-ref-post-process",
        "quality": _quality(),
        "draft_entities": [{"text": "Cervix"}],
    }
    payload.update(overrides)
    return PersistReviewRequest(**payload)


def test_pause_writes_pending_operations_review_task() -> None:
    task = persist_extraction_review_task(_req())
    assert task["task_type"] == TASK_TYPE
    assert task["status"] == "pending"
    assert task["run_id"] == "run-1"
    assert task["next_action_id"] == "act-ref-post-process"
    assert task["task_id"]
    assert "Cervix" in task["draft_entities_json"]


def test_write_query_does_not_require_an_episode() -> None:
    assert "HITLTask" in CREATE_EXTRACTION_REVIEW_TASK
    assert "EpisodeOfCare" not in CREATE_EXTRACTION_REVIEW_TASK
    assert "extraction_quality_review" in CREATE_EXTRACTION_REVIEW_TASK
    assert "source_text" in CREATE_EXTRACTION_REVIEW_TASK


def test_unlock_query_completes_paused_stage_only() -> None:
    assert "paused" in UNLOCK_PAUSED_EXTRACTION_STAGE
    assert "completed" in UNLOCK_PAUSED_EXTRACTION_STAGE


def test_complete_replaces_draft_and_resumes_once() -> None:
    task = persist_extraction_review_task(_req(draft_entities=[{"text": "Ovary"}]))
    source = "Ms Smith NHS 943 476 5919\nCervix [X]"
    reviewed = [{"text": "Cervix"}]
    first = plan_extraction_resume(
        task=task,
        source_text=source,
        reviewed_entities=reviewed,
        already_resumed=False,
    )
    second = plan_extraction_resume(
        task=task,
        source_text=source,
        reviewed_entities=reviewed,
        already_resumed=True,
    )
    assert first.entities == reviewed
    assert first.entities != [{"text": "Ovary"}]
    assert first.publish is True
    assert first.next_step_id == "act-ref-post-process"
    assert first.next_event_type == "durable_step"
    assert "943 476 5919" not in first.few_shot["input"]
    assert second.publish is False
    assert second.already_resumed is True


def test_resume_writes_stage_and_publishes_once() -> None:
    task = persist_extraction_review_task(_req(draft_entities=[{"text": "Ovary"}]))
    client = MagicMock()
    client.run.side_effect = [
        [{"status": "pending", "resumed_at": None, **task}],
        [{"step_id": "act-ref-extract"}],
        [{"task_id": task["task_id"], "status": "resolved"}],
    ]
    published: list[dict] = []

    def _publish(message: dict) -> None:
        published.append(message)

    result = resume_extraction_review(
        client,
        task_id=task["task_id"],
        source_text="Cervix [X]",
        reviewed_entities=[{"text": "Cervix"}],
        publish=_publish,
    )
    assert result.publish is True
    assert len(published) == 1
    assert published[0]["action_id"] == "act-ref-post-process"
    assert published[0]["event_type"] == "durable_step"
    assert published[0]["run_id"] == "run-1"
    cypher_calls = [call.args[0] for call in client.run.call_args_list]
    assert any("paused" in query for query in cypher_calls)


def test_durable_pause_helper_writes_hitl_task() -> None:
    from libs.workflow.durable_step_runner import _enqueue_extraction_quality_review
    from libs.workflow.durable_steps import StepRequest, StepResult

    client = MagicMock()
    request = StepRequest(
        event_type="durable_step",
        run_id="run-1",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p1",
        plan_definition_id="pd-referral-assessment",
    )
    result = StepResult(
        status="paused",
        output={
            "entities": [{"text": "Cervix"}],
            "document_quality": _quality().to_dict(),
            "encounter_text": "Cervix [X] from document chunks",
            "chunk_ids": ["c1"],
            "text_segmentation_mode": "document_chunks",
        },
    )
    _enqueue_extraction_quality_review(client, request, result, ["act-next"])
    assert client.run.called
    assert "HITLTask" in client.run.call_args[0][0]
    assert "EpisodeOfCare" not in client.run.call_args[0][0]
    assert (
        client.run.call_args.kwargs.get("source_text")
        == "Cervix [X] from document chunks"
    )


def test_review_detail_returns_letter_and_draft() -> None:
    task = persist_extraction_review_task(_req())
    client = MagicMock()
    client.run.return_value = [task]
    store = MagicMock()
    store.load_accumulated_state.return_value = {"encounter_text": "Cervix [X]"}
    detail = load_extraction_review_detail(client, task["task_id"], store=store)
    assert detail["source_text"] == "Cervix [X]"
    assert detail["draft_entities"][0]["text"] == "Cervix"
    assert detail["task_id"] == task["task_id"]


def test_generic_hitl_resolve_does_not_unlock_extraction_review() -> None:
    assert generic_hitl_resolve_allowed(TASK_TYPE) is False
    assert generic_hitl_resolve_allowed("exclusion_conflict") is True


def test_create_query_does_not_reset_cancelled_status() -> None:
    after_create = CREATE_EXTRACTION_REVIEW_TASK.split("ON CREATE SET", 1)[1]
    later_set = after_create.split("SET", 1)[1].split("RETURN", 1)[0]
    assert "t.status" not in later_set


def test_cancel_query_does_not_complete_or_teach() -> None:
    assert "cancelled" in CANCEL_EXTRACTION_REVIEW_TASK
    assert "pending" in CANCEL_EXTRACTION_REVIEW_TASK
    assert "cancel_reason" in CANCEL_EXTRACTION_REVIEW_TASK
    assert "completed" not in CANCEL_PAUSED_EXTRACTION_STAGE
    assert "cancelled" in CANCEL_PAUSED_EXTRACTION_STAGE
    assert "running" not in CANCEL_PAUSED_EXTRACTION_STAGE


def test_cancel_marks_task_and_does_not_resume() -> None:
    task = persist_extraction_review_task(_req())
    client = MagicMock()
    client.run.side_effect = [
        [{"status": "pending", "resumed_at": None, **task}],
        [{"task_id": task["task_id"], "status": "cancelled"}],
        [{"step_id": "act-ref-extract"}],
    ]
    result = cancel_extraction_review(
        client,
        task_id=task["task_id"],
        reason="duplicate",
        cancelled_by="staff",
    )
    assert result.status == "cancelled"
    assert result.reason == "duplicate"
    assert result.taught is False
    assert result.resumed is False
    queries = [call.args[0] for call in client.run.call_args_list]
    assert any("cancel_reason" in query for query in queries)
    assert not any("FormFingerprint" in query for query in queries)
    assert not any("completed" in query and "paused" in query for query in queries)


def test_cancel_requires_a_known_reason() -> None:
    task = persist_extraction_review_task(_req())
    client = MagicMock()
    try:
        cancel_extraction_review(
            client,
            task_id=task["task_id"],
            reason="not-a-reason",
            cancelled_by="staff",
        )
    except ValueError as exc:
        assert "reason" in str(exc)
        return
    raise AssertionError("expected ValueError")


def test_cancel_is_safe_when_already_cancelled() -> None:
    task = persist_extraction_review_task(_req())
    client = MagicMock()
    client.run.side_effect = [[{**task, "status": "cancelled", "resumed_at": None}]]
    result = cancel_extraction_review(
        client,
        task_id=task["task_id"],
        reason="duplicate",
        cancelled_by="staff",
    )
    assert result.status == "cancelled"
    assert result.already_cancelled is True
    assert client.run.call_count == 1
