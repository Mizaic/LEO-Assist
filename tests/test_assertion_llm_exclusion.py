"""LLM extractor assertion parsing aligned with annotation guidelines."""

from __future__ import annotations

import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel_path: str) -> str:
    with open(os.path.join(_REPO_ROOT, rel_path), encoding="utf-8") as fh:
        return fh.read()


class TestLLMExtractorParsesAssertion:
    def test_parse_terms_uses_parse_assertion(self) -> None:
        src = _read("services/coding_worker/app/pipeline/llm_extractor.py")
        assert "_parse_assertion(term.get" in src

    def test_parse_assertion_maps_absent(self) -> None:
        src = _read("services/coding_worker/app/pipeline/llm_extractor.py")
        assert 'return value if value in _VALID_ASSERTIONS else "present"' in src
        assert "_parse_assertion(term.get" in src


class TestExtractionPromptIncludesAssertion:
    def test_output_format_includes_assertion(self) -> None:
        from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1

        output_start = EXTRACTION_SYSTEM_V1.find("OUTPUT FORMAT")
        output_section = EXTRACTION_SYSTEM_V1[output_start:]
        assert '"assertion"' in output_section

    def test_assertion_section_present(self) -> None:
        from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1

        assert "ASSERTION" in EXTRACTION_SYSTEM_V1
        assert "DO NOT ASSIGN" not in EXTRACTION_SYSTEM_V1


class TestConTextAssertionAfterPresentInit:
    def _apply_context(self, sentence_text: str, entity_text: str) -> str:
        try:
            from libs.ner.context_engine import apply_context_detection_to_dicts
        except ImportError:
            pytest.skip("MedSpaCy not available in this environment")

        entities = [
            {
                "text": entity_text,
                "label": "finding",
                "assertion": "present",
                "start": sentence_text.lower().find(entity_text.lower()),
                "end": sentence_text.lower().find(entity_text.lower())
                + len(entity_text),
            }
        ]
        apply_context_detection_to_dicts(sentence_text, entities)
        return entities[0]["assertion"]

    def test_negated_entity_gets_absent(self) -> None:
        result = self._apply_context("No chest pain reported.", "chest pain")
        assert result == "absent"

    def test_fhx_entity_gets_family(self) -> None:
        result = self._apply_context("FHx of diabetes.", "diabetes")
        assert result == "family"
