"""Prostate-urological rulebook v1 - gold-patient regression (artefact level).

Gold patient: 9990001005.
Expected episode: ep-9abc2565f1e8711f, status=completed, ~18 encounters.

Atlas trace:
  VT: VT-426CF21F (Prostate-urological rulebook v1 gold regression on 9990001005)
  VERIFIES: DI-FA3CE229, DI-AC6838DD
"""

from __future__ import annotations

import pytest

from libs.episode_detector.loader import DEFAULTS_DIR, load_rulebook
from libs.episode_detector.rulebook import validate_no_pii


@pytest.fixture(scope="module")
def prostate_v1():
    return load_rulebook(DEFAULTS_DIR / "prostate_urological.v1.json")


def test_prostate_v1_is_auto_eligible(prostate_v1):
    # Plan: "Flip activation to auto_publish: true, suggest: true in the
    # JSON (not in code)." v0 was review-only; v1 is the auto-eligible
    # gold-signed-off rulebook.
    assert prostate_v1.activation.auto_publish is True
    assert prostate_v1.activation.suggest is True


def test_prostate_v1_referral_anchors_include_2ww_and_alt_urological(
    prostate_v1,
):
    refs = set(prostate_v1.anchors.referral_snomed)
    # Gold encounters repeat 2WW urological referrals 2025-08-01/-04/-06.
    assert "276431000000102" in refs
    # Alt urological referral code from the plan.
    assert "199251000000107" in refs


def test_prostate_v1_suspected_anchors_capture_gold_pattern(prostate_v1):
    suspected = set(prostate_v1.anchors.suspected_snomed)
    # Gold pattern: 315268008 prostate suspected 2025-08-01.
    assert "315268008" in suspected
    # Upstream urinary/genitourinary suspected codes that the gold
    # reviewer accepted as part of the prostate episode (not stripped
    # by cross_site_guard because prostate OWNS the urinary concept).
    assert "397657005" in suspected
    # Generic suspected cancer is not prostate-specific; breast 2WW
    # encounters also carry it, so it must not anchor prostate episodes.
    assert "162572001" not in suspected


def test_prostate_v1_psa_is_result_observation(prostate_v1):
    # Plan: "PSA observable 1030791000000100".
    assert (
        "1030791000000100" in prostate_v1.signals.result_channel.observation_snomed
    )


def test_prostate_v1_completed_closure_recognises_gp_letter(prostate_v1):
    # Plan: "closure via outpatient GP letter 801541000000102 with
    # 180-day post-letter quiet window".
    rule = prostate_v1.closure.completed
    assert "snomed:801541000000102" in rule.requires_any_of
    assert rule.and_no_confirmed_within_days == 180


def test_prostate_v1_cross_site_guard_blocks_other_site_suspected(
    prostate_v1,
):
    # Symmetric to breast v1: if a prostate-anchored candidate picks up
    # a suspected-breast / suspected-lung / suspected-UGI / suspected-LGI
    # code, strip it. Prevents the prostate case from capturing a
    # concurrent breast investigation.
    guard = set(prostate_v1.cross_site_guard)
    assert "134405005" in guard   # Breast suspected
    assert "162573006" in guard   # Lung suspected
    assert "162574000" in guard   # Upper GI suspected
    assert "162575004" in guard   # Lower GI suspected


def test_prostate_v1_pathway_form_types_accept_legacy_aliases(prostate_v1):
    form_types = set(prostate_v1.signals.pathway_channel.form_types)
    assert "2ww_prostate_urological" in form_types
    # Legacy aliases preserved from pc._FORM_TYPE_TO_SITE so older
    # referral forms still bind to the prostate rulebook.
    assert "2ww_prostate" in form_types
    assert "2ww_urology" in form_types


def test_prostate_v1_confirmed_and_benign_sets_disjoint(prostate_v1):
    confirmed = set(prostate_v1.signals.code_channel.confirmed_snomed)
    benign = set(prostate_v1.signals.code_channel.benign_closure_snomed)
    assert confirmed.isdisjoint(benign)


def test_prostate_v1_version_advances_on_v0(prostate_v1):
    v0 = load_rulebook(DEFAULTS_DIR / "prostate_urological.v0.json")
    assert v0.activation.auto_publish is False  # v0 was review-only
    assert prostate_v1.activation.auto_publish is True
    assert prostate_v1.rulebook_version.startswith("v1")


def test_prostate_v1_passes_validate_no_pii(prostate_v1):
    validate_no_pii(prostate_v1)
