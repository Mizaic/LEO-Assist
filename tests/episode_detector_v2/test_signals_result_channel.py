"""Tests for episode_detector_v2.signals.result_channel."""

from __future__ import annotations

from datetime import date

from libs.episode_detector.loader import (
    DEFAULTS_DIR,
    load_default_bundle,
    load_rulebook,
    override_sites,
    set_current_bundle,
)
from services.analysis_worker.app.episode_detector_v2.signals.result_channel import (
    extract_result_signals,
)
from services.analysis_worker.app.episode_detector_v2.types import TimelineEvent


def _event(encounter_id: str, text: str) -> TimelineEvent:
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=date(2025, 6, 11),
        event_kind="encounter",
        text_snippet=text,
    )


def test_cyst_of_breast_with_investigation_emits_ruled_out_result_signal():
    event = _event(
        "cyst",
        "Minor: Cyst of breast. Aspiration of breast. "
        "Mammogram - M2. US scan of breast - U2.",
    )

    signals = extract_result_signals([event])

    assert len(signals) == 1
    assert signals[0].site_key == "breast"
    assert signals[0].intent == "ruled_out"
    assert signals[0].channel == "result"


def test_cyst_without_breast_investigation_does_not_close_pathway():
    event = _event("cyst", "History of breast cyst checked previously.")

    assert extract_result_signals([event]) == []


def test_historical_breast_treatment_summary_is_not_positive_result_signal():
    event = _event(
        "history",
        "Problem: Malignant neoplasm of female breast - L invasive ductal "
        "carcinoma ER+ve; WLE + sentinel node Bx 9/5/23; radiotherapy "
        "5 fractions 24/8-31/8/23; tamoxifen. History: hx of breast ca "
        "2 yrs ago, found another lump.",
    )

    assert extract_result_signals([event]) == []


def test_normal_flexible_cystoscopy_closes_urology_pathway():
    prostate_v1 = load_rulebook(DEFAULTS_DIR / "prostate_urological.v1.json")
    set_current_bundle(
        override_sites(
            load_default_bundle(),
            {prostate_v1.site_key: prostate_v1},
        )
    )
    event = _event(
        "normal-cystoscopy",
        "Minor: Haematuria. Flexible cystoscopy (Xa7va) - normal.",
    )

    signals = extract_result_signals([event])

    assert len(signals) == 1
    assert signals[0].site_key == "prostate_urological"
    assert signals[0].intent == "ruled_out"


def test_skin_excision_tumour_free_margin_emits_ruled_out_result_signal():
    event = _event(
        "skin-result",
        "Skin Cancer Follow Up. Histopathology reports noted. "
        "Excision left forearm-compound naevus with moderate atypia; "
        "surgical margin is tumour free. Plan-results letter to patient "
        "and GP. Discharge.",
    )

    signals = extract_result_signals([event])

    assert len(signals) == 1
    assert signals[0].site_key == "skin"
    assert signals[0].intent == "ruled_out"
