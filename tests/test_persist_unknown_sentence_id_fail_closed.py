"""An unresolvable sentence id must be reported, never guessed.

This is the defect that put all 13 facts of the reference Sherwood 2WW
referral on the document banner. The model answered with a sentence label
the loader had never issued. Nothing checked, so the write fell through to
matching by character offset, offset 0 hit the banner chunk, and the run
finished green with every fact attributed to the wrong text and no evidence
offsets at all.

Two lookups had only two answers where they needed three
(fail-closed-boundary.mdc rule 2):

1. The sentence label to :Chunk id lookup on the write path. A label with
   no chunk behind it must stop the write for those facts and tell a
   person, not send an id into a MATCH that finds nothing.
2. The evidence-sentence lookup. When the fact's words are not in the
   sentence we hold, returning the whole block unchanged passes a banner
   off as the sentence the fact came from.

Atlas trace:
  DI: DI-B7A69F26 (fail-closed boundary), DI-02AB393F (degraded runs
      routed to human review), DI-16CE412B
  DO: DO-728930A1
  Risk: R-294446BF
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

from libs.cypher.documents_queries import select_evidence_sentence_traced
from libs.pipeline_graph.subgraphs.persist import (
    UNWRITABLE_FACTS_WARNING,
    write_patient_graph,
)

_BANNER_CHUNK = "b689f4e037be32adc8f70163067c0063"
_EXAM_CHUNK = "4a8d9afbdb1e46b4caedb0aadcdbece1"

_BANNER_TEXT = "--- Document: Sherwood 2WW gynae referral.doc ---"
_EXAM_TEXT = "On examination: abdo full soft, non tender."


def _state(**overrides: Any) -> dict[str, Any]:
    """A document-chunks run whose fact names a label the loader never issued."""
    state: dict[str, Any] = {
        "encounter_id": "enc-1",
        "patient_id": "pat-1",
        "encounter_text": f"{_BANNER_TEXT}\n\n{_EXAM_TEXT}",
        "text_segmentation_mode": "document_chunks",
        "sentences": [
            {"sentence_id": "s0", "text": _BANNER_TEXT, "start": 0, "end": 48},
            {"sentence_id": "s1", "text": _EXAM_TEXT, "start": 50, "end": 93},
        ],
        "chunk_id_by_sentence_id": {"s0": _BANNER_CHUNK, "s1": _EXAM_CHUNK},
        "entities": [
            {
                "text": "non tender",
                "label": "finding",
                "concept_id": "301371003",
                # The model answered with a label from the few-shot examples
                # rather than one of the two this bundle actually has.
                "__sentence_id": "s7",
            }
        ],
        "errors": [],
    }
    state.update(overrides)
    return state


def _run(state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the patient-graph write, capturing the payload it would send."""
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    client = MagicMock()
    client.session.return_value = session
    captured: list[dict[str, Any]] = []

    def _capture(encounter_id, sentences_payload, session, **kwargs):
        del encounter_id, session, kwargs
        captured.extend(sentences_payload)
        return sum(len(s.get("terms") or []) for s in sentences_payload)

    with (
        patch(
            "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client",
            return_value=client,
        ),
        patch(
            "libs.cypher.documents_queries.write_documents_from_sentences_payload",
            side_effect=_capture,
        ),
    ):
        result = write_patient_graph(state)
    return result, captured


def test_an_unknown_label_is_not_written_against_an_id_that_matches_nothing() -> None:
    _, payload = _run(_state())
    written_ids = [row["sentence_id"] for row in payload if row.get("terms")]
    assert written_ids == [], (
        "a fact on an unknown label reached the write; "
        f"it would MATCH (src:Chunk {{id: {written_ids}}}) and find nothing"
    )


def test_an_unknown_label_never_lands_on_the_banner_chunk() -> None:
    """The exact symptom: everything attributed to chunk ordinal 1."""
    _, payload = _run(_state())
    banner_terms = [
        row for row in payload if row["sentence_id"] == _BANNER_CHUNK and row["terms"]
    ]
    assert banner_terms == []


def test_the_run_warns_a_person_that_facts_were_not_saved() -> None:
    result, _ = _run(_state())
    warnings = result.get("warnings") or []
    assert any(UNWRITABLE_FACTS_WARNING in w for w in warnings), (
        "losing a clinical fact must be visible to a person; a log line is "
        f"not. warnings={warnings}"
    )


