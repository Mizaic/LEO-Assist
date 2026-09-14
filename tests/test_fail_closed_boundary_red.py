"""Red tests for the fail-closed boundary (Slice 1 of the pipeline refactor).

Each test asserts the CORRECT fail-closed behaviour at a known fail-open
site. A site still carrying ``xfail(strict=True)`` is still open. When a
site is fixed its test flips to XPASS, CI fails, and that is the signal to
delete the marker.

Patient safety is band 1 in .cursor/rules/precedence.mdc, so these are
being closed as they are found rather than held for a numbered slice.
Sites 5 and 7 are fixed and their markers are gone.

Rule: .cursor/rules/fail-closed-boundary.mdc

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DI: DI-02AB393F (degraded runs routed to human review)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
  Risk: R-294446BF
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B7A69F26")
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from libs.pipeline.document_quality import score_document_quality
from libs.pipeline.form_schema_store import load_form_schema, reset_schema_cache
from libs.pipeline_graph.registry import SubgraphRegistry, _register_defaults
from libs.pipeline_graph.subgraphs.post_processing import run_post_process
from libs.workflow.durable_step_runner import _step_result_for_output
from libs.terminology.client import TerminologyClient
from libs.workflow.engine import ActionDefinition, WorkflowEngine
from libs.workflow.plan_manifest import PlanAction

REPO_ROOT = Path(__file__).resolve().parents[1]


class _RaisingClient:
    """Neo4j client stand-in whose every query fails."""

    def run(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise ConnectionError("neo4j unreachable")


# ---------------------------------------------------------------------------
# Site 1 -- post-processing subgraph swallows any exception
# ---------------------------------------------------------------------------


def test_post_processing_failure_is_not_passed_off_as_processed() -> None:
    """Site 1: post-processing subgraph returns raw entities as processed.

    Clinical consequence: all 23 post-processing layers can fail --
    including the negation and scope guards -- and the run still reports
    ``processed_entities`` and finishes as ``completed``. A clinician
    sees ungated LLM output presented as guarded output.

    FIXED. See tests/test_post_processing_fail_closed.py.
    """
    state = {
        "encounter_text": "No chest pain today.",
        "entities": [{"text": "chest pain", "assertion": "present"}],
        "local_concept_patterns": [],
    }
    with patch(
        "libs.pipeline.post_processing.run_post_processing_with_trace",
        side_effect=RuntimeError("scope guard exploded"),
    ):
        result = run_post_process(state)  # type: ignore[arg-type]

    assert result.get("degraded") is True, (
        "post-processing failure must mark the run degraded, not hand back "
        f"the raw entities: {result!r}"
    )


# ---------------------------------------------------------------------------
# Site 2 -- ConText import failure installs a no-op stub
# ---------------------------------------------------------------------------


def test_context_engine_has_no_noop_fallback() -> None:
    """Site 2: a failed ConText import installs a no-op stub.

    Clinical consequence: negation detection is switched off silently.
    "No chest pain" is then recorded as chest pain present. Nothing in
    the output tells the clinician the guard was missing.

    FIXED. See tests/test_post_processing_context_required.py.
    """
    source = (REPO_ROOT / "libs" / "pipeline" / "post_processing.py").read_text()
    header = source.split("_SENTENCE_BOUNDARY_RE", 1)[0]

    assert "def apply_context_detection_to_dicts" not in header, (
        "a no-op stub for a safety layer is prohibited; the ConText import "
        "must fail the run instead"
    )


# ---------------------------------------------------------------------------
# Site 3 -- form schema lookup returns None on a Neo4j error
# ---------------------------------------------------------------------------


def test_form_schema_lookup_failure_differs_from_not_found() -> None:
    """Site 3: a Neo4j error returns None, same as "form never taught".

    Clinical consequence: a taught form's checkbox normalisation is
    skipped when the database blips. Ticked boxes on a referral form are
    read as untouched, so real findings never reach the record.

    FIXED. See tests/test_form_schema_lookup_fail_closed.py.
    """
    reset_schema_cache()
    with pytest.raises(Exception):
        load_form_schema(_RaisingClient(), "fingerprint-abc")


# ---------------------------------------------------------------------------
# Site 4 -- subgraph registration failures are logged and skipped
# ---------------------------------------------------------------------------


def test_subgraph_registration_failure_aborts_startup() -> None:
    """Site 4: a subgraph that fails to import is silently absent.

    Clinical consequence: the worker starts with a shorter pipeline than
    the plan asks for. A missing terminology or post-processing subgraph
    produces runs that look normal but skipped a clinical stage.

    FIXED. See tests/test_subgraph_registry_fail_closed.py.
    """
    registry = SubgraphRegistry()
    registration_error: Exception | None = None
    with patch.dict(sys.modules, {"libs.pipeline_graph.subgraphs.terminology": None}):
        try:
            _register_defaults(registry)
        except Exception as exc:  # noqa: BLE001 - we assert on it below
            registration_error = exc

    assert not registry.has(
        "terminology"
    ), "precondition: the patched terminology import must have failed"
    assert registration_error is not None, (
        "a subgraph that fails to import must abort worker startup, not be "
        "logged and skipped"
    )


# ---------------------------------------------------------------------------
# Site 5 -- windowed extraction returns partial results as complete
# ---------------------------------------------------------------------------


def test_partial_window_extraction_is_typed_as_partial() -> None:
    """Site 5: the first window failure breaks the loop, partial kept.

    Clinical consequence: only part of the letter was read, yet the
    entities are returned in the same shape as a complete extraction.
    Findings in the unread half are absent, which reads as "not present".

    FIXED. ``run_windowed_llm_extraction`` now reports
    ``extraction_partial``, an honest ``extraction_windows_completed``
    alongside the planned ``extraction_window_count``, and a warning a
    person can see. Oversized chunks are also split across windows instead
    of trimmed, so the other silent-loss path in this file is closed too.
    See tests/test_windowed_extraction_partial.py.
    """
    from libs.nlp.sentence_splitter import SentenceChunk
    from libs.pipeline.windowed_llm_extraction import run_windowed_llm_extraction

    chunks = [
        SentenceChunk(sentence_id="c1", text="Chest pain noted.", start=0, end=17),
        SentenceChunk(
            sentence_id="c2", text="Family history of cancer.", start=18, end=43
        ),
        SentenceChunk(
            sentence_id="c3", text="Weight loss over 3 months.", start=44, end=70
        ),
    ]
    calls: list[int] = []

    def _flaky(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append(1)
        if len(calls) == 1:
            return {"entities": [{"text": "chest pain"}], "llm_tokens": {}}
        raise RuntimeError("window 2 timed out")

    result = run_windowed_llm_extraction(
        "\n".join(c.text for c in chunks),
        chunks,
        {},
        window_size=1,
        window_overlap=0,
        context_mode="window_local",
        max_window_input_tokens=4000,
        run_llm_extraction=_flaky,
    )

    assert result.get("extraction_partial") is True, (
        "a run that read 1 of 3 windows must be typed as partial, not "
        f"returned as a complete extraction: {sorted(result)!r}"
    )


# ---------------------------------------------------------------------------
# Site 6 -- workflow engine mislabels any KeyError as an unknown subgraph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subgraph_keyerror_is_not_reported_as_unknown_subgraph() -> None:
    """Site 6: a KeyError inside a subgraph is reported as a config fault.

    Clinical consequence: a real clinical logic bug is recorded as
    "Unknown subgraph". The step returns a soft error string, so triage
    chases a deployment problem while the coding defect stays hidden.

    FIXED. See tests/test_workflow_engine_error_classification.py.
    """

    class _BadGraph:
        def invoke(self, _state: dict[str, Any]) -> dict[str, Any]:
            raise KeyError("entities")

    class _Registry:
        def build(self, _subgraph_id: str, **_kwargs: Any) -> Any:
            return _BadGraph()

    engine = WorkflowEngine()
    engine._registry = _Registry()  # type: ignore[assignment]
    action = ActionDefinition(
        action_id="post",
        subgraph_id="post_processing",
        trigger_type="named-event",
        trigger_name="coding_requested",
    )

    step_result = await engine._execute_step(action, {"patient_id": "p1"})

    assert "Unknown subgraph" not in (step_result.error or ""), (
        "a KeyError raised inside the subgraph must not be reported as a "
        f"missing registration: {step_result.error!r}"
    )


# ---------------------------------------------------------------------------
# Site 7 -- errors switch the human review gate off
# ---------------------------------------------------------------------------


def test_extraction_errors_do_not_switch_off_the_review_gate() -> None:
    """Site 7: ``if ... and not errors`` skips the quality gate on error.

    Clinical consequence: the worst extractions -- the ones that errored
    -- are the ones that never pause for a human. An error must raise
    the need for review, never remove it.

    FIXED. See tests/test_durable_step_runner_fail_closed.py.
    """
    quality = score_document_quality(
        "Section A: Gynaecological Cancer type suspected\nOvary [ ] Cervix [X]",
        few_shot_max_similarity=0.10,
        known_fingerprints={},
    )
    action = PlanAction(action_id="extract", subgraph_id="extraction")
    payload = {
        "entities": [{"text": "Cervix"}],
        "document_quality": quality.to_dict(),
        "errors": ["extraction_window_failed index=2: timeout"],
    }

    result = _step_result_for_output(action, payload)

    assert result.status == "paused", (
        "an errored low-quality extraction must still pause for human "
        f"review, got status={result.status!r}"
    )


# ---------------------------------------------------------------------------
# Site 8 -- a terminology outage reads as "no such clinical term"
# ---------------------------------------------------------------------------


def test_terminology_lookup_failure_differs_from_no_match() -> None:
    """Site 8: ``TerminologyClient.resolve`` returned ``{}`` on an outage.

    Clinical consequence: while the terminology service is down a
    referral is coded as though the letter held nothing codeable. Every
    span comes back unresolved, persist drops the facts, and the run
    still finishes as completed. The reviewer's warning says "no SNOMED
    match found", which points at the letter instead of the outage.

    FIXED. See tests/test_terminology_lookup_fail_closed.py.
    """
    with patch.object(
        TerminologyClient, "_resolve_batch", side_effect=ConnectionError("down")
    ):
        with pytest.raises(Exception):
            TerminologyClient().resolve(["benign"])
