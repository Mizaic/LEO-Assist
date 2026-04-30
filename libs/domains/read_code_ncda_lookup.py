"""GP Read-code-to-NCDA-role lookup table.

This module maps GP Read code identifiers (the alphanumeric strings that
appear inside parentheses in encounter text, e.g. "XaMeA", "XE1vW", "J5031")
to canonical NCDA roles plus an optional outcome attribute.

These Read codes are a free, stable pre-coding signal: GPs use them as their
primary mechanism for coded entry into EMIS / SystmOne, and the codes are
written into the consultation text at ingest time, BEFORE our pipeline's
SNOMED coding pass runs. This makes them safe to use as features in the
NCDA detector at inference, even though our :DOCUMENTS-mapped SNOMEDs are
downstream and unavailable.

The table was seeded by walking every encounter inside the 33 reviewed
EpisodeOfCare records, regex-extracting (XYZ) Read-code-shaped substrings,
and grouping by milestone_type. Curator + LLM-at-curation expansion will
add more entries over time; reviewer signoff happens via the Stage 9b
audit tile (action: add_to_read_code_lookup).

NCDA roles:
  - "ftr"        : Fast Track Referral / 2WW / urgent suspected cancer
  - "seen"       : First specialist visit / clinic letter
  - "dx"         : Diagnosis outcome reached (cancer found OR cancer ruled out)
  - "treatment"  : First definitive treatment for cancer
  - "none"       : Not an NCDA anchor (working diagnosis, admin, etc.)

Optional outcome (only when role == "dx"):
  - "cancer_found"
  - "cancer_excluded"
"""

from __future__ import annotations

from typing import Literal

NcdaRole = Literal["ftr", "seen", "dx", "treatment", "none"]
DxOutcome = Literal["cancer_found", "cancer_excluded"]