def test_the_warning_says_what_happened_in_plain_english() -> None:
    result, _ = _run(_state())
    warning = next(
        w for w in (result.get("warnings") or []) if UNWRITABLE_FACTS_WARNING in w
    )
    assert "not saved" in warning
    assert "check this run" in warning


def test_an_earlier_warning_is_not_erased() -> None:
    result, _ = _run(_state(warnings=["healthcare_service_missing"]))
    assert "healthcare_service_missing" in (result.get("warnings") or [])


def test_the_no_sentence_marker_is_never_written_as_a_chunk_id() -> None:
    """``s-fallback`` means "we do not know which sentence".

    It is not a hash and not an ``s0``-style label, so a shape-based check
    waves it through and the write becomes
    ``MATCH (src:Chunk {id: 's-fallback'})``, which finds nothing.
    """
    state = _state()
    del state["entities"][0]["__sentence_id"]
    result, payload = _run(state)

    written_ids = [row["sentence_id"] for row in payload if row.get("terms")]
    assert written_ids == [], f"s-fallback reached the write as {written_ids}"
    assert any(UNWRITABLE_FACTS_WARNING in w for w in (result.get("warnings") or []))


def test_a_known_label_still_reaches_its_own_chunk() -> None:
    """The fix must not stop a correctly labelled fact from being saved."""
    state = _state()
    state["entities"][0]["__sentence_id"] = "s1"
    result, payload = _run(state)

    carrying = [row for row in payload if row.get("terms")]
    assert len(carrying) == 1
    assert carrying[0]["sentence_id"] == _EXAM_CHUNK
    assert not [
        w for w in (result.get("warnings") or []) if UNWRITABLE_FACTS_WARNING in w
    ]


# ---------------------------------------------------------------------------
# The evidence-sentence lookup must also have three answers
# ---------------------------------------------------------------------------


def test_evidence_lookup_reports_when_the_fact_is_in_the_sentence() -> None:
    narrowed, found = select_evidence_sentence_traced(_EXAM_TEXT, "non tender")
    assert found is True
    assert narrowed == _EXAM_TEXT


def test_evidence_lookup_narrows_to_the_smallest_matching_line() -> None:
    block = f"{_BANNER_TEXT}\n{_EXAM_TEXT}"
    narrowed, found = select_evidence_sentence_traced(block, "non tender")
    assert found is True
    assert narrowed == _EXAM_TEXT


def test_evidence_lookup_reports_a_fact_that_is_not_in_the_sentence() -> None:
    """Returning the banner as the fact's sentence is a guess, not evidence."""
    _, found = select_evidence_sentence_traced(_BANNER_TEXT, "non tender")
    assert found is False, (
        "the fact's words are not in this text, so the lookup must say so "
        "rather than hand the whole banner back as the evidence sentence"
    )


def test_evidence_lookup_reports_an_empty_sentence() -> None:
    _, found = select_evidence_sentence_traced("", "non tender")
    assert found is False


def test_evidence_lookup_reports_an_empty_fact() -> None:
    _, found = select_evidence_sentence_traced(_EXAM_TEXT, "")
    assert found is False


def test_the_writer_says_out_loud_when_it_cannot_locate_the_evidence(
    caplog: Any,
) -> None:
    """A silent debug line let the banner pass as the fact's own sentence."""
    from libs.cypher.documents_queries import _collect_pending_document_writes

    payload = [
        {
            "sentence_id": _BANNER_CHUNK,
            "text": _BANNER_TEXT,
            "persist_source_label": "Chunk",
            "terms": [
                {
                    "text": "non tender",
                    "semantic_tag": "finding",
                    "assertion": "present",
                    "coding": {"snomed_concept_id": "301371003"},
                }
            ],
        }
    ]

    with caplog.at_level(logging.WARNING, logger="libs.cypher.documents_queries"):
        _collect_pending_document_writes(
            "enc-1",
            payload,
            source="pipeline",
            model_name="",
            model_version="",
            contract_version="",
            run_id="run-1",
            source_label="Chunk",
            active_terms=set(),
        )

    assert any(
        "evidence_not_located" in record.getMessage() for record in caplog.records
    ), f"expected a warning naming the unlocated fact, got {caplog.messages}"
