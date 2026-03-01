from __future__ import annotations

from libs.ner.context_detector import (
    apply_context_detection,
    detect_assertion,
    normalize_situation_lookup,
)


class TestDetectAssertion:

    def test_family_history_prefix(self) -> None:
        text = "FH of dyspepsia (mum and brother)"
        start = text.index("dyspepsia")
        end = start + len("dyspepsia")
        assert detect_assertion(text, start, end) == "family"

    def test_fhx_prefix(self) -> None:
        text = "FHx: diabetes, hypertension"
        start = text.index("diabetes")
        end = start + len("diabetes")
        assert detect_assertion(text, start, end) == "family"

    def test_family_history_long_form(self) -> None:
        text = "Family history of bowel cancer."
        start = text.index("bowel cancer")
        end = start + len("bowel cancer")
        assert detect_assertion(text, start, end) == "family"

    def test_relative_mention_nearby(self) -> None:
        text = "Mother had breast cancer at age 50."
        start = text.index("breast cancer")
        end = start + len("breast cancer")
        assert detect_assertion(text, start, end) == "family"

    def test_no_family_context_returns_present(self) -> None:
        text = "Patient diagnosed with dyspepsia."
        start = text.index("dyspepsia")
        end = start + len("dyspepsia")
        assert detect_assertion(text, start, end) == "present"

    def test_negation_detected(self) -> None:
        text = "No evidence of infection on examination."
        start = text.index("infection")
        end = start + len("infection")
        assert detect_assertion(text, start, end) == "absent"

    def test_negation_scope_covers_slash_separated_list(self) -> None:
        """GP pattern: 'no X/ Y/ Z' means all listed items are negated."""
        text = "No red flags - no weight loss/ haematemesis/ jaundice/ fever/ malaena"
        entities = [
            ("weight loss", text.index("weight loss"), text.index("weight loss") + len("weight loss")),
            ("haematemesis", text.index("haematemesis"), text.index("haematemesis") + len("haematemesis")),
            ("jaundice", text.index("jaundice"), text.index("jaundice") + len("jaundice")),
            ("fever", text.index("fever"), text.index("fever") + len("fever")),
            ("malaena", text.index("malaena"), text.index("malaena") + len("malaena")),
        ]
        for name, start, end in entities:
            assert detect_assertion(text, start, end) == "absent", f"{name} should be absent"

    def test_historical_detected(self) -> None:
        text = "History of previous DVT."
        start = text.index("DVT")
        end = start + len("DVT")
        assert detect_assertion(text, start, end) == "historical"

    def test_uncertainty_detected(self) -> None:
        text = "Possible chest infection."
        start = text.index("chest infection")
        end = start + len("chest infection")
        assert detect_assertion(text, start, end) == "possible"

    def test_family_takes_priority_over_negation(self) -> None:
        text = "FH: no diabetes."
        start = text.index("diabetes")
        end = start + len("diabetes")
        assert detect_assertion(text, start, end) == "family"


class TestApplyContextDetection:

    def test_sets_family_assertion_on_entities(self) -> None:
        text = "FH of dyspepsia (mum and brother)"
        entities = [
            {"text": "dyspepsia", "label": "disorder", "start": 6, "end": 15, "assertion": "present"},
        ]
        apply_context_detection(text, entities)
        assert entities[0]["assertion"] == "family"

    def test_does_not_override_existing_non_present_assertion(self) -> None:
        text = "FH of dyspepsia (mum and brother)"
        entities = [
            {"text": "dyspepsia", "label": "disorder", "start": 6, "end": 15, "assertion": "absent"},
        ]
        apply_context_detection(text, entities)
        assert entities[0]["assertion"] == "absent"

    def test_patient_level_entity_stays_present(self) -> None:
        text = "Patient has dyspepsia."
        entities = [
            {"text": "dyspepsia", "label": "disorder", "start": 12, "end": 21, "assertion": "present"},
        ]
        apply_context_detection(text, entities)
        assert entities[0]["assertion"] == "present"

    def test_situation_entity_gets_normalized_lookup(self) -> None:
        text = "Patient on waiting list for op (9R55.)"
        entities = [
            {"text": "Patient on waiting list for op", "label": "situation", "start": 0, "end": 29, "assertion": "present"},
        ]
        apply_context_detection(text, entities)
        assert entities[0]["normalized"] == "planned procedure"


class TestNormalizeSituationLookup:

    def test_waiting_list(self) -> None:
        assert normalize_situation_lookup("Patient on waiting list for op") == "planned procedure"

    def test_booked_for(self) -> None:
        assert normalize_situation_lookup("Booked for colonoscopy") == "planned procedure"

    def test_referred_for(self) -> None:
        assert normalize_situation_lookup("Referred for MRI") == "referral to service"

    def test_referral_to(self) -> None:
        assert normalize_situation_lookup("Referral to urology") == "referral to service"

    def test_awaiting(self) -> None:
        assert normalize_situation_lookup("Awaiting biopsy results") == "planned procedure"

    def test_2ww_referral(self) -> None:
        assert normalize_situation_lookup("2WW referral for suspected cancer") == "fast track referral"

    def test_no_match_returns_none(self) -> None:
        assert normalize_situation_lookup("Cancer ruled out") is None

    def test_planned(self) -> None:
        assert normalize_situation_lookup("Colonoscopy planned") == "planned procedure"
