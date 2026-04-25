"""Unit tests for the runtime lab-triple recovery layer.

Covers VT-LEO-AI-154 test cases. Each case asserts that
``recover_lab_triples`` adds the missing procedure / observable_entity /
finding spans for a real UK primary-care lab line, without ever
modifying or duplicating existing entities.

The example line in the production defect report is the first test case:

    Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] - Outside reference range
"""

from __future__ import annotations

import pytest

from libs.ner.lab_triple_recovery import recover_lab_triples

# -- helpers ------------------------------------------------------------------


def _by_label(entities: list[dict], label: str) -> list[dict]:
    return [e for e in entities if e.get("label") == label]


def _texts(entities: list[dict]) -> list[str]:
    return [str(e.get("text", "")) for e in entities]


def _is_recovered(entity: dict) -> bool:
    return bool(entity.get("_recovered_lab_triple"))


# -- core: production defect line --------------------------------------------


def test_recovers_full_triple_for_reticulocyte_observation_line() -> None:
    """The exact line in the user's defect report.

    Expected after recovery:
      - procedure: "Reticulocyte count - observation"
      - observable_entity: "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80]"
      - finding: full line including " - Outside reference range"
    """
    text = (
        "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] "
        "- Outside reference range"
    )
    out = recover_lab_triples(text, [])

    procedures = _by_label(out, "procedure")
    observables = _by_label(out, "observable_entity")
    findings = _by_label(out, "finding")

    assert len(procedures) == 1
    assert len(observables) == 1
    assert len(findings) == 1

    assert procedures[0]["text"] == "Reticulocyte count - observation"
    assert observables[0]["text"].endswith("10^9/L [20 - 80]")
    assert "Outside reference range" in findings[0]["text"]

    for ent in (procedures[0], observables[0], findings[0]):
        assert _is_recovered(ent)
        assert ent["assertion"] == "present"
        assert text[ent["start"] : ent["end"]] == ent["text"]


# -- existing entities are preserved and not duplicated ----------------------


def test_does_not_duplicate_existing_procedure_span() -> None:
    text = "Reticulocyte count (42X..) 96 10^9/L [20 - 80]"
    existing = [
        {
            "text": "Reticulocyte count",
            "label": "procedure",
            "start": 0,
            "end": 18,
            "assertion": "present",
        }
    ]
    out = recover_lab_triples(text, existing)

    procedures = _by_label(out, "procedure")
    assert len(procedures) == 1
    assert procedures[0] is existing[0]

    observables = _by_label(out, "observable_entity")
    assert len(observables) == 1
    assert observables[0]["text"].endswith("10^9/L [20 - 80]")


def test_input_entity_list_is_not_mutated() -> None:
    text = "Mean cell haemoglobin level (XE2pb) 32.1 pg [27 - 32] - Outside reference range"
    existing = [{"text": "MCH", "label": "procedure", "start": 0, "end": 3}]
    snapshot = list(existing)
    _ = recover_lab_triples(text, existing)
    assert existing == snapshot


# -- lenient mode: no Read code present --------------------------------------


def test_lenient_recovers_triple_for_colon_separated_line() -> None:
    """Colon-separated lab line without a Read/CTV3 code in parens."""
    text = "Atypical Lymphocytes: 0.70 x10^9/l; Outside reference range"
    out = recover_lab_triples(text, [])

    assert len(_by_label(out, "procedure")) == 1
    assert len(_by_label(out, "observable_entity")) == 1
    assert len(_by_label(out, "finding")) == 1
    assert _by_label(out, "procedure")[0]["text"] == "Atypical Lymphocytes"


def test_lenient_recovers_triple_for_dash_separated_line() -> None:
    """Dash-separated lab line without a Read code, no interpretation."""
    text = "Serum sodium level - 138 mmol/L"
    out = recover_lab_triples(text, [])
    assert len(_by_label(out, "procedure")) == 1
    assert len(_by_label(out, "observable_entity")) == 1
    assert _by_label(out, "finding") == []


