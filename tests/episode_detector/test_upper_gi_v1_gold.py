"""Upper GI rulebook v1 - gold-patient regression (artefact level).

Gold patient: 4920262426 (upper-GI arm; concurrent lung arm in lung.v1).
Expected: partial match of the patient's ep-manual-* upper-GI rows.

Atlas trace:
  VT: VT-31B7A37B (Upper GI rulebook v1 gold regression on 4920262426)
  VERIFIES: DI-FA3CE229, DI-AC6838DD
"""

from __future__ import annotations

import pytest

from libs.episode_detector.loader import DEFAULTS_DIR, load_rulebook
from libs.episode_detector.rulebook import validate_no_pii


@pytest.fixture(scope="module")
def upper_gi_v1():
    return load_rulebook(DEFAULTS_DIR / "upper_gi.v1.json")


def test_upper_gi_v1_is_auto_eligible(upper_gi_v1):
    assert upper_gi_v1.activation.auto_publish is True
    assert upper_gi_v1.activation.suggest is True


def test_upper_gi_v1_anchors_include_2ww_referral_and_gold_suspected(
    upper_gi_v1,
):
    # Gold: UGI 2WW 276551000000108 (2025-08-12) and dysphagia
    # suspected SNOMED 315273002 (2025-07-14).
    assert "276551000000108" in upper_gi_v1.anchors.referral_snomed
    assert "315273002" in upper_gi_v1.anchors.suspected_snomed


def test_upper_gi_v1_text_channel_catches_dysphagia_pattern(upper_gi_v1):
    patterns = " ".join(upper_gi_v1.signals.text_channel.regex_catalogue)
    # Plan: "text patterns dysphagia / indigestion".
    assert "dysphagia" in patterns
    assert "indigestion" in patterns


def test_upper_gi_v1_ppi_treatment_signal_present(upper_gi_v1):
    # Plan: "treatment signal = PPI medicinal product (108666007)".
    assert "108666007" in upper_gi_v1.signals.treatment_channel.snomed
    patterns = " ".join(
        upper_gi_v1.signals.treatment_channel.regex_catalogue
    )
    assert "proton pump inhibitor" in patterns.lower() or "ppi" in patterns.lower()


def test_upper_gi_v1_pathway_reason_regex_covers_gold_terms(upper_gi_v1):
    # The patient's referral reason captured dysphagia; the reason
    # regex must recognise that so the pathway channel emits a signal
    # even when the form_type field is unset.
    reason_patterns = " ".join(upper_gi_v1.signals.pathway_channel.reason_regex)
    assert "dysphagia" in reason_patterns


def test_upper_gi_v1_cross_site_guard_blocks_concurrent_lung_suspected(
    upper_gi_v1,
):
    # Patient 4920262426 has a concurrent lung episode. The UGI rulebook
    # must NOT pull the lung suspected code 162573006 into the UGI
    # candidate window.
    guard = set(upper_gi_v1.cross_site_guard)
    assert "162573006" in guard   # Lung suspected
    assert "134405005" in guard   # Breast suspected (defensive)


def test_upper_gi_v1_confirmed_and_benign_sets_disjoint(upper_gi_v1):
    confirmed = set(upper_gi_v1.signals.code_channel.confirmed_snomed)
    benign = set(upper_gi_v1.signals.code_channel.benign_closure_snomed)
    assert confirmed.isdisjoint(benign)


def test_upper_gi_v1_version_advances_on_v0(upper_gi_v1):
    v0 = load_rulebook(DEFAULTS_DIR / "upper_gi.v0.json")
    assert v0.activation.auto_publish is False
    assert upper_gi_v1.activation.auto_publish is True
    assert upper_gi_v1.rulebook_version.startswith("v1")


def test_upper_gi_v1_passes_validate_no_pii(upper_gi_v1):
    validate_no_pii(upper_gi_v1)