# ---------------------------------------------------------------------------
# Curated Read-code -> (role, outcome) lookup.
#
# Entries verified against:
#  - Reviewed-episode encounter text occurrences (n>=2 milestoned encounters).
#  - EMIS Read v2 / CTV3 dictionary semantics where the code resolves.
#
# When a code's dominant milestone differed across reviewed episodes, the
# clinically-correct role wins (e.g. XE1vW = Malignant tumour of rectum is
# always (dx, cancer_found) regardless of whether one v2 milestoning happened
# to tag it as treatment_started by accident).
# ---------------------------------------------------------------------------
READ_CODE_TO_NCDA_ROLE: dict[str, tuple[NcdaRole, DxOutcome | None]] = {
    # -- FTR / urgent suspected cancer referrals ----------------------------
    # Site-specific PRISM 2WW referral codes - extracted from full encounter corpus.
    # Each code appears exclusively in GP PRISM questionnaire and medical secretary
    # booking submission encounters (the two encounter types that ARE an active FTR).
    "XaMeA": ("ftr", None),  # Fast track referral for suspected skin cancer
    "XaMeB": ("ftr", None),  # Fast track referral for suspected gynaecological cancer
    "XaMeC": ("ftr", None),  # Fast track referral for suspected breast cancer
    "XaMeF": ("ftr", None),  # Fast track referral for suspected urological cancer
    "XaMeG": ("ftr", None),  # Fast track referral for suspected haematology malignancy
    "XaMeH": ("ftr", None),  # Fast track referral for suspected lung cancer
    "XaMeJ": ("ftr", None),  # Fast track referral for suspected upper GI cancer
    "XaMeK": ("ftr", None),  # Fast track referral for suspected brain tumour
    "XaMkD": ("ftr", None),  # Fast track referral for suspected head and neck cancer
    "Xaalp": ("ftr", None),  # Fast track referral for suspected lower GI cancer
    "Y3dd2": ("ftr", None),  # Fast track referral for suspected cancer (non-site-specific)
    # Supporting 2WW booking / pathway codes - appear alongside site codes.
    # XaMJa is generic choice-and-booking admin and also appears on non-cancer
    # referrals (e.g. echocardiography), so it must not create FTR alone.
    "XaMJa": ("none", None),  # Choice and booking enhanced services admin
    "XaY59": ("none", None),  # Outbound referral - generic, not cancer-specific
    "XaEir": ("ftr", None),  # Refer for suspected cancer
    "XaIvd": ("ftr", None),  # Suspected cancer pathway referral
    "Xa4in": ("ftr", None),  # Refer for two-week-wait cancer pathway
    "XaAdt": ("ftr", None),  # Two-week-wait suspected cancer referral
    "XaL1F": ("ftr", None),  # 2WW gynaecology referral
    "XaMns": ("ftr", None),  # 2WW lung cancer referral
    # -- SEEN / first specialist clinic visit -------------------------------
    # "Seen in fast track suspected [site] cancer clinic" codes.
    # These appear in receptionist attendance records when the patient is seen.
    # NOTE: the same codes also appear in Type-4 retrospective admin tracking
    # notes ("2WW    Seen in 2WW Clinic?:..."). The silver_labeller applies an
    # exclusion check for that pattern before reaching the Read code branch.
    "XaPyP": ("seen", None),  # Seen in fast track suspected brain tumour clinic
    "XaPyQ": ("seen", None),  # Seen in fast track suspected breast cancer clinic
    "XaPyV": ("seen", None),  # Seen in fast track suspected gynaecological cancer clinic
    "XaPya": ("seen", None),  # Seen in fast track suspected head and neck cancer clinic
    "XaPyb": ("seen", None),  # Seen in fast track suspected colorectal cancer clinic
    "XaPyc": ("seen", None),  # Seen in fast track suspected lung cancer clinic
    "XaPyd": ("seen", None),  # Seen in fast track suspected skin cancer clinic
    "XaPyg": ("seen", None),  # Seen in fast track suspected cancer clinic (generic/NSS)
    "XaPyj": ("seen", None),  # Seen in fast track suspected upper GI cancer clinic
    "XaPyk": ("seen", None),  # Seen in fast track suspected urological cancer clinic
    # Additional outpatient attendance codes
    "XaIPT": ("seen", None),  # Outpatient consultation
    "XB002": ("seen", None),  # Outpatient appointment attended
    "X78WY": ("seen", None),  # Specialist review
    # -- Dx (cancer found) --------------------------------------------------
    "XE1vW": ("dx", "cancer_found"),  # Malignant tumour of rectum
    # XE1Sf is listed as "Malignant neoplasm of breast" in Read v2 but EMIS
    # reuses it as "Infectious disease: prevention/control" inside phlebotomy
    # CBS templates and cervical screening templates.  Mapping it to dx/cancer_found
    # causes false positives on virtually every routine blood draw and smear.
    # Genuine breast cancer diagnoses are captured by phrase matching and other codes.
    "XE1Sf": ("none", None),  # overloaded code — NOT reliable as cancer Dx
    "X78WM": ("dx", "cancer_found"),  # Cancer diagnosis communicated
    "X78WW": ("dx", "cancer_found"),  # Cancer confirmed at MDT
    "X78Y6": ("dx", "cancer_found"),  # Histology confirms malignancy
    "Xa980": ("dx", "cancer_found"),  # Carcinoma confirmed
    "Xa99l": ("dx", "cancer_found"),  # Adenocarcinoma confirmed
    "Xa3AJ": ("dx", "cancer_found"),  # Squamous cell carcinoma confirmed
    "XaAzZ": ("dx", "cancer_found"),  # Basal cell carcinoma confirmed
    "XaK2I": ("dx", "cancer_found"),  # Malignancy confirmed on biopsy
    "Ya0ln": ("dx", "cancer_found"),  # New cancer diagnosis (UK ext)
    "X40Qa": ("dx", "cancer_found"),  # Histopathology positive
    "X79cS": ("dx", "cancer_found"),  # MDT outcome - cancer confirmed
    "X20AR": ("dx", "cancer_found"),  # Tumour stage T2
    "Xa0U8": ("dx", "cancer_found"),  # Lymphoma confirmed
    "XaFC7": ("dx", "cancer_found"),  # Confirmed prostate cancer
    "XaW9C": ("dx", "cancer_found"),  # Carcinoma in situ confirmed
    # X90PX listed in CTV3 as "Endometrial carcinoma confirmed" but EMIS reuses
    # this code in clinical-supervision and other general template encounters for
    # non-endometrial-cancer patients.  It produces false dx/cancer_found labels
    # on supervision encounters for patients with haematological or other cancers.
    "X90PX": ("none", None),  # overloaded — unreliable as NCDA Dx signal
    "X70lS": ("none", None),  # Positron emission tomography - generic investigation
    "G5730": ("none", None),  # Atrial fibrillation - non-cancer LTC
    "XaaEP": ("dx", "cancer_found"),  # Histology malignant
    # -- FTR (screening programme referrals) --------------------------------
    # Breast and bowel screening programmes trigger an NCDA pathway in the same
    # way as GP 2WW referrals.  The GP practice receives a report/letter and
    # records it with the following codes.
    "68621": ("ftr", None),  # Breast neoplasm screening abnormal (NHS Breast Screening)
    "XaPVj": ("ftr", None),  # Bowel cancer screening FOBT positive result letter
    # -- Dx (investigation / outcome not yet determined) --------------------
    # These are specific cancer-pathway investigation procedures.  They map to
    # dx role with outcome=None because the result is not embedded in the EMIS
    # coded entry.  The simple_linker prefers outcome-bearing encounters; these
    # act as a fallback when no explicit outcome encounter exists (e.g. when the
    # GP practice only records the procedure date, not the clinic letter text).
    "537..": ("dx", None),   # Mammogram
    "585C.": ("dx", None),   # US scan of breast
    "X70lf": ("dx", None),   # Ultrasound scan (site/result determined from text)
    "7135.": ("dx", None),   # Biopsy of breast (includes core needle)
    "XS9or": ("dx", None),   # Stereotactically guided core needle biopsy of breast
    "XaF0P": ("dx", None),   # MRI of breast
    "Y0785": ("dx", None),   # Dermoscopy (skin cancer assessment)
    "XaPQa": ("dx", None),   # CT colonoscopy
    "XaJGZ": ("dx", None),   # Colonoscopy (lower GI cancer pathway)
    "XE0Gd": ("dx", None),   # Transperineal needle biopsy of prostate
    "XaW00": ("dx", None),   # Multiparametric MRI prostate
    "X40U7": ("dx", None),   # Bronchoscopy (lung cancer pathway)
    "XaDxJ": ("dx", None),   # CT chest (lung pathway)
    # -- Dx (cancer excluded / benign closure) ------------------------------
    "J5031": ("dx", "cancer_excluded"),  # Faecal impaction (working benign dx)
    "XaYQ7": ("dx", "cancer_excluded"),  # Discharge from cancer pathway - benign
    "X753K": ("dx", "cancer_excluded"),  # No malignancy on biopsy
    "Xa0F5": ("dx", "cancer_excluded"),  # Benign tumour confirmed
    "XE0e5": ("dx", "cancer_excluded"),  # Discharged from clinic - well
    "Xa3qz": ("dx", "cancer_excluded"),  # Benign skin lesion confirmed
    "Ub0oq": ("dx", "cancer_excluded"),  # No evidence of cancer found
    "Xa7va": ("dx", "cancer_excluded"),  # Reassurance given - no malignancy
    # -- Treatment ----------------------------------------------------------
    "X40EC": ("treatment", None),  # Chemotherapy started
    # XaXfG and XaIg6 were previously listed here as treatment.  In the live
    # corpus they appear overwhelmingly in non-cancer admin/templates:
    #   XaXfG = "Medication reconciliation" (pharmacist drug-review activity,
    #           fires on BP / eczema / Parkinson's reviews, not chemotherapy)
    #   XaIg6 = "Comment note" (generic admin comment box, fires on phone
    #           messages, e-mails, NEWS2 triage, district-nurse status updates)
    # Mapping them to treatment created phantom treatment_started anchors that
    # in turn caused the simple linker to spawn duplicate cohort-1a episodes
    # when paired with any nearby cancer-mention encounter.  See agent
    # transcript debugging session for patient 6243439488.  Treatment for
    # cancer drugs (Letrozole, Tamoxifen, etc.) is still picked up via the
    # bare-drug-token check on TREATMENT_DRUG_TOKENS, so genuine endocrine and
    # chemo encounters remain detected.  They are now classified as 'none'
    # (see the none section below) so the labeller short-circuits cleanly.
    "XaZ08": ("treatment", None),  # Hormone therapy started
    "XaF83": ("treatment", None),  # Surgery for cancer
    "7H601": ("treatment", None),  # Radical prostatectomy procedure
    "XaLQR": ("treatment", None),  # Radiotherapy started
    "Xa8SI": ("treatment", None),  # Targeted therapy started
    "XaBtn": ("treatment", None),  # Immunotherapy commenced
    "X71bL": ("treatment", None),  # Adjuvant therapy
    "Xa3HE": ("treatment", None),  # Brachytherapy
    "Xa8Pv": ("treatment", None),  # Mastectomy
    "XaVvz": ("treatment", None),  # Lumpectomy
    "Xaa4d": ("treatment", None),  # Cancer drug therapy
    "8B311": ("treatment", None),  # Chemotherapy administration
    "XacLJ": ("treatment", None),  # Anti-cancer therapy
    "XE1vV": ("treatment", None),  # Cancer treatment plan agreed
    "XaXfH": ("treatment", None),  # Treatment cycle 1
    # NOTE: XaLQR, XaEJK, XaK2I, Ua1Rc are intentionally NOT listed here.
    # They appear in phlebotomy CBS templates with very different meanings:
    #   XaLQR = "Informed consent given" (phlebotomy), NOT "Radiotherapy started"
    #   XaEJK = "Blood sample taken" (phlebotomy), NOT "Cancer of unknown primary"
    #   XaK2I = "Phlebotomy generated from secondary care", NOT "Malignancy on biopsy"
    #   Ua1Rc = "Use of aseptic technique" (phlebotomy), NOT "Cancer diagnosis"
    # These generic CBS codes fire on almost every blood draw and must not trigger
    # NCDA roles. They are explicitly added to the none section below.
    # -- None (working diagnoses, admin, lab codes) -------------------------
    # These appear in FTR-adjacent encounters but are NOT NCDA anchors.
    # Explicitly listed so the deterministic labeller short-circuits rather
    # than falling through to the (too-broad) phrase-pattern matcher.
    "X76sB": ("none", None),  # Clinical history - admin
    "Xa1qL": ("none", None),  # Generic Consultation code (appears in all encounter types)
    "XE25C": ("none", None),  # Prostate-specific antigen level (PSA lab test)
    "Xaf0H": ("none", None),  # Quantitative faecal immunochemical test (FIT lab result)
    "X76sV": ("none", None),  # Clinical history and observations
    "XaIVg": ("none", None),  # Refer for cancer specialist opinion (too generic - fires on phone consults)
    "XaBzA": ("none", None),  # Refer for cancer suspected (too generic - fires on consultations)
    # Generic admin-template codes — present in the vast majority of clinical
    # encounters and must NOT trigger any NCDA role.
    "XaIg6": ("none", None),  # Comment note — generic admin comment box (phone messages, e-mails, status updates)
    "XaXfG": ("none", None),  # Medication reconciliation — pharmacist drug-review activity, NOT chemotherapy
    "XaIg4": ("none", None),  # Administration note — generic admin entry
    "XaMiI": ("none", None),  # Short message service (SMS) text sent - admin
    "9159.": ("none", None),  # Patient telephone number - admin
    "9N31.": ("none", None),  # Telephone encounter type - admin
    "Y41c9": ("none", None),  # Chronic symptoms (encounter reason)
    "Y3c8e": ("none", None),  # qFIT requested (test request, not an FTR)
    "Y36a6": ("none", None),  # Provision of FIT kit - admin
    "XaPII": ("none", None),  # Nasopharyngeal virology swab - investigation
    "XM08J": ("none", None),  # Dysphagia (symptom code)
    # Phlebotomy CBS template codes — appear in virtually every blood draw
    "XaEJK": ("none", None),  # Blood sample taken (phlebotomy CBS) — NOT cancer
    "XaK2I": ("none", None),  # Phlebotomy generated from secondary care — NOT biopsy
    "Ua1Rc": ("none", None),  # Use of aseptic technique — NOT cancer diagnosis
    "XaLQR": ("none", None),  # Informed consent given (phlebotomy) — NOT radiotherapy
    "XaXHK": ("none", None),  # Informed consent given for treatment (phlebotomy CBS)
    "9N2S.": ("none", None),  # Seen by practice phlebotomist — admin
    "XaAZQ": ("none", None),  # Referral by GP (CBS claim) — admin, NOT an NCDA referral
    "X78uI": ("none", None),  # Blood test type: Routine — lab admin
    "X78uK": ("none", None),  # Blood test type: Urgent — lab admin
    "XaIvd": ("none", None),  # Telephone triage encounter — generic contact, not FTR
    # Haematological condition monitoring codes — appear in phlebotomy /
    # long-term condition review encounters and must not trigger dx role.
    "Xa0SP": ("none", None),  # Myeloproliferative disorder — LTC monitoring, not NCDA Dx
}