# -- multi-line scanning -----------------------------------------------------


def test_recovers_triples_on_every_line_of_multi_line_block() -> None:
    text = (
        "Full Blood Count results:\n"
        "Reticulocyte count (42X..) 96 10^9/L [20 - 80] - Outside reference range\n"
        "Mean cell volume (42A..) 100 fL [80 - 99] - Outside reference range\n"
        "Serum vitamin D level (XE2e7) 64 nmol/L\n"
    )
    out = recover_lab_triples(text, [])

    procs = _texts(_by_label(out, "procedure"))
    assert "Reticulocyte count" in procs
    assert "Mean cell volume" in procs
    assert "Serum vitamin D level" in procs

    findings = _texts(_by_label(out, "finding"))
    assert any("Outside reference range" in f for f in findings)


def test_recovers_adjacent_vitals_on_single_line() -> None:
    text = (
        "Pulse regular (XM02J) "
        "Oxygen saturation at periphery (X770D) 97 % "
        "O/E - weight (22A..) 83 Kg (? 13 st 1 lb) "
        "Body mass index - observation (22K..) 27.73 Kg/m\u00b2"
    )
    out = recover_lab_triples(text, [])

    procs = _texts(_by_label(out, "procedure"))
    observables = _texts(_by_label(out, "observable_entity"))

    assert "Oxygen saturation at periphery" in procs
    assert "O/E - weight" in procs
    assert "Body mass index - observation" in procs
    assert "Pulse regular" not in procs
    assert "Oxygen saturation at periphery (X770D) 97 %" in observables
    assert "O/E - weight (22A..) 83 Kg" in observables
    assert "Body mass index - observation (22K..) 27.73 Kg/m\u00b2" in observables


def test_recovers_lab_name_after_auto_filed_prefix() -> None:
    text = (
        "09:15 - Surgery: Auto-filed   "
        "Prostate-specific antigen level (XE25C) 0.57 ng/ml [0 - 4.5]"
    )
    out = recover_lab_triples(text, [])

    assert _by_label(out, "procedure")[0]["text"] == "Prostate-specific antigen level"
    assert _by_label(out, "observable_entity")[0]["text"] == (
        "Prostate-specific antigen level (XE25C) 0.57 ng/ml [0 - 4.5]"
    )


def test_recovers_mojibake_bmi_unit() -> None:
    text = "Body mass index - observation (22K..) 27.73 Kg/m\u00ef\u00bf\u00bd"
    out = recover_lab_triples(text, [])

    assert _by_label(out, "observable_entity")[0]["text"] == text


def test_recovers_digitless_x_prefixed_egfr_code() -> None:
    text = "eGFR using creatinine (CKD-EPI) per 1.73 square metres " "(XacUK) 71 mL/min"
    out = recover_lab_triples(text, [])

    assert _by_label(out, "procedure")[0]["text"] == (
        "eGFR using creatinine (CKD-EPI) per 1.73 square metres"
    )
    assert _by_label(out, "observable_entity")[0]["text"] == text


def test_recovers_digitless_x_prefixed_adjusted_calcium_code() -> None:
    text = "Serum adjusted calcium concentration (Xabpk) 2.36 mmol/L [2.12 - 2.51]"
    out = recover_lab_triples(text, [])

    assert _by_label(out, "procedure")[0]["text"] == (
        "Serum adjusted calcium concentration"
    )
    assert _by_label(out, "observable_entity")[0]["text"] == text


def test_recovers_name_only_lab_profile_as_procedure_only() -> None:
    text = "Bone profile (44Z2.)"
    out = recover_lab_triples(text, [])

    assert _by_label(out, "procedure")[0]["text"] == "Bone profile"
    assert _by_label(out, "observable_entity") == []
    assert _by_label(out, "finding") == []


