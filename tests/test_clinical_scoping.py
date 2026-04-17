"""VT-LEO-AI-121 - Specialty markers library.

Covers TC-001, TC-002, TC-004, TC-005, TC-006.
"""

from __future__ import annotations

import logging

import pytest

from libs.clinical_scoping import (
    SPECIALTY_MARKERS,
    filter_rows_by_specialty,
    specialty_for,
)


def test_specialty_markers_cover_major_cancer_types():
    """VT-118-TC-001."""
    required = {
        "breast",
        "lung",
        "colorectal",
        "prostate",
        "melanoma",
        "oesophageal",
        "stomach",
        "pancreatic",
        "ovarian",
        "cervical",
        "endometrial",
        "head_and_neck",
        "bladder",
        "renal",
        "liver",
    }
    missing = required - set(SPECIALTY_MARKERS.keys())
    assert not missing, f"Missing specialty markers for: {sorted(missing)}"


@pytest.mark.parametrize(
    "cancer_type,positive,negative",
    [
        (
            "colorectal",
            ["FIT positive result", "colonoscopy performed", "rectal bleeding"],
            ["PSA elevated", "mammogram clear"],
        ),
        (
            "prostate",
            ["PSA 12.5", "transurethral biopsy", "Gleason 3+4"],
            ["colonoscopy normal", "breast lump"],
        ),
        (
            "breast",
            [
                "breast lump palpated",
                "nipple discharge",
                "mammogram abnormal",
                "DCIS on core biopsy",
                "invasive ductal carcinoma grade 2",
                "ER+ve HER2 negative",
                "Ca breast follow-up",
            ],
            ["PSA high", "dysphagia"],
        ),
        (
            "stomach",
            [
                "Carcinoma of stomach (X78gA)",
                "gastric ca diagnosis",
                "OGD performed last week",
                "gastroscopy for IDA",
            ],
            ["PSA elevated", "rectal bleeding"],
        ),
        (
            "non_site_specific",
            [
                "2WW referral fast track",
                "two-week wait pathway",
                "suspected cancer concerns",
                "non-specific signs of cancer",
                "vague symptom screening",
            ],
            ["mammogram normal", "PSA 1.2"],
        ),
        (
            "head_and_neck",
            [
                "neck lump noted on examination",
                "neck swelling for 6 weeks",
                "hoarse voice",
                "ENT referral",
            ],
            ["PSA elevated", "mammogram normal"],
        ),
        (
            "leukaemia",
            [
                "AML relapse",
                "CML chronic phase",
                "CLL watch and wait",
                "myeloblasts in peripheral blood",
            ],
            [
                "ALL patients receive a follow-up",
                "Was ALL stable",
                "blast crisis not relevant here",
            ],
        ),
        (
            "lung",
            ["CT chest shows mass", "bronchoscopy", "haemoptysis"],
            ["PR bleeding", "breast change"],
        ),
    ],
)
def test_specialty_for_matches_relevant_terms_only(cancer_type, positive, negative):
    """VT-118-TC-002."""
    marker = specialty_for(cancer_type)
    assert marker is not None
    for text in positive:
        assert marker.search(text), f"{cancer_type} marker should match '{text}'"
    for text in negative:
        assert not marker.search(text), (
            f"{cancer_type} marker should NOT match '{text}'"
        )


def test_filter_excludes_cross_specialty_evidence():
    """VT-118-TC-004: cross-cancer rows are dropped."""
    rows = [
        {"encounter_text": "colonoscopy to caecum, normal"},
        {"encounter_text": "rectal bleeding with FIT positive"},
        {"encounter_text": "lower gi clinic review"},
        {"encounter_text": "PSA 18.5, Gleason 4+3"},
        {"encounter_text": "transurethral biopsy of prostate"},
    ]
    filtered = filter_rows_by_specialty(rows, "colorectal")
    assert len(filtered) == 3
    for row in filtered:
        assert any(
            term in row["encounter_text"].lower()
            for term in ("colon", "rectal", "lower gi", "fit")
        )


def test_filter_falls_back_to_unfiltered_when_no_match(caplog):
    """VT-118-TC-005: zero matches => fallback + WARNING."""
    rows = [
        {"encounter_text": "PSA 18.5"},
        {"encounter_text": "prostate biopsy"},
    ]
    with caplog.at_level(logging.WARNING, logger="libs.clinical_scoping.specialty_markers"):
        filtered = filter_rows_by_specialty(rows, "colorectal")
    assert len(filtered) == 2
    assert any("colorectal" in r.message for r in caplog.records)
    assert any("falling back" in r.message.lower() for r in caplog.records)


def test_filter_missing_marker_returns_unfiltered(caplog):
    """VT-118-TC-006: no marker defined => unfiltered + DEBUG."""
    rows = [
        {"encounter_text": "some text"},
        {"encounter_text": "more text"},
    ]
    with caplog.at_level(logging.DEBUG, logger="libs.clinical_scoping.specialty_markers"):
        filtered = filter_rows_by_specialty(rows, "other")
    assert len(filtered) == 2
    assert any(
        "no specialty marker" in r.message.lower() for r in caplog.records
    )


def test_filter_empty_cancer_type_returns_unfiltered():
    """Null-safe: empty cancer_type is a no-op filter."""
    rows = [{"encounter_text": "x"}, {"encounter_text": "y"}]
    assert filter_rows_by_specialty(rows, "") == rows
    assert filter_rows_by_specialty(rows, None) == rows  # type: ignore[arg-type]


def test_specialty_for_empty_returns_none():
    assert specialty_for("") is None
    assert specialty_for(None) is None  # type: ignore[arg-type]
    assert specialty_for("nonexistent_cancer") is None
