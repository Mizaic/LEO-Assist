"""Tests for v2 detector milestone-link inference.

Atlas trace:
  DI: DI-8A5FCF4F
"""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.milestone_inference import (
    SUPPORTED_MILESTONE_TYPES,
    add_same_day_referral_sent_encounter_ids,
    infer_benign_presentation_encounter_ids,
    infer_contextual_encounter_ids,
    infer_milestone_links,
    infer_walkback_encounter_ids,
    prune_duplicate_same_day_referral_encounter_ids,
    prune_weak_breast_context_encounter_ids,
)
from services.analysis_worker.app.episode_detector_v2.types import (
    ResolvedEpisode,
    TimelineEvent,
)


def _event(encounter_id: str, occurred_on: date, text: str) -> TimelineEvent:
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=occurred_on,
        event_kind="encounter",
        text_snippet=text,
        coded_entities=(),
    )


def _episode(*encounter_ids: str, site_key: str = "breast") -> ResolvedEpisode:
    return ResolvedEpisode(
        episode_id="ep",
        site_key=site_key,
        encounter_ids=list(encounter_ids),
        start_date=date(2025, 3, 10),
        end_date=None,
        suspected_site=site_key,
        role="diagnosis",
        intent="confirmed",
        status="open",
        confidence_tier="auto",
        needs_human_review=False,
        review_reasons=[],
        vote_count=1,
        supporting_signals=[],
        alternatives_considered=[],
        generator_consensus=["diagnosis_anchored"],
    )


def test_infers_multiple_supported_milestones_per_encounter():
    event = _event(
        "gp",
        date(2025, 3, 10),
        "History: F2F review. Breast lump. Examination: breast exam. "
        "Plan: 2ww breast referral.",
    )

    links = infer_milestone_links(_episode("gp"), [event])

    assert {(link.encounter_id, link.milestone_type) for link in links} == {
        ("gp", "first_presentation"),
        ("gp", "referral"),
    }
    assert all(link.milestone_type in SUPPORTED_MILESTONE_TYPES for link in links)


def test_referral_admin_waiting_for_information_is_referral_sent():
    event = _event(
        "admin",
        date(2025, 3, 10),
        "Choice and booking enhanced services administration. "
        "Hospital Fast track referral for suspected breast cancer updated: "
        "Waiting For Information. Patient awaiting OPD appt.: Yes 2ww breast.",
    )

    links = infer_milestone_links(_episode("admin"), [event])

    assert [link.milestone_type for link in links] == ["referral_sent"]


def test_head_neck_waiting_for_information_is_referral_sent():
    event = _event(
        "head-neck-admin",
        date(2025, 5, 2),
        "Fast track referral for suspected head and neck cancer. "
        "Choice and booking enhanced services administration. 2WW. "
        "Patient awaiting OPD appt.: Yes Head & Neck. "
        "Hospital Fast track referral for suspected head and neck cancer "
        "updated: Waiting For Information.",
    )

    links = infer_milestone_links(_episode("head-neck-admin"), [event])

    assert [link.milestone_type for link in links] == ["referral_sent"]


def test_head_neck_prism_questionnaire_started_is_referral_admin():
    event = _event(
        "head-neck-prism",
        date(2025, 5, 1),
        "- PRISM 2WW Head and Neck - questionnaire started. "
        "Fast track referral for suspected head and neck cancer. "
        "PRISM Pathway & Referral Impl SysteM V3. "
        "2WW Head & Neck Pathway accessed. "
        "2WW Head and Neck PRISM to Ms Sheila Redfern. "
        "Outbound referral.",
    )

    links = infer_milestone_links(_episode("head-neck-prism"), [event])

    assert [link.milestone_type for link in links] == [
        "referral_sent",
        "referral_admin",
    ]


def test_breast_prism_questionnaire_started_is_referral_admin():
    event = _event(
        "breast-prism",
        date(2025, 3, 26),
        "- PRISM 2WW Breast Female - questionnaire started. "
        "Fast track referral for suspected breast cancer. "
        "PRISM Pathway & Referral Impl SysteM V3. "
        "2WW Breast Female Referral Pathway/Breast Clinic accessed. "
        "Outbound referral. 2WW Breast Female PRISM to Unknown.",
    )

    links = infer_milestone_links(_episode("breast-prism"), [event])

    assert [link.milestone_type for link in links] == [
        "referral_sent",
        "referral_admin",
    ]


