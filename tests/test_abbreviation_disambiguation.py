"""VT-LEO-AI-081: Ambiguous abbreviation disambiguation tests.

Verifies:
  - NAD is in _ALWAYS_IGNORE_TERMS: all resolver output is suppressed regardless
    of concept ID (both 'No abnormality detected' and biochemistry concepts)
  - CA / MSK / NAD rules present in extraction prompt
  - Dual-path parity: escalation prompt contains same rules
  - Non-blocked terms pass through unchanged
"""

from __future__ import annotations

import re
import pytest

from libs.terminology.client import (
    ResolvedTerm,
    _ABBREV_BLOCKED_CONCEPTS,
    _ALWAYS_IGNORE_TERMS,
    _filter_abbrev_noise,
    _filter_observable_without_value,
)
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1
from libs.llm_client.escalation import _CANDIDATES_SYSTEM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_term(concept_id: str, tag: str = "finding") -> ResolvedTerm:
    return ResolvedTerm(
        text="NAD",
        concept_id=concept_id,
        term=f"concept-{concept_id}",
        semantic_tag=tag,
        score=1.0,
    )


def _make_dict(key: str, concept_id: str) -> dict:
    return {key: concept_id, "term": f"concept-{concept_id}", "score": 1.0}


# ---------------------------------------------------------------------------
# VT-081-TC-001: NAD is in the always-ignore set
# ---------------------------------------------------------------------------


class TestNADAlwaysIgnore:
    """NAD is always-ignored: the resolver must return nothing for this term."""

    def test_nad_in_always_ignore_terms(self) -> None:
        assert "nad" in _ALWAYS_IGNORE_TERMS

    def test_nad_not_in_blocked_concepts(self) -> None:
        # NAD moved from blocklist to always-ignore; blocklist should be empty
        assert "nad" not in _ABBREV_BLOCKED_CONCEPTS

    @pytest.mark.parametrize(
        "concept_id",
        [
            "131143000",  # Nicotinamide adenine dinucleotide (substance)
            "104695007",  # Glutamate dehydrogenase NAD measurement (procedure)
            "124316006",  # Deficiency of NAD kinase (disorder)
            "281900007",  # No abnormality detected (finding) -- also suppressed
        ],
    )
    def test_all_nad_concepts_suppressed_resolved_term(self, concept_id: str) -> None:
        """Every concept is suppressed for 'nad' -- including the GP meaning."""
        candidates = [_make_term(concept_id)]
        result = _filter_abbrev_noise("nad", candidates)
        assert result == [], f"Expected empty result for NAD but got {result}"

    @pytest.mark.parametrize(
        "concept_id",
        [
            "131143000",
            "104695007",
            "124316006",
            "281900007",
        ],
    )
    def test_all_nad_concepts_suppressed_raw_dict(self, concept_id: str) -> None:
        candidates = [_make_dict("snomed_concept_id", concept_id)]
        result = _filter_abbrev_noise("nad", candidates)
        assert result == []

    @pytest.mark.parametrize("text_variant", ["NAD", "Nad", "nAD", "nad"])
    def test_all_case_variants_suppressed(self, text_variant: str) -> None:
        candidates = [_make_term("281900007")]
        result = _filter_abbrev_noise(text_variant, candidates)
        assert result == []

    def test_empty_candidates_returns_empty(self) -> None:
        result = _filter_abbrev_noise("nad", [])
        assert result == []


# ---------------------------------------------------------------------------
# VT-081-TC-002: Non-blocked terms pass through unchanged
# ---------------------------------------------------------------------------


