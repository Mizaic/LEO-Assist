"""A run that did not read the whole letter must say so.

Two ways the extractor can read less than the letter and still hand back
something shaped exactly like a complete extraction:

1. A window raises. ``_collect_windows`` breaks out of the loop and keeps
   whatever it already had. ``extraction_window_count`` still reports the
   PLANNED number of windows, so the result looks like every window ran.
2. A window does not fit the token budget. ``_build_window_context`` trims
   it to half the budget and writes a log line. The dropped half is never
   seen by the model.

Either way, findings in the unread part are simply absent, and absent reads
as "not present" to whoever picks the referral up. Absence of a finding and
failure to look for it must not be the same output.

Rule: .cursor/rules/fail-closed-boundary.mdc rule 3 -- partial results are
typed as partial.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any

from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline.windowed_llm_extraction import run_windowed_llm_extraction


def _three_chunks() -> list[SentenceChunk]:
    return [
        SentenceChunk(sentence_id="c1", text="Chest pain noted.", start=0, end=17),
        SentenceChunk(
            sentence_id="c2", text="Family history of cancer.", start=18, end=43
        ),
        SentenceChunk(
            sentence_id="c3", text="Weight loss over 3 months.", start=44, end=70
        ),
    ]


def _run(
    chunks: list[SentenceChunk],
    extractor: Any,
    *,
    max_window_input_tokens: int = 4000,
) -> dict[str, Any]:
    return run_windowed_llm_extraction(
        "\n".join(c.text for c in chunks),
        chunks,
        {},
        window_size=1,
        window_overlap=0,
        context_mode="window_local",
        max_window_input_tokens=max_window_input_tokens,
        run_llm_extraction=extractor,
    )


def _ok(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"entities": [{"text": "chest pain"}], "llm_tokens": {}}


def _fails_on_second_call() -> Any:
    calls: list[int] = []

    def _flaky(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append(1)
        if len(calls) == 1:
            return {"entities": [{"text": "chest pain"}], "llm_tokens": {}}
        raise RuntimeError("window 2 timed out")

    return _flaky


# ---------------------------------------------------------------------------
# A window that fails
# ---------------------------------------------------------------------------


def test_a_failed_window_types_the_run_as_partial() -> None:
    result = _run(_three_chunks(), _fails_on_second_call())
    assert result.get("extraction_partial") is True, (
        "a run that read 1 of 3 windows must be typed as partial, not "
        f"returned as a complete extraction: {sorted(result)!r}"
    )


def test_completed_window_count_tells_the_truth() -> None:
    """extraction_window_count is the plan, not what actually ran."""
    result = _run(_three_chunks(), _fails_on_second_call())
    assert result.get("extraction_window_count") == 3
    assert result.get("extraction_windows_completed") == 1


def test_a_failed_window_warns_in_plain_english() -> None:
    result = _run(_three_chunks(), _fails_on_second_call())
    warnings = result.get("warnings") or []
    assert warnings, f"expected a warning a person can see: {sorted(result)!r}"
    joined = " ".join(str(w) for w in warnings).lower()
    assert "part" in joined or "not read" in joined
    assert "person" in joined or "check" in joined


def test_facts_already_found_are_still_kept() -> None:
    """Failing closed must not throw away what was genuinely read."""
    result = _run(_three_chunks(), _fails_on_second_call())
    assert result.get("entities"), "entities found before the failure are evidence"


# ---------------------------------------------------------------------------
# A chunk too big for one window
# ---------------------------------------------------------------------------


def _long_chunk() -> SentenceChunk:
    lines = [
        f"Line {n:03d}: serum analyte {n} result {n}.{n % 10} umol/L"
        for n in range(200)
    ]
    text = "\n".join(lines)
    return SentenceChunk(sentence_id="big", text=text, start=0, end=len(text))


def test_an_oversized_chunk_is_split_not_trimmed() -> None:
    """Splitting replaced truncation, so nothing is cut off the bottom."""
    chunk = _long_chunk()
    seen: list[str] = []

    def _record(context: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        seen.append(context)
        return {"entities": [], "llm_tokens": {}}

    result = _run([chunk], _record, max_window_input_tokens=2000)

    assert result.get("extraction_window_count", 0) > 1
    assert result.get("extraction_window_truncated_count") == 0
    assert result.get("extraction_partial") is not True


def test_every_line_of_an_oversized_chunk_reaches_the_model() -> None:
    """The clinical point: no line is silently dropped."""
    chunk = _long_chunk()
    seen: list[str] = []

    def _record(context: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        seen.append(context)
        return {"entities": [], "llm_tokens": {}}

    _run([chunk], _record, max_window_input_tokens=2000)

    everything = "\n".join(seen)
    missing = [line for line in str(chunk.text).split("\n") if line not in everything]
    assert not missing, f"{len(missing)} lines never reached the model"


# ---------------------------------------------------------------------------
# The happy path must be untouched
# ---------------------------------------------------------------------------


def test_a_complete_run_is_not_marked_partial() -> None:
    result = _run(_three_chunks(), _ok)
    assert result.get("extraction_partial") is not True
    assert not result.get("warnings")
    assert result.get("extraction_windows_completed") == 3
    assert result.get("extraction_window_count") == 3


def test_a_complete_run_still_returns_its_entities() -> None:
    result = _run(_three_chunks(), _ok)
    assert result.get("entities")
    assert result.get("extraction_route") == "llm-windowed"