def test_same_day_duplicate_referral_sent_prefers_prism_admin_row():
    events = [
        _event(
            "prism",
            date(2025, 5, 15),
            "- PRISM 2WW Breast Female - questionnaire started. "
            "Fast track referral for suspected breast cancer. "
            "PRISM Pathway & Referral Impl SysteM V3. "
            "2WW Breast Female Referral Pathway/Breast Clinic accessed.",
        ),
        _event(
            "duplicate",
            date(2025, 5, 15),
            "Fast track referral for suspected breast cancer. "
            "Choice and booking enhanced services administration. "
            "Patient awaiting OPD appt.: Yes 2ww breast.",
        ),
    ]

    links = infer_milestone_links(_episode("prism", "duplicate"), events)

    assert [
        (link.encounter_id, link.milestone_type)
        for link in links
        if link.milestone_type in {"referral_sent", "referral_admin"}
    ] == [("prism", "referral_sent"), ("prism", "referral_admin")]


def test_same_day_duplicate_referral_sent_prunes_candidate_membership():
    events = [
        _event(
            "prism",
            date(2025, 5, 15),
            "- PRISM 2WW Breast Female - questionnaire started. "
            "Fast track referral for suspected breast cancer. "
            "PRISM Pathway & Referral Impl SysteM V3.",
        ),
        _event(
            "duplicate",
            date(2025, 5, 15),
            "Fast track referral for suspected breast cancer. "
            "Choice and booking enhanced services administration. "
            "Patient awaiting OPD appt.: Yes 2ww breast.",
        ),
    ]

    assert prune_duplicate_same_day_referral_encounter_ids(
        site_key="breast",
        candidate_encounter_ids=["prism", "duplicate"],
        timeline=events,
    ) == ["prism"]


def test_add_same_day_referral_sent_adds_admin_row_for_pathway_day():
    events = [
        _event("presentation", date(2025, 3, 10), "Plan: 2ww breast referral."),
        _event(
            "admin",
            date(2025, 3, 10),
            "Fast track referral for suspected breast cancer. "
            "Patient awaiting OPD appt.: Yes 2ww breast.",
        ),
    ]

    assert add_same_day_referral_sent_encounter_ids(
        site_key="breast",
        candidate_encounter_ids=["presentation"],
        timeline=events,
    ) == ["presentation", "admin"]


def test_prune_weak_breast_context_removes_unrelated_postnatal_history():
    events = [
        _event(
            "breast-pathway",
            date(2025, 9, 1),
            "Seen in fast track suspected breast cancer clinic.",
        ),
        _event(
            "postnatal",
            date(2025, 10, 2),
            "6-8 Week Postnatal Maternity Check. "
            "Unable to latch on to breast for feeding.",
        ),
    ]

    assert prune_weak_breast_context_encounter_ids(
        site_key="breast",
        candidate_encounter_ids=["breast-pathway", "postnatal"],
        timeline=events,
    ) == ["breast-pathway"]


def test_outpatient_date_awaiting_biopsy_is_referral_admin_not_diagnostics():
    event = _event(
        "awaiting-biopsy",
        date(2025, 5, 13),
        "2WW Date of First outpatient appointment: 07 Apr 2025 Breast. "
        "Awaiting needle biopsy.",
    )

    links = infer_milestone_links(_episode("awaiting-biopsy"), [event])

    assert [link.milestone_type for link in links] == ["referral_admin"]


def test_letrozole_commenced_is_treatment_started_not_outcome_letter():
    event = _event(
        "letrozole",
        date(2025, 5, 19),
        "Drug Review Reconciliation. Reconcilliation source: Breast clinic "
        "letter 28/04/25. New repeat medication: letrozole. Comments: pt "
        "commenced on letrozole 2.5mg od by breast surgeon.",
    )

    links = infer_milestone_links(_episode("letrozole"), [event])

    assert [link.milestone_type for link in links] == ["treatment_started"]
    assert links[0].treatment_type == "endocrine_therapy"


def test_hormone_treatment_side_effect_is_treatment_toxicity():
    event = _event(
        "hot-flushes",
        date(2025, 6, 19),
        "History: Has Breast Ca on letrazole. Complaining of hot flushes "
        "since starting letrazole.",
    )

    links = infer_milestone_links(_episode("hot-flushes"), [event])

    assert {link.milestone_type for link in links} == {
        "related_gp_visit",
        "treatment_toxicity",
    }


