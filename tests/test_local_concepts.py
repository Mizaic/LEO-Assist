"""VT -- LEO-local concept id helpers (happy and non-happy paths)."""

from __future__ import annotations

import pytest

from libs.terminology.local_concepts import (
    CODE_SYSTEM_LEO_LOCAL,
    RESERVED_ACTION_TEMPLATES,
    force_exact_match_for_local,
    is_local_concept_id,
    is_narrative_action,
    slugify_local_label,
    validate_action_kind,
    validate_concept_kind,
    validate_local_concept_id,
)


class TestLocalConceptIdHappy:
    def test_accepts_leo_local_finding_id(self):
        assert is_local_concept_id("LEO-LOCAL-ACNE-FULMINANS")
        assert validate_local_concept_id("leo-local-acne-fulminans") == (
            "LEO-LOCAL-ACNE-FULMINANS"
        )

    def test_accepts_leo_act_template_id(self):
        assert is_local_concept_id("LEO-ACT-ADVISE")
        assert "LEO-ACT-ADVISE" in RESERVED_ACTION_TEMPLATES

    def test_slugify_builds_valid_id(self):
        assert slugify_local_label("Acne fulminans") == "LEO-LOCAL-ACNE-FULMINANS"

    def test_code_system_constant(self):
        assert CODE_SYSTEM_LEO_LOCAL == "leo_local"

    def test_force_exact_match_for_local_ids(self):
        assert force_exact_match_for_local("LEO-LOCAL-X", True) is False
        assert force_exact_match_for_local("123456", True) is True


class TestLocalConceptIdUnhappy:
    def test_rejects_numeric_snomed(self):
        assert not is_local_concept_id("73211009")
        with pytest.raises(ValueError, match="LEO-LOCAL"):
            validate_local_concept_id("73211009")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="required"):
            validate_local_concept_id("  ")

    def test_rejects_wrong_prefix(self):
        with pytest.raises(ValueError):
            validate_local_concept_id("LOCAL-ACNE")

    def test_rejects_lowercase_slug_chars_after_normalise_ok(self):
        # validate uppercases; spaces/symbols must fail after strip
        with pytest.raises(ValueError):
            validate_local_concept_id("LEO-LOCAL-acne fulminans")

    def test_slugify_empty_label(self):
        with pytest.raises(ValueError, match="empty"):
            slugify_local_label("   ")


class TestConceptAndActionKinds:
    def test_valid_concept_kinds(self):
        assert validate_concept_kind("finding") == "finding"
        assert validate_concept_kind("NARRATIVE_ACTION") == "narrative_action"

    def test_invalid_concept_kind(self):
        with pytest.raises(ValueError, match="Invalid concept_kind"):
            validate_concept_kind("symptom")

    def test_action_kind_defaults_and_narrative(self):
        assert validate_action_kind(None) == "snomed_procedure"
        assert validate_action_kind("narrative") == "narrative"
        assert is_narrative_action("narrative") is True
        assert is_narrative_action("snomed_procedure") is False

    def test_invalid_action_kind(self):
        with pytest.raises(ValueError, match="Invalid action_kind"):
            validate_action_kind("order")
