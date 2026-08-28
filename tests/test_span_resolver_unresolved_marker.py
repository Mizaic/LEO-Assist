"""A span the resolver could not place must say so.

``SpanResolver.resolve`` returns a fallback span when it cannot find a
surface form. In the Sherwood referral run 64bf2111 that fallback fired
for 17 of 18 extracted facts, and nothing in the output said so: the
entities looked exactly like entities whose offsets were found.

Making ``resolve`` raise or return ``None`` would stop every referral run
until the sentence-id defect behind it is fixed, so the fallback span
stays. What changes is that the caller can now see the fallback happened
and record it on the fact, which is the minimum a clinician needs to know
that the offsets on that fact were guessed.

Atlas trace:
  DI: DI-B7A69F26  (fail-closed boundary)
  DI: DI-02AB393F  (degraded runs routed to human review)
  Risk: R-294446BF
"""

from __future__ import annotations

from dataclasses import dataclass

from libs.ner.span_resolver import SpanResolver


@dataclass
class _FakeSentence:
    sentence_id: str
    text: str
    start: int


def test_a_found_term_reports_resolved() -> None:
    encounter = "Patient has CKD stage 3"
    resolver = SpanResolver(encounter_text=encounter, sentences=[])

    outcome = resolver.resolve_traced("ckd stage 3")

    assert outcome.resolved is True
    assert encounter[outcome.start : outcome.end] == "CKD stage 3"


def test_a_term_missing_from_its_sentence_reports_unresolved() -> None:
    """The exact shape of the Sherwood defect: right chunk id, wrong text.

    The offsets are still the old fallback, so no run changes behaviour.
    Only the flag is new.
    """
    encounter = "one. two. three."
    sentence = _FakeSentence(
        sentence_id="s1", text="two.", start=encounter.index("two")
    )
    resolver = SpanResolver(encounter_text=encounter, sentences=[sentence])

    outcome = resolver.resolve_traced("never appears", sentence_id="s1")

    assert outcome.resolved is False
    assert outcome.start == sentence.start
    assert outcome.end == sentence.start + len("never appears")


def test_a_term_missing_from_the_whole_encounter_reports_unresolved() -> None:
    resolver = SpanResolver(encounter_text="Patient has a cough", sentences=[])

    outcome = resolver.resolve_traced("nil palp masses")

    assert outcome.resolved is False
    assert outcome.start == 0


def test_empty_term_reports_unresolved() -> None:
    resolver = SpanResolver(encounter_text="anything", sentences=[])

    outcome = resolver.resolve_traced("   ")

    assert outcome.resolved is False


def test_resolve_tuple_behaviour_is_unchanged() -> None:
    """The existing two-value contract must keep working untouched."""
    encounter = "Patient has type 2 diabetes mellitus."
    sentence = _FakeSentence(sentence_id="s1", text=encounter, start=0)
    resolver = SpanResolver(encounter_text=encounter, sentences=[sentence])

    start, end = resolver.resolve("type 2 diabetes mellitus", sentence_id="s1")

    assert encounter[start:end] == "type 2 diabetes mellitus"


def test_extractor_records_the_unresolved_flag_on_the_fact() -> None:
    """An unplaced fact carries the marker into pipeline state."""
    from libs.pipeline_graph.subgraphs._extractor import _resolve_item_span

    encounter = "one. two. three."
    sentence = _FakeSentence(
        sentence_id="s1", text="two.", start=encounter.index("two")
    )
    resolver = SpanResolver(encounter_text=encounter, sentences=[sentence])

    start, end, meta = _resolve_item_span(resolver, "never appears", "s1")

    assert meta.get("span_unresolved") is True
    assert start == sentence.start
    assert end == sentence.start + len("never appears")


def test_extractor_leaves_no_marker_on_a_placed_fact() -> None:
    from libs.pipeline_graph.subgraphs._extractor import _resolve_item_span

    encounter = "Patient has a cough today."
    resolver = SpanResolver(encounter_text=encounter, sentences=[])

    start, end, meta = _resolve_item_span(resolver, "cough", None)

    assert meta == {}
    assert encounter[start:end] == "cough"
