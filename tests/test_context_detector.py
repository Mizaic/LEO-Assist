from __future__ import annotations

from libs.ner.context_detector import normalize_situation_lookup


class TestNormalizeSituationLookup:

    def test_waiting_list(self) -> None:
        assert normalize_situation_lookup("Patient on waiting list for op") == "planned procedure"

    def test_booked_for(self) -> None:
        assert normalize_situation_lookup("Booked for colonoscopy") == "planned procedure"

    def test_referred_for(self) -> None:
        assert normalize_situation_lookup("Referred for MRI") == "referral to service"

    def test_referral_to(self) -> None:
        assert normalize_situation_lookup("Referral to urology") == "referral to service"

    def test_awaiting_procedure(self) -> None:
        assert normalize_situation_lookup("Awaiting biopsy") == "planned procedure"

    def test_awaiting_results_no_normalisation(self) -> None:
        """'Awaiting results' should not be normalised to 'planned procedure'."""
        assert normalize_situation_lookup("Awaiting blood results") is None

    def test_awaiting_report_no_normalisation(self) -> None:
        assert normalize_situation_lookup("Awaiting report") is None

    def test_2ww_referral(self) -> None:
        assert normalize_situation_lookup("2WW referral for suspected cancer") == "fast track referral"

    def test_no_match_returns_none(self) -> None:
        assert normalize_situation_lookup("Cancer ruled out") is None

    def test_planned_procedure(self) -> None:
        assert normalize_situation_lookup("Planned procedure next month") == "planned procedure"

    def test_planned_pregnancy_no_normalisation(self) -> None:
        """'Planned pregnancy' should not be normalised to 'planned procedure'."""
        assert normalize_situation_lookup("Planned pregnancy") is None

    def test_planned_surgery(self) -> None:
        assert normalize_situation_lookup("Planned surgery for hernia") == "planned procedure"
