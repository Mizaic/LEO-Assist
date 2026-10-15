"""Word fit between a lookup phrase and the wording a SNOMED concept matched on.

A fulltext hit may only be attached when its wording claims nothing the
phrase did not say ("New onset" must not become "New onset angina"), and
the phrase words it misses are only time or onset words ("abdominal pain
for 6 weeks" may become "Abdominal pain").

Risk R-76DCF7B7 (incorrect SNOMED code used as a confirmed clinical fact).
Phrases are SNOMED wordings or the de-identified hard cases, not patient text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.terminology.word_fit import covers, strip_qualifiers, tokens, word_fit

HARD_CASES = Path(__file__).parent / "fixtures" / "terminology_sim" / "hard_cases.json"

STRIPPED = {
    "onset_abdo_hyphen": "abdominal pain",
    "onset_abdo": "abdominal pain",
    "onset_abdo_of": "Abdominal pain",
    "onset_constipation": "constipation",
    "onset_diarrhoea": "diarrhoea",
    "recent_onset_diarrhoea": "diarrhoea",
    "recent_onset_cibh": "change in bowel habit",
    "onset_rectal_bleeding": "rectal bleeding",
    "keep_onset_angina": "angina",
    "keep_newly_diagnosed_diabetes": "diagnosed diabetes",
    "duration_diarrhoea": "diarrhoea",
    "duration_abdo": "abdominal pain",
    "plain_cibh": "Change in bowel habit",
    "plain_weight_loss": "Unexplained weight loss",
    "plain_ida": "Iron deficiency anaemia",
    "plain_blood_in_stool": "Blood in stool",
    "nocode_new_onset": "",
    "nocode_onset": "onset",
}


def _hard_cases():
    return json.loads(HARD_CASES.read_text(encoding="utf-8"))


class TestTokens:
    def test_drops_stop_words_and_simple_plurals(self):
        assert tokens("Pain in the joints") == {"pain", "joint"}

    def test_keeps_double_s_and_short_words(self):
        assert tokens("Loss of gas") == {"loss", "gas"}

    def test_ies_plural_matches_y_singular(self):
        assert tokens("allergies") == tokens("allergy")
        assert covers("no known drug allergies", "No known drug allergy")


class TestWordFit:
    def test_new_onset_does_not_cover_new_onset_angina(self):
        fit = word_fit("New onset", "New onset angina")
        assert fit.precision < 1.0
        assert not covers("New onset", "New onset angina")

    def test_abdominal_pain_for_6_weeks_misses_only_qualifiers(self):
        fit = word_fit("abdominal pain for 6 weeks", "Abdominal pain")
        assert fit.precision == 1.0
        assert fit.missing_are_qualifiers
        assert covers("abdominal pain for 6 weeks", "Abdominal pain")

    def test_diarrhoea_for_3_months_does_not_cover_gestation_period(self):
        assert not covers("diarrhoea for 3 months", "Gestation period, 3 months")

    def test_no_shared_word_is_not_a_fit(self):
        assert not word_fit("onset", "Angina").missing_are_qualifiers
        assert not covers("onset", "Angina")

    def test_missing_clinical_word_is_not_covered(self):
        assert not covers("New onset rectal bleeding", "Rectal")
        assert not covers("New onset rectal bleeding", "Rectal bleeding, painful")
        assert not covers("Rectal bleeding", "Bleeding")


class TestMeasurementUnits:
    def test_blood_pressure_reading_with_mmhg_covers_blood_pressure(self):
        assert covers("blood pressure | 130 / 80 mmHg", "Blood pressure")

    def test_weight_in_kg_covers_weight(self):
        assert covers("weight: 78 kg", "Weight")

    def test_bmi_in_kg_per_m2_covers_bmi(self):
        assert covers("BMI: 25.43 kg/m2", "BMI")

    def test_unit_letter_without_a_number_is_not_a_unit(self):
        # "L" here means left, not litres.
        assert not covers("L scapula", "Scapula")

    def test_unit_does_not_excuse_a_missing_clinical_word(self):
        assert not covers("sitting blood pressure 130/80 mmHg", "Blood pressure")


class TestStripQualifiers:
    def test_every_hard_case_has_an_expected_stripped_form(self):
        assert {c["case_id"] for c in _hard_cases()} == set(STRIPPED)

    @pytest.mark.parametrize("case", _hard_cases(), ids=lambda c: c["case_id"])
    def test_strips_onset_and_duration_wording(self, case):
        assert strip_qualifiers(case["phrase"]) == STRIPPED[case["case_id"]]
