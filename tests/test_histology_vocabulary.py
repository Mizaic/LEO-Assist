"""VT-LEO-AI-147 -- Histology vocabulary expansion in anchor_detector.

DI-LEO-AI-149: Verifies the expanded _RE_CONFIRMED_CANCER and _RE_NO_CANCER
patterns recognise standard histology and benign-histology vocabulary
without misclassifying suspected-cancer / referral text.
"""

from __future__ import annotations

import pytest

from services.analysis_worker.app.analyzers.anchor_detector import (
    _RE_CONFIRMED_CANCER,
    _RE_NO_CANCER,
    _classify_text_encounters,
)


HISTOLOGY_POSITIVE_CORPUS = [
    "Invasive ductal carcinoma, grade 2",
    "Invasive lobular carcinoma of breast, ER positive",
    "Adenocarcinoma of colon, T2 N0 M0",
    "Squamous cell carcinoma of skin, well differentiated",
    "Basal cell carcinoma, infiltrating type",
    "BCC excision margin clear",
    "SCC of larynx, moderately differentiated",
    "DCIS high grade with comedonecrosis",
    "LCIS noted on excision",
    "Carcinoma in-situ of cervix",
    "Melanoma in-situ, Breslow 0.4mm",
    "Metastatic disease in axillary nodes",
    "Histopathology: poorly differentiated adenocarcinoma",
    "Gleason 7 (3+4) prostate",
    "FIGO IIIB endometrial",
    "Dukes B colorectal",
    "Stage IIa breast cancer",
    "Clark level III melanoma",
]

SUSPECTED_OR_REFERRAL_CORPUS = [
    "Fast track referral for suspected breast cancer (XaMeC)",
    "PRISM 2WW Breast Female questionnaire finalised: 17 Feb 2025",
    "?suspected lung cancer for investigation",
    "query carcinoma -- send for biopsy",
    "Referral to 2WW skin clinic for assessment",
    "Suspected malignancy -- urgent referral submitted",
]

BENIGN_HISTOLOGY_CORPUS = [
    "Lipoma excised, no further action",
    "Fibroadenoma confirmed on biopsy",
    "Sebaceous cyst removed",
    "Epidermal cyst, benign",
    "Seborrhoeic keratosis, no malignancy",
    "Actinic keratosis treated with cryotherapy",
    "Skin tag excised",
    "Acrochordon noted",
    "Dermatofibroma, benign lesion",
    "Benign naevus -- discharged",
    "No malignant cells identified",
    "No abnormality detected on imaging",
    "Normal histology, unremarkable findings",
    "Unremarkable biopsy",
    "Inflammatory change only",
    "Reactive atypia, no atypical cells",
    "Hyperplastic polyp removed",
    "Discharged back to GP, reassurance given",
]

MALIGNANT_OR_REFERRAL_NEGATIVE_CORPUS = [
    "Invasive ductal carcinoma confirmed",
    "Adenocarcinoma of stomach",
    "Fast track referral for suspected breast cancer",
    "PRISM 2WW lung cancer",
    "Confirmed melanoma, Breslow 1.2mm",
    "Metastatic disease in liver",
]


class TestConfirmedCancerCorpus:
    def test_histology_positive_all_match(self):
        misses = [p for p in HISTOLOGY_POSITIVE_CORPUS if not _RE_CONFIRMED_CANCER.search(p)]
        assert not misses, f"_RE_CONFIRMED_CANCER missed: {misses!r}"

    def test_suspected_referral_zero_false_positive(self):
        false_pos = [p for p in SUSPECTED_OR_REFERRAL_CORPUS if _RE_CONFIRMED_CANCER.search(p)]
        assert not false_pos, f"_RE_CONFIRMED_CANCER false-positive on: {false_pos!r}"


class TestBenignClosureCorpus:
    def test_benign_histology_all_match(self):
        misses = [p for p in BENIGN_HISTOLOGY_CORPUS if not _RE_NO_CANCER.search(p)]
        assert not misses, f"_RE_NO_CANCER missed: {misses!r}"

    def test_malignant_referral_zero_false_positive(self):
        false_pos = [p for p in MALIGNANT_OR_REFERRAL_NEGATIVE_CORPUS if _RE_NO_CANCER.search(p)]
        assert not false_pos, f"_RE_NO_CANCER false-positive on: {false_pos!r}"


