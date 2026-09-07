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


def test_form_chrome_lump_does_not_become_headline_when_letter_denies() -> None:
    """A1 tick-box label must not invent a lump the letter denies.

    Atlas: DI-ED65569C / DO-FE774247 / VT-6CA911CF
    """
    from libs.sbar.situation_headline import headline_from_coded_facts
    from libs.sbar.situation_source import build_structured_situation

    facts = [
        {
            "text": "Newly presenting discrete hard breast lump",
            "assertion": "present",
            "term": "Newly presenting discrete hard breast lump",
            "label": "finding",
            "__source": "form_schema_checkbox",
        },
        {
            "text": "lump",
            "assertion": "absent",
            "term": "Lump of breast (finding)",
            "label": "finding",
            "concept_id": "89164003",
        },
    ]
    headline = headline_from_coded_facts(facts)
    if headline:
        assert "discrete hard lump" not in headline.lower()
        assert "hard breast lump" not in headline.lower()

    result = build_structured_situation(
        referral_request={"priority": "TWO_WEEK_WAIT", "clinic_type": "2WW_BREAST"},
        referral_reason=None,
        trigger_scoped_letter="There is no discrete lump in either breast.",
        coded_facts=facts,
    )
    assert "discrete hard lump" not in result.headline.lower()


def test_placeholder_reason_loses_to_coded_exam_lump() -> None:
    """UBRN 000486035327: exam lump must lead, not A1 and not 'no details'.

    Atlas: DI-ED65569C / DO-FE774247 / VT-6CA911CF
    """
    result = build_structured_situation(
        referral_request={
            "id": "000486035327",
            "reason": (
                "Breast symptoms requiring urgent specialist assessment, "
                "with no specific symptom details provided in the referral text."
            ),
            "clinic_type": "2WW_BREAST",
            "priority": "TWO_WEEK_WAIT",
        },
        referral_reason=None,
        trigger_scoped_letter="On examination: small deep palpable left breast lump.",
        form_clinical_section="A1. Newly presenting discrete hard lump [X]",
        coded_facts=[
            {
                "text": "a small deep palpable lump measuring approximately I cm",
                "assertion": "present",
                "term": "Lump of breast (finding)",
                "label": "finding",
                "concept_id": "89164003",
            }
        ],
    )
    low = result.headline.lower()
    assert "lump" in low
    assert "no specific symptom" not in low
    assert "newly presenting discrete hard" not in low
    assert result.source_precedence == ["coded_facts"]


def test_nkda_situation_does_not_beat_hypertrophy() -> None:
    """No-known-allergy is a situation tag, not the referral trigger."""
    from libs.sbar.situation_headline import headline_from_coded_facts

    headline = headline_from_coded_facts(
        [
            {
                "text": "very large breasts",
                "assertion": "present",
                "term": "Hypertrophy of breast (disorder)",
                "label": "disorder",
            },
            {
                "text": "No known allergies",
                "assertion": "present",
                "term": "No known allergy (situation)",
                "label": "situation",
            },
        ]
    )
    assert headline is not None
    assert "hypertrophy" in headline.lower()
    assert "allerg" not in headline.lower()


def test_hypertrophy_outranks_back_pain_for_breast_referral() -> None:
    """UBRN 000486741220: name breast hypertrophy, not musculoskeletal pain."""
    from libs.sbar.situation_headline import headline_from_coded_facts

    headline = headline_from_coded_facts(
        [
            {
                "text": "chronic middle and upper back, neck and shoulder pain",
                "assertion": "present",
                "term": None,
                "label": "finding",
            },
            {
                "text": "Hypertrophy of breast",
                "assertion": "present",
                "term": "Hypertrophy of breast (disorder)",
                "label": "disorder",
                "concept_id": "372281005",
            },
        ]
    )
    assert headline is not None
    assert "hypertrophy" in headline.lower()
    assert "shoulder" not in headline.lower()
    assert "back" not in headline.lower()


def test_vitals_do_not_beat_a_nipple_finding() -> None:
    """Lifestyle and pulse must not outrank the presenting nipple finding."""
    from libs.sbar.situation_headline import headline_from_coded_facts

    headline = headline_from_coded_facts(
        [
            {
                "text": "Pulse regular",
                "assertion": "present",
                "term": "Pulse regular (finding)",
                "label": "finding",
            },
            {
                "text": "Ex-smoker",
                "assertion": "present",
                "term": "Ex-smoker (finding)",
                "label": "finding",
            },
            {
                "text": "sensitive right nipple",
                "assertion": "present",
                "term": "Nipple sensitive (finding)",
                "label": "finding",
            },
        ]
    )
    assert headline is not None
    assert "nipple" in headline.lower()
    assert "pulse" not in headline.lower()
    assert "smoker" not in headline.lower()


