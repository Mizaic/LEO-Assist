"""DI-LEO-AI-200: NSS classification rule.

Only explicit NSS surface forms (per the SNOMED guideline synonym
list for concept 1556551000000104) classify text as
'non_site_specific'. Generic cancer terms ("carcinoma",
"neoplasm", "cancer", "fast", etc.) without a clear site signal
must classify as 'unknown' so the episode builder can absorb the
encounter into a temporally-overlapping typed pathway.
"""

from __future__ import annotations

import pytest

from services.analysis_worker.app.analyzers.episode_builder._site_resolution import (
    _extract_condition_key,
    _extract_condition_key_from_anchor,
)


class TestNssExplicitSurfaceForms:
    """Only the canonical NSS surface forms classify as NSS."""

    @pytest.mark.parametrize(
        "text",
        [
            "Fast track referral for suspected cancer due to non-site-specific symptoms",
            "Fast track referral for suspected cancer due to non site specific symptoms",
            "Fast track referral for suspected cancer due to non-site-specific symptoms (procedure)",
            "2WW NSS referral",
            "NSS 2ww referral",
            "Fast track NSS referral",
            "NSS referral",
            "Patient discussed: non-specific symptoms suggestive of cancer",
            "Non specific symptoms - 2WW referred",
        ],
    )
    def test_explicit_nss_phrase_classifies_as_nss(self, text: str):
        assert _extract_condition_key(text) == "non_site_specific"


class TestNssNegativeFalsePositives:
    """Common phrases that previously matched NSS must no longer do so."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Fasting blood test taken", "unknown"),
            ("Patient is fasting before procedure", "unknown"),
            ("Make this a fast turnaround", "unknown"),
            ("Fast track prostate clinic referral", "prostate"),
            ("Carcinoma of unknown primary", "unknown"),
            ("Neoplasm of unspecified site", "unknown"),
            ("Cancer screening discussion", "unknown"),
            ("Suspected malignancy", "unknown"),
            ("Tumour biopsy taken", "unknown"),
            ("Sexual Healthcare (Complex) PRISM Pathway Accessed", "unknown"),
            ("Mental Health Crisis PRISM Pathway Accessed", "unknown"),
            ("Cancer follow-up clinic attended", "unknown"),
            ("Routine oncology surveillance visit", "unknown"),
        ],
    )
    def test_phrase_does_not_match_nss(self, text: str, expected: str):
        assert _extract_condition_key(text) == expected


class TestNssTypedSiteWins:
    """A specific cancer site in the same text must outrank NSS."""

    def test_breast_with_nss_qualifier_classifies_as_breast(self):
        text = "Fast track referral for suspected breast cancer (XaMeC)"
        assert _extract_condition_key(text) == "breast"

    def test_lung_with_fast_token_classifies_as_lung(self):
        text = "Fast track referral for suspected lung cancer (XaMeH)"
        assert _extract_condition_key(text) == "lung"


class TestNssAnchorResolution:
    """_extract_condition_key_from_anchor honours the same rule."""

    def test_anchor_concept_id_for_nss_returns_nss(self):
        anchor = {
            "concept_id": "1556551000000104",
            "concept_name": "Fast track referral for suspected cancer "
            "due to non-site-specific symptoms (procedure)",
        }
        assert _extract_condition_key_from_anchor(anchor) == "non_site_specific"

    def test_anchor_with_explicit_breast_site_key_returns_breast(self):
        anchor = {
            "site_key": "breast",
            "concept_name": "Fast track referral",
        }
        assert _extract_condition_key_from_anchor(anchor) == "breast"

    def test_anchor_with_no_site_signal_returns_unknown(self):
        anchor = {
            "concept_name": "Fast track referral",
        }
        assert _extract_condition_key_from_anchor(anchor) == "unknown"

    def test_anchor_with_generic_cancer_term_returns_unknown(self):
        anchor = {
            "concept_name": "Suspected malignancy",
        }
        assert _extract_condition_key_from_anchor(anchor) == "unknown"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
