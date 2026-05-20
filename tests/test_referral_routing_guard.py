"""VT coverage for referral routing suppression (DI-B5C78811 / UN-89E2AE36)."""

from __future__ import annotations

from libs.ner.referral_routing_guard import (
    is_informational_referral_routing,
    should_keep_referral_span,
    should_suppress_referral_routing_entity,
)
from libs.pipeline.post_processing import run_post_processing


def test_brain_cns_email_routing_suppressed() -> None:
    assert is_informational_referral_routing("Urgent 2WW brain/CNS referral")


def test_brain_cns_email_clinical_kept() -> None:
    assert not is_informational_referral_routing("personality change")
    assert not is_informational_referral_routing("abnormal MRI")
    assert should_keep_referral_span("abnormal MRI")


def test_ng12_neuro_routing_suppressed() -> None:
    assert is_informational_referral_routing("2WW brain/CNS referral")


def test_ng12_neuro_mri_kept() -> None:
    text = "urgent MRI scan of the brain"
    assert should_keep_referral_span(text)
    assert not is_informational_referral_routing(text)


def test_lower_gi_submitted_suppressed() -> None:
    assert is_informational_referral_routing("2WW lower GI referral submitted")


def test_fit_plus_kept() -> None:
    assert not is_informational_referral_routing("FIT+")
    assert not is_informational_referral_routing("FIT-")


def test_letter_boilerplate_suppressed() -> None:
    assert is_informational_referral_routing(
        "refer this patient under the breast suspected cancer pathway"
    )


def test_run_post_processing_drops_routing_entity() -> None:
    entities = [
        {
            "text": "Urgent 2WW brain/CNS referral",
            "label": "procedure",
            "start": 0,
            "end": 29,
            "assertion": "present",
        },
        {
            "text": "personality change",
            "label": "finding",
            "start": 40,
            "end": 58,
            "assertion": "present",
        },
    ]
    encounter = "Urgent 2WW brain/CNS referral for personality change."
    out = run_post_processing(encounter, entities, enable_disorder_gate=False)
    texts = [e["text"] for e in out]
    assert "personality change" in texts
    assert "Urgent 2WW brain/CNS referral" not in texts


def test_should_suppress_entity_dict() -> None:
    assert should_suppress_referral_routing_entity(
        {"text": "2WW referral placed", "label": "procedure"}
    )
    assert not should_suppress_referral_routing_entity(
        {"text": "urgent MRI scan of the brain", "label": "procedure"}
    )
