"""VT-LEO-AI-139 -- Broadened breast specialty marker.

Verifies the DI-LEO-AI-138 regex extension covers common breast-care
phrasings (endocrine therapy, infiltrating duct, axilla / sentinel,
BRCA, triple-negative) without leaking into unrelated domains.
"""

from __future__ import annotations

from libs.clinical_scoping.specialty_markers import SPECIALTY_MARKERS


BREAST = SPECIALTY_MARKERS["breast"]


class TestLegacyAnchorsPreserved:
    def test_breast_word(self):
        assert BREAST.search("left breast lump, 2WW")

    def test_nipple(self):
        assert BREAST.search("nipple discharge noted")

    def test_mammogram(self):
        assert BREAST.search("mammogram booked next week")

    def test_mastectomy(self):
        assert BREAST.search("scheduled for mastectomy Thursday")

    def test_dcis(self):
        assert BREAST.search("low-grade DCIS on pathology")

    def test_her2(self):
        assert BREAST.search("HER2 positive, referred to oncology")


class TestDI138NewAnchors:
    def test_letrozole_endocrine_therapy(self):
        assert BREAST.search("started on Letrozole 2.5mg daily")

    def test_tamoxifen(self):
        assert BREAST.search("tamoxifen 20mg prescribed")

    def test_exemestane(self):
        assert BREAST.search("switched to exemestane after 5 years")

    def test_infiltrating_duct(self):
        assert BREAST.search("infiltrating duct carcinoma on core biopsy")

    def test_infiltrating_ductal(self):
        assert BREAST.search("infiltrating ductal carcinoma grade 2")

    def test_triple_negative(self):
        assert BREAST.search("triple-negative invasive carcinoma")
        assert BREAST.search("triple negative subtype")

    def test_brca_gene(self):
        assert BREAST.search("BRCA1 positive, family history")
        assert BREAST.search("BRCA2 mutation identified")
        assert BREAST.search("BRCA carrier, annual surveillance")

    def test_axilla_and_sentinel(self):
        assert BREAST.search("axillary node sampling planned")
        assert BREAST.search("sentinel node biopsy scheduled")


class TestNegativeCorpus:
    def test_no_match_on_prostate_text(self):
        text = (
            "Prostate adenocarcinoma, Gleason 3+4. PSA 8.2. "
            "Scheduled for TRUS biopsy."
        )
        assert BREAST.search(text) is None

    def test_no_match_on_colorectal_text(self):
        text = (
            "Rectal adenocarcinoma, completed colonoscopy. "
            "Awaiting flexible sigmoidoscopy follow-up."
        )
        assert BREAST.search(text) is None

    def test_no_match_on_lung_text(self):
        text = (
            "Suspected lung cancer. CT chest ordered. "
            "Patient smoker, haemoptysis reported."
        )
        assert BREAST.search(text) is None

    def test_no_match_on_generic_admin(self):
        text = (
            "Short message service text message sent to patient. "
            "Please use the link below to send photos."
        )
        assert BREAST.search(text) is None


class TestRealTextCorpusRecall:
    """Spot-check representative phrasings lifted from the 60-sample
    2026-04 audit -- these are the exact patterns DI-138 was designed
    to capture."""

    def test_fast_track_phrase(self):
        assert BREAST.search("Fast track referral for suspected breast cancer (XaMeC)")

    def test_breast_clinic_letter(self):
        assert BREAST.search("Breast Clinic to Woodbrook Medical Centre")

    def test_breast_surgeon(self):
        assert BREAST.search("Breast Surgeon to Dr Medical Woodbrook")

    def test_infiltrating_duct_prose(self):
        assert BREAST.search("Letter added to problem Infiltrating duct carcinoma")

    def test_letrozole_prescription(self):
        assert BREAST.search("(R) Letrozole 2.5mg tablets - 56 tablet")