def test_cancer_care_review_is_not_diagnosis_confirmed():
    event = _event(
        "care-review",
        date(2025, 9, 24),
        "Problem: Malignant tumour of breast. History: Cancer care review "
        "and general catch up given recent events. Confirmed breast cancer. "
        "Main issue is medication induced menopausal hot flushing.",
    )

    links = infer_milestone_links(_episode("care-review"), [event])

    assert {link.milestone_type for link in links} == {
        "related_gp_visit",
        "treatment_toxicity",
    }


def test_head_neck_fast_track_clinic_seen_is_first_seen():
    event = _event(
        "head-neck-seen",
        date(2025, 7, 7),
        "Seen in fast track suspected head and neck cancer clinic (XaPya).",
    )

    links = infer_milestone_links(
        _episode("head-neck-seen", site_key="head_neck"),
        [event],
    )

    assert [link.milestone_type for link in links] == ["first_seen"]


def test_head_neck_retrospective_seen_field_is_first_seen():
    event = _event(
        "head-neck-seen-admin",
        date(2025, 7, 14),
        "2WW Seen in 2WW Clinic?: Seen in fast track suspected head and "
        "neck cancer clinic (XaPya) 07 Jul 2025.",
    )

    links = infer_milestone_links(
        _episode("head-neck-seen-admin", site_key="head_neck"),
        [event],
    )

    assert [link.milestone_type for link in links] == ["first_seen"]


def test_breast_retrospective_seen_field_is_first_seen():
    event = _event(
        "breast-seen-admin",
        date(2025, 2, 28),
        "2WW Seen in 2WW Clinic?: Seen in fast track suspected breast "
        "cancer clinic (XaPyQ) 16 Feb 2025.",
    )

    links = infer_milestone_links(_episode("breast-seen-admin"), [event])

    assert [link.milestone_type for link in links] == ["first_seen"]


def test_head_neck_occipital_lymph_node_is_benign_closure():
    event = _event(
        "occipital-node",
        date(2025, 7, 7),
        "Minor: Occipital lymph node (X753K) (New Episode). "
        "Occipital lymph node (X753K).",
    )

    links = infer_milestone_links(
        _episode("occipital-node", site_key="head_neck"),
        [event],
    )

    assert [link.milestone_type for link in links] == ["benign_closure"]


def test_head_neck_followup_disruption_is_not_first_presentation():
    event = _event(
        "neck-followup",
        date(2025, 6, 9),
        "History: Planned review following Derm A+G outcome. "
        "Reviewed other issues. Re lump on neck - taxi failed to collect "
        "her for appt so rescheduled for July 1st. "
        "Plan: Ongoing support offered. Is planning on going ahead with "
        "breast surgery.",
    )

    links = infer_milestone_links(
        _episode("neck-followup", site_key="head_neck"),
        [event],
    )

    assert {link.milestone_type for link in links} == {
        "care_obstruction",
        "related_gp_visit",
    }


def test_neck_followup_with_breast_surgery_is_not_breast_first_presentation():
    event = _event(
        "breast-followup",
        date(2025, 6, 9),
        "History: Planned review following Derm A+G outcome. "
        "Re lump on neck - taxi failed to collect her for appt so rescheduled. "
        "Is planning on going ahead with breast surgery.",
    )

    links = infer_milestone_links(_episode("breast-followup"), [event])

    assert {link.milestone_type for link in links} == {
        "care_obstruction",
        "related_gp_visit",
    }


def test_normal_breast_ultrasound_is_benign_closure():
    event = _event(
        "normal-us",
        date(2025, 9, 1),
        "US scan of breast - R - normal.",
    )

    links = infer_milestone_links(_episode("normal-us"), [event])

    assert {link.milestone_type for link in links} == {
        "benign_closure",
        "specialist_diagnostics",
    }


def test_historical_normal_mammogram_does_not_close_current_referral():
    event = _event(
        "presentation",
        date(2025, 1, 27),
        "Problem: Breast lump detected by self-examination. "
        "History: felt lump left breast today. Mammogram normal 1 year ago.",
    )

    links = infer_milestone_links(_episode("presentation"), [event])

    assert "benign_closure" not in {link.milestone_type for link in links}


