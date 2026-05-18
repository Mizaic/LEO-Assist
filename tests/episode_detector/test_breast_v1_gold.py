"""Breast rulebook v1 - gold-patient regression (artefact level).

Gold patient: 9990001002.
Expected episode: ep-3b16d19e1a2a1615, status=closed_benign, 6 encounters.

Atlas trace:
  VT: VT-7F9A700C (Breast rulebook v1 gold regression on 9990001002)
  VERIFIES: DI-FA3CE229, DI-AC6838DD

This VT asserts that the rulebook artefact captures the clinical
pattern that drove the manual reviewer's closed_benign sign-off:

  - 2WW breast referral anchor (276341000000100) present in anchors
  - Second-attendance clinic-seen code (382431000000103) present
  - Ultrasound-normal SNOMED (169254007) in benign closure set
  - Breast ultrasound observation code (47079000) recognised
  - Urinary-system-suspected SNOMED (397657005) explicitly guarded
    against via cross_site_guard
  - Benign closure requires no confirmed SNOMED within 90 days

The dry-run parity assertion against the live graph runs at P6, once
the detector's signal extractors read from the RulebookBundle instead
of module-level constants. v1's artefact-level coverage gate is what
proves the rulebook *captures* the gold pattern; the P6 gate proves
the *detector* executes it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from libs.episode_detector.loader import DEFAULTS_DIR, load_rulebook


BREAST_V1: Path = DEFAULTS_DIR / "breast.v1.json"


@pytest.fixture(scope="module")
def breast_v1():
    return load_rulebook(BREAST_V1)


def test_breast_v1_is_auto_eligible(breast_v1):
    assert breast_v1.activation.auto_publish is True
    assert breast_v1.activation.suggest is True


def test_breast_v1_includes_2ww_referral_anchor(breast_v1):
    assert "276341000000100" in breast_v1.anchors.referral_snomed


def test_breast_v1_includes_repeat_clinic_seen_anchor(breast_v1):
    # Gold: patient 9990001002 had a second fast-track clinic attendance
    # 2025-09-16. The clinic-seen SNOMED has to be in anchors so the
    # evidence aggregator counts the repeat attendance as a signal.
    assert "382431000000103" in breast_v1.anchors.clinic_seen_snomed


def test_breast_v1_ultrasound_normal_is_benign_closure_signal(breast_v1):
    # Gold: ultrasound reported normal 2025-09-01. The benign closure
    # rule must recognise 169254007 as a benign signal.
    assert "169254007" in breast_v1.signals.code_channel.benign_closure_snomed


def test_breast_v1_ultrasound_observation_code_recognised(breast_v1):
    # 47079000 is the ultrasound examination code used by the gold
    # encounter; it must be in the result channel's observation set so
    # the negative-terms scan fires on that encounter's interpretation.
    assert "47079000" in breast_v1.signals.result_channel.observation_snomed


def test_breast_v1_benign_closure_requires_ultrasound_normal(breast_v1):
    rule = breast_v1.closure.benign
    assert "snomed:169254007" in rule.requires_any_of
    assert rule.and_no_confirmed_within_days == 90


def test_breast_v1_urinary_snomed_is_cross_site_guarded(breast_v1):
    # Patient 9990001002 has a stray 397657005 (urinary system suspected)
    # code. It must NOT enter the breast episode -- the cross_site_guard
    # list is the declarative switch that blocks it.
    assert "397657005" in breast_v1.cross_site_guard


def test_breast_v1_confirmed_SNOMEDS_not_in_benign_set(breast_v1):
    confirmed = set(breast_v1.signals.code_channel.confirmed_snomed)
    benign = set(breast_v1.signals.code_channel.benign_closure_snomed)
    assert confirmed.isdisjoint(benign), (
        "Confirmed and benign SNOMED sets must not overlap"
    )


def test_breast_v1_windows_narrower_than_v0(breast_v1):
    # v1 tightens to the NICE NG12 breast diagnostic horizon.
    assert breast_v1.windows.lookback_days <= 365
    assert breast_v1.windows.lookahead_days <= 730


def test_breast_v1_version_advances_on_v0(breast_v1):
    v0 = load_rulebook(DEFAULTS_DIR / "breast.v0.json")
    assert breast_v1.rulebook_version != v0.rulebook_version
    assert breast_v1.rulebook_version.startswith("v1")


def test_breast_v1_screening_pattern_in_catalogue(breast_v1):
    # NHS Breast Screening Programme abnormal recall is a distinct
    # first-presentation pathway: the patient never presents to the GP
    # with symptoms -- the screening programme triggers the episode.
    # The regex_catalogue must recognise this encounter type so the
    # text channel fires even when no symptomatic SNOMED codes are
    # present.
    catalogue = breast_v1.signals.text_channel.regex_catalogue
    screening_patterns = [p for p in catalogue if "Screening Programme" in p]
    assert screening_patterns, (
        "breast.v1 text_channel.regex_catalogue must include an NHS Breast "
        "Screening Programme pattern to detect screening-detected episodes"
    )
    neoplasm_patterns = [p for p in catalogue if "neoplasm screening" in p]
    assert neoplasm_patterns, (
        "breast.v1 text_channel.regex_catalogue must include a 'breast "
        "neoplasm screening abnormal' pattern to match the Read-coded text"
    )


def test_breast_v1_normal_screening_in_exclusion_catalogue(breast_v1):
    # A routine NHS Breast Screening Programme letter reporting a normal
    # result contains "breast" and would fire a diagnosis signal unless
    # explicitly excluded. The exclusion_catalogue suppresses that signal
    # so a normal screening encounter never seeds a breast cancer episode.
    excl = breast_v1.signals.text_channel.exclusion_catalogue
    normal_patterns = [p for p in excl if "normal" in p.lower()]
    assert normal_patterns, (
        "breast.v1 exclusion_catalogue must contain a pattern matching "
        "'breast neoplasm screening normal' to suppress false-positive "
        "episodes from routine NHS Breast Screening Programme normal results"
    )


def test_breast_v1_screening_pattern_in_referral_sent_catalogue(breast_v1):
    # The screening programme notification is the referral trigger for
    # a screening-detected episode. It must fire as referral_sent so
    # the episode_engine LLM receives a context hint for that milestone.
    referral_sent = (
        breast_v1.signals.text_channel.context_role_catalogue.get(
            "referral_sent", ()
        )
    )
    programme_patterns = [p for p in referral_sent if "Screening Programme" in p]
    assert programme_patterns, (
        "breast.v1 referral_sent context catalogue must include an NHS Breast "
        "Screening Programme pattern to surface the screening recall as a "
        "referral_sent context milestone"
    )


def test_breast_v1_passes_validate_no_pii(breast_v1):
    # load_rulebook already runs validate_no_pii, but an explicit
    # acceptance assertion pins the invariant in the gold test so it
    # cannot silently drift.
    from libs.episode_detector.rulebook import validate_no_pii

    validate_no_pii(breast_v1)
