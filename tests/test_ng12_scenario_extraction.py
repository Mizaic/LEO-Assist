"""Parametrised extraction checks against 348 NG12 EXT scenarios."""

from __future__ import annotations

import json
import pathlib

import pytest

from libs.nlp.sentence_splitter import SentenceChunk
from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

from tests.helpers.ng12_scenario_loader import load_paired_scenarios

_FIX = pathlib.Path(__file__).parent / "fixtures" / "ng12_scenarios"

_, _EXT_ROOT, _ = load_paired_scenarios()
_EXT_SCENARIOS: list[dict] = _EXT_ROOT["scenarios"]
_EXT_IDS: list[str] = [s["id"] for s in _EXT_SCENARIOS]


def _make_extractor() -> LLMExtractor:
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
    chunks: list[SentenceChunk] = []
    offset = 0
    for idx, part in enumerate(note.split(". ")):
        text = part.strip()
        if not text:
            continue
        start = note.find(text, offset)
        if start < 0:
            start = 0
        end = start + len(text)
        chunks.append(
            SentenceChunk(
                sentence_id=f"s{idx + 1}",
                text=text,
                start=start,
                end=end,
            )
        )
        offset = end
    return chunks or [
        SentenceChunk(sentence_id="s1", text=note, start=0, end=len(note))
    ]


@pytest.mark.parametrize("scenario", _EXT_SCENARIOS, ids=_EXT_IDS)
def test_parse_terms_extraction_rows(scenario: dict) -> None:
    """``_parse_terms`` output matches expected_entities for every row."""
    extractor = _make_extractor()
    note = scenario["encounter_note"]
    sentences = _sentences_from_note(note)
    payload = {"terms": scenario["llm_response_terms"]}
    terms_out = extractor._parse_terms(payload, sentences, encounter_text=note)
    extracted_lower = [t.text.lower() for t in terms_out]
    for expected in scenario.get("expected_entities", []):
        match = next(
            (t for t in terms_out if t.text.lower() == expected["text"].lower()),
            None,
        )
        assert match is not None, (
            f"{scenario['id']}: missing entity {expected['text']} "
            f"got {extracted_lower}"
        )
        assert match.lookup_term.lower() == expected["lookup_term"].lower()
        assert match.semantic_tag == expected["semantic_tag"]
        assert match.assertion == "present"


@pytest.mark.parametrize("scenario", _EXT_SCENARIOS, ids=_EXT_IDS)
def test_no_duplicate_extracted_text(scenario: dict) -> None:
    """Each surface form appears at most once per scenario."""
    extractor = _make_extractor()
    note = scenario["encounter_note"]
    sentences = _sentences_from_note(note)
    terms_out = extractor._parse_terms(
        {"terms": scenario["llm_response_terms"]},
        sentences,
        encounter_text=note,
    )
    texts = [t.text.lower() for t in terms_out]
    for t in set(texts):
        assert texts.count(t) == 1, f"{scenario['id']}: duplicate {t}"


def test_fixture_file_count() -> None:
    """Sanity: 348 scenarios on disk."""
    data = json.loads((_FIX / "ng12_extraction_scenarios.json").read_text())
    assert len(data["scenarios"]) == 348
