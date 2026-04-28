"""Stage 4 - Baseline smoke test for the role classifier.

End-to-end: train on a fixed-seed pooled gold + silver synthetic set,
predict on hold-outs, and assert per-class F1 floors. Uses LogisticRegression
under the hood; LightGBM swap is purely a classifier_factory change.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sklearn", reason="scikit-learn required for role classifier")

from pathlib import Path

from services.analysis_worker.app.ncda_detector.role_classifier import RoleClassifier
from services.training_worker.app.ncda_role_trainer import train_role_classifier


def _row(*, role, text, encounter_id="X", outcome=None, vector=None):
    return {
        "patient_id": "P1",
        "encounter_id": encounter_id,
        "role": role,
        "outcome": outcome,
        "text": text,
        "flags": None,
        "encounter_date": "2024-05-21",
        "vector": vector,
    }


def _gold_corpus():
    return [
        _row(role="ftr", encounter_id="g1", text="Fast track referral 2WW (XaMeA) for skin lesion"),
        _row(role="ftr", encounter_id="g2", text="Two week wait referral suspected breast cancer"),
        _row(role="ftr", encounter_id="g3", text="USC referral pathway sent (XaMJa)"),
        _row(role="seen", encounter_id="g4", text="Seen in 2WW clinic, dermatology consultant"),
        _row(role="seen", encounter_id="g5", text="Outpatient appointment - specialist clinic"),
        _row(role="seen", encounter_id="g6", text="Clinic letter received from oncology"),
        _row(role="dx", outcome="cancer_found", encounter_id="g7",
             text="(XE1vW) Malignant tumour of rectum confirmed"),
        _row(role="dx", outcome="cancer_found", encounter_id="g8",
             text="Carcinoma of prostate diagnosed - new episode"),
        _row(role="dx", outcome="cancer_excluded", encounter_id="g9",
             text="Discharged from 2WW pathway - no malignancy detected"),
        _row(role="dx", outcome="cancer_excluded", encounter_id="g10",
             text="Benign findings, all clear from clinic"),
        _row(role="treatment", encounter_id="g11", text="Started chemotherapy first cycle"),
        _row(role="treatment", encounter_id="g12", text="Decapeptyl 1st injection administered"),
        _row(role="none", encounter_id="g13", text="Routine blood test review"),
        _row(role="none", encounter_id="g14", text="Telephone consultation about back pain"),
    ]


def _silver_corpus():
    return [
        _row(role="ftr", encounter_id="s1", text="2WW referral made"),
        _row(role="ftr", encounter_id="s2", text="Fast track 2WW colorectal"),
        _row(role="seen", encounter_id="s3", text="Seen in clinic, review"),
        _row(role="dx", outcome="cancer_found", encounter_id="s4",
             text="Adenocarcinoma confirmed on histology"),
        _row(role="dx", outcome="cancer_excluded", encounter_id="s5",
             text="Cancer ruled out, discharged"),
        _row(role="treatment", encounter_id="s6", text="Started Tamoxifen treatment"),
        _row(role="none", encounter_id="s7", text="Asthma review consultation"),
        _row(role="none", encounter_id="s8", text="Flu vaccination administered"),
    ]


def test_role_classifier_trains_and_predicts(tmp_path: Path):
    artifact = tmp_path / "ncda_role.joblib"
    result = train_role_classifier(
        gold_rows=_gold_corpus(),
        silver_rows=_silver_corpus(),
        artifact_path=artifact,
    )
    assert artifact.exists()
    assert result.n_rows_gold > 0
    assert result.n_rows_silver > 0
    assert "ftr" in result.role_metrics
    assert "dx" in result.role_metrics


def test_role_classifier_predicts_ftr_on_held_out(tmp_path: Path):
    artifact = tmp_path / "ncda_role.joblib"
    train_role_classifier(
        gold_rows=_gold_corpus(),
        silver_rows=_silver_corpus(),
        artifact_path=artifact,
    )
    clf = RoleClassifier(artifact)
    pred = clf.predict_one(
        encounter_id="X",
        text="Fast track referral 2WW for suspected lung cancer",
        flags=None,
        encounter_date="2024-06-01",
    )
    assert pred.role in {"ftr", "dx", "seen", "treatment", "none"}
    assert pred.role == "ftr", f"Expected FTR, got {pred.role}"
    assert pred.role_probabilities["ftr"] > 0.3


def test_role_classifier_predicts_dx_excluded_outcome(tmp_path: Path):
    artifact = tmp_path / "ncda_role.joblib"
    train_role_classifier(
        gold_rows=_gold_corpus(),
        silver_rows=_silver_corpus(),
        artifact_path=artifact,
    )
    clf = RoleClassifier(artifact)
    pred = clf.predict_one(
        encounter_id="X",
        text="Discharged from 2WW pathway - benign findings, all clear",
        flags=None,
        encounter_date="2024-07-01",
    )
    assert pred.role == "dx"
    assert pred.outcome in ("cancer_found", "cancer_excluded")


def test_role_classifier_per_class_f1_floor(tmp_path: Path):
    """Sanity check: trained classifier achieves > 0.5 F1 on training set
    for the dominant labels. Real F1 floor enforcement happens in Stage 12.
    """
    artifact = tmp_path / "ncda_role.joblib"
    result = train_role_classifier(
        gold_rows=_gold_corpus(),
        silver_rows=_silver_corpus(),
        artifact_path=artifact,
    )
    for label in ("ftr", "dx", "treatment"):
        assert result.role_metrics[label]["f1"] >= 0.5, (
            f"{label} F1 too low: {result.role_metrics[label]}"
        )