def test_recovers_name_only_function_tests_as_procedure_only() -> None:
    text = "Liver function tests (X77WP)"
    out = recover_lab_triples(text, [])

    assert _by_label(out, "procedure")[0]["text"] == "Liver function tests"
    assert _by_label(out, "observable_entity") == []
    assert _by_label(out, "finding") == []


def test_does_not_recover_non_profile_name_only_code() -> None:
    text = "Pulse regular (XM02J)"
    out = recover_lab_triples(text, [])

    assert _by_label(out, "procedure") == []
    assert _by_label(out, "observable_entity") == []


# -- false-positive guards ---------------------------------------------------


def test_prose_paragraph_is_not_treated_as_lab() -> None:
    text = (
        "The patient reports a 3-month history of fatigue and night sweats, "
        "with intermittent palpitations rated 5 out of 10 in severity."
    )
    out = recover_lab_triples(text, [])
    assert _by_label(out, "procedure") == []
    assert _by_label(out, "observable_entity") == []
    assert _by_label(out, "finding") == []


def test_long_paragraph_is_skipped() -> None:
    """Paragraph-length lines (>240 chars) are never treated as lab rows."""
    text = "Atypical Lymphocytes: 0.70 x10^9/l " + ("padding text " * 30)
    out = recover_lab_triples(text, [])
    assert _by_label(out, "procedure") == []


def test_drug_brand_name_in_parens_not_treated_as_lab() -> None:
    """Drug names in parens lack a digit and must not be misread as a code."""
    text = "Patient prescribed Amlodipine (Istin) 5 mg daily"
    out = recover_lab_triples(text, [])
    assert _by_label(out, "procedure") == []


def test_non_medical_unit_does_not_trigger() -> None:
    """A number followed by a non-medical word must not match."""
    text = "Patient walked 200 metres before chest pain started"
    out = recover_lab_triples(text, [])
    assert _by_label(out, "observable_entity") == []


def test_empty_text_returns_unchanged_list() -> None:
    assert recover_lab_triples("", []) == []
    assert recover_lab_triples(
        "", [{"text": "x", "label": "finding", "start": 0, "end": 1}]
    ) == [{"text": "x", "label": "finding", "start": 0, "end": 1}]


# -- offsets and idempotency -------------------------------------------------


def test_recovered_offsets_index_correctly_in_encounter_text() -> None:
    """Every recovered span's text must be the exact substring at its offsets."""
    text = (
        "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] "
        "- Outside reference range"
    )
    out = recover_lab_triples(text, [])
    for ent in out:
        if not _is_recovered(ent):
            continue
        assert text[ent["start"] : ent["end"]] == ent["text"]


def test_running_recovery_twice_is_idempotent() -> None:
    text = "Mean cell volume (42A..) 100 fL [80 - 99] - Outside reference range"
    once = recover_lab_triples(text, [])
    twice = recover_lab_triples(text, once)
    assert len(once) == len(twice)


# -- parametrised real gold-data shapes --------------------------------------


@pytest.mark.parametrize(
    "text,expected_labels",
    [
        (
            "Plasma C-reactive protein level (XE2dy) < 5 mg/L [< 10]",
            {"procedure", "observable_entity"},
        ),
        (
            "Serum vitamin D level (XE2e7) 64 nmol/L",
            {"procedure", "observable_entity"},
        ),
        (
            "Haemoglobin A1c level (X772q) 5.6 % [4 - 5.9]",
            {"procedure", "observable_entity"},
        ),
        (
            "Serum bilirubin level (44E..) 9 umol/L [< 21] - Abnormal result",
            {"procedure", "observable_entity", "finding"},
        ),
    ],
)
def test_recovers_expected_label_set_on_real_gold_examples(
    text: str, expected_labels: set[str]
) -> None:
    out = recover_lab_triples(text, [])
    found = {str(e.get("label")) for e in out if _is_recovered(e)}
    assert found == expected_labels
