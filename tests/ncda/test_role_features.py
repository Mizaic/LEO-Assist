"""Tests for Stage 4 role-classifier feature extraction."""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.role_features import (
    compute_role_archetypes,
    date_features,
    extract_features,
    flag_features,
    phrase_features,
    read_code_features,
    vector_delta_features,
    vector_features,
)


def test_phrase_features_fire_on_role_text():
    feats = phrase_features("Fast track referral for suspected breast cancer")
    assert feats["phrase_ftr"] == 1
    assert feats["phrase_seen"] == 0


def test_phrase_features_dx_excluded_pattern():
    feats = phrase_features("Discharged from 2WW pathway, all clear")
    assert feats["phrase_dx_excluded"] == 1


def test_read_code_features_curated_lookup():
    feats = read_code_features("Sent (XaMeA) for skin lesion")
    assert feats["code_ftr"] == 1
    assert feats["code_dx"] == 0


def test_read_code_features_dx_outcome_split():
    feats = read_code_features("(XE1vW) malignant rectal tumour")
    assert feats["code_dx"] == 1
    assert feats["code_dx_found"] == 1
    assert feats["code_dx_excluded"] == 0


def test_read_code_features_drug_token_treated_as_treatment():
    feats = read_code_features("Started Tamoxifen this week")
    assert feats["code_treatment"] == 1


def test_flag_features_back_dated_detected():
    feats = flag_features("Face to face | back-dated entry on: 15 Jan 2024")
    assert feats["flag_face_to_face"] == 1
    assert feats["flag_back_dated"] == 1


def test_flag_features_handle_none():
    feats = flag_features(None)
    assert all(v == 0 for v in feats.values())


def test_date_features_extract_day_month_dow():
    feats = date_features("2024-05-21")
    assert feats["date_dow"] == 2  # Tue
    assert feats["date_dom"] == 21
    assert feats["date_moy"] == 5


def test_date_features_handle_missing():
    feats = date_features(None)
    assert feats == {"date_dow": 0, "date_dom": 0, "date_moy": 0}


def test_vector_features_emit_one_per_dim():
    feats = vector_features([0.1, 0.2, 0.3])
    assert feats == {"v0": 0.1, "v1": 0.2, "v2": 0.3}


def test_vector_delta_features_cosine_to_archetype():
    archetypes = {"ftr": [1.0, 0.0], "dx": [0.0, 1.0]}
    feats = vector_delta_features([1.0, 0.0], archetypes)
    assert feats["vdelta_ftr"] == 1.0
    assert feats["vdelta_dx"] == 0.0


def test_vector_delta_features_no_archetypes_returns_empty():
    feats = vector_delta_features([1.0, 0.0], None)
    assert feats == {}


def test_extract_features_combines_all():
    feats = extract_features(
        text="Fast track referral (XaMeA) for breast lump",
        flags="Face to face",
        encounter_date="2024-05-21",
        vector=[1.0, 0.0],
        archetypes={"ftr": [1.0, 0.0]},
    )
    assert feats["phrase_ftr"] == 1
    assert feats["code_ftr"] == 1
    assert feats["flag_face_to_face"] == 1
    assert feats["date_moy"] == 5
    assert feats["v0"] == 1.0
    assert feats["vdelta_ftr"] == 1.0


def test_compute_role_archetypes_means_per_role():
    rows = [
        {"role": "ftr", "vector": [1.0, 0.0]},
        {"role": "ftr", "vector": [0.0, 1.0]},
        {"role": "dx", "vector": [0.5, 0.5]},
    ]
    archetypes = compute_role_archetypes(rows)
    assert archetypes["ftr"] == [0.5, 0.5]
    assert archetypes["dx"] == [0.5, 0.5]


def test_compute_role_archetypes_skips_rows_without_vector():
    rows = [
        {"role": "ftr", "vector": [1.0, 0.0]},
        {"role": "ftr", "vector": None},
    ]
    archetypes = compute_role_archetypes(rows)
    assert archetypes["ftr"] == [1.0, 0.0]
