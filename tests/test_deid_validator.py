"""Tests for `libs/ner/deid_validator.py`.

Atlas trace:
  DO: DO-8EF2EC20
  DI: DI-2F963FC6

Validates that the strict de-id validator:
  - flags raw patient/encounter IDs that bypass the hashing convention
  - flags exact encounter dates while accepting year-rounded dates
  - flags every PHI pattern category in record `text` and entity text
  - tolerates placeholder tokens (already de-identified)
  - sanitises record metadata into the training-safe form
"""

from __future__ import annotations

from libs.ner.deid_validator import (
    DeIdIssue,
    DeIdValidator,
    sanitise_record_metadata,
)


def _record(**overrides):
    base = {
        "patient_id": "pat_abcdef123456",
        "encounter_id": "enc_xyz",
        "text": "Patient reports headache",
        "entities": [],
        "metadata": {},
    }
    base.update(overrides)
    return base


class TestMetadataChecks:
    def test_clean_record_returns_no_issues(self):
        out = DeIdValidator().check_record(_record())
        assert out == []

    def test_raw_patient_id_is_flagged(self):
        out = DeIdValidator().check_record(_record(patient_id="9876543210"))
        kinds = {i.issue_type for i in out}
        assert "raw_patient_id" in kinds

    def test_raw_encounter_id_is_flagged(self):
        out = DeIdValidator().check_record(
            _record(encounter_id="raw-encounter-uuid")
        )
        kinds = {i.issue_type for i in out}
        assert "raw_encounter_id" in kinds

    def test_doc_prefixed_encounter_id_is_accepted(self):
        out = DeIdValidator().check_record(_record(encounter_id="doc_xyz"))
        assert all(i.issue_type != "raw_encounter_id" for i in out)

    def test_exact_encounter_date_is_flagged(self):
        out = DeIdValidator().check_record(
            _record(metadata={"encounter_date": "2025-04-12"})
        )
        kinds = {i.issue_type for i in out}
        assert "exact_encounter_date" in kinds

    def test_year_rounded_date_is_accepted(self):
        out = DeIdValidator().check_record(
            _record(metadata={"encounter_date": "2025-01-01"})
        )
        assert all(i.issue_type != "exact_encounter_date" for i in out)

    def test_uuid_in_metadata_is_flagged(self):
        out = DeIdValidator().check_record(
            _record(metadata={"trace_id": "550e8400-e29b-41d4-a716-446655440000"})
        )
        kinds = {i.issue_type for i in out}
        assert "uuid_leak" in kinds

    def test_long_numeric_id_in_metadata_is_flagged(self):
        out = DeIdValidator().check_record(
            _record(metadata={"node_id": "1234567890"})
        )
        assert any(i.issue_type == "numeric_id_leak" for i in out)

    def test_encounter_year_metadata_is_allowed(self):
        out = DeIdValidator().check_record(
            _record(metadata={"encounter_year": "2024"})
        )
        assert all(i.issue_type != "numeric_id_leak" for i in out)


class TestTextChecks:
    def test_nhs_number_in_text_is_flagged(self):
        out = DeIdValidator().check_record(_record(text="NHS 485 777 3456"))
        assert any(i.issue_type == "nhs_number" for i in out)

    def test_uk_postcode_in_text_is_flagged(self):
        out = DeIdValidator().check_record(_record(text="lives at SW1A 1AA"))
        assert any(i.issue_type == "postcode" for i in out)

    def test_email_in_text_is_flagged(self):
        out = DeIdValidator().check_record(
            _record(text="email patient@example.org")
        )
        assert any(i.issue_type == "email" for i in out)

    def test_iso_date_in_text_is_flagged(self):
        out = DeIdValidator().check_record(_record(text="seen on 2025-04-12"))
        assert any(i.issue_type == "date_iso" for i in out)

    def test_honorific_name_in_text_is_flagged(self):
        out = DeIdValidator().check_record(_record(text="Mr Smith attended"))
        assert any(i.issue_type == "honorific_name" for i in out)

    def test_placeholders_do_not_trigger_issues(self):
        out = DeIdValidator().check_record(
            _record(text="Patient [PERSON] visited [DATE] at [POSTCODE]")
        )
        assert out == []

    def test_entity_text_is_also_checked(self):
        out = DeIdValidator().check_record(
            _record(
                text="generic clinical note",
                entities=[{"entity_id": "E1", "text": "NHS 485 777 3456"}],
            )
        )
        assert any(
            i.field == "entity.E1.text" and i.issue_type == "nhs_number"
            for i in out
        )


class TestIssueShape:
    def test_to_dict_returns_three_string_fields(self):
        issue = DeIdIssue("text", "nhs_number", "485 777 3456")
        assert issue.to_dict() == {
            "field": "text",
            "issue_type": "nhs_number",
            "detail": "485 777 3456",
        }


class TestSanitiseRecord:
    def test_patient_id_is_hashed_and_removed_from_top_level(self):
        out = sanitise_record_metadata(_record(patient_id="rawpid-123"))
        assert "patient_id" not in out
        assert out["metadata"]["_hashed_patient_id"].startswith("pat_")

    def test_encounter_id_is_hashed_and_removed(self):
        out = sanitise_record_metadata(_record(encounter_id="raw-enc-9"))
        assert "encounter_id" not in out
        assert out["metadata"]["_hashed_encounter_id"].startswith("enc_")

    def test_encounter_date_is_rounded_to_year(self):
        rec = _record(metadata={"encounter_date": "2024-07-09"})
        out = sanitise_record_metadata(rec)
        assert out["metadata"]["encounter_year"] == "2024"
        assert "encounter_date" not in out["metadata"]

    def test_existing_text_passes_through_unchanged(self):
        rec = _record(text="Patient reports headache")
        out = sanitise_record_metadata(rec)
        assert out["text"] == "Patient reports headache"
