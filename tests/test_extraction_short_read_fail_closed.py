"""A full-document extraction that read only part of the letter must say so.

The windowed path already types a short read as partial. The
full-document path does not. It hands ``encounter_text`` to
``guard_user_clinical_text``, which ends in ``replaced[:max_chars]`` --
a silent cut at 16,000 characters with no log, no warning, and no flag.

NHS 4568668417 is the worked example. Her referral bundle is 26,585
characters. The quantitative faecal immunochemical test (FIT) result
sits at offset 20,541 and the serum cancer antigen 125 (CA125) result
at 24,499. Both fell off the end. The Assessment then offered both
tests again as though they had never been done, and nothing on the run
said 40% of the letter was never read.

Absence of a finding and failure to look for it must not produce the
same output.

Rule: .cursor/rules/fail-closed-boundary.mdc rule 3 -- partial results
are typed as partial.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any

import pytest

from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline.extraction_completeness import (
    INCOMPLETE_EXTRACTION_WARNING,
    short_read_fields,
)
from libs.pipeline.llm_clinical_input import (
    DEFAULT_USER_TEXT_MAX_CHARS,
    guard_user_clinical_text_checked,
)
from libs.pipeline_graph.subgraphs._extractor import LLMExtractorAdapter

# Size of the real referral bundle for NHS 4568668417.
REFERRAL_BUNDLE_CHARS = 26_585


class _FakeResp:
    def __init__(self, text: str) -> None:
        self.text = text
        self.input_tokens = 100
        self.output_tokens = 20
        self.cached_input_tokens = 0


class _FakeLLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def converse(self, system, messages, **kwargs):  # noqa: ANN001
        _ = (system, kwargs)
        self.messages = messages
        return _FakeResp('{"terms": []}')


@pytest.fixture
def adapter(monkeypatch) -> LLMExtractorAdapter:
    monkeypatch.setattr(
        "libs.prompts.registry.compose_prompt_with_annotation_guidelines",
        lambda _name, instructions: instructions,
    )
    monkeypatch.setattr(
        "libs.pipeline.llm_clinical_input.deidentify_encounter_text",
        lambda text: text,
    )
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm", lambda tier="small": _FakeLLM()
    )
    return LLMExtractorAdapter(system_prompt="Base instructions")


def _letter(chars: int) -> str:
    """A letter of a given size with the FIT result at the very end."""
    filler = "Routine blood results are within normal limits. "
    tail = "Quantitative faecal immunochemical test < 4 ug/g."
    body = (filler * (chars // len(filler) + 1))[: chars - len(tail)]
    return body + tail


# ---------------------------------------------------------------------------
# The guard must have three answers, not two
# ---------------------------------------------------------------------------


def test_guard_reports_that_it_cut_the_letter(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.pipeline.llm_clinical_input.deidentify_encounter_text",
        lambda text: text,
    )
    result = guard_user_clinical_text_checked(_letter(REFERRAL_BUNDLE_CHARS))
    assert result.truncated is True
    assert result.original_chars == REFERRAL_BUNDLE_CHARS
    assert result.kept_chars == DEFAULT_USER_TEXT_MAX_CHARS
    assert result.dropped_chars == REFERRAL_BUNDLE_CHARS - DEFAULT_USER_TEXT_MAX_CHARS


def test_guard_reports_a_whole_letter_as_whole(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.pipeline.llm_clinical_input.deidentify_encounter_text",
        lambda text: text,
    )
    result = guard_user_clinical_text_checked(_letter(500))
    assert result.truncated is False
    assert result.dropped_chars == 0
    assert "faecal immunochemical" in result.text


# ---------------------------------------------------------------------------
# The extractor must pass the short read on, not swallow it
# ---------------------------------------------------------------------------


def test_extractor_usage_reports_the_short_read(adapter) -> None:
    letter = _letter(REFERRAL_BUNDLE_CHARS)
    _items, usage = adapter.extract_batch_with_usage(
        letter,
        [SentenceChunk("s0", "Abdominal pain.", 0, 15)],
    )
    assert usage["clinical_text_truncated"] is True
    assert usage["clinical_text_dropped_chars"] == (
        REFERRAL_BUNDLE_CHARS - DEFAULT_USER_TEXT_MAX_CHARS
    )


def test_extractor_usage_is_clean_for_a_whole_letter(adapter) -> None:
    _items, usage = adapter.extract_batch_with_usage(
        _letter(500),
        [SentenceChunk("s0", "Abdominal pain.", 0, 15)],
    )
    assert usage["clinical_text_truncated"] is False
    assert usage["clinical_text_dropped_chars"] == 0


# ---------------------------------------------------------------------------
# A short read types the run as partial, in the same words the
# windowed path already uses
# ---------------------------------------------------------------------------


def test_short_read_types_the_run_as_partial() -> None:
    fields = short_read_fields(
        ["10,585 characters of the letter were not read"],
    )
    assert fields["extraction_partial"] is True
    warning = fields["warnings"][0]
    assert warning.startswith(INCOMPLETE_EXTRACTION_WARNING)
    assert "a person needs to check this referral" in warning
    assert "10,585 characters" in warning


def test_no_reasons_means_no_partial_marker() -> None:
    assert short_read_fields([]) == {}