# Drug names that GPs sometimes embed in parentheses for treatment encounters.
# These are not Read codes but indicate treatment start when present.
TREATMENT_DRUG_TOKENS: frozenset[str] = frozenset(
    [
        "TRIPTORELIN",  # GnRH analogue (prostate)
        "DEGARELIX",  # GnRH antagonist (prostate)
        "DECAPEPTYL",  # Triptorelin brand (prostate)
        "ZOLADEX",  # Goserelin (breast / prostate)
        "TAMOXIFEN",  # Anti-oestrogen (breast)
        "LETROZOLE",  # Aromatase inhibitor (breast)
        "ANASTROZOLE",  # Aromatase inhibitor (breast)
        "BICALUTAMIDE",  # Anti-androgen (prostate)
        "PEMBROLIZUMAB",  # Immunotherapy
        "CARBOPLATIN",  # Platinum chemo
        "PACLITAXEL",  # Taxane chemo
        "DOCETAXEL",  # Taxane chemo
        "CYCLOPHOSPHAMIDE",  # Alkylating chemo
    ]
)

# Junk tokens that the (XYZ) regex catches but are not Read codes.
# Excluded from the lookup so they never accidentally classify an encounter.
KNOWN_JUNK_TOKENS: frozenset[str] = frozenset(
    [
        "Requested",
        "Complete",
        "Completed",
        "Pharmacist",
        "PCN",
        "UHL",
        "R",
        "april",
        "breach",
        "2010",
        "2024",
        "2025",
        "New Episode",
    ]
)


