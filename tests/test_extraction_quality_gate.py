"""VT for DI-4A012A59 -- pause, correct, unlock, de-identified few-shot."""

from __future__ import annotations

from libs.pipeline.document_quality import score_document_quality
from libs.pipeline.extraction_quality_gate import (
    DEFAULT_QUALITY_THRESHOLD,
    TASK_TYPE,
    build_review_task,
    complete_extraction_review,
    decide_extraction_gate,
    is_stage_pause_not_failure,
)
from libs.workflow.durable_step_runner import (
    _is_stage_failure,
    _step_result_for_output,
)
from libs.workflow.durable_steps import StepResult
from libs.workflow.plan_manifest import PlanAction


def _low_quality():
    return score_document_quality(
        "Section A: Gynaecological Cancer type suspected\nOvary [ ] Cervix [X]",
        few_shot_max_similarity=0.10,
        known_fingerprints={},
    )


def _high_quality():
    text = "Appendix A: Referral criteria\n| GP gut feeling | [X] |"
    fp = __import__(
        "libs.pipeline.document_quality", fromlist=["form_fingerprint"]
    ).form_fingerprint(text)
    return score_document_quality(
        text,
        few_shot_max_similarity=0.92,
        known_fingerprints={"nss": fp},
    )


def test_pause_builds_operations_review_task() -> None:
    task = build_review_task(
        run_id="run-1",
        patient_id="p1",
        quality=_low_quality(),
        draft_entities=[{"text": "Cervix"}],
    )
    assert task["task_type"] == TASK_TYPE
    assert task["status"] == "pending"
    assert task["run_id"] == "run-1"
    assert "few_shot_ood" in task["reason"]


def test_low_score_pauses_and_keeps_draft() -> None:
    draft = [{"text": "Cervix", "semantic_tag": "body structure"}]
    decision = decide_extraction_gate(
        _low_quality(), draft_entities=draft, threshold=DEFAULT_QUALITY_THRESHOLD
    )
    assert decision.action == "pause"
    assert decision.draft_entities == draft
    assert decision.next_event_type is None


def test_high_score_continues() -> None:
    decision = decide_extraction_gate(
        _high_quality(), draft_entities=[], threshold=DEFAULT_QUALITY_THRESHOLD
    )
    assert decision.action == "continue"
    assert decision.next_event_type == "post_processing_requested"


def test_paused_is_not_treated_as_failed() -> None:
    paused = StepResult(status="paused")
    failed = StepResult(status="failed", errors=["boom"])
    assert is_stage_pause_not_failure(paused) is True
    assert _is_stage_failure(paused) is False
    assert _is_stage_failure(failed) is True


def test_complete_replaces_draft_writes_deid_few_shot_and_resumes_once() -> None:
    source = (
        "Ms Smith NHS 943 476 5919\n"
        "Section A: Gynaecological Cancer type suspected\n"
        "Cervix [X]\n"
        "polyp noted around cervical opening"
    )
    draft = [{"text": "Ovary", "semantic_tag": "body structure"}]
    reviewed = [{"text": "Cervix", "semantic_tag": "body structure"}]
    result = complete_extraction_review(
        source_text=source,
        draft_entities=draft,
        reviewed_entities=reviewed,
        known_fingerprints={},
    )
    assert result.entities == reviewed
    assert result.entities != draft
    assert result.resume_once is True
    assert result.next_event_type == "post_processing_requested"
    assert result.few_shot["deidentified"] is True
    assert "943 476 5919" not in result.few_shot["input"]
    assert (
        "NHS_NUMBER" in result.few_shot["input"] or "[NHS" in result.few_shot["input"]
    )
    assert result.form_fingerprint_id
    assert result.form_fingerprint_id != "unknown"


def test_missing_quality_does_not_pause_extraction() -> None:
    action = PlanAction(action_id="extract", subgraph_id="extraction")
    result = _step_result_for_output(action, {"entities": []})
    assert result.status == "completed"
    assert "extraction_quality_pause" not in result.warnings


def test_low_quality_payload_pauses_extraction() -> None:
    action = PlanAction(action_id="extract", subgraph_id="extraction")
    quality = _low_quality().to_dict()
    result = _step_result_for_output(
        action, {"entities": [{"text": "Cervix"}], "document_quality": quality}
    )
    assert result.status == "paused"
    assert "extraction_quality_pause" in result.warnings
