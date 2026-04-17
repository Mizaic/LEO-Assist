"""VT-LEO-AI-103 -- LLM extractor does not assign assertion.

Verifies that:
1. Both LLM extraction code paths always initialise assertion='present',
   regardless of any assertion value in the raw LLM JSON output.
2. The extraction prompt schemas do not contain an assertion field.
3. ConText correctly applies non-present assertions after extraction has
   initialised everything to 'present'.

Uses source inspection for modules with heavy optional dependencies
(numpy/medspacy), consistent with the pattern in test_assertion_pipeline_fix.py.
"""

from __future__ import annotations

import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(rel_path: str) -> str:
    """Return raw source text for a repo-relative file path."""
    with open(os.path.join(_REPO_ROOT, rel_path), encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# TC-001: LLMExtractor._parse_terms always returns assertion=present
# ---------------------------------------------------------------------------


class TestLLMExtractorParserAssertionAlwaysPresent:
    """Source-level verification that _parse_terms never reads assertion from LLM JSON."""

    def test_parse_terms_does_not_read_assertion_from_term(self):
        """assertion must be hardcoded 'present', not term.get('assertion')."""
        src = _read("services/coding_worker/app/pipeline/llm_extractor.py")
        assert 'term.get("assertion")' not in src, (
            "llm_extractor._parse_terms must not read assertion from LLM JSON; "
            "assertion must always be set to 'present'"
        )

    def test_parse_terms_hardcodes_assertion_present(self):
        """_parse_terms must contain the literal assignment assertion = 'present'."""
        src = _read("services/coding_worker/app/pipeline/llm_extractor.py")
        assert (
            'assertion = "present"' in src
        ), "_parse_terms must assign assertion = 'present' unconditionally"


# ---------------------------------------------------------------------------
# TC-002: _extractor.py build path always returns assertion=present
# ---------------------------------------------------------------------------


class TestExtractorBuildPathAssertionAlwaysPresent:
    """_extractor.py ExtractionItem construction must hardcode 'present'."""

    def test_extractor_does_not_read_assertion_from_term(self):
        src = _read("libs/pipeline_graph/subgraphs/_extractor.py")
        assert 't.get("assertion"' not in src, (
            "_extractor.py must not read assertion from the LLM term dict; "
            "assertion must be hardcoded to 'present'"
        )

    def test_extractor_hardcodes_assertion_present(self):
        src = _read("libs/pipeline_graph/subgraphs/_extractor.py")
        assert (
            'assertion="present"' in src
        ), "_extractor.py must hardcode assertion='present' in ExtractionItem"


# ---------------------------------------------------------------------------
# TC-003: extraction_v1.py prompt schema has no assertion field
# ---------------------------------------------------------------------------


class TestExtractionPromptSchemaNoAssertion:
    def test_output_format_section_has_no_assertion_key(self):
        from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1

        output_start = EXTRACTION_SYSTEM_V1.find("OUTPUT FORMAT")
        assert output_start != -1, "OUTPUT FORMAT section not found in prompt"
        output_section = EXTRACTION_SYSTEM_V1[output_start:]
        assert (
            '"assertion"' not in output_section
        ), "assertion field must not appear in OUTPUT FORMAT schema"

    def test_priority_order_has_no_assertion_step(self):
        from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1

        assert "Assign exactly one assertion" not in EXTRACTION_SYSTEM_V1

    def test_assertion_values_section_removed(self):
        from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1

        assert "ASSERTION VALUES" not in EXTRACTION_SYSTEM_V1


# ---------------------------------------------------------------------------
# TC-004: llm_extractor._OUTPUT_FORMAT has no assertion field
# ---------------------------------------------------------------------------


class TestLLMExtractorOutputFormatSchemaNoAssertion:
    def test_output_format_constant_has_no_assertion_key(self):
        src = _read("services/coding_worker/app/pipeline/llm_extractor.py")
        idx = src.find("_OUTPUT_FORMAT")
        assert idx != -1
        block = src[idx : idx + 800]
        assert (
            '"assertion"' not in block
        ), "assertion field must not appear in _OUTPUT_FORMAT schema"


# ---------------------------------------------------------------------------
# TC-005 / TC-006: ConText applies non-present assertion after present init
# ---------------------------------------------------------------------------


class TestConTextAssertionAfterPresentInit:
    """ConText must correct assertion when entities are initialised to present."""

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

    def test_negated_entity_gets_absent(self):
        result = self._apply_context("No chest pain reported.", "chest pain")
        assert result == "absent"

    def test_fhx_entity_gets_family(self):
        result = self._apply_context("FHx of diabetes.", "diabetes")
        assert result == "family"