def test_nipple_outranks_nonspecific_breast_pain() -> None:
    """UBRN 000486386168: name the nipple finding, not intractable pain."""
    from libs.sbar.situation_headline import headline_from_coded_facts

    headline = headline_from_coded_facts(
        [
            {
                "text": "intractable breast pain",
                "assertion": "present",
                "term": "Intractable breast pain (finding)",
                "label": "finding",
            },
            {
                "text": "sensitive right nipple",
                "assertion": "present",
                "term": "Nipple sensitive (finding)",
                "label": "finding",
            },
        ]
    )
    assert headline is not None
    assert "nipple" in headline.lower()
    assert "pain" not in headline.lower()


def test_placeholder_reason_loses_to_coded_nipple_finding() -> None:
    """UBRN 000486386168: nipple sensitivity must lead, not 'no presenting symptom'."""
    result = build_structured_situation(
        referral_request={
            "id": "000486386168",
            "reason": (
                "Urgent breast referral with no presenting symptom or "
                "clinical concern documented in the referral text."
            ),
            "clinic_type": "2WW_BREAST",
            "priority": "TWO_WEEK_WAIT",
        },
        referral_reason=None,
        trigger_scoped_letter="She reports a sensitive right nipple. There is no lump.",
        coded_facts=[
            {
                "text": "sensitive right nipple",
                "assertion": "present",
                "term": "Nipple sensitive (finding)",
                "label": "finding",
                "concept_id": "247328001",
            },
            {
                "text": "lump",
                "assertion": "absent",
                "term": "Lump of breast (finding)",
                "label": "finding",
                "concept_id": "89164003",
            },
        ],
    )
    low = result.headline.lower()
    assert "nipple" in low
    assert "no presenting symptom" not in low
    assert "lump" not in low
    assert result.source_precedence == ["coded_facts"]


def test_boilerplate_reason_loses_to_coded_nipple_when_clinic_unknown() -> None:
    """In-memory LLM referral reasons must not beat a coded nipple finding."""
    result = build_structured_situation(
        referral_request={
            "id": "000486386168",
            "reason": (
                "Breast referral for symptomatic breast concern on the "
                "urgent suspected cancer pathway."
            ),
            "clinic_type": "",
            "priority": "TWO_WEEK_WAIT",
        },
        referral_reason=None,
        trigger_scoped_letter="She reports a sensitive right nipple.",
        coded_facts=[
            {
                "text": "sensitive right nipple",
                "assertion": "present",
                "term": "Nipple sensitive (finding)",
                "label": "finding",
            }
        ],
    )
    assert "nipple" in result.headline.lower()
    assert result.source_precedence == ["coded_facts"]


def test_placeholder_reason_loses_to_coded_hypertrophy() -> None:
    """UBRN 000486741220: name hypertrophy, not an empty 2WW priority line."""
    result = build_structured_situation(
        referral_request={
            "id": "000486741220",
            "reason": (
                "Referral made for specialist assessment, but no presenting "
                "symptoms or clinical concern are stated in the provided text."
            ),
            "clinic_type": "",
            "priority": "TWO_WEEK_WAIT",
        },
        referral_reason=None,
        trigger_scoped_letter="Referral for breast reduction. Hypertrophy of breast.",
        coded_facts=[
            {
                "text": "Hypertrophy of breast",
                "assertion": "present",
                "term": "Hypertrophy of breast (disorder)",
                "label": "disorder",
                "concept_id": "372281005",
            }
        ],
    )
    low = result.headline.lower()
    assert "hypertrophy" in low
    assert "no presenting" not in low
    assert result.source_precedence == ["coded_facts"]


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


def test_drops_invented_pmb_when_bleeding_is_absent() -> None:
    from libs.sbar.situation_headline import drop_invented_pmb

    text = (
        "This 57-year-old woman is on a two-week-wait gynaecology "
        "pathway for suspected cervical malignancy. "
        "Headline trigger: postmenopausal bleeding."
    )
    out = drop_invented_pmb(
        text,
        present_terms=["Vaginal discharge (finding)"],
        structured_headline="Suspected cervical cancer. Vaginal discharge.",
    )
    assert "postmenopausal bleeding" not in out.lower()
    assert "cervical" in out.lower()