# ---------------------------------------------------------------------------
# Cancer-site annotations for FTR and Seen-In Read codes.
#
# These let the simple linker match FTRs to Dx encounters for the same tumour
# site without needing the ML classifier.  The site tokens are the same keys
# used in silver_labeller._SITE_TOKENS so the same comparison works end-to-end.
# ---------------------------------------------------------------------------

CancerSite = Literal[
    "breast", "lung", "lower_gi", "upper_gi", "skin", "urological",
    "gynaecological", "haematological", "head_neck", "brain", "nss",
]

#: Maps each FTR Read code to its cancer site.
FTR_CODE_TO_SITE: dict[str, CancerSite] = {
    "XaMeA": "skin",
    "XaMeB": "gynaecological",
    "XaMeC": "breast",
    "68621": "breast",    # NHS Breast Screening Programme abnormal mammogram
    "XaMeF": "urological",
    "XaMeG": "haematological",
    "XaMeH": "lung",
    "XaMeJ": "upper_gi",
    "XaMeK": "brain",
    "XaMkD": "head_neck",
    "Xaalp": "lower_gi",
    "Y3dd2": "nss",
}

#: Maps each "Seen in fast track" Read code to its cancer site.
SEEN_CODE_TO_SITE: dict[str, CancerSite] = {
    "XaPyP": "brain",
    "XaPyQ": "breast",
    "XaPyV": "gynaecological",
    "XaPya": "head_neck",
    "XaPyb": "lower_gi",
    "XaPyc": "lung",
    "XaPyd": "skin",
    "XaPyg": "nss",
    "XaPyj": "upper_gi",
    "XaPyk": "urological",
}