class TestNonBlockedTermsUnchanged:
    def test_htn_not_in_blocklist(self) -> None:
        assert "htn" not in _ABBREV_BLOCKED_CONCEPTS

    def test_htn_not_in_always_ignore(self) -> None:
        assert "htn" not in _ALWAYS_IGNORE_TERMS

    def test_htn_candidates_pass_through(self) -> None:
        htn = _make_term("38341003", "disorder")
        result = _filter_abbrev_noise("htn", [htn])
        assert len(result) == 1
        assert result[0].concept_id == "38341003"

    def test_unknown_term_candidates_unchanged(self) -> None:
        t = _make_term("999999999")
        result = _filter_abbrev_noise("xyz", [t])
        assert len(result) == 1

    def test_abpi_educational_phrase_is_suppressed(self) -> None:
        candidates = [_make_term("38341003", "disorder")]
        result = _filter_abbrev_noise(
            "An abnormal ABPI - ankle brachial pressure index could suggest significant arterial stenosis.",
            candidates,
        )
        assert result == []

    def test_reduced_abpi_may_indicate_phrase_is_suppressed(self) -> None:
        candidates = [_make_term("38341003", "disorder")]
        result = _filter_abbrev_noise(
            "A reduced ABPI - ankle brachial pressure index may indicate peripheral arterial disease.",
            candidates,
        )
        assert result == []

    def test_not_on_thyroid_tx_is_suppressed(self) -> None:
        candidates = [_make_term("38341003", "disorder")]
        result = _filter_abbrev_noise("Not on Thyroid Tx", candidates)
        assert result == []

    def test_service_config_ignore_pattern_is_applied(self, monkeypatch) -> None:
        from libs import terminology

        monkeypatch.setattr(
            terminology.client,
            "_load_dynamic_ignore_patterns",
            lambda force_refresh=False: (
                re.compile(r"\beducational\s+statement\b", re.IGNORECASE),
            ),
        )
        candidates = [_make_term("38341003", "disorder")]
        result = _filter_abbrev_noise(
            "This educational statement should never be coded.",
            candidates,
        )
        assert result == []


# ---------------------------------------------------------------------------
# VT-081-TC-003: Both object types handled
# ---------------------------------------------------------------------------


class TestFilterPolymorphism:
    def test_resolvedterm_objects_suppressed_for_nad(self) -> None:
        r = _make_term("281900007")
        result = _filter_abbrev_noise("nad", [r])
        assert result == []

    def test_raw_dicts_suppressed_for_nad(self) -> None:
        d = {"snomed_concept_id": "281900007", "term": "No abnormality detected"}
        result = _filter_abbrev_noise("nad", [d])
        assert result == []

    def test_resolvedterm_passes_through_for_other_terms(self) -> None:
        r = _make_term("38341003", "disorder")
        result = _filter_abbrev_noise("hypertension", [r])
        assert result == [r]


class TestObservableNeedsValue:
    def test_observable_removed_without_value(self) -> None:
        obs = ResolvedTerm(
            text="ABPI - ankle brachial pressure index",
            concept_id="446841001",
            term="Ankle brachial pressure index",
            semantic_tag="observable_entity",
            score=1.0,
        )
        proc = ResolvedTerm(
            text="ABPI - ankle brachial pressure index",
            concept_id="401221002",
            term="Ankle brachial pressure index",
            semantic_tag="procedure",
            score=0.9,
        )
        filtered = _filter_observable_without_value(
            "ABPI - ankle brachial pressure index performed at previous clinic",
            [obs, proc],
        )
        assert len(filtered) == 1
        assert filtered[0].semantic_tag == "procedure"

    def test_observable_kept_with_numeric_value(self) -> None:
        obs = ResolvedTerm(
            text="ABPI 0.72",
            concept_id="446841001",
            term="Ankle brachial pressure index",
            semantic_tag="observable_entity",
            score=1.0,
        )
        filtered = _filter_observable_without_value("ABPI 0.72", [obs])
        assert len(filtered) == 1
        assert filtered[0].semantic_tag == "observable_entity"

    def test_observable_reference_range_phrase_removed_without_blood_context(self) -> None:
        obs = ResolvedTerm(
            text="ABPI",
            concept_id="446841001",
            term="Ankle brachial pressure index",
            semantic_tag="observable_entity",
            score=1.0,
        )
        filtered = _filter_observable_without_value(
            "ABPI is out of reference range on repeat measurement",
            [obs],
        )
        assert len(filtered) == 0

    def test_observable_kept_with_blood_reference_range_phrase(self) -> None:
        obs = ResolvedTerm(
            text="serum potassium",
            concept_id="446841001",
            term="Potassium level",
            semantic_tag="observable_entity",
            score=1.0,
        )
        filtered = _filter_observable_without_value(
            "Serum potassium is out of reference range on repeat blood test",
            [obs],
        )
        assert len(filtered) == 1
        assert filtered[0].semantic_tag == "observable_entity"


