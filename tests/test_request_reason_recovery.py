from __future__ import annotations

from libs.ner.request_reason_recovery import (
    recover_request_reason_entities,
    recover_request_reason_findings,
)


def _by_label(entities: list[dict], label: str) -> list[dict]:
    return [entity for entity in entities if entity.get("label") == label]


def test_recovers_abdo_pain_from_reasons_for_request() -> None:
    text = (
        "Clinical Information: Clinical Details: none "
        "Reasons for Request:      abdo pain."
    )

    out = recover_request_reason_findings(text, [])

    findings = _by_label(out, "finding")
    assert len(findings) == 1
    assert findings[0]["text"] == "abdo pain"
    assert text[findings[0]["start"] : findings[0]["end"]] == "abdo pain"


def test_does_not_recover_unrecognised_request_reason() -> None:
    text = "Reasons for Request:      annual bloods."

    out = recover_request_reason_findings(text, [])

    assert out == []


def test_does_not_duplicate_existing_request_reason_finding() -> None:
    text = "Reasons for Request: abdo pain."
    existing = [{"text": "abdo pain", "label": "finding", "start": 21, "end": 30}]

    out = recover_request_reason_findings(text, existing)

    assert out == existing


def test_recovers_lower_gi_2ww_request_as_suspected_cancer_situation() -> None:
    text = "Clinical Information: Reasons for Request: 2WW LGI."

    out = recover_request_reason_entities(text, [])

    situations = _by_label(out, "situation")
    assert len(situations) == 1
    assert situations[0]["text"] == "2WW LGI"
    assert situations[0]["snomed_concept_id"] == "315274008"
    assert (
        situations[0]["snomed_term"]
        == "Malignant neoplasm of lower gastrointestinal tract suspected (situation)"
    )


def test_recovers_spaced_2ww_request_as_suspected_cancer_situation() -> None:
    text = "Clinical Information: Reasons for Request: for Lower GI 2 WW referral."

    out = recover_request_reason_entities(text, [])

    situations = _by_label(out, "situation")
    assert len(situations) == 1
    assert situations[0]["text"] == "for Lower GI 2 WW referral"
    assert situations[0]["snomed_concept_id"] == "315274008"


def test_recovers_tww_request_as_suspected_cancer_situation() -> None:
    text = "Clinical Information: Reasons for Request: urgent breast TWW bloods."

    out = recover_request_reason_entities(text, [])

    situations = _by_label(out, "situation")
    assert len(situations) == 1
    assert situations[0]["text"] == "urgent breast TWW bloods"
    assert situations[0]["snomed_concept_id"] == "134405005"


def test_recovers_prostate_2ww_request_as_prostate_suspected() -> None:
    text = "Clinical Information: Reasons for Request: Urology 2ww for hard prostate."

    out = recover_request_reason_entities(text, [])

    situations = _by_label(out, "situation")
    assert len(situations) == 1
    assert situations[0]["snomed_concept_id"] == "315268008"


def test_recovers_nss_2ww_request_as_generic_suspected_cancer() -> None:
    text = "Clinical Information: Reasons for Request: 2ww nss bloods."

    out = recover_request_reason_entities(text, [])

    situations = _by_label(out, "situation")
    assert len(situations) == 1
    assert situations[0]["text"] == "2ww nss bloods"
    assert situations[0]["snomed_concept_id"] == "162572001"


def test_recovers_plain_2ww_bloods_as_generic_suspected_cancer() -> None:
    text = "Clinical Information: Reasons for Request: 2ww bloods."

    out = recover_request_reason_entities(text, [])

    situations = _by_label(out, "situation")
    assert len(situations) == 1
    assert situations[0]["text"] == "2ww bloods"
    assert situations[0]["snomed_concept_id"] == "162572001"


def test_recovers_2ww_target_site_before_background_breast_history() -> None:
    text = (
        "Clinical Information: Reasons for Request: Refer re neck - ?2ww neck "
        "as has breast cancer ??relevant ?skin based - hard to be sure."
    )

    out = recover_request_reason_entities(text, [])

    situations = _by_label(out, "situation")
    assert len(situations) == 1
    assert situations[0]["snomed_concept_id"] == "315277001"
