"""A post-processing failure must never look like a clean run.

``run_post_process`` wraps all 23 post-processing layers, including the
negation guard (ConText) and the scope guard. When that stack fails the
entities it was given have not been through any guard. Handing them back
as ``processed_entities`` tells the rest of the pipeline they were
checked, so "No chest pain" can reach the record as chest pain present.

``fail-closed-boundary.mdc`` rule 1: an unavailable guard degrades the
run, and the degradation has to be visible to the person reading the
record. A log line is not visible.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26  (fail-closed boundary for clinical safety layers)
  DI: DI-02AB393F  (degraded runs routed to human review)
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from libs.pipeline_graph.subgraphs.post_processing import (
    POST_PROCESSING_FAILED_WARNING,
    run_post_process,
)

_LETTER = "No chest pain today. Abdomen soft."
_RAW_ENTITIES: list[dict[str, Any]] = [
    {"text": "chest pain", "label": "finding", "start": 3, "end": 13},
]


def _state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "encounter_text": _LETTER,
        "entities": [dict(e) for e in _RAW_ENTITIES],
        "local_concept_patterns": [],
    }
    state.update(overrides)
    return state


def _failing_run(exc: Exception) -> Any:
    return patch(
        "libs.pipeline.post_processing.run_post_processing_with_trace",
        side_effect=exc,
    )


def _clean_run(processed: list[dict[str, Any]]) -> Any:
    return patch(
        "libs.pipeline.post_processing.run_post_processing_with_trace",
        return_value=(processed, [{"layer_id": "layer_0", "status": "completed"}]),
    )


# -- the failure path ------------------------------------------------------


def test_a_failed_layer_marks_the_run_degraded() -> None:
    """A guard that blew up must degrade the run, not finish it."""
    with _failing_run(RuntimeError("scope guard exploded")):
        result = run_post_process(_state())  # type: ignore[arg-type]

    assert result.get("degraded") is True, result


def test_a_missing_module_marks_the_run_degraded() -> None:
    """An import failure is a missing guard, same as a guard that crashed."""
    with _failing_run(ImportError("no module named medspacy")):
        result = run_post_process(_state())  # type: ignore[arg-type]

    assert result.get("degraded") is True, result


def test_a_failed_layer_warns_a_person_in_words_they_can_read() -> None:
    """The person triaging the run must be told the checks did not run."""
    with _failing_run(RuntimeError("scope guard exploded")):
        result = run_post_process(_state())  # type: ignore[arg-type]

    warnings = result.get("warnings") or []
    assert POST_PROCESSING_FAILED_WARNING in warnings, warnings
    assert "safety checks did not run" in POST_PROCESSING_FAILED_WARNING.lower()
    assert POST_PROCESSING_FAILED_WARNING.isascii()


def test_raw_entities_are_not_handed_back_as_processed() -> None:
    """Unguarded output must never be labelled as guarded output."""
    with _failing_run(RuntimeError("scope guard exploded")):
        result = run_post_process(_state())  # type: ignore[arg-type]

    assert not result.get("processed_entities"), result.get("processed_entities")
    assert not result.get("entities"), result.get("entities")


def test_a_failed_layer_still_records_the_error() -> None:
    """Triage keeps the machine detail as well as the plain-English line."""
    with _failing_run(RuntimeError("scope guard exploded")):
        result = run_post_process(_state())  # type: ignore[arg-type]

    assert any("scope guard exploded" in e for e in result.get("errors") or [])
    trace = result.get("post_processing_trace") or []
    assert trace and trace[0].get("status") == "error"


def test_a_failed_layer_keeps_warnings_raised_earlier() -> None:
    """Post-processing adds to the run's warnings, it does not replace them."""
    with _failing_run(RuntimeError("scope guard exploded")):
        result = run_post_process(  # type: ignore[arg-type]
            _state(warnings=["healthcare_service_missing"])
        )

    warnings = result.get("warnings") or []
    assert "healthcare_service_missing" in warnings
    assert POST_PROCESSING_FAILED_WARNING in warnings


# -- the happy path must not change ---------------------------------------


def test_a_clean_run_is_not_marked_degraded() -> None:
    """A run where every guard worked must not cry wolf."""
    processed = [{"text": "chest pain", "label": "finding", "assertion": "absent"}]
    with _clean_run(processed):
        result = run_post_process(_state())  # type: ignore[arg-type]

    assert result.get("degraded") is not True, result


def test_a_clean_run_raises_no_warning() -> None:
    """No warning on a clean run, so a real warning still means something."""
    processed = [{"text": "chest pain", "label": "finding", "assertion": "absent"}]
    with _clean_run(processed):
        result = run_post_process(_state())  # type: ignore[arg-type]

    assert result.get("warnings") == []
    assert result.get("errors") == []


def test_a_clean_run_returns_the_guarded_entities() -> None:
    """The guarded entities are what flows on, unchanged by this fix."""
    processed = [{"text": "chest pain", "label": "finding", "assertion": "absent"}]
    with _clean_run(processed):
        result = run_post_process(_state())  # type: ignore[arg-type]

    assert result["entities"] == processed
    assert result["processed_entities"] == processed
    assert result["post_processing_trace"] == [
        {"layer_id": "layer_0", "status": "completed"}
    ]
