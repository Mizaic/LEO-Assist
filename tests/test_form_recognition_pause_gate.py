"""An unrecognised form pauses the run; a failed lookup degrades it.

The UBRN-shaped bundle is an untaught specialty form plus the national
e-RS PDF. Before this gate the extraction step finished as ``completed``
and the specialty form was read with generic rules. Now it pauses with
reason ``form_not_recognised`` so a person can teach the form.

Fail-closed boundary: rule 1 (a failed lookup degrades the run) and rule 4
(an error never skips the pause).

Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
Risk R-B88CCFD6. Fail-closed: UN-89E2AE36, DI-B7A69F26, DI-02AB393F.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from libs.pipeline.document_quality import DocumentQuality
from libs.pipeline.form_recognition_apply import recognise_texts, recognition_fields
from libs.pipeline.form_schema_store import reset_schema_cache
from libs.referral_quality.inprocess_dry_run import build_quality_report
from libs.workflow.durable_step_runner import (
    _enqueue_extraction_quality_review,
    _step_result_for_output,
)
from libs.workflow.durable_steps import StepRequest
from libs.workflow.plan_manifest import PlanAction
from tests.form_recognition_corpus import bundle_chunks, load_manifest, load_schemas

_PAUSE_COPY = "We did not recognise this form. Teach it, then run extraction again."


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_schema_cache()
    yield
    reset_schema_cache()


def _extraction() -> PlanAction:
    return PlanAction(action_id="extract", subgraph_id="extraction")


def _good_quality() -> dict[str, Any]:
    return DocumentQuality(
        document_quality_score=1.0,
        quality_reasons=[],
        form_fingerprint_id="fp",
        few_shot_max_similarity=0.9,
    ).to_dict()


def _bundle(bundle_id: str) -> dict[str, Any]:
    (bundle,) = [b for b in load_manifest()["bundles"] if b["id"] == bundle_id]
    return bundle


def _extraction_output(bundle: dict[str, Any], **extra: Any) -> dict[str, Any]:
    chunks = bundle_chunks(bundle)
    outcomes = recognise_texts(chunks, load_schemas)
    fields = recognition_fields(chunks, outcomes)
    return {
        "entities": [{"text": "Rectal bleeding"}],
        "document_quality": _good_quality(),
        "form_recognition": fields["form_recognition"],
        "form_schema_match": fields["form_schema_match"],
        "form_schema_fingerprint": fields["form_schema_fingerprint"],
        **extra,
    }


def _failed_lookup_output() -> dict[str, Any]:
    def _boom() -> list:
        raise RuntimeError("graph unavailable")

    chunks = bundle_chunks(_bundle("taught-gynae-plus-ers"))
    fields = recognition_fields(chunks, recognise_texts(chunks, _boom))
    return {
        "entities": [],
        "document_quality": _good_quality(),
        "form_recognition": fields["form_recognition"],
        "form_schema_match": fields["form_schema_match"],
    }


@pytest.mark.parametrize(
    "bundle", load_manifest()["bundles"], ids=lambda bundle: bundle["id"]
)
def test_labelled_bundles_pause_exactly_when_expected(bundle) -> None:
    result = _step_result_for_output(_extraction(), _extraction_output(bundle))
    assert (result.status == "paused") is bundle["expect_pause"]


def test_the_ubrn_shaped_bundle_pauses_with_form_not_recognised() -> None:
    bundle = _bundle("ubrn-shaped-untaught-lower-gi-plus-ers")
    result = _step_result_for_output(_extraction(), _extraction_output(bundle))
    assert result.status == "paused"
    assert result.output["pause_reason"] == _PAUSE_COPY
    reasons = result.output["document_quality"]["quality_reasons"]
    assert reasons[0] == "form_not_recognised"
    assert "form_not_recognised" in result.warnings


def test_the_my_work_task_carries_the_reason_and_evidence() -> None:
    bundle = _bundle("ubrn-shaped-untaught-lower-gi-plus-ers")
    result = _step_result_for_output(_extraction(), _extraction_output(bundle))
    client = MagicMock()
    request = StepRequest(
        event_type="durable_step",
        run_id="run-ubrn",
        workflow_id="pd-referral-assessment",
        step_id="extract",
        patient_id="p-1",
        plan_definition_id="pd-referral-assessment",
    )
    with patch(
        "libs.pipeline.extraction_review_letter.letter_from_pause_output",
        return_value="letter",
    ):
        _enqueue_extraction_quality_review(client, request, result, ["post"])
    params = client.run.call_args.kwargs
    assert params["reason"].split(",")[0] == "form_not_recognised"
    stored = json.loads(params["document_quality_json"])
    rows = stored["form_recognition"]
    unrecognised = [row for row in rows if row["outcome"] == "unrecognised"]
    assert unrecognised[0]["title"].startswith("Lower GI")
    assert unrecognised[0]["best"]["missing"]


def test_an_error_never_skips_the_form_pause() -> None:
    bundle = _bundle("ubrn-shaped-untaught-lower-gi-plus-ers")
    output = _extraction_output(bundle, errors=["window 2 timed out"])
    result = _step_result_for_output(_extraction(), output)
    assert result.status == "paused"


def test_a_failed_lookup_degrades_and_pauses() -> None:
    result = _step_result_for_output(_extraction(), _failed_lookup_output())
    assert result.status == "paused"
    assert result.output["degraded"] is True
    assert "degraded_safety_layer" in result.warnings


def test_a_failed_match_without_rows_still_degrades() -> None:
    """The state match alone is enough: a missing evidence list fails closed."""
    output = {
        "entities": [],
        "document_quality": _good_quality(),
        "form_schema_match": "failed",
    }
    result = _step_result_for_output(_extraction(), output)
    assert result.status == "paused"
    assert result.output["degraded"] is True


def test_a_failed_row_degrades_even_without_the_state_match() -> None:
    output = {
        "entities": [],
        "document_quality": _good_quality(),
        "form_recognition": [{"outcome": "recognition_failed", "title": "a.pdf"}],
    }
    result = _step_result_for_output(_extraction(), output)
    assert result.status == "paused"
    assert result.output["degraded"] is True


def test_an_unrecognised_match_without_rows_still_pauses() -> None:
    output = {
        "entities": [],
        "document_quality": _good_quality(),
        "form_schema_match": "unrecognised",
    }
    result = _step_result_for_output(_extraction(), output)
    assert result.status == "paused"
    assert result.output["pause_reason"] == _PAUSE_COPY


def test_the_dry_run_report_says_the_live_run_would_pause() -> None:
    bundle = _bundle("ubrn-shaped-untaught-lower-gi-plus-ers")
    report = build_quality_report("000000000000", _extraction_output(bundle))
    recognition = report["form_recognition"]
    assert recognition["match"] == "unrecognised"
    assert recognition["would_pause"] is True
    assert recognition["would_degrade"] is False
    assert [row["outcome"] for row in recognition["documents"]] == [
        "unrecognised",
        "recognised",
    ]


def test_the_dry_run_report_for_a_taught_bundle_would_not_pause() -> None:
    bundle = _bundle("taught-gynae-plus-ers")
    report = build_quality_report("000000000000", _extraction_output(bundle))
    assert report["form_recognition"]["would_pause"] is False


def test_other_steps_are_not_gated() -> None:
    output = {"form_schema_match": "unrecognised", "form_recognition": []}
    action = PlanAction(action_id="sbar", subgraph_id="sbar")
    assert _step_result_for_output(action, output).status == "completed"
