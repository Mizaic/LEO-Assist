"""Tests for libs/ner/span_resolver.SpanResolver."""

from __future__ import annotations

from dataclasses import dataclass

from libs.ner.span_resolver import SpanResolver


@dataclass
class _FakeSentence:
    sentence_id: str
    text: str
    start: int


def test_resolve_returns_absolute_offsets_inside_tagged_sentence():
    encounter = "Admin header line 1\nPatient has type 2 diabetes mellitus and HTN."
    sentence = _FakeSentence(
        sentence_id="s1",
        text="Patient has type 2 diabetes mellitus and HTN.",
        start=encounter.index("Patient"),
    )

    resolver = SpanResolver(encounter_text=encounter, sentences=[sentence])

    start, end = resolver.resolve("type 2 diabetes mellitus", sentence_id="s1")

    assert encounter[start:end] == "type 2 diabetes mellitus"


def test_resolve_advances_cursor_within_sentence_for_repeated_mentions():
    encounter = "HTN is new; HTN started today."
    sentence = _FakeSentence(
        sentence_id="s1",
        text=encounter,
        start=0,
    )

    resolver = SpanResolver(encounter_text=encounter, sentences=[sentence])

    first_start, first_end = resolver.resolve("HTN", sentence_id="s1")
    second_start, second_end = resolver.resolve("HTN", sentence_id="s1")

    assert encounter[first_start:first_end] == "HTN"
    assert encounter[second_start:second_end] == "HTN"
    assert first_start != second_start
    assert second_start > first_start


def test_resolve_case_insensitive_and_falls_back_to_encounter_search():
    encounter = "Patient has CKD stage 3"

    resolver = SpanResolver(encounter_text=encounter, sentences=[])

    start, end = resolver.resolve("ckd stage 3")

    assert encounter[start:end] == "CKD stage 3"


def test_resolve_unknown_sentence_id_falls_back_to_encounter_search():
    encounter = "A. Background\nPatient has hypertension."

    sentence = _FakeSentence(
        sentence_id="s1",
        text="Patient has hypertension.",
        start=encounter.index("Patient"),
    )

    resolver = SpanResolver(encounter_text=encounter, sentences=[sentence])

    start, end = resolver.resolve("hypertension", sentence_id="s-missing")

    assert encounter[start:end] == "hypertension"


def test_resolve_empty_text_returns_fallback_span():
    resolver = SpanResolver(encounter_text="anything", sentences=[])

    start, end = resolver.resolve("   ")

    assert start == 0
    assert end == 1


def test_resolve_returns_sentence_start_when_mention_not_in_sentence():
    encounter = "one. two. three."
    sentence = _FakeSentence(
        sentence_id="s1",
        text="two.",
        start=encounter.index("two"),
    )

    resolver = SpanResolver(encounter_text=encounter, sentences=[sentence])

    start, end = resolver.resolve("never appears", sentence_id="s1")

    assert start == sentence.start
    assert end == sentence.start + len("never appears")