def test_lipoma_of_breast_is_benign_closure():
    event = _event(
        "lipoma",
        date(2025, 2, 16),
        "Minor: Lipoma of breast (Xa0F5) (New Episode). "
        "US scan of breast (585C.) (New Episode).",
    )

    links = infer_milestone_links(_episode("lipoma"), [event])

    assert "benign_closure" in {link.milestone_type for link in links}


def test_cyst_of_breast_is_benign_closure():
    event = _event(
        "cyst",
        date(2025, 6, 11),
        "Minor: Cyst of breast (XaYQ7) (New Episode). "
        "Aspiration of breast (Xa3qz) (New Episode). "
        "Mammogram (537..) - M2. US scan of breast (585C.) - U2.",
    )

    links = infer_milestone_links(_episode("cyst"), [event])

    assert "benign_closure" in {link.milestone_type for link in links}


def test_generic_breast_correspondence_is_supporting_not_outcome_letter():
    event = _event(
        "letter",
        date(2025, 9, 1),
        "Surgery: Medical Secretary. Breast to Woodbrook Medical Centre.",
    )

    links = infer_milestone_links(_episode("letter"), [event])

    assert [link.milestone_type for link in links] == ["related_correspondence"]


def test_generic_med3_without_breast_context_is_not_related_gp_visit():
    event = _event(
        "med3",
        date(2025, 10, 1),
        "eMED3 new statement issued, not fit for work. Diagnosis: viral illness.",
    )

    links = infer_milestone_links(_episode("med3"), [event])

    assert [link.milestone_type for link in links] == ["related_correspondence"]


def test_benign_closure_can_use_earlier_breast_lump_presentation():
    events = [
        _event(
            "presentation",
            date(2025, 3, 13),
            "History: found a breast lump yesterday. Examination: breast examined.",
        ),
        _event(
            "normal-us",
            date(2025, 9, 1),
            "US scan of breast - R - normal.",
        ),
    ]

    ids = infer_benign_presentation_encounter_ids(
        site_key="breast",
        candidate_encounter_ids=["presentation", "normal-us"],
        intent="ruled_out",
        boundary_end=date(2025, 9, 1),
        timeline=events,
    )

    assert ids == ["presentation"]


def test_staging_and_treatment_context_use_ui_supported_vocabulary():
    events = [
        _event(
            "node",
            date(2025, 6, 4),
            "Major: Metastasis to lymph node - macrometastasis. "
            "Biopsy of sentinel lymph node.",
        ),
        _event(
            "chemo-plan",
            date(2025, 7, 22),
            "History: Starts chemo on Saturday.",
        ),
        _event(
            "chemo-start",
            date(2025, 8, 13),
            "Major: Chemotherapy.",
        ),
        _event(
            "bloods",
            date(2025, 10, 15),
            "Phlebotomy Service. Consultation comment: Pre Chemo.",
        ),
    ]

    links = infer_milestone_links(
        _episode("node", "chemo-plan", "chemo-start", "bloods"),
        events,
    )

    by_encounter = {link.encounter_id: set() for link in links}
    for link in links:
        by_encounter[link.encounter_id].add(link.milestone_type)
    assert by_encounter["node"] == {
        "diagnosis_confirmed",
        "specialist_diagnostics",
    }
    assert by_encounter["chemo-plan"] == {"treatment_planned"}
    assert by_encounter["chemo-start"] == {"treatment_started"}
    assert by_encounter["bloods"] == {
        "primary_care_investigations",
        "treatment_monitoring",
    }
    treatment_types = {
        (link.encounter_id, link.milestone_type): link.treatment_type for link in links
    }
    assert treatment_types[("chemo-plan", "treatment_planned")] == "chemotherapy"
    assert treatment_types[("chemo-start", "treatment_started")] == "chemotherapy"
    assert treatment_types[("bloods", "treatment_monitoring")] == "chemotherapy"
    assert all(link.milestone_type in SUPPORTED_MILESTONE_TYPES for link in links)


def test_chemo_side_effects_use_treatment_toxicity_context():
    event = _event(
        "toxicity",
        date(2025, 10, 23),
        "Currently undergoing chemotherapy treatment and struggling with "
        "fatigue and other side effects.",
    )

    links = infer_milestone_links(_episode("toxicity"), [event])

    assert [link.milestone_type for link in links] == ["treatment_toxicity"]
    assert links[0].treatment_type == "chemotherapy"


