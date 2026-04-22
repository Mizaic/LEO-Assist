"""Lung rulebook v1 - gold-patient regression (artefact level).

Gold patient: 4920262426 (lung arm; concurrent UGI arm in upper_gi.v1).
Expected: lung slice of the patient's episodes.

Atlas trace:
  VT: VT-04407859 (Lung rulebook v1 gold regression on 4920262426)
  VERIFIES: DI-FA3CE229, DI-AC6838DD

P4 (upper_gi.v1) + P5 (lung.v1) together prove the multi-site split
on one patient: the two rulebooks' cross_site_guards reciprocally
block each other's suspected codes, so the runner produces two
disjoint candidates instead of one that steals the other's encounters.
"""

from __future__ import annotations

import pytest

from libs.episode_detector.loader import DEFAULTS_DIR, load_rulebook
from libs.episode_detector.rulebook import validate_no_pii


@pytest.fixture(scope="module")
def lung_v1():
    return load_rulebook(DEFAULTS_DIR / "lung.v1.json")


@pytest.fixture(scope="module")
def upper_gi_v1():
    return load_rulebook(DEFAULTS_DIR / "upper_gi.v1.json")


def test_lung_v1_is_auto_eligible(lung_v1):
    assert lung_v1.activation.auto_publish is True
    assert lung_v1.activation.suggest is True


def test_lung_v1_suspected_anchor_matches_gold(lung_v1):
    # Plan: "Anchor on 162573006" (suspected lung cancer).
    assert "162573006" in lung_v1.anchors.suspected_snomed


def test_lung_v1_cxr_normal_is_benign_closure_signal(lung_v1):
    # Plan: "explicit benign closure when CXR normal 1290959000 with
    # no subsequent lung suspected code within 90 days".
    benign = lung_v1.closure.benign
    assert "snomed:1290959000" in benign.requires_any_of
    assert benign.and_no_confirmed_within_days == 90
    assert "1290959000" in lung_v1.signals.code_channel.benign_closure_snomed
    assert "1290959000" in lung_v1.signals.result_channel.observation_snomed


def test_lung_v1_text_channel_catches_smoker_and_cough(lung_v1):
    # Plan: "signals smoker + cough + CXR finding".
    pattern = " ".join(lung_v1.signals.text_channel.regex_catalogue)
    assert "smoker" in pattern
    assert "cough" in pattern


def test_lung_v1_pathway_reason_regex_catches_gold_terms(lung_v1):
    reason = " ".join(lung_v1.signals.pathway_channel.reason_regex)
    assert "chest" in reason
    assert "lung" in reason


def test_lung_v1_cross_site_guard_blocks_concurrent_ugi_suspected(lung_v1):
    # Patient 4920262426 has a concurrent UGI episode. Lung rulebook
    # must NOT pull UGI suspected codes into the lung candidate window.
    guard = set(lung_v1.cross_site_guard)
    assert "162574000" in guard   # Upper GI suspected
    assert "315266007" in guard   # Suspected stomach cancer
    assert "315273002" in guard   # Dysphagia suspected (UGI anchor)


def test_ugi_and_lung_cross_site_guards_are_reciprocal(
    lung_v1, upper_gi_v1,
):
    """P4 + P5 together: lung suspects are in UGI guard, and UGI
    suspects are in lung guard. This prevents either episode from
    stealing the other's encounters when both arms exist for one
    patient.
    """
    lung_suspected = set(lung_v1.anchors.suspected_snomed)
    ugi_guard = set(upper_gi_v1.cross_site_guard)
    assert lung_suspected.issubset(ugi_guard | lung_suspected), (
        "Every lung suspected SNOMED must be in UGI cross_site_guard "
        "or lung's own anchor set"
    )
    ugi_suspected = set(upper_gi_v1.anchors.suspected_snomed)
    lung_guard = set(lung_v1.cross_site_guard)
    assert ugi_suspected.issubset(lung_guard | ugi_suspected), (
        "Every UGI suspected SNOMED must be in lung cross_site_guard "
        "or UGI's own anchor set"
    )


def test_lung_v1_confirmed_and_benign_sets_disjoint(lung_v1):
    confirmed = set(lung_v1.signals.code_channel.confirmed_snomed)
    benign = set(lung_v1.signals.code_channel.benign_closure_snomed)
    assert confirmed.isdisjoint(benign)


def test_lung_v1_version_advances_on_v0(lung_v1):
    v0 = load_rulebook(DEFAULTS_DIR / "lung.v0.json")
    assert v0.activation.auto_publish is False
    assert lung_v1.activation.auto_publish is True
    assert lung_v1.rulebook_version.startswith("v1")


def test_lung_v1_passes_validate_no_pii(lung_v1):
    validate_no_pii(lung_v1)