def test_drops_invented_postmenopausal_vaginal_bleeding() -> None:
    """Write-back Situation must not lead on invented PMB wording.

    Atlas: DI-ED65569C / VT-6CA911CF. pv bleeding was absent.
    """
    from libs.sbar.situation_headline import drop_invented_pmb

    text = (
        "This woman is referred on a two-week-wait gynaecology pathway "
        "for postmenopausal vaginal bleeding and suspected cervical cancer."
    )
    out = drop_invented_pmb(
        text,
        present_terms=["Vaginal discharge (finding)"],
        structured_headline="Suspected cervical cancer. Vaginal discharge.",
    )
    assert "postmenopausal" not in out.lower() or "bleeding" not in out.lower()
    assert "cervical" in out.lower() or "discharge" in out.lower()


def test_keeps_pmb_when_it_is_a_present_finding() -> None:
    from libs.sbar.situation_headline import drop_invented_pmb

    text = "Urgent 2WW gynaecology referral for postmenopausal bleeding."
    out = drop_invented_pmb(
        text,
        present_terms=["Postmenopausal bleeding (finding)"],
        structured_headline="Postmenopausal bleeding.",
    )
    assert "postmenopausal bleeding" in out.lower()


def test_drops_invented_nipple_discharge_when_absent() -> None:
    """UBRN 000486386168: do not name discharge the letter denies.

    Atlas: DI-ED65569C / VT-6CA911CF
    """
    from libs.sbar.situation_headline import drop_invented_absent_findings

    text = (
        "This 81-year-old woman needs triage of an urgent two-week-wait "
        "breast clinic referral for persistent unilateral nipple discharge."
    )
    out = drop_invented_absent_findings(
        text,
        absent_terms=["no nipple discharge"],
        present_terms=["sensitive right nipple"],
        structured_headline="sensitive right nipple.",
    )
    assert "discharge" not in out.lower()
    assert "nipple" in out.lower()


def test_drops_copied_empty_reason_when_headline_exists() -> None:
    """UBRN 000486741220: do not copy 'no presenting symptom' over hypertrophy."""
    from libs.sbar.situation_headline import drop_copied_empty_reason

    text = (
        "This 33-year-old woman has a two-week-wait symptomatic breast "
        "referral for specialist assessment. The referral text does not "
        "state any presenting symptom or clinical concern."
    )
    out = drop_copied_empty_reason(
        text,
        structured_headline="Hypertrophy of breast.",
    )
    assert "hypertrophy" in out.lower()
    assert "presenting symptom" not in out.lower()


def test_names_coded_headline_when_llm_omits_the_finding() -> None:
    """UBRN 000486386168: generic 'breast concerns' must still name the nipple."""
    from libs.sbar.situation_headline import prefer_coded_headline

    text = (
        "This 81-year-old woman needs triage of an urgent two-week-wait "
        "breast referral for symptomatic breast concerns."
    )
    out = prefer_coded_headline(
        text,
        structured_headline="sensitive right nipple.",
    )
    assert "nipple" in out.lower()


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


def test_resolved_codes_keep_label_so_hypertrophy_can_lead() -> None:
    """Gate 3 coded facts must keep semantic tag and assertion.

    Atlas: DI-ED65569C / DO-FE774247 / VT-6CA911CF
    """
    from libs.sbar.orchestrator_gate3 import _coded_facts
    from libs.sbar.source_resolver import ResolvedCode
    from libs.sbar.situation_headline import headline_from_coded_facts

    facts = _coded_facts(
        [
            ResolvedCode(
                concept_id="1",
                term="Back pain (finding)",
                semantic_tag="finding",
                assertion="present",
                evidence="chronic shoulder pain",
            ),
            ResolvedCode(
                concept_id="372281005",
                term="Hypertrophy of breast (disorder)",
                semantic_tag="disorder",
                assertion="present",
                evidence="very large breasts",
            ),
        ]
    )
    headline = headline_from_coded_facts(facts)
    assert headline is not None
    assert "hypertrophy" in headline.lower()
    assert facts[1]["label"] == "disorder"
    assert facts[1]["assertion"] == "present"