#: Keywords that signal each cancer site in free text.  Aligned with
#: silver_labeller._SITE_TOKENS so site hints are comparable.
# Order matters: site_from_text returns the first dict key whose tokens match.
# More cancer-specific sites (breast, urological, haematological) come before
# broad terms like "lung" whose tokens ("thoracic", "respiratory") can appear
# incidentally in non-lung encounters (e.g. "XR Thoracic spine" in a prostate
# review, NEWS2 "RR" / "respiratory rate" in an A&E triage).
SITE_KEYWORDS: dict[CancerSite, tuple[str, ...]] = {
    "breast":          ("breast", "mammogram", "mammography"),
    "urological":      ("prostate", "urology", "urological", "bladder", "haematuria", "renal", "kidney", "psa"),
    "haematological":  ("haematol", "lymphoma", "leukaemia", "myeloma", "sll", "cll"),
    "lower_gi":        ("lower gi", "colorectal", "bowel", "rectal", "rectum", "colon", "fit positive", "lgi"),
    "upper_gi":        ("upper gi", "oesophag", "stomach", "gastric", "dysphagia"),
    "gynaecological":  ("gynae", "gynaecolog", "cervix", "endometri", "ovari", "uterus"),
    "head_neck":       ("head and neck", "head & neck", "thyroid", "larynx", "pharynx", "tongue", "hoarse"),
    "skin":            ("skin", "dermoscopy", "dermatology", "melanoma", "lesion"),
    "lung":            ("lung", "chest x-ray", "cxr", "thoracic", "respiratory"),
    "brain":           ("brain", "cns", "neurosurg", "headache", "seizure"),
    "nss":             ("non-site specific", "nss", "weight loss", "fatigue"),
}


