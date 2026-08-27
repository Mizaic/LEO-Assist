"""Tests for cross-form section borrowing (similarity matching).

Atlas trace: DI-5C9CA57B

TDD red phase -- these tests fail until form_schema_similarity.py is implemented.
"""

from __future__ import annotations

import pytest

from libs.pipeline.form_schema_similarity import (
    SectionMatch,
    find_similar_sections,
    merge_borrowed_and_detected,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_schema(
    fingerprint: str = "fp-a",
    org: str = "Org A",
    service: str = "Gynae",
    form_name: str = "2WW Gynae",
    sections: list[dict] | None = None,
) -> dict:
    if sections is None:
        sections = []
    return {
        "fingerprint": fingerprint,
        "organization_id": org,
        "service_id": service,
        "form_name": form_name,
        "sections": sections,
    }


def _make_section(
    section_id: str = "sec-1",
    label: str = "Referral Criteria",
    section_type: str = "checkbox_yesno",
    start_pattern: str = "Referral Criteria",
    items: list[dict] | None = None,
) -> dict:
    return {
        "section_id": section_id,
        "label": label,
        "section_type": section_type,
        "start_pattern": start_pattern,
        "items": items or [],
        "semantic_tags": ["finding"],
    }


# ---------------------------------------------------------------------------
# find_similar_sections
# ---------------------------------------------------------------------------

class TestFindSimilarSections:
    def test_exact_match_returns_section(self):
        """An exact heading match should return a high-confidence SectionMatch."""
        schema = _make_schema(
            fingerprint="fp-a",
            sections=[_make_section(start_pattern="Referral Criteria")],
        )
        chunks = ["| Referral Criteria |", "Some other text"]
        matches = find_similar_sections(chunks, [schema])
        assert len(matches) == 1
        assert matches[0].confidence >= 0.85
        assert matches[0].source_fingerprint == "fp-a"
        assert matches[0].section["start_pattern"] == "Referral Criteria"

    def test_fuzzy_match_above_threshold(self):
        """A near-identical heading should still match."""
        schema = _make_schema(
            sections=[_make_section(start_pattern="Patient Awareness")]
        )
        # Slight variation: extra space, lowercase
        chunks = ["| patient awareness |"]
        matches = find_similar_sections(chunks, [schema], threshold=0.80)
        assert len(matches) == 1

    def test_no_match_below_threshold(self):
        """A heading that is very different should produce no match."""
        schema = _make_schema(
            sections=[_make_section(start_pattern="Referral Criteria")]
        )
        chunks = ["Some unrelated text about allergies"]
        matches = find_similar_sections(chunks, [schema], threshold=0.85)
        assert len(matches) == 0

    def test_empty_chunks_returns_empty(self):
        schema = _make_schema(
            sections=[_make_section(start_pattern="Referral Criteria")]
        )
        matches = find_similar_sections([], [schema])
        assert matches == []

    def test_empty_schemas_returns_empty(self):
        matches = find_similar_sections(["Referral Criteria"], [])
        assert matches == []

    def test_match_carries_source_metadata(self):
        """Borrowing metadata (org, service, form_name) must be on the result."""
        schema = _make_schema(
            fingerprint="fp-xyz",
            org="Sherwood FT",
            service="Gynae 2WW",
            form_name="Gynae 2WW Referral",
            sections=[_make_section(start_pattern="Cancer Type")],
        )
        chunks = ["Cancer Type"]
        matches = find_similar_sections(chunks, [schema])
        assert matches[0].source_org == "Sherwood FT"
        assert matches[0].source_service == "Gynae 2WW"
        assert matches[0].source_form_name == "Gynae 2WW Referral"

    def test_returns_section_with_items(self):
        """The borrowed section dict must carry through the known items."""
        items = [
            {
                "pattern": "Cervix",
                "entity_text": "Cervical cancer suspected",
                "semantic_tag": "finding",
                "assertion": "present",
                "procedure_snomed": "",
                "procedure_display": "",
                "analytes": [],
                "value_placeholder": "",
            }
        ]
        schema = _make_schema(
            sections=[_make_section(start_pattern="Cancer Type", items=items)]
        )
        chunks = ["Cancer Type"]
        matches = find_similar_sections(chunks, [schema])
        assert matches[0].section["items"] == items

    def test_deduplicates_same_pattern_across_schemas(self):
        """When two schemas have the same section, only the best match is returned."""
        schema_a = _make_schema(
            fingerprint="fp-a",
            sections=[_make_section(start_pattern="Referral Criteria")],
        )
        schema_b = _make_schema(
            fingerprint="fp-b",
            sections=[_make_section(start_pattern="Referral Criteria")],
        )
        chunks = ["Referral Criteria"]
        matches = find_similar_sections(chunks, [schema_a, schema_b])
        # Only one winner per distinct start_pattern
        patterns = [m.section["start_pattern"] for m in matches]
        assert patterns.count("Referral Criteria") == 1

    def test_admin_sections_are_excluded(self):
        """admin and template_noise sections must never be borrowed."""
        schema = _make_schema(
            sections=[
                _make_section(
                    start_pattern="Patient Details", section_type="admin"
                )
            ]
        )
        chunks = ["Patient Details"]
        matches = find_similar_sections(chunks, [schema])
        assert matches == []

    def test_multiple_sections_matched_from_one_schema(self):
        """Two distinct section headings in the same form should both match."""
        schema = _make_schema(
            sections=[
                _make_section(
                    section_id="s1", start_pattern="Referral Criteria"
                ),
                _make_section(
                    section_id="s2",
                    start_pattern="Patient Awareness",
                    section_type="checkbox_yesno",
                ),
            ]
        )
        chunks = ["Referral Criteria", "Patient Awareness and Consent"]
        matches = find_similar_sections(chunks, [schema], threshold=0.70)
        patterns = {m.section["start_pattern"] for m in matches}
        assert "Referral Criteria" in patterns
        assert "Patient Awareness" in patterns

    def test_confidence_is_between_0_and_1(self):
        schema = _make_schema(
            sections=[_make_section(start_pattern="Referral Criteria")]
        )
        chunks = ["Referral Criteria"]
        matches = find_similar_sections(chunks, [schema])
        assert 0.0 <= matches[0].confidence <= 1.0


# ---------------------------------------------------------------------------
# merge_borrowed_and_detected
# ---------------------------------------------------------------------------

class TestMergeBorrowedAndDetected:
    def _section_dict(self, section_id: str, start_pattern: str) -> dict:
        return {
            "section_id": section_id,
            "label": start_pattern,
            "section_type": "checkbox_yesno",
            "start_pattern": start_pattern,
            "items": [],
            "default_semantic_tags": ["finding"],
        }

    def test_borrowed_section_augmented_with_provenance(self):
        """Borrowed sections gain a borrowed_from key."""
        match = SectionMatch(
            section=_make_section(start_pattern="Referral Criteria"),
            source_fingerprint="fp-a",
            source_org="Org A",
            source_service="Gynae",
            source_form_name="2WW Gynae",
            confidence=0.95,
        )
        detected = [self._section_dict("llm-1", "Clinical History")]
        result = merge_borrowed_and_detected([match], detected)
        borrowed = [s for s in result if s.get("borrowed_from")]
        assert len(borrowed) == 1
        assert borrowed[0]["borrowed_from"]["org"] == "Org A"
        assert borrowed[0]["borrowed_from"]["service"] == "Gynae"
        assert borrowed[0]["borrowed_from"]["confidence"] == 0.95

    def test_llm_detected_sections_kept(self):
        """LLM-detected sections that have no borrowed match are kept as-is."""
        detected = [self._section_dict("llm-1", "Clinical History")]
        result = merge_borrowed_and_detected([], detected)
        assert len(result) == 1
        assert result[0]["section_id"] == "llm-1"

    def test_borrowed_section_does_not_duplicate_llm_section(self):
        """When LLM also found the same section, the borrowed version wins."""
        match = SectionMatch(
            section=_make_section(start_pattern="Referral Criteria"),
            source_fingerprint="fp-a",
            source_org="Org A",
            source_service="Gynae",
            source_form_name="2WW",
            confidence=0.95,
        )
        detected = [
            self._section_dict("llm-1", "Referral Criteria"),
            self._section_dict("llm-2", "Clinical History"),
        ]
        result = merge_borrowed_and_detected([match], detected)
        ref_crit = [s for s in result if "Referral Criteria" in s["start_pattern"]]
        assert len(ref_crit) == 1
        # It should be the borrowed one (has items and borrowed_from)
        assert ref_crit[0].get("borrowed_from") is not None

    def test_empty_both_returns_empty(self):
        result = merge_borrowed_and_detected([], [])
        assert result == []
