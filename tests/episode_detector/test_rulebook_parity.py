"""v0 rulebook byte-identical parity with current Python constants.

Atlas trace:
  VT: VT-9D9DDA68 (schema + validator + parity)

These tests fail loudly if a contributor edits a detector constant in
code without regenerating the v0 snapshot. v0 is the frozen baseline;
any deviation from the live Python constants is a deliberate governance
event that must go through a new rulebook version.
"""

from __future__ import annotations

from libs.episode_detector.loader import load_default_bundle
from services.analysis_worker.app.episode_detector_v2 import site_keys as sk
from services.analysis_worker.app.episode_detector_v2.signals import (
    pathway_channel as pc,
)


def test_breast_anchors_match_python_constants():
    bundle = load_default_bundle()
    rb = bundle.get("breast")
    assert rb is not None
    assert set(rb.anchors.suspected_snomed) == set(sk.BREAST_SNOMED_SUSPECTED)
    assert set(rb.anchors.confirmed_snomed) == set(sk.BREAST_SNOMED_CONFIRMED)


def test_breast_code_channel_matches_python_constants():
    rb = load_default_bundle().get("breast")
    assert rb is not None
    cc = rb.signals.code_channel
    assert set(cc.suspected_snomed) == set(sk.BREAST_SNOMED_SUSPECTED)
    assert set(cc.confirmed_snomed) == set(sk.BREAST_SNOMED_CONFIRMED)
    assert set(cc.benign_closure_snomed) == set(sk.BREAST_SNOMED_BENIGN_CLOSURE)


def test_each_site_referral_snomed_matches_registry():
    bundle = load_default_bundle()
    for site in sk.ALL_SITES:
        rb = bundle.get(site)
        assert rb is not None, site
        expected = {
            code for code, mapped in sk.REFERRAL_SNOMED_TO_SITE.items()
            if mapped == site
        }
        assert set(rb.anchors.referral_snomed) == expected, site


def test_each_site_clinic_seen_snomed_matches_registry():
    bundle = load_default_bundle()
    for site in sk.ALL_SITES:
        rb = bundle.get(site)
        assert rb is not None, site
        expected = {
            code for code, mapped in sk.CLINIC_SEEN_SNOMED_TO_SITE.items()
            if mapped == site
        }
        assert set(rb.anchors.clinic_seen_snomed) == expected, site


def test_suspected_site_snomed_registry_round_trips_into_rulebooks():
    bundle = load_default_bundle()
    for site in sk.ALL_SITES:
        rb = bundle.get(site)
        assert rb is not None, site
        expected_suspected = {
            cid for cid, (mapped, intent)
            in sk.SUSPECTED_SITE_SNOMED.items()
            if mapped == site and intent == "suspected"
        }
        expected_confirmed = {
            cid for cid, (mapped, intent)
            in sk.SUSPECTED_SITE_SNOMED.items()
            if mapped == site and intent == "confirmed"
        }
        if site == sk.SITE_BREAST:
            expected_suspected |= set(sk.BREAST_SNOMED_SUSPECTED)
            expected_confirmed |= set(sk.BREAST_SNOMED_CONFIRMED)
        assert (
            set(rb.signals.code_channel.suspected_snomed)
            == expected_suspected
        ), site
        assert (
            set(rb.signals.code_channel.confirmed_snomed)
            == expected_confirmed
        ), site


def test_each_site_pathway_form_types_match_registry():
    bundle = load_default_bundle()
    for site in sk.ALL_SITES:
        rb = bundle.get(site)
        assert rb is not None, site
        expected = {
            key for key, mapped in pc._V0_FORM_TYPE_TO_SITE.items()
            if mapped == site
        }
        assert set(rb.signals.pathway_channel.form_types) == expected, site


def test_each_site_activation_matches_ACTIVATION_registry():
    bundle = load_default_bundle()
    for site in sk.ALL_SITES:
        rb = bundle.get(site)
        assert rb is not None, site
        expected = sk.ACTIVATION[site]
        assert rb.activation.auto_publish == expected.auto_publish, site
        assert rb.activation.suggest == expected.suggest, site