def test_chemo_started_is_distinct_treatment_started():
    event = _event(
        "chemo-started",
        date(2024, 10, 17),
        "History: under oncology - chemo started end of Sept 24 - "
        'Ca Left breast "going thru chemo".',
    )

    links = infer_milestone_links(_episode("chemo-started"), [event])

    by_type = {link.milestone_type: link for link in links}
    assert by_type["treatment_started"].treatment_type == "chemotherapy"


def test_surgery_treatment_started_has_surgery_type():
    event = _event(
        "surgery",
        date(2024, 7, 4),
        "Wide local excision of breast lesion. "
        "Block dissection of axillary lymph nodes.",
    )

    links = infer_milestone_links(_episode("surgery"), [event])

    treatment = [link for link in links if link.milestone_type == "treatment_started"]
    assert treatment[0].treatment_type == "surgery"


def test_lymphoedema_follow_up_is_not_treatment_started():
    event = _event(
        "lymph",
        date(2025, 8, 21),
        "Lymphoedema Clinic. Lymphoedema to left arm and hand following "
        "treatment for Breast cancer.",
    )

    links = infer_milestone_links(_episode("lymph"), [event])

    assert [link.milestone_type for link in links] == ["related_specialist_visit"]


def test_generic_axillary_metastasis_can_join_breast_context():
    event = _event(
        "node",
        date(2024, 5, 31),
        "Ultrasound guided biopsy - Axillary lymph nodes. "
        "Major: Metastasis to lymph node - Ipsilateral axillary.",
    )

    ids = infer_contextual_encounter_ids(
        site_key="breast",
        candidate_encounter_ids=["node"],
        timeline=[event],
    )

    assert ids == ["node"]


def test_hrt_screening_background_does_not_join_breast_context():
    event = _event(
        "hrt",
        date(2024, 12, 13),
        "Hormone replacement therapy review. HRT questionnaire. "
        "Breast screening up to date: Yes. Family history of breast cancer: No.",
    )

    ids = infer_contextual_encounter_ids(
        site_key="breast",
        candidate_encounter_ids=["hrt"],
        timeline=[event],
    )

    assert ids == []


def test_diagnosis_walkback_finds_uncoded_metastatic_precursors():
    events = [
        _event(
            "back-pain",
            date(2025, 1, 21),
            "History: right lower back pain and flank pain. Urgent care centre.",
        ),
        _event(
            "unknown-primary",
            date(2025, 2, 27),
            "Major: Metastasis to bone of unknown primary. Hypercalcaemia.",
        ),
        _event(
            "breast-diagnosis",
            date(2025, 3, 24),
            "Major: Infiltrating duct carcinoma of breast.",
        ),
    ]

    ids = infer_walkback_encounter_ids(
        site_key="breast",
        anchor_event_id="breast-diagnosis",
        generator="diagnosis_anchored",
        intent="confirmed",
        timeline=events,
    )

    assert ids == ["back-pain", "unknown-primary"]


def test_walkback_requires_diagnosis_anchor_and_metastatic_bridge():
    events = [
        _event(
            "back-pain",
            date(2025, 1, 21),
            "History: right lower back pain and flank pain. Urgent care centre.",
        ),
        _event(
            "breast-diagnosis",
            date(2025, 3, 24),
            "Major: Infiltrating duct carcinoma of breast.",
        ),
    ]

    assert (
        infer_walkback_encounter_ids(
            site_key="breast",
            anchor_event_id="breast-diagnosis",
            generator="site_cohort_anchored",
            intent="confirmed",
            timeline=events,
        )
        == []
    )
    assert (
        infer_walkback_encounter_ids(
            site_key="breast",
            anchor_event_id="breast-diagnosis",
            generator="diagnosis_anchored",
            intent="confirmed",
            timeline=events,
        )
        == []
    )


def test_walkback_events_get_reviewable_milestones():
    events = [
        _event(
            "back-pain",
            date(2025, 1, 21),
            "History: right lower back pain and flank pain. Urgent care centre.",
        ),
        _event(
            "unknown-primary",
            date(2025, 2, 27),
            "Major: Metastasis to bone of unknown primary. Hypercalcaemia.",
        ),
    ]

    links = infer_milestone_links(_episode("back-pain", "unknown-primary"), events)
    by_encounter = {link.encounter_id: set() for link in links}
    for link in links:
        by_encounter[link.encounter_id].add(link.milestone_type)

    assert by_encounter["back-pain"] == {"first_presentation"}
    assert by_encounter["unknown-primary"] == {"diagnosis_confirmed"}
