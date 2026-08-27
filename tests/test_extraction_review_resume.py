"""VT for DI-4A012A59 -- persist HITL task and resume once."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.cypher.extraction_review_queries import (
    CANCEL_EXTRACTION_REVIEW_TASK,
    CANCEL_PAUSED_EXTRACTION_STAGE,
    CREATE_EXTRACTION_REVIEW_TASK,
    UNLOCK_PAUSED_EXTRACTION_STAGE,
)
from libs.pipeline.document_quality import form_fingerprint, score_document_quality
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
    rerun_paused_extraction,
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


def test_review_detail_includes_org_and_service_from_pipeline_state() -> None:
    """Detail must expose org/service ids and names for pre-populating teach form."""
    task = persist_extraction_review_task(_req())
    client = MagicMock()
    client.run.return_value = [task]
    store = MagicMock()
    store.load_accumulated_state.return_value = {
        "encounter_text": "Cervix [X]",
        "healthcare_service_org_id": "org-spoa-1",
        "healthcare_service_org_name": "Sherwood Forest Hospitals",
        "healthcare_service_id": "svc-gynaecology",
        "healthcare_service_name": "2WW Gynaecology",
    }
    detail = load_extraction_review_detail(client, task["task_id"], store=store)
    assert detail["organization_id"] == "org-spoa-1"
    assert detail["organization_name"] == "Sherwood Forest Hospitals"
    assert detail["service_id"] == "svc-gynaecology"
    assert detail["service_name"] == "2WW Gynaecology"


def test_review_detail_org_and_service_default_to_empty_when_absent() -> None:
    """If both state and graph have no service scope, defaults are empty strings."""
    task = persist_extraction_review_task(_req())
    client = MagicMock()

    def _run(query, **_kwargs):
        if "PipelineRun" in query and "case_id" in query:
            return [{"case_id": ""}]
        return [task]

    client.run.side_effect = _run
    store = MagicMock()
    store.load_accumulated_state.return_value = {"encounter_text": "Some letter"}
    detail = load_extraction_review_detail(client, task["task_id"], store=store)
    assert detail["organization_id"] == ""
    assert detail["organization_name"] == ""
    assert detail["service_id"] == ""
    assert detail["service_name"] == ""


def test_review_detail_returns_content_fingerprint_hash() -> None:
    letter = "Section A: Gynaecological Cancer type suspected\nOvary [ ] Cervix [X]"
    task = persist_extraction_review_task(_req())
    client = MagicMock()
    client.run.return_value = [task]
    store = MagicMock()
    store.load_accumulated_state.return_value = {"encounter_text": letter}
    detail = load_extraction_review_detail(client, task["task_id"], store=store)
    assert detail["form_fingerprint"] == form_fingerprint(letter)
    assert detail["form_fingerprint"] != "unknown"


def test_review_detail_falls_back_to_graph_when_state_lacks_org_service() -> None:
    """When accumulated state has no service scope, resolve via ReferralRequest."""
    from libs.cypher.extraction_review_queries import GET_RUN_CASE_ID
    from libs.clinical_scoping.healthcare_service import HealthcareServiceScope

    task = persist_extraction_review_task(_req())
    task_id = task["task_id"]

    def _run(query, **_kwargs):
        if query == GET_RUN_CASE_ID:
            return [{"case_id": "000481914514"}]
        return [task]

    client = MagicMock()
    client.run.side_effect = _run
    store = MagicMock()
    store.load_accumulated_state.return_value = {
        "encounter_text": "Referral letter",
        "ubrn": "000481914514",
    }

    scope = HealthcareServiceScope(
        id="svc-graph-gynaecology",
        name="2WW Gynaecology",
        specialty="2WW",
        guideline_ids=["NG12"],
        organization_id="org-graph-1",
        organization_name="Sherwood Forest Hospitals",
    )

    from unittest.mock import patch

    with patch(
        "libs.pipeline.extraction_review_store.resolve_healthcare_service",
        return_value=scope,
    ) as resolve_mock:
        detail = load_extraction_review_detail(client, task_id, store=store)

    resolve_mock.assert_called_once_with(
        client,
        source_node_type="ReferralRequest",
        source_node_id="000481914514",
    )
    assert detail["organization_id"] == "org-graph-1"
    assert detail["organization_name"] == "Sherwood Forest Hospitals"
    assert detail["service_id"] == "svc-graph-gynaecology"
    assert detail["service_name"] == "2WW Gynaecology"


def test_review_detail_graph_fallback_prefers_patient_ubrn_match() -> None:
    from libs.cypher.extraction_review_queries import (
        GET_REFERRAL_BY_PATIENT_UBRN,
        GET_REVIEW_IDENTIFIERS,
        GET_RUN_CASE_ID,
    )
    from libs.clinical_scoping.healthcare_service import HealthcareServiceScope

    task = persist_extraction_review_task(_req(patient_id="p-718"))
    task_id = task["task_id"]
    calls: list[str] = []

    def _run(query, **_kwargs):
        calls.append(query)
        if query == GET_RUN_CASE_ID:
            return [{"case_id": ""}]
        if query == GET_REVIEW_IDENTIFIERS:
            return [{"nhs_number": "", "ubrn": "000481914514"}]
        if query == GET_REFERRAL_BY_PATIENT_UBRN:
            return [{"referral_id": "rr-by-ubrn"}]
        return [task]

    client = MagicMock()
    client.run.side_effect = _run
    store = MagicMock()
    store.load_accumulated_state.return_value = {"encounter_text": "Referral letter"}
    scope = HealthcareServiceScope(
        id="6711368",
        name="Fast track cancer referral",
        specialty="2WW",
        guideline_ids=[],
        organization_id="M0L1I",
        organization_name="Sherwood Forest Hospitals",
    )

    from unittest.mock import patch

    with patch(
        "libs.pipeline.extraction_review_store.resolve_healthcare_service",
        return_value=scope,
    ) as resolve_mock:
        detail = load_extraction_review_detail(client, task_id, store=store)

    assert GET_REFERRAL_BY_PATIENT_UBRN in calls
    resolve_mock.assert_called_once_with(
        client,
        source_node_type="ReferralRequest",
        source_node_id="rr-by-ubrn",
    )
    assert detail["organization_name"] == "Sherwood Forest Hospitals"


def test_review_detail_graph_fallback_not_called_when_state_has_both_ids() -> None:
    """When state already has both IDs, the graph fallback query is not called."""
    from libs.cypher.extraction_review_queries import GET_RUN_CASE_ID

    task = persist_extraction_review_task(_req())
    task_id = task["task_id"]
    fallback_calls: list[str] = []

    def _run(query, **_kwargs):
        if query == GET_RUN_CASE_ID:
            fallback_calls.append("called")
        return [task]

    client = MagicMock()
    client.run.side_effect = _run
    store = MagicMock()
    store.load_accumulated_state.return_value = {
        "encounter_text": "Letter",
        "healthcare_service_org_id": "org-from-state",
        "healthcare_service_org_name": "State Org",
        "healthcare_service_id": "svc-from-state",
        "healthcare_service_name": "State Service",
    }
    detail = load_extraction_review_detail(client, task_id, store=store)
    assert detail["organization_id"] == "org-from-state"
    assert detail["organization_name"] == "State Org"
    assert detail["service_id"] == "svc-from-state"
    assert detail["service_name"] == "State Service"
    assert (
        fallback_calls == []
    ), "graph fallback must not be called when state is complete"


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


def test_rerun_paused_extraction_resets_stage_and_publishes() -> None:
    task = persist_extraction_review_task(_req())
    client = MagicMock()
    client.run.side_effect = [
        [{"status": "pending", "resumed_at": None, **task}],
        [{"step_id": "act-ref-extract"}],
        [{"task_id": task["task_id"], "status": "superseded"}],
    ]
    published: list[dict] = []

    result = rerun_paused_extraction(
        client,
        task_id=task["task_id"],
        publish=published.append,
        triggered_by="staff",
    )
    assert result.published is True
    assert result.run_id == "run-1"
    assert result.step_id == "act-ref-extract"
    assert len(published) == 1
    assert published[0]["action_id"] == "act-ref-extract"
    assert published[0]["event_type"] == "durable_step"
    queries = [call.args[0] for call in client.run.call_args_list]
    assert any("pending" in query and "paused" in query for query in queries)
    assert any("superseded" in query for query in queries)