def site_from_read_codes(text: str) -> "CancerSite | None":
    """Return the cancer site encoded by FTR or Seen-In Read codes in the text.

    Checks FTR_CODE_TO_SITE first, then SEEN_CODE_TO_SITE.  Returns None when
    no recognised site code is present.
    """
    import re as _re
    for token in _re.findall(r"\(([A-Za-z0-9.]+)\)", text or ""):
        if token in FTR_CODE_TO_SITE:
            return FTR_CODE_TO_SITE[token]
        if token in SEEN_CODE_TO_SITE:
            return SEEN_CODE_TO_SITE[token]
    return None


def site_from_text(text: str) -> "CancerSite | None":
    """Return the most likely cancer site inferred from keyword signals in text.

    Used to annotate Dx encounters (which don't carry FTR codes) so the simple
    linker can match them to FTR encounters by site.
    """
    lower = (text or "").lower()
    for site, tokens in SITE_KEYWORDS.items():
        if any(tok in lower for tok in tokens):
            return site
    return None


def lookup_read_code(token: str) -> tuple[NcdaRole, DxOutcome | None] | None:
    """Return the (role, outcome) for a Read code token, or None if unknown.

    Drug-name tokens always return ("treatment", None). Junk tokens always
    return None even if a future caller adds them to the curated dict.
    """
    if token in KNOWN_JUNK_TOKENS:
        return None
    if token.upper() in TREATMENT_DRUG_TOKENS:
        return ("treatment", None)
    return READ_CODE_TO_NCDA_ROLE.get(token)


def role_count_summary() -> dict[str, int]:
    """Counts of curated Read codes per NCDA role; used by Stage 12 evaluation."""
    counts: dict[str, int] = {"ftr": 0, "seen": 0, "dx": 0, "treatment": 0, "none": 0}
    for role, _ in READ_CODE_TO_NCDA_ROLE.values():
        counts[role] = counts.get(role, 0) + 1
    return counts
