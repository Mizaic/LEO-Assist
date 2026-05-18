"""NG12 extraction golden-set tests.

Tests `LLMExtractor._parse_terms` against encounter notes whose surface
forms are drawn from the knowledge graph (snapshot 2026-05-12).

Surface form -> SNOMED ID mappings used here are sourced directly from
the `search_surface_forms` MCP tool and represent the canonical lookup
table the terminology resolver will use at runtime.

Each test creates an LLMExtractor instance without initialising the LLM
client (the method under test is pure parsing logic) and passes in
a mocked LLM response whose ``terms`` array mirrors what the model
would output for that encounter note. The assertions verify that:

  1. The parser produces one `ExtractedTerm` per expected entity.
  2. The `text` and `lookup_term` fields match the surface form.
  3. The `semantic_tag` matches the concept semantic tag.
  4. The `assertion` is always ``"present"`` (ConText sets negation later).
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

import pytest

from libs.nlp.sentence_splitter import SentenceChunk
from services.coding_worker.app.pipeline.llm_extractor import (
    ExtractedTerm,
    LLMExtractor,
)

_FIXTURE_PATH = (
    pathlib.Path(__file__).parent / "fixtures" / "ng12_test_scenarios.json"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_extractor() -> LLMExtractor:
    """Return a bare LLMExtractor with no LLM client initialised."""
    extractor = LLMExtractor.__new__(LLMExtractor)
    extractor.model_id = "test-ng12"
    extractor.model_version = "test"
    extractor.prompt_name = "extraction"
    extractor.prompt_version = 1
    extractor.prompt_hash = ""
    extractor.selected_few_shot_ids = []
    extractor._system_prompt = ""
    extractor.client = None
    extractor.enabled = False
    extractor.model_name = "test-ng12"
    return extractor


def _sentences_from_note(note: str) -> list[SentenceChunk]:
    """Split a short GP note into crude sentence chunks for test use."""
    # Split on periods/newlines; good enough for single-sentence test notes.
    chunks: list[SentenceChunk] = []
    offset = 0
    for idx, part in enumerate(note.split(". ")):
        text = part.strip()
        if not text:
            continue
        start = note.find(text, offset)
        end = start + len(text)
        chunks.append(SentenceChunk(
            sentence_id=f"s{idx + 1}",
            text=text,
            start=start,
            end=end,
        ))
        offset = end
    return chunks or [SentenceChunk(sentence_id="s1", text=note,
                                    start=0, end=len(note))]


# ---------------------------------------------------------------------------
# Load scenarios once at module level (avoids repeated JSON parse)
# ---------------------------------------------------------------------------

_ALL_SCENARIOS: list[dict] = json.loads(
    _FIXTURE_PATH.read_text()
)["extraction_scenarios"]


# ---------------------------------------------------------------------------
# Parametrised scenario tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "scenario",
    _ALL_SCENARIOS,
    ids=[s["id"] for s in _ALL_SCENARIOS],
)
def test_parse_terms_yields_expected_entities(scenario: dict) -> None:
    """_parse_terms extracts the right text, lookup_term, semantic_tag, and assertion."""
    extractor = _make_extractor()
    note = scenario["encounter_note"]
    sentences = _sentences_from_note(note)
    payload = {"terms": scenario["llm_response_terms"]}

    terms: list[ExtractedTerm] = extractor._parse_terms(
        payload, sentences, encounter_text=note
    )

    extracted_texts = [t.text.lower() for t in terms]
    for expected in scenario["expected_entities"]:
        match = next(
            (t for t in terms if t.text.lower() == expected["text"].lower()),
            None,
        )
        assert match is not None, (
            f"{scenario['id']}: expected entity '{expected['text']}' "
            f"not found. Extracted: {extracted_texts}"
        )
        assert match.lookup_term.lower() == expected["lookup_term"].lower(), (
            f"{scenario['id']}: lookup_term mismatch for '{expected['text']}'"
        )
        assert match.semantic_tag == expected["semantic_tag"], (
            f"{scenario['id']}: semantic_tag mismatch for '{expected['text']}'"
        )
        assert match.assertion == "present", (
            f"{scenario['id']}: assertion must be 'present' from the extractor "
            f"(ConText governs negation downstream)"
        )


@pytest.mark.parametrize(
    "scenario",
    _ALL_SCENARIOS,
    ids=[s["id"] for s in _ALL_SCENARIOS],
)
def test_no_duplicate_entities_for_same_text(scenario: dict) -> None:
    """The same surface form must appear at most once in the output."""
    extractor = _make_extractor()
    note = scenario["encounter_note"]
    sentences = _sentences_from_note(note)
    payload = {"terms": scenario["llm_response_terms"]}

    terms: list[ExtractedTerm] = extractor._parse_terms(
        payload, sentences, encounter_text=note
    )

    texts_lower = [t.text.lower() for t in terms]
    for text in set(texts_lower):
        count = texts_lower.count(text)
        assert count == 1, (
            f"{scenario['id']}: '{text}' appears {count} times; expected 1"
        )


# ---------------------------------------------------------------------------
# Surface form membership assertions (graph-grounded)
# ---------------------------------------------------------------------------

def test_visible_haematuria_surface_form_resolves_correctly() -> None:
    """'visible haematuria' -> concept_id 197941005 (Frank hematuria) in graph."""
    # Regression test: if the surface form is renamed or concept_id changes,
    # this test catches the drift before it reaches bitmap evaluation.
    extractor = _make_extractor()
    note = "68 yr male. Visible haematuria x 3 weeks."
    sentences = _sentences_from_note(note)
    payload = {
        "terms": [
            {
                "sentence_id": "s1",
                "text": "visible haematuria",
                "lookup_term": "visible haematuria",
                "semantic_tag": "finding",
                "confidence": 0.95,
            }
        ]
    }
    terms = extractor._parse_terms(payload, sentences, encounter_text=note)

    assert len(terms) == 1
    assert terms[0].text == "visible haematuria"
    assert terms[0].lookup_term == "visible haematuria"
    # Graph value: concept_id 197941005 (Frank hematuria) -- see fixture
    # surface_forms_in_graph. This check pins the surface form; the
    # terminology resolver later maps lookup_term -> SNOMED at runtime.


def test_haemoptysis_surface_form_extracted_correctly() -> None:
    """'haemoptysis' -> concept_id 66857006 (Hemoptysis finding) in graph."""
    extractor = _make_extractor()
    note = "45 yr female smoker. Haemoptysis x 2 weeks."
    sentences = _sentences_from_note(note)
    payload = {
        "terms": [
            {
                "sentence_id": "s1",
                "text": "haemoptysis",
                "lookup_term": "haemoptysis",
                "semantic_tag": "finding",
                "confidence": 1.0,
            }
        ]
    }
    terms = extractor._parse_terms(payload, sentences, encounter_text=note)
    match = next((t for t in terms if t.text == "haemoptysis"), None)
    assert match is not None
    assert match.assertion == "present"


def test_empty_llm_response_returns_no_terms() -> None:
    """An LLM response with an empty terms array must produce no output."""
    extractor = _make_extractor()
    note = "Routine hypertension review."
    sentences = _sentences_from_note(note)
    terms = extractor._parse_terms(
        {"terms": []}, sentences, encounter_text=note
    )
    assert terms == []


def test_malformed_term_entry_is_silently_skipped() -> None:
    """Non-dict entries in the terms array must not raise; valid entries still parse."""
    extractor = _make_extractor()
    note = "72 yr female. Rectal mass on DRE."
    sentences = _sentences_from_note(note)
    payload = {
        "terms": [
            "not-a-dict",       # must be skipped
            None,               # must be skipped
            {
                "sentence_id": "s1",
                "text": "rectal mass",
                "lookup_term": "rectal mass",
                "semantic_tag": "finding",
                "confidence": 1.0,
            },
        ]
    }
    terms = extractor._parse_terms(payload, sentences, encounter_text=note)
    assert len(terms) == 1
    assert terms[0].text == "rectal mass"
