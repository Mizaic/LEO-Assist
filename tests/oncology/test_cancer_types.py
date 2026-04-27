"""VT-LEO-AI-528: Canonical NCDA cancer-type vocabulary contract.

Pins ``libs/oncology/cancer_types.py`` so the segmenter LLM, the
writer, the dashboard, and the audit endpoints share one source of
truth and historical raw values cannot reappear in the chart axes.
"""

from __future__ import annotations

import pytest

from libs.oncology.cancer_types import (
    CANONICAL_CANCER_TYPES,
    CANONICAL_CANCER_TYPE_SET,
    CancerType,
    is_canonical,
    normalise_cancer_type,
)

# Every raw value observed on the live graph (per the migration plan)
# plus near-synonyms we expect a producer to emit.
_OBSERVED_RAW_VALUES: tuple[tuple[str, str], ...] = (
    ("breast", "Breast"),
    ("skin", "Melanoma"),
    ("colorectal", "Colorectal"),
    ("head and neck", "Oropharyngeal"),
    ("head_neck", "Oropharyngeal"),
    ("lower_gi", "Colorectal"),
    ("prostate", "Prostate"),
    ("urinary bladder / prostate", "Prostate"),
    ("urological", "Other"),
    ("prostate_urological", "Other"),
    ("lung", "Lung"),
    ("upper gi", "Other"),
    ("upper_gi", "Other"),
    ("upper gastrointestinal", "Other"),
    ("gynaecological", "Other"),
    ("gynae", "Other"),
    ("gynaecological (cervix)", "Cervical"),
    ("cervix", "Cervical"),
    ("endometrium", "Endometrial"),
    ("endometrial", "Endometrial"),
    ("kidney", "Renal"),
    ("renal", "Renal"),
    ("oesophagus", "Oesophageal"),
    ("gastric/oesophageal", "Oesophageal"),
    ("stomach/oesophagus (junctional)", "Oesophageal"),
    ("thyroid", "Thyroid"),
    ("thyroid/neck (non-site-specific pathway)", "Thyroid"),
    ("brain", "Brain"),
    ("liver", "Liver"),
    ("anal", "Colorectal"),
    ("haematology", "Lymphoma"),
    ("hematology", "Lymphoma"),
    ("lymphoid", "Lymphoma"),
    ("haematology (lymphoma)", "Lymphoma"),
    ("salivary gland", "Other"),
    ("cardiac", "Other"),
    ("brain_cns", "Brain"),
    ("lymph node / mediastinal mass (pediatric)", "Lymphoma"),
    ("unknown", "Unknown Primary"),
)


@pytest.mark.parametrize("raw,expected", _OBSERVED_RAW_VALUES)
def test_observed_raw_values_remap_to_canonical(raw: str, expected: str):
    """VT-528-TC-001: every raw cancer_type value present on the live
    graph (per the migration plan) maps to a canonical NCDA value."""
    assert normalise_cancer_type(raw) == expected
    assert is_canonical(expected)


@pytest.mark.parametrize("canonical", list(CANONICAL_CANCER_TYPES))
def test_normalisation_is_idempotent(canonical: str):
    """VT-528-TC-002: feeding the canonical value back through the
    normaliser returns the same value (no-op on canonical input)."""
    assert normalise_cancer_type(canonical) == canonical


def test_blank_and_none_become_no_information():
    """VT-528-TC-003: ``None``, empty string, and whitespace-only input
    all collapse onto the ``No Information`` sentinel."""
    assert normalise_cancer_type(None) == "No Information"
    assert normalise_cancer_type("") == "No Information"
    assert normalise_cancer_type("   ") == "No Information"


def test_unknown_raw_value_falls_back_to_other():
    """VT-528-TC-004: any non-empty value that is not in the rewrite
    map nor an exact canonical value lands in ``Other`` -- never the
    raw string -- so chart axes never render free text."""
    assert normalise_cancer_type("zzz_made_up_site") == "Other"


def test_case_insensitive_match():
    """VT-528-TC-005: ``BREAST`` / ``Breast`` / ``breast`` all
    canonicalise to the same value."""
    assert (
        normalise_cancer_type("BREAST")
        == normalise_cancer_type("Breast")
        == normalise_cancer_type("breast")
        == "Breast"
    )


def test_canonical_list_has_30_unique_entries():
    """VT-528-TC-006: the canonical list has the expected NCDA
    cardinality (27 NCDA tumour entries + 3 sentinel entries)."""
    assert len(CANONICAL_CANCER_TYPES) == 30
    assert len(set(CANONICAL_CANCER_TYPES)) == 30
    assert "Other" in CANONICAL_CANCER_TYPE_SET
    assert "Unknown Primary" in CANONICAL_CANCER_TYPE_SET
    assert "No Information" in CANONICAL_CANCER_TYPE_SET


def test_other_and_unknown_are_sticky():
    """VT-528-TC-007: ``Other`` and ``Unknown Primary`` are themselves
    canonical and remain unchanged through the normaliser."""
    assert normalise_cancer_type("Other") == "Other"
    assert normalise_cancer_type("other") == "Other"
    assert normalise_cancer_type("Unknown Primary") == "Unknown Primary"
    assert normalise_cancer_type("unknown primary") == "Unknown Primary"


def test_cancer_type_enum_matches_canonical_list():
    """VT-528-TC-008: the ``CancerType`` enum and the
    ``CANONICAL_CANCER_TYPES`` tuple agree (no entry can be added to
    one without the other)."""
    assert tuple(c.value for c in CancerType) == CANONICAL_CANCER_TYPES
