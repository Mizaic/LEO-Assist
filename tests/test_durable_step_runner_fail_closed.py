"""Site 7: an error must never switch the human review gate off.

`.cursor/rules/fail-closed-boundary.mdc` rule 4: "Failure must never be
why a run skips the pause. An error raises the need for a person to
look, so it must make a pause more likely, not less."

Clinical consequence of the old shape (`if ... and not errors:`): the
worst extractions, the ones that errored, were the only ones that never
paused for a human. Nobody read the half-read letter.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DI: DI-02AB393F (degraded runs routed to human review)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.document_quality import DocumentQuality, score_document_quality
from libs.workflow.durable_step_runner import (
    _coerce_failure_result,
    _is_stage_failure,
    _step_result_for_output,
)
from libs.workflow.plan_manifest import PlanAction

_LOW_QUALITY_FORM = (
    "Section A: Gynaecological Cancer type suspected\nOvary [ ] Cervix [X]"
)


def _extraction_action() -> PlanAction:
    return PlanAction(action_id="extract", subgraph_id="extraction")


def _low_quality() -> dict[str, Any]:
    quality = score_document_quality(
        _LOW_QUALITY_FORM,
        few_shot_max_similarity=0.10,
        known_fingerprints={},
    )
    assert quality.document_quality_score < 0.6, "precondition: quality must be low"
    return quality.to_dict()


def _good_quality() -> dict[str, Any]:
    return DocumentQuality(
        document_quality_score=0.95,
        quality_reasons=[],
        form_fingerprint_id="fp-good",
        few_shot_max_similarity=0.90,
    ).to_dict()


# ---------------------------------------------------------------------------
# Happy paths -- correct behaviour must not change
# ---------------------------------------------------------------------------


def test_clean_good_quality_extraction_completes() -> None:
    """A clean, high-quality extraction still finishes without a pause."""
    result = _step_result_for_output(
        _extraction_action(),
        {"entities": [{"text": "Cervix"}], "document_quality": _good_quality()},
    )
    assert result.status == "completed"
    assert result.errors == []
    assert "extraction_quality_pause" not in result.warnings


def test_clean_extraction_without_quality_scores_completes() -> None:
    """No quality score and no errors is still a completed step."""
    result = _step_result_for_output(_extraction_action(), {"entities": []})
    assert result.status == "completed"
    assert "extraction_quality_pause" not in result.warnings


def test_clean_low_quality_extraction_pauses() -> None:
    """The existing quality pause keeps working when nothing errored."""
    result = _step_result_for_output(
        _extraction_action(),
        {"entities": [{"text": "Cervix"}], "document_quality": _low_quality()},
    )
    assert result.status == "paused"
    assert "extraction_quality_pause" in result.warnings


def test_clean_non_extraction_step_completes() -> None:
    """A healthy step on another subgraph is untouched."""
    action = PlanAction(action_id="post", subgraph_id="post_processing")
    result = _step_result_for_output(action, {"processed_entities": [{"text": "x"}]})
    assert result.status == "completed"


# ---------------------------------------------------------------------------
# Site 7 -- errors must never remove the pause
# ---------------------------------------------------------------------------


def test_errored_low_quality_extraction_still_pauses() -> None:
    """The named defect: errors used to skip the quality gate entirely."""
    result = _step_result_for_output(
        _extraction_action(),
        {
            "entities": [{"text": "Cervix"}],
            "document_quality": _low_quality(),
            "errors": ["extraction_window_failed index=2: timeout"],
        },
    )
    assert result.status == "paused"
    assert "extraction_quality_pause" in result.warnings


def test_errored_extraction_keeps_its_errors_on_the_paused_result() -> None:
    """Pausing must not hide the failure that caused it."""
    result = _step_result_for_output(
        _extraction_action(),
        {
            "entities": [{"text": "Cervix"}],
            "document_quality": _low_quality(),
            "errors": ["extraction_window_failed index=2: timeout"],
        },
    )
    assert result.errors == ["extraction_window_failed index=2: timeout"]


def test_errored_extraction_still_runs_the_quality_gate() -> None:
    """The gate decision must be recorded on the output, errors or not."""
    result = _step_result_for_output(
        _extraction_action(),
        {
            "entities": [{"text": "Cervix"}],
            "document_quality": _low_quality(),
            "errors": ["extraction_window_failed index=2: timeout"],
        },
    )
    assert result.output.get("extraction_gate") == "pause"


def test_paused_errored_extraction_says_why_in_plain_english() -> None:
    """The reason a person reads must be plain English, action first.

    When the pause coincides with an error, the wording tells the person
    part of the letter could not be read, which is the more useful fact.
    """
    result = _step_result_for_output(
        _extraction_action(),
        {
            "entities": [{"text": "Cervix"}],
            "document_quality": _low_quality(),
            "errors": ["extraction_window_failed index=2: timeout"],
        },
    )
    reason = str(result.output.get("pause_reason") or "")
    assert reason, "a paused step must carry a reason a person can read"
    assert reason.isascii()
    assert reason.startswith("Check this letter by hand.")
    assert "could not be read" in reason


# ---------------------------------------------------------------------------
# Site 7 -- an error alone keeps the HARDER stop it already had
#
# A pause is softer than a failure: `_is_stage_failure` returns False for
# a paused result even when it carries errors. So an error on its own must
# not be converted into a pause, or the run would stop being marked
# failed. It keeps the hard stop, which dispatches no successor.
# ---------------------------------------------------------------------------


def test_errored_extraction_with_good_quality_keeps_the_hard_stop() -> None:
    """An error with no quality concern still fails the run, not pauses it."""
    result = _step_result_for_output(
        _extraction_action(),
        {
            "entities": [{"text": "Cervix"}],
            "document_quality": _good_quality(),
            "errors": ["extraction_window_failed index=2: timeout"],
        },
    )
    assert result.status != "paused", "a pause would soften the hard stop"
    assert _is_stage_failure(result), "an errored step must still fail the run"
    assert _coerce_failure_result(result).status == "failed"


def test_errored_extraction_without_quality_scores_keeps_the_hard_stop() -> None:
    """A missing quality score must not turn a failure into a pause."""
    result = _step_result_for_output(
        _extraction_action(),
        {
            "entities": [{"text": "Cervix"}],
            "errors": ["extraction_window_failed index=2: timeout"],
        },
    )
    assert _is_stage_failure(result)
    assert _coerce_failure_result(result).status == "failed"


def test_errored_extraction_is_never_a_clean_success() -> None:
    """Whichever stop applies, the errors stay visible on the result."""
    errors = ["extraction_window_failed index=2: timeout"]
    for quality in (_good_quality(), _low_quality()):
        result = _step_result_for_output(
            _extraction_action(),
            {
                "entities": [{"text": "Cervix"}],
                "document_quality": quality,
                "errors": list(errors),
            },
        )
        assert result.errors == errors
        paused = result.status == "paused"
        assert paused or _is_stage_failure(result), (
            "an errored extraction must either pause for a person or fail "
            f"the run, got status={result.status!r}"
        )
        assert result.next_event_type is None or not paused


# ---------------------------------------------------------------------------
# Site 7 -- route the site 1 `degraded` flag to a human
# ---------------------------------------------------------------------------


def test_degraded_extraction_payload_pauses() -> None:
    """A safety layer that could not run must stop the run for a person.

    The `degraded` key is written by the post-processing subgraph (site
    1). This payload is hand-built so this test does not depend on that
    change landing first.
    """
    result = _step_result_for_output(
        _extraction_action(),
        {
            "entities": [{"text": "Cervix"}],
            "document_quality": _good_quality(),
            "degraded": True,
        },
    )
    assert result.status == "paused"
    assert "degraded_safety_layer" in result.warnings
    assert (
        "extraction_quality_pause" not in result.warnings
    ), "the quality gate did not ask for this pause, so do not claim it did"


def test_degraded_post_processing_payload_pauses() -> None:
    """Degradation on any subgraph pauses, not just on extraction."""
    action = PlanAction(action_id="post", subgraph_id="post_processing")
    result = _step_result_for_output(
        action,
        {"processed_entities": [{"text": "chest pain"}], "degraded": True},
    )
    assert result.status == "paused"


def test_degraded_pause_says_why_in_plain_english() -> None:
    action = PlanAction(action_id="post", subgraph_id="post_processing")
    result = _step_result_for_output(action, {"degraded": True})
    reason = str(result.output.get("pause_reason") or "")
    assert reason.isascii()
    assert reason.startswith("Check this letter by hand.")
    assert "safety check" in reason


def test_degraded_false_does_not_pause() -> None:
    """An explicit `degraded: False` is a healthy run."""
    action = PlanAction(action_id="post", subgraph_id="post_processing")
    result = _step_result_for_output(
        action, {"processed_entities": [{"text": "x"}], "degraded": False}
    )
    assert result.status == "completed"
