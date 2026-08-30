"""Gate 3 D3.1-D3.2 -- structured-first Situation."""

from __future__ import annotations

from libs.sbar.situation_source import (
    ReferralReasonEvidence,
    build_structured_situation,
    reason_evidence_to_dict,
)


def test_prefers_referral_request_reason() -> None:
    result = build_structured_situation(
        referral_request={
            "id": "rr-1",
            "reason": "Suspected gall bladder malignancy.",
            "priority": "urgent",
        },
        referral_reason=None,
        trigger_scoped_letter="Unrelated attachment prose.",
        run_id="run-1",
    )
    assert "gall bladder" in result.headline.lower()
    assert result.source_precedence == ["referral_request.reason"]
    assert result.referral_reason is not None
    assert result.letter_extract is None


def test_specialty_mismatched_reason_loses_to_2ww_form_section() -> None:
    """A stored shoulder reason must not lead a 2WW gynaecology Situation."""
    result = build_structured_situation(
        referral_request={
            "id": "rr-gynae",
            "reason": (
                "left shoulder injury after a fall with inability to "
                "complete range of movement and loud crepitus"
            ),
            "clinic_type": "2WW_GYNAECOLOGY",
            "priority": "TWO_WEEK_WAIT",
        },
        referral_reason=None,
        trigger_scoped_letter="Two Week Wait Referral to Gynaecology",
        form_clinical_section=(
            "Post-menopausal bleeding started in the last 24 hours "
            "after 10 years on HRT"
        ),
    )
    assert result.source_precedence == ["form_clinical_section"]
    assert "shoulder" not in result.headline.lower()
    assert "bleeding" in result.headline.lower()


def test_matching_2ww_reason_still_wins() -> None:
    result = build_structured_situation(
        referral_request={
            "id": "rr-gynae",
            "reason": "Suspected cervical cancer. Yellow vaginal discharge.",
            "clinic_type": "2WW_GYNAECOLOGY",
            "priority": "TWO_WEEK_WAIT",
        },
        referral_reason=None,
        trigger_scoped_letter="Two Week Wait Referral to Gynaecology",
        form_clinical_section="Yellow vaginal discharge for 10 days",
    )
    assert result.source_precedence == ["referral_request.reason"]
    assert "cervical" in result.headline.lower()


def test_absent_pmb_does_not_become_structured_headline() -> None:
    from libs.sbar.situation_headline import headline_from_coded_facts

    headline = headline_from_coded_facts(
        [
            {
                "text": "no pv bleeding",
                "assertion": "absent",
                "term": "Bleeding from vagina (finding)",
                "concept_id": "289530006",
            },
            {
                "text": "vaginal discharge- yellowish",
                "assertion": "present",
                "term": "Vaginal discharge (finding)",
                "concept_id": "271939006",
            },
            {
                "text": "Cervix",
                "assertion": "present",
                "term": "Malignant neoplasm of cervix uteri suspected (situation)",
                "concept_id": "315266007",
            },
            {
                "text": "post menopausal for 1.5yrs",
                "assertion": "present",
                "term": "Postmenopausal state (finding)",
                "concept_id": "76498008",
            },
        ]
    )
    assert headline is not None
    assert "postmenopausal bleeding" not in headline.lower()
    assert "discharge" in headline.lower()
    assert "cervix" in headline.lower() or "cervical" in headline.lower()


def test_persists_referral_reason_evidence_with_provenance() -> None:
    evidence = ReferralReasonEvidence(
        reason_text="Progressive dysphagia.",
        source_type="Chunk",
        source_id="chunk-1",
        chunk_id="chunk-1",
        evidence_text="Reason for referral: progressive dysphagia.",
        run_id="run-1",
    )
    payload = reason_evidence_to_dict(evidence)
    assert payload["chunk_id"] == "chunk-1"
    assert payload["run_id"] == "run-1"
    assert payload["result_version"] == "1.0"