# ---------------------------------------------------------------------------
# VT-081-TC-004 to TC-006: Extraction prompt content checks
# ---------------------------------------------------------------------------


class TestExtractionPromptRules:
    def test_admin_only_lines_do_not_extract_rule_present(self) -> None:
        """Purely admin lines must not get invented clinical entities."""
        prompt_lower = EXTRACTION_SYSTEM_V1.lower()
        assert "purely administrative text" in prompt_lower
        assert "workflow text" in prompt_lower
        assert "safety-netting" in prompt_lower

    def test_nad_do_not_extract_rule_present(self) -> None:
        """NAD must appear in the DO NOT EXTRACT section."""
        assert "NAD" in EXTRACTION_SYSTEM_V1
        assert "Do NOT extract" in EXTRACTION_SYSTEM_V1

    def test_nad_never_extract_rule_in_prompt(self) -> None:
        """Prompt must explicitly block NAD extraction."""
        prompt_lower = EXTRACTION_SYSTEM_V1.lower()
        assert "nad -> never extract" in prompt_lower

    def test_nad_prompt_says_do_not_code(self) -> None:
        """Prompt must tell LLM not to code NAD."""
        assert any(
            phrase in EXTRACTION_SYSTEM_V1
            for phrase in [
                "Do NOT extract",
                "never extract",
                "NAD -> never extract",
            ]
        )

    def test_ca_disambiguation_present(self) -> None:
        prompt_lower = EXTRACTION_SYSTEM_V1.lower()
        assert "ca" in prompt_lower
        assert (
            "organ" in prompt_lower
            or "body site" in prompt_lower
            or "site" in prompt_lower
        )

    def test_ca_requires_site_context(self) -> None:
        assert any(
            phrase in EXTRACTION_SYSTEM_V1
            for phrase in [
                '"CA" alone',
                "CA alone",
                "without an organ",
                "leave uncoded",
                "NOT be extracted",
            ]
        )

    def test_msk_specialty_tag_rule_present(self) -> None:
        assert "MSK" in EXTRACTION_SYSTEM_V1
        assert any(
            phrase in EXTRACTION_SYSTEM_V1
            for phrase in [
                "specialty",
                "category",
                "body system",
                "specialty tag",
            ]
        )


# ---------------------------------------------------------------------------
# VT-081-TC-007 to TC-010: Escalation prompt parity (dual-path consistency)
# ---------------------------------------------------------------------------


class TestEscalationPromptParity:
    def test_ca_rule_in_candidates_system(self) -> None:
        assert any(
            phrase in _CANDIDATES_SYSTEM
            for phrase in [
                "CA without",
                "CA alone",
                "no organ",
                "organ/site",
                "organ or body site",
            ]
        )

    def test_msk_rule_in_candidates_system(self) -> None:
        assert any(
            phrase in _CANDIDATES_SYSTEM
            for phrase in [
                "MSK alone",
                "MSK",
                "specialty tag",
                "specialty or system",
            ]
        )

    def test_nad_rule_in_candidates_system(self) -> None:
        """Escalation prompt must state NAD is not_codeable."""
        assert any(
            phrase in _CANDIDATES_SYSTEM
            for phrase in [
                "not_codeable",
                "NAD",
                "No apparent distress",
                "cannot be determined",
            ]
        )

    def test_nad_escalation_says_not_codeable(self) -> None:
        """The NAD rule in the escalation prompt must lead to not_codeable."""
        nad_section = _CANDIDATES_SYSTEM[_CANDIDATES_SYSTEM.find("NAD") :]
        first_line = nad_section[:300]
        assert "not_codeable" in first_line or "leave" in first_line.lower()

    def test_nad_ambiguity_stated_in_candidates_system(self) -> None:
        """Escalation prompt must state the ambiguity, not just the GP meaning."""
        combined = _CANDIDATES_SYSTEM.lower()
        assert "no apparent distress" in combined or "ambiguous" in combined
