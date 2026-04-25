from __future__ import annotations

from libs.ner.span_finder import find_span


def test_find_span_accepts_omitted_read_code_for_lab_observable() -> None:
    sentence = (
        "08:11 - Surgery: Auto-filed Urine creatinine level (XE2qO) "
        "5.5 mmol/L Clinical Information: Reasons for Request: htn review."
    )

    span = find_span(sentence, "Urine creatinine level 5.5 mmol/L")

    assert span is not None
    start, end = span
    assert sentence[start:end] == "Urine creatinine level (XE2qO) 5.5 mmol/L"


def test_find_span_accepts_omitted_read_code_with_range() -> None:
    sentence = (
        "Serum vitamin B12 level (XE2pf) 226 ng/L [211 - 911] "
        "Patients with symptoms suggestive of B12 deficiency may benefit."
    )

    span = find_span(sentence, "Serum vitamin B12 level 226 ng/L [211 - 911]")

    assert span is not None
    start, end = span
    assert sentence[start:end] == (
        "Serum vitamin B12 level (XE2pf) 226 ng/L [211 - 911]"
    )


def test_find_span_does_not_invent_a_code_for_non_measurement_text() -> None:
    sentence = "Patient has chronic kidney disease (stage 3) and hypertension."

    assert find_span(sentence, "chronic kidney disease hypertension") is None
