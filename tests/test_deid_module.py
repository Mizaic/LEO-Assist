"""Tests for `libs/deid/deid.py` -- the NER-preprocessing PHI redaction pass.

This is the de-identification pass applied before the NER extractor sees the
text. It is distinct from `libs/utils/deidentify.py`, which handles the
LLM-submission path. Both must independently meet the residual-PHI gates.

Atlas trace:
  DO: DO-9BF76337
  DI: DI-8A943628
"""

from __future__ import annotations

import pytest

from libs.deid.deid import DeidResult, _build_org_pattern, deidentify


class TestPHIRedaction:
    """Each PHI category produces the documented placeholder token."""

    def test_redacts_nhs_number_with_spaces(self):
        out = deidentify("Patient NHS number 485 777 3456 noted")
        assert "[NHS_NO]" in out.text
        assert "485 777 3456" not in out.text

    def test_redacts_nhs_number_with_hyphens(self):
        out = deidentify("NHS no 485-777-3456 on file")
        assert "[NHS_NO]" in out.text
        assert "485-777-3456" not in out.text

    def test_redacts_nhs_number_no_separators(self):
        out = deidentify("NHS 4857773456 noted")
        assert "[NHS_NO]" in out.text
        assert "4857773456" not in out.text

    def test_redacts_full_uk_postcode(self):
        out = deidentify("Address SW1A 1AA recorded")
        assert "[POSTCODE]" in out.text
        assert "SW1A 1AA" not in out.text

    def test_redacts_postcode_lowercase(self):
        out = deidentify("postcode sw1a 1aa today")
        assert "[POSTCODE]" in out.text

    def test_redacts_uk_phone_07(self):
        out = deidentify("Mobile 07700 900123 logged")
        assert "[PHONE]" in out.text
        assert "07700 900123" not in out.text

    def test_redacts_uk_phone_landline(self):
        out = deidentify("Tel 020 7946 0958 for clinic")
        assert "[PHONE]" in out.text

    def test_redacts_email_address(self):
        out = deidentify("Contact patient.test@example.co.uk soon")
        assert "[EMAIL]" in out.text
        assert "patient.test@example.co.uk" not in out.text

    def test_redacts_date_slash_format(self):
        out = deidentify("DOB 14/03/1985 confirmed")
        assert "[DATE]" in out.text
        assert "14/03/1985" not in out.text

    def test_redacts_date_long_format(self):
        out = deidentify("Reviewed on 14 March 2024 in clinic")
        assert "[DATE]" in out.text


class TestNonRedaction:
    """Clinical content that is not PHI must NOT be redacted, otherwise the
    NER stage loses signal needed for SNOMED coding."""

    @pytest.mark.parametrize(
        "text",
        [
            "Patient reports chest pain and breathlessness",
            "BP 145/92 mmHg recorded today",
            "HbA1c is 58 mmol/mol",
            "Prescribed amlodipine 5mg once daily",
            "History of hypertension and type 2 diabetes",
        ],
    )
    def test_clinical_content_passes_through_unchanged(self, text):
        out = deidentify(text)
        assert out.text == text
        assert out.replacements == []


class TestOrgRedaction:
    """`DEID_LOCAL_ORGS` adds a per-deployment redaction list (GAP-014)."""

    def test_no_orgs_pattern_when_env_empty(self, monkeypatch):
        monkeypatch.delenv("DEID_LOCAL_ORGS", raising=False)
        assert _build_org_pattern() is None

    def test_no_orgs_pattern_when_env_blank(self, monkeypatch):
        monkeypatch.setenv("DEID_LOCAL_ORGS", "  ")
        assert _build_org_pattern() is None

    def test_redacts_configured_org_name(self, monkeypatch):
        monkeypatch.setenv(
            "DEID_LOCAL_ORGS",
            "St Mary's Hospital,City Walk Clinic",
        )
        out = deidentify("Referred from St Mary's Hospital today")
        assert "[ORG]" in out.text
        assert "St Mary's Hospital" not in out.text

    def test_org_redaction_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("DEID_LOCAL_ORGS", "City Walk Clinic")
        out = deidentify("seen at city walk clinic last week")
        assert "[ORG]" in out.text

    def test_org_pattern_orders_longest_first(self, monkeypatch):
        """If two configured names overlap, the longer must match first so
        we don't leave a partial PHI fragment behind."""
        monkeypatch.setenv("DEID_LOCAL_ORGS", "Mary,St Mary's Hospital")
        out = deidentify("transferred from St Mary's Hospital")
        assert "[ORG]" in out.text
        assert "St Mary's" not in out.text


class TestReplacementsLog:
    """`replacements` records every redaction so the caller can audit and,
    if needed, map NER spans back to the original character offsets."""

    def test_returns_deid_result_dataclass(self):
        out = deidentify("hello world")
        assert isinstance(out, DeidResult)
        assert isinstance(out.replacements, list)

    def test_records_original_value_in_replacements(self):
        out = deidentify("NHS 485 777 3456 noted")
        nhs_hits = [r for r in out.replacements if "485" in r[2]]
        assert nhs_hits, f"expected NHS replacement, got {out.replacements}"

    def test_records_replacement_for_each_phi_category(self):
        text = (
            "Mr Smith on 14/03/1985 NHS 485 777 3456 "
            "lives at SW1A 1AA email a@b.co tel 07700 900123"
        )
        out = deidentify(text)
        kinds = {
            "[DATE]": "14/03/1985" in [r[2] for r in out.replacements],
            "[NHS_NO]": any("485" in r[2] for r in out.replacements),
            "[POSTCODE]": "SW1A 1AA" in [r[2] for r in out.replacements],
            "[EMAIL]": any("a@b" in r[2] for r in out.replacements),
            "[PHONE]": any("07700" in r[2] for r in out.replacements),
        }
        missing = [k for k, v in kinds.items() if not v]
        assert not missing, f"missing replacements for {missing}"

    def test_empty_text_produces_empty_result(self):
        out = deidentify("")
        assert out.text == ""
        assert out.replacements == []


class TestIdempotence:
    """Re-running deidentify on already-redacted text must be a no-op."""

    def test_running_twice_is_stable(self):
        once = deidentify("Patient NHS 485 777 3456 at SW1A 1AA")
        twice = deidentify(once.text)
        assert twice.text == once.text
