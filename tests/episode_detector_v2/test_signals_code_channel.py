"""Tests for episode_detector_v2.signals.code_channel.

Atlas trace:
  DI: DI-8A5FCF4F
"""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.signals.code_channel import (
    extract_code_signals,
)
from services.analysis_worker.app.episode_detector_v2.types import TimelineEvent


def _evt(encounter_id="enc-1", codes=()):
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=date(2024, 3, 15),
        event_kind="encounter",
        coded_entities=tuple(codes),
    )


def test_breast_confirmed_concept_emits_confirmed_signal():
    evt = _evt(codes=[{"concept_id": "254837009", "display_name": "Malignant"}])
    signals = extract_code_signals([evt])
    assert len(signals) == 1
    assert signals[0].channel == "code"
    assert signals[0].site_key == "breast"
    assert signals[0].intent == "confirmed"
    assert signals[0].confidence >= 0.9


def test_backdated_problem_list_breast_diagnosis_is_not_confirmation_signal():
    evt = TimelineEvent(
        encounter_id="enc-1",
        occurred_on=date(2025, 3, 26),
        event_kind="encounter",
        text_snippet=(
            "Fast track referral for suspected breast cancer. "
            "Major: Invasive carcinoma of breast - lobular."
        ),
        coded_entities=(
            {
                "concept_id": "713609000",
                "display_name": "Invasive carcinoma of breast (disorder)",
                "source": "major_text_cancer_backfill",
                "evidence": "Major: Invasive carcinoma of breast - lobular",
            },
        ),
        raw={"encounter_flags": "This event was back-dated and entered on: 24 Sep 2025"},
    )

    assert extract_code_signals([evt]) == []


def test_backdated_breast_diagnosis_with_biopsy_context_is_confirmation_signal():
    evt = TimelineEvent(
        encounter_id="enc-1",
        occurred_on=date(2024, 5, 31),
        event_kind="encounter",
        text_snippet=(
            "Ultrasound guided biopsy - Axillary lymph nodes. "
            "Major: Metastasis to lymph node - Ipsilateral axillary."
        ),
        coded_entities=(
            {
                "concept_id": "254837009",
                "display_name": "Malignant neoplasm of breast (disorder)",
                "source": "major_text_cancer_backfill",
                "evidence": "Major: Malignant tumour of breast",
            },
        ),
        raw={"encounter_flags": "This event was back-dated and entered on: 04 Jul 2024"},
    )

    signals = extract_code_signals([evt])

    assert len(signals) == 1
    assert signals[0].site_key == "breast"
    assert signals[0].intent == "confirmed"


def test_axillary_metastatic_lymph_node_signal_confirms_breast_context():
    evt = _evt(
        codes=[
            {
                "concept_id": "94392001",
                "display_name": "Metastatic malignant neoplasm to lymph node",
                "evidence": (
                    "Major: Metastasis to lymph node - Ipsilateral axillary"
                ),
            }
        ]
    )

    signals = extract_code_signals([evt])

    assert len(signals) == 1
    assert signals[0].site_key == "breast"
    assert signals[0].intent == "confirmed"


def test_non_axillary_metastatic_lymph_node_is_not_breast_signal():
    evt = _evt(
        codes=[
            {
                "concept_id": "94392001",
                "display_name": "Metastatic malignant neoplasm to lymph node",
                "evidence": "Metastasis to lymph node",
            }
        ]
    )

    assert extract_code_signals([evt]) == []


def test_infiltrating_duct_carcinoma_legacy_code_confirms_breast():
    evt = _evt(
        codes=[
            {
                "concept_id": "999999999",
                "display_name": "Infiltrating duct carcinoma",
                "evidence": "Infiltrating duct carcinoma (BB91.)",
            }
        ]
    )

    signals = extract_code_signals([evt])

    assert len(signals) == 1
    assert signals[0].site_key == "breast"
    assert signals[0].intent == "confirmed"


def test_cancer_care_review_problem_list_is_not_confirmation_signal():
    evt = TimelineEvent(
        encounter_id="enc-1",
        occurred_on=date(2025, 9, 24),
        event_kind="encounter",
        text_snippet=(
            "Problem: Invasive carcinoma of breast - lobular. "
            "History: Cancer care review and general catch up."
        ),
        coded_entities=(
            {
                "concept_id": "713609000",
                "display_name": "Invasive carcinoma of breast (disorder)",
                "source": "deterministic_cancer_diagnosis_coder",
                "evidence": "Problem: Invasive carcinoma of breast - lobular",
            },
        ),
    )

    assert extract_code_signals([evt]) == []


def test_breast_suspected_concept_emits_suspected_signal():
    evt = _evt(codes=[{"concept_id": "134405005"}])
    signals = extract_code_signals([evt])
    assert signals[0].intent == "suspected"


def test_bad_breast_code_with_neck_2ww_evidence_routes_to_head_neck():
    evt = _evt(
        codes=[
            {
                "concept_id": "134405005",
                "display_name": "Malignant neoplasm of breast suspected (situation)",
                "evidence": (
                    "Refer re neck - ?2ww neck as has breast cancer "
                    "??relevant ?skin based - hard to be sure"
                ),
            }
        ]
    )

    signals = extract_code_signals([evt])

    assert len(signals) == 1
    assert signals[0].site_key == "head_neck"
    assert signals[0].intent == "suspected"


def test_unknown_concept_emits_no_signal():
    evt = _evt(codes=[{"concept_id": "999999999"}])
    signals = extract_code_signals([evt])
    assert signals == []


def test_negated_assertion_overrides_intent_to_ruled_out():
    evt = _evt(
        codes=[{"concept_id": "254837009", "assertion": "negated"}]
    )
    signals = extract_code_signals([evt])
    assert signals[0].intent == "ruled_out"
    assert signals[0].confidence >= 0.85


def test_emits_lung_confirmed_signal_for_registered_lung_snomed():
    """Stub-site fail-safe: lung is not auto-eligible but the code
    channel still emits a signal so the coverage check sees the
    encounter and flags it for human review.
    """
    evt = _evt(codes=[{"concept_id": "363358000", "display_name": "Malignant lung"}])
    signals = extract_code_signals([evt])
    assert len(signals) == 1
    assert signals[0].site_key == "lung"
    assert signals[0].intent == "confirmed"


def test_emits_upper_gi_suspected_signal_for_registered_ugi_snomed():
    evt = _evt(codes=[{"concept_id": "162574000", "display_name": "Suspected UGI ca"}])
    signals = extract_code_signals([evt])
    assert len(signals) == 1
    assert signals[0].site_key == "upper_gi"
    assert signals[0].intent == "suspected"


def test_emits_head_neck_referral_signal_for_registered_2ww_snomed():
    evt = _evt(
        codes=[
            {
                "concept_id": "280521000000108",
                "display_name": (
                    "Fast track referral for suspected head and neck cancer "
                    "(procedure)"
                ),
            }
        ]
    )

    signals = extract_code_signals([evt])

    assert len(signals) == 1
    assert signals[0].site_key == "head_neck"
    assert signals[0].role == "referral"
    assert signals[0].intent == "suspected"


def test_truly_unknown_cancer_concept_still_emits_no_signal():
    evt = _evt(codes=[{"concept_id": "111111111"}])
    assert extract_code_signals([evt]) == []