def _row(text: str, enc_id: str) -> dict:
    return {
        "encounter_id": enc_id,
        "encounter_date": "2025-03-26",
        "content_type": "clinical",
        "text": text,
    }


class TestClassifierRouting:
    """VT-147-TC-005 / TC-006: histology cancer -> diagnosis bucket;
    benign -> benign-closure bucket. Buckets returned by
    _classify_text_encounters are an 8-tuple in order:
    referrals(0), diagnoses(1), treatments(2), specialists(3),
    benign_closures(4), specialist_letters(5),
    first_presentations(6), first_seens(7).
    """

    HISTOLOGY_FOR_ROUTING = [
        "Invasive ductal carcinoma, grade 2 -- breast",
        "Adenocarcinoma of colon T2 N0 M0",
        "DCIS high grade -- left breast",
        "Gleason 7 prostate",
    ]

    BENIGN_FOR_ROUTING = [
        "Lipoma excised, benign",
        "Fibroadenoma on biopsy",
        "No malignant cells identified",
        "Unremarkable histology, discharged back to GP",
    ]

    def test_histology_cancer_routed_to_diagnosis(self):
        rows = [_row(t, f"hist-{i}") for i, t in enumerate(self.HISTOLOGY_FOR_ROUTING)]
        result = _classify_text_encounters(rows, already_coded_ids=set())
        diagnoses = result[1]
        referrals = result[0]
        benign = result[4]
        ids = {f"hist-{i}" for i in range(len(self.HISTOLOGY_FOR_ROUTING))}
        diag_ids = {r["encounter_id"] for r in diagnoses}
        assert ids.issubset(diag_ids), (
            f"Expected all histology cancer ids in diagnosis bucket, "
            f"missing: {ids - diag_ids!r}"
        )
        assert not (ids & {r["encounter_id"] for r in referrals})
        assert not (ids & {r["encounter_id"] for r in benign})

    def test_benign_histology_routed_to_benign_closure(self):
        rows = [_row(t, f"ben-{i}") for i, t in enumerate(self.BENIGN_FOR_ROUTING)]
        result = _classify_text_encounters(rows, already_coded_ids=set())
        benign_bucket = result[4]
        diag_bucket = result[1]
        ids = {f"ben-{i}" for i in range(len(self.BENIGN_FOR_ROUTING))}
        ben_ids = {r["encounter_id"] for r in benign_bucket}
        assert ids.issubset(ben_ids), (
            f"Expected all benign ids in benign-closure bucket, "
            f"missing: {ids - ben_ids!r}"
        )
        assert not (ids & {r["encounter_id"] for r in diag_bucket})


class TestReferralGuardPreserved:
    """VT-147-TC-007: histology-bearing referrals must NEVER fire diagnosis
    or benign-closure -- _is_referral_enc must continue to suppress them.
    """

    def test_histology_in_fast_track_referral(self):
        text = "Fast track referral for suspected invasive ductal carcinoma"
        result = _classify_text_encounters(
            [_row(text, "ref-hist-1")], already_coded_ids=set()
        )
        referrals = {r["encounter_id"] for r in result[0]}
        diagnoses = {r["encounter_id"] for r in result[1]}
        benign = {r["encounter_id"] for r in result[4]}
        assert "ref-hist-1" in referrals
        assert "ref-hist-1" not in diagnoses
        assert "ref-hist-1" not in benign

    def test_histology_in_prism_referral(self):
        text = "PRISM 2WW Breast Female questionnaire finalised: 17 Feb 2025. Suspected DCIS."
        result = _classify_text_encounters(
            [_row(text, "ref-hist-2")], already_coded_ids=set()
        )
        referrals = {r["encounter_id"] for r in result[0]}
        diagnoses = {r["encounter_id"] for r in result[1]}
        assert "ref-hist-2" in referrals
        assert "ref-hist-2" not in diagnoses
