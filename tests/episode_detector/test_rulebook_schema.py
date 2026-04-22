"""Hermetic tests for the SiteRulebook schema, loader, and PII validator.

Atlas trace:
  VT: VT-9D9DDA68 (rulebook schema + validator verification)
  VT: VT-(loader parity, see tests/test_rulebook_parity.py)
"""

from __future__ import annotations

import json

import pytest

from libs.episode_detector import (
    RulebookBundle,
    RulebookPiiError,
    RulebookSchemaVersionError,
    SiteRulebook,
    validate_no_pii,
)
from libs.episode_detector.loader import (
    build_bundle_from_rulebooks,
    clear_current_bundle,
    current_bundle,
    load_default_bundle,
    override_sites,
    set_current_bundle,
)
from libs.episode_detector.rulebook import (
    Activation,
    Anchors,
    CodeChannel,
    Closure,
    ClosureRule,
    ResultChannel,
    ScorerWeights,
    Signals,
    TextChannel,
    TierThresholds,
    TreatmentChannel,
    Windows,
    from_mapping,
)


# ----------------------------------------------------------------------
# Schema round-trip
# ----------------------------------------------------------------------


def _minimal_rulebook() -> SiteRulebook:
    return SiteRulebook(
        site_key="breast",
        rulebook_version="v0-test",
        anchors=Anchors(
            referral_snomed=("276341000000100",),
            confirmed_snomed=("254837009",),
        ),
        activation=Activation(auto_publish=True, suggest=True),
    )


def test_round_trip_preserves_every_field():
    rb = _minimal_rulebook()
    rebuilt = SiteRulebook.from_json(rb.to_json())
    assert rebuilt == rb


def test_unknown_schema_version_raises():
    data = json.loads(_minimal_rulebook().to_json())
    data["schema_version"] = "99.0.0"
    with pytest.raises(RulebookSchemaVersionError):
        from_mapping(data)


def test_defaults_ship_every_site():
    bundle = load_default_bundle()
    expected = {
        "breast", "upper_gi", "lung", "lower_gi", "gynae", "head_neck",
        "haematology", "skin", "prostate_urological", "brain_cns",
    }
    assert set(bundle.sites) == expected


def test_defaults_breast_is_auto_eligible():
    bundle = load_default_bundle()
    breast = bundle.get("breast")
    assert breast is not None
    assert breast.activation.auto_publish is True
    assert breast.activation.suggest is True


def test_defaults_non_breast_is_review_only():
    bundle = load_default_bundle()
    for site_key in bundle.sites:
        if site_key == "breast":
            continue
        rb = bundle.get(site_key)
        assert rb is not None
        assert rb.activation.auto_publish is False, (
            f"{site_key} should be review-only in v0"
        )


def test_bundle_get_or_disabled_is_failsafe():
    bundle = RulebookBundle()
    rb = bundle.get_or_disabled("nonexistent_site")
    assert rb.site_key == "nonexistent_site"
    assert rb.activation.auto_publish is False
    assert rb.activation.suggest is False


def test_bundle_key_lookup_normalises_case_and_whitespace():
    bundle = load_default_bundle()
    assert bundle.get("  BREAST  ") is not None
    assert bundle.get("Breast") is not None


# ----------------------------------------------------------------------
# PII validator -- planted-PII tests
# ----------------------------------------------------------------------


def test_validate_no_pii_accepts_clean_rulebook():
    rb = _minimal_rulebook()
    validate_no_pii(rb)


def test_validate_no_pii_rejects_10_digit_nhs_number_in_term():
    rb = SiteRulebook(
        site_key="breast",
        rulebook_version="v0-test",
        signals=Signals(
            result_channel=ResultChannel(
                investigation_terms=("patient 4920262426 seen",),
            ),
        ),
    )
    with pytest.raises(RulebookPiiError, match="7\\+ digit run"):
        validate_no_pii(rb)


def test_validate_no_pii_rejects_nhs_number_marker_in_text():
    rb = SiteRulebook(
        site_key="breast",
        rulebook_version="v0-test",
        signals=Signals(
            text_channel=TextChannel(
                regex_catalogue=("nhs number missing",),
            ),
        ),
    )
    with pytest.raises(RulebookPiiError, match="identifier marker"):
        validate_no_pii(rb)


def test_validate_no_pii_rejects_iso_date_in_positive_term():
    rb = SiteRulebook(
        site_key="breast",
        rulebook_version="v0-test",
        signals=Signals(
            result_channel=ResultChannel(
                positive_terms=("biopsy on 2025-07-14",),
            ),
        ),
    )
    with pytest.raises(RulebookPiiError, match="YYYY-MM-DD date"):
        validate_no_pii(rb)


def test_validate_no_pii_rejects_long_free_text():
    # 250-character string - way longer than any real regex pattern or
    # clinical term. Treated as probable copied PHI.
    giant = "a " * 130
    rb = SiteRulebook(
        site_key="breast",
        rulebook_version="v0-test",
        signals=Signals(
            text_channel=TextChannel(regex_catalogue=(giant,)),
        ),
    )
    with pytest.raises(RulebookPiiError, match="exceeds"):
        validate_no_pii(rb)


def test_validate_no_pii_accepts_snomed_ids_in_anchor_fields():
    rb = SiteRulebook(
        site_key="breast",
        rulebook_version="v0-test",
        anchors=Anchors(
            referral_snomed=("276341000000100", "199251000000107"),
            confirmed_snomed=("1701000119104", "254837009"),
        ),
    )
    validate_no_pii(rb)


def test_validate_no_pii_rejects_snomed_field_with_short_digits():
    rb = SiteRulebook(
        site_key="breast",
        rulebook_version="v0-test",
        anchors=Anchors(referral_snomed=("12345",)),
    )
    with pytest.raises(RulebookPiiError, match="6-18"):
        validate_no_pii(rb)


def test_validate_no_pii_accepts_closure_string_references():
    # "result.negative_terms" is a dotted reference string -- legal in
    # closure rules and must not be rejected as PII.
    rb = SiteRulebook(
        site_key="breast",
        rulebook_version="v0-test",
        closure=Closure(
            benign=ClosureRule(
                requires_any_of=("result.negative_terms", "snomed:266569009"),
                and_no_confirmed_within_days=90,
            ),
        ),
    )
    validate_no_pii(rb)


# ----------------------------------------------------------------------
# Loader / process-wide bundle
# ----------------------------------------------------------------------


def test_set_and_clear_current_bundle_round_trips():
    try:
        custom = build_bundle_from_rulebooks([_minimal_rulebook()])
        set_current_bundle(custom)
        assert current_bundle() is custom
    finally:
        clear_current_bundle()


def test_current_bundle_lazy_loads_defaults_when_uninitialised():
    clear_current_bundle()
    try:
        bundle = current_bundle()
        assert bundle.get("breast") is not None
    finally:
        clear_current_bundle()


def test_override_sites_replaces_only_named_sites():
    base = load_default_bundle()
    replacement = SiteRulebook(
        site_key="breast",
        rulebook_version="challenger-1",
    )
    merged = override_sites(base, {"breast": replacement})
    assert merged.get("breast") is replacement
    assert merged.get("lung") == base.get("lung")


def test_build_bundle_from_rulebooks_rejects_pii():
    bad = SiteRulebook(
        site_key="breast",
        rulebook_version="v0-test",
        signals=Signals(
            result_channel=ResultChannel(
                investigation_terms=("patient 4920262426",),
            ),
        ),
    )
    with pytest.raises(RulebookPiiError):
        build_bundle_from_rulebooks([bad])
