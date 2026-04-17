"""VT-LEO-AI-153: cancer-site classification from gold-mined surface forms.

Verifies match_cancer_site, the canonical-key contract, the noise filter,
and that _extract_condition_key_from_anchor prefers an explicit site_key.
"""

from __future__ import annotations

import pytest

from services.analysis_worker.app.analyzers.cancer_site_terms import (
    CANCER_SITE_TERMS,
    match_cancer_site,
)
from services.analysis_worker.app.analyzers.episode_builder._site_resolution import (
    _PATHWAY_GROUP_KEYS,
    _PATHWAY_TO_SPECIFIC,
    _SITE_MAP,
    _extract_condition_key_from_anchor,
)


def _canonical_keys() -> set[str]:
    keys = {key for _kw, key in _SITE_MAP} | set(_PATHWAY_GROUP_KEYS)
    keys |= set(_PATHWAY_TO_SPECIFIC.keys())
    for sub in _PATHWAY_TO_SPECIFIC.values():
        keys |= set(sub)
    return keys | {"non_site_specific", "unknown", "other"}


_CANONICAL_KEYS: set[str] = _canonical_keys()


def test_specific_cancer_text_yields_breast_key() -> None:
    """VT-153-TC-001"""
    text = (
        "Fast track referral for suspected breast cancer; PRISM 2WW. "
        "DCIS query, breast lump on left side."
    )
    result = match_cancer_site(text)
    assert result is not None, "expected a match"
    site, hits = result
    assert site == "breast"
    assert hits >= 1


def test_highest_hit_site_wins_on_mixed_text() -> None:
    """VT-153-TC-002 -- a single incidental organ mention is outweighed."""
    text = (
        "Patient has incidental note re breast in family history. "
        "Today: bowel cancer follow-up, colorectal MDT outcome attached, "
        "rectum imaging review."
    )
    result = match_cancer_site(text)
    assert result is not None
    site, _hits = result
    assert site == "colorectal"


def test_empty_or_no_cancer_text_returns_none() -> None:
    """VT-153-TC-003"""
    assert match_cancer_site("") is None
    assert match_cancer_site("Routine BP review, no symptoms.") is None


def test_every_dictionary_key_is_canonical() -> None:
    """VT-153-TC-004 -- no drift between mined dict and _SITE_MAP."""
    drift = set(CANCER_SITE_TERMS.keys()) - _CANONICAL_KEYS
    assert drift == set(), f"non-canonical site keys found: {drift}"


def test_noise_filter_drops_generic_findings() -> None:
    """VT-153-TC-005 -- 'cramps', 'amy was not elevated', 'abnormal lfts'
    must NOT appear in any site list, since their parent SNOMED concept
    only incidentally mentions an organ.
    """
    forbidden = {"cramps", "amy was not elevated", "abnormal lfts"}
    for site, forms in CANCER_SITE_TERMS.items():
        leaked = forbidden & set(forms)
        assert leaked == set(), f"noise leaked into {site!r}: {leaked}"


def test_extract_condition_key_prefers_explicit_site_key() -> None:
    """VT-153-TC-006"""
    anchor = {
        "site_key": "breast",
        "concept_id": 363346000,
        "concept_name": "Text: confirmed cancer diagnosis",
    }
    assert _extract_condition_key_from_anchor(anchor) == "breast"


def test_extract_condition_key_falls_back_when_site_key_unknown() -> None:
    """If site_key is missing or unknown, the existing resolution path
    must continue to work (non-regression for coded anchors).
    """
    anchor_no_sk = {
        "concept_id": "276341000000100",
        "concept_name": "Fast track referral for suspected breast cancer",
    }
    assert _extract_condition_key_from_anchor(anchor_no_sk) == "breast"

    anchor_unknown_sk = {
        "site_key": "unknown",
        "concept_id": "276401000000108",
        "concept_name": "Fast track referral for suspected lower GI cancer",
    }
    assert _extract_condition_key_from_anchor(anchor_unknown_sk) == "colorectal"


@pytest.mark.parametrize(
    "text,expected",
    [
        # Each phrase below is taken from real surface forms in the
        # gold-mined dictionary so the test exercises actual dict matches.
        ("Histology confirms breast cancer; lump in left breast.", "breast"),
        ("Biopsy of prostate scheduled, prostate cancer suspected.", "prostate"),
        ("Bowel cancer screening fit positive; suspected bowel cancer.", "colorectal"),
        ("Skin lesion excised; basal cell carcinoma on temple.", "melanoma"),
        (
            "Cancer of fallopian tube on imaging; ovarian cystectomy planned.",
            "ovarian",
        ),
        ("Multiple myeloma follow-up after bone marrow biopsy.", "myeloma"),
    ],
)
def test_canonical_recognition(text: str, expected: str) -> None:
    """Smoke-test that canonical NCDA keys come out for typical phrases."""
    result = match_cancer_site(text)
    assert result is not None, f"no match for: {text}"
    assert result[0] == expected
