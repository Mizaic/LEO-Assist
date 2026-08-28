"""A fact's own words beat the model's guess about which chunk it came from.

Measured on the Sherwood 2WW referral. Blood pressure and heart rate are
real observations, printed in chunk 8::

    | Blood Pressure | 140 / 80 mmHg, 24 Nov 2025 |  |  |
    | Heart rate | 70 bpm, |  |  |

Both were persisted against chunk 10, the blood panel. Because the words are
not in chunk 10, the writer could not locate the span, dropped the evidence
offsets, and stored the panel header as the evidence sentence. The values
survived, so a reviewer sees "blood pressure 140/80" with a quote that does
not contain it and no offsets to jump to.

Dropping the offsets is the correct fail-closed behaviour and stays. What was
missing is the recovery: the fact's own words appear in exactly one chunk, and
that is better evidence of origin than a label the model produced. When the
match is unambiguous the write is re-pointed at the chunk that really holds
the words. When it is ambiguous or absent, nothing is guessed.

Atlas trace:
  DI: DI-B7A69F26  (fail-closed boundary)
  Risk: R-294446BF
"""

from __future__ import annotations

from libs.cypher.documents_queries import (
    _collect_pending_document_writes,
    locate_span_in_sentences,
)

VITALS = "Minimum Dataset:\n| Blood Pressure | 140 / 80 mmHg, 24 Nov 2025 |  |  |"
PANEL = "Blood Results\n| Date specimen collected | Battery Headers | Result |"


def _sentence(sentence_id: str, text: str, terms: list[dict]) -> dict:
    return {
        "sentence_id": sentence_id,
        "text": text,
        "persist_source_label": "Chunk",
        "terms": terms,
    }


def _term(text: str, concept_id: str = "75367002") -> dict:
    return {
        "text": text,
        "semantic_tag": "observable entity",
        "coding": {"snomed_concept_id": concept_id, "snomed_term": "Blood pressure"},
    }


def _writes(sentences: list[dict]):
    return _collect_pending_document_writes(
        "enc-1",
        sentences,
        source="pipeline",
        model_name="llm-small",
        model_version="1",
        contract_version="1",
        run_id="run-1",
        source_label="Chunk",
        active_terms=set(),
    )


class TestLocateSpanInSentences:
    def test_it_finds_the_one_sentence_holding_the_words(self) -> None:
        sentences = [
            _sentence("s10", PANEL, []),
            _sentence("s8", VITALS, []),
        ]

        hit = locate_span_in_sentences(sentences, "Blood Pressure", claimed_index=0)

        assert hit is not None
        assert hit[0] == 1

    def test_it_is_case_insensitive(self) -> None:
        sentences = [_sentence("s10", PANEL, []), _sentence("s8", VITALS, [])]

        assert locate_span_in_sentences(sentences, "blood pressure", 0) is not None

    def test_it_refuses_when_two_sentences_hold_the_words(self) -> None:
        """Ambiguous origin must not be guessed."""
        sentences = [
            _sentence("s10", PANEL, []),
            _sentence("s8", VITALS, []),
            _sentence("s9", VITALS, []),
        ]

        assert locate_span_in_sentences(sentences, "Blood Pressure", 0) is None

    def test_it_refuses_when_no_sentence_holds_the_words(self) -> None:
        sentences = [_sentence("s10", PANEL, [])]

        assert locate_span_in_sentences(sentences, "Blood Pressure", 0) is None

    def test_it_ignores_the_sentence_that_was_claimed(self) -> None:
        """The claimed sentence already failed; it must not be re-offered."""
        sentences = [_sentence("s8", VITALS, []), _sentence("s10", PANEL, [])]

        assert locate_span_in_sentences(sentences, "Blood Pressure", 0) is None


class TestRelocationInTheWrite:
    def test_a_misattributed_fact_is_written_against_the_right_chunk(self) -> None:
        sentences = [
            _sentence("s10", PANEL, [_term("Blood Pressure")]),
            _sentence("s8", VITALS, []),
        ]

        writes = _writes(sentences)

        assert len(writes) == 1
        assert writes[0].params["source_id"] == "s8"

    def test_offsets_are_recovered_after_relocation(self) -> None:
        sentences = [
            _sentence("s10", PANEL, [_term("Blood Pressure")]),
            _sentence("s8", VITALS, []),
        ]

        params = _writes(sentences)[0].params

        assert params["evidence_start"] is not None
        assert params["evidence_end"] is not None

    def test_the_evidence_sentence_holds_the_words(self) -> None:
        sentences = [
            _sentence("s10", PANEL, [_term("Blood Pressure")]),
            _sentence("s8", VITALS, []),
        ]

        evidence = _writes(sentences)[0].params["evidence_sentence"]

        assert "Blood Pressure" in evidence
        assert "Battery Headers" not in evidence

    def test_an_unrecoverable_fact_keeps_no_offsets(self) -> None:
        """Fail closed: still no offsets when the words are nowhere."""
        sentences = [_sentence("s10", PANEL, [_term("Blood Pressure")])]

        params = _writes(sentences)[0].params

        assert params["evidence_start"] is None
        assert params["evidence_end"] is None
        assert params["source_id"] == "s10"

    def test_an_ambiguous_fact_is_not_moved(self) -> None:
        sentences = [
            _sentence("s10", PANEL, [_term("Blood Pressure")]),
            _sentence("s8", VITALS, []),
            _sentence("s9", VITALS, []),
        ]

        params = _writes(sentences)[0].params

        assert params["source_id"] == "s10"
        assert params["evidence_start"] is None

    def test_a_correctly_attributed_fact_is_untouched(self) -> None:
        sentences = [
            _sentence("s8", VITALS, [_term("Blood Pressure")]),
            _sentence("s10", PANEL, []),
        ]

        params = _writes(sentences)[0].params

        assert params["source_id"] == "s8"
        assert params["evidence_start"] is not None
