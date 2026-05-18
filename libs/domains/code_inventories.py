"""Curated Read/CTV3 code inventories for the stale-episode and

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

missed-cancer fixes.

These inventories capture the explicit Read/CTV3 codes, free-text
phrases, and prescribed-drug patterns that the GP record uses to
communicate cancer-pathway outcomes when a hospital letter has not
yet been ingested.

They power six rules in the episode builder:

1. Same-day "diagnosis from problem-list" - if the GP adds a malignancy
   problem code (e.g. "Malignant tumour of breast (X78WM)") inside the
   active 2WW window, treat it as a confirmed diagnosis anchor
   (DI-LEO-AI-159 / DI-LEO-AI-161).
2. Same-day "benign explanation from problem-list" - if the GP adds an
   alternative benign diagnosis (e.g. "Laryngopharyngeal reflux (XaK99)")
   or a benign-investigation phrase ("Mammogram - normal", "Cancer
   excluded - discharge to GP") inside the active 2WW window, treat it
   as a benign closure anchor (DI-LEO-AI-159 / DI-LEO-AI-161).
3. Site reconciliation - if the encounter text contains an explicit
   fast-track referral Read code ("Fast track referral for suspected
   breast cancer (XaMeC)"), trust that site over the gold-mined surface
   form match (DI-LEO-AI-161).
4. Free-text malignancy term recognition - if a problem-list line
   ("Major: ...", "Problem: ...", "Active Problem: ...") contains a
   malignancy term ("Carcinoma of prostate", "Invasive carcinoma of
   breast"), treat it as a confirmed diagnosis anchor with the term's
   site key, even when the surrounding Read code is not in the curated
   inventory (DI-LEO-AI-171).
   The same DI also covers the broader Read-code appendix sweep
   (active-cancer-care codes, history-of-cancer guard, B5/B57 mapping
   bug fix, and additional Xa-prefix carcinoma codes).
5. Adjuvant cancer-therapy inference - if a post-referral encounter
   carries an active repeat prescription line for a pathognomonic
   anti-cancer drug (letrozole, tamoxifen, abiraterone, triptorelin,
   etc.), treat it as a confirmed diagnosis anchor with HITL flag
   (DI-LEO-AI-172).
6. Site reconciliation in episode build - if a diagnosis-bearing anchor
   carries a stronger site signal than the referral, the episode's
   cancer_type is updated and the episode is flagged HITL
   (DI-LEO-AI-173).

All Read code and term entries are sourced verbatim from the deep-read
of 41 stale-episode encounter dumps and the 2025 closed_benign audit
(DI-LEO-AI-171). Add to this file - never invent codes from memory.

Additionally, DI-LEO-AI-175 / DI-LEO-AI-177 / DI-LEO-AI-178 (the
2026-04-17 skin-cancer audit) extend this file with:

7. Skin / melanoma vocabulary completeness - XaMeA (2WW skin
   referral), XaPyd (2WW skin clinic), the B32.. melanoma family,
   Xa99Y (lentigo maligna melanoma), CANCER_TREATMENT_PROCEDURE_CODES
   (7G055 wide excision + X90PX biopsy action), and the histological
   subtype patterns (lentigo maligna, superficial spreading, nodular,
   acral lentiginous, desmoplastic).
8. Cancer follow-up template recogniser - CANCER_FOLLOW_UP_PHRASES
   maps secondary-care surveillance template names ("Skin Cancer
   Follow Up", "Breast Cancer Follow Up", "Cancer follow up clinic")
   to their NCDA cancer site (DI-LEO-AI-177).
9. Benign-investigation phrase scope guard -
   BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT lists the tier-2 phrase
   labels that require cancer-pathway context in the same encounter
   to count as benign closure (DI-LEO-AI-178). The matching helper
   text_has_cancer_pathway_context() implements the gate.

Design controls: DI-LEO-AI-159, DI-LEO-AI-161, DI-LEO-AI-171,
DI-LEO-AI-172, DI-LEO-AI-173, DI-LEO-AI-175, DI-LEO-AI-177,
DI-LEO-AI-178, R-LEO-AI-162, R-LEO-AI-163, R-LEO-AI-170,
R-LEO-AI-171, R-LEO-AI-172, R-LEO-AI-173, VT-LEO-AI-157,
VT-LEO-AI-161, VT-LEO-AI-170, VT-LEO-AI-172.
"""

from __future__ import annotations

import re
from typing import Pattern

# ---------------------------------------------------------------------------
# Malignancy diagnosis Read/CTV3 codes (rule 1)
# ---------------------------------------------------------------------------
# Codes that, if present inside a 2WW post-referral window, indicate the
# GP has accepted a confirmed cancer diagnosis. Each code maps to the
# canonical NCDA cancer-site key used by EpisodeOfCare.cancer_type.
#
# Verbatim from the corpus (example episodes that triggered the catch
# noted alongside). Sourced from Read/CTV3 cancer appendix
# (configs/read codes/readcode.md) and the deep-read of stale dumps.
MALIGNANCY_READ_CODES: dict[str, str] = {
    # -- corpus-confirmed in deep-read --
    "X78WM": "breast",  # Malignant tumour of breast
    "X78XO": "endometrial",  # Endometrial carcinoma
    "BB5j2": "endometrial",  # Endometrioid carcinoma
    # -- corpus-confirmed in 2025 closed_benign audit (DI-LEO-AI-171) --
    "X78Y6": "prostate",  # Carcinoma of prostate (eps a6c093d2702d379f, e7c8b99ad0ae77ab)
    "Ya0ln": "breast",  # Invasive carcinoma of breast (corpus)
    # -- high-confidence siblings from Read code appendix --
    "B00..": "head_and_neck",  # Malignant neoplasm of lip
    "B01..": "head_and_neck",  # Malignant neoplasm of tongue
    "B02..": "head_and_neck",  # Major salivary glands malignant
    "B03..": "head_and_neck",  # Gum & mouth malignant
    "B04..": "head_and_neck",  # Floor of mouth malignant
    "B05..": "head_and_neck",  # Oropharynx malignant
    "B06..": "head_and_neck",  # Nasopharynx malignant
    "B07..": "head_and_neck",  # Hypopharynx malignant
    "B10..": "oesophageal",  # Malignant neoplasm of oesophagus
    "B11..": "stomach",  # Malignant neoplasm of stomach
    "B12..": "small_intestine",  # Malignant neoplasm of small intestine
    "B13..": "colorectal",  # Malignant neoplasm of colon
    "B14..": "colorectal",  # Malignant neoplasm of rectum
    "B15..": "liver",  # Malignant neoplasm of liver
    "B16..": "pancreatic",  # Malignant neoplasm of pancreas
    "B22..": "lung",  # Malignant neoplasm of trachea/bronchus/lung
    "B34..": "breast",  # Malignant neoplasm of female breast
    "B40..": "cervical",  # Malignant neoplasm of cervix uteri
    "B41..": "endometrial",  # Malignant neoplasm of body of uterus
    "B43..": "ovarian",  # Malignant neoplasm of ovary
    "B46..": "prostate",  # Malignant neoplasm of prostate
    "B47..": "testicular",  # Malignant neoplasm of testis
    "B49..": "bladder",  # Malignant neoplasm of bladder
    "B4A..": "renal",  # Malignant neoplasm of kidney
    # NOTE: B5... covers connective/soft tissue + skin + breast in the
    # Read appendix (B57.. is the brain sub-prefix). The previous
    # "B5..." -> head_and_neck mapping was a bug introduced when the
    # appendix was first transcribed; do NOT add a generic B5 entry. We
    # rely on the more specific sub-prefixes below to avoid mis-routing
    # connective-tissue sarcomas to head_and_neck.
    "B57..": "brain",  # Malignant neoplasm of brain
    "B62..": "thyroid",  # Malignant neoplasm of thyroid gland
    "B63..": "haematological",  # Hodgkin's disease
    "B64..": "lymphoma",  # Non-Hodgkin's lymphoma
    "B66..": "myeloma",  # Multiple myeloma
    "B67..": "leukaemia",  # Lymphoid leukaemia
    "B68..": "leukaemia",  # Myeloid leukaemia
    "B69..": "leukaemia",  # Monocytic leukaemia
    # -- additional Xa-prefix carcinoma codes from the Read appendix --
    # (sourced from configs/read codes/readcode.md; kept conservative
    #  to avoid over-firing on rare or non-NCDA-relevant subtypes)
    "Xa3eL": "breast",  # Carcinoma of breast - upper, inner quadrant
    "Xa3eM": "breast",  # Carcinoma of breast - lower, inner quadrant
    "Xa3eO": "breast",  # Carcinoma breast - lower, outer quadrant
    "Xa3eP": "breast",  # Carcinoma of breast - axillary tail
    "Xa3eQ": "breast",  # Carcinoma of breast NOS
    "Xa0bQ": "breast",  # Sarcoma of breast
    "Xa0bS": "breast",  # Malignant lymphoma of breast
    "Xa0Ge": "head_and_neck",  # Carcinoma of larynx
    "Xa1oQ": "head_and_neck",  # Carcinoma of vocal cord
    "Xa97p": "head_and_neck",  # Malignant tumour of anterior two-thirds of tongue
    "Xa97t": "head_and_neck",  # Malignant tumour of soft tissue of head/face/neck
    "Xa9EA": "head_and_neck",  # Malignant tumour of posterior wall of hypopharynx
    "Xa0KG": "lung",  # Malignant tumour of lung
    "Xa0DF": "oesophageal",  # Adenocarcinoma of oesophagus
    "Xa34F": "colorectal",  # Carcinoma of anal canal
    "Xa34H": "colorectal",  # Carcinoma of sigmoid colon
    "Xa84V": "colorectal",  # Adenocarcinoma of sigmoid colon
    "XaA0C": "colorectal",  # Adenocarcinoma of ileum
    "Xa97q": "liver",  # Malignant tumour of liver
    "Xa3eF": "liver",  # Carcinoma liver/biliary system
    "XaB1g": "pancreatic",  # Carcinoma of head of pancreas
    "XaB1h": "pancreatic",  # Carcinoma of body of pancreas
    "XaB1i": "pancreatic",  # Carcinoma of tail of pancreas
    "Xa36r": "cervical",  # Carcinoma of cervix
    "XaBmX": "endometrial",  # Adenocarcinoma of uterus
    "Xa0Ei": "ovarian",  # Carcinoma of fallopian tube
    "Xa0Eq": "ovarian",  # Carcinoma of Bartholin's gland
    "Xa97y": "ovarian",  # Malignant tumour of vulva
    "Xa059": "urological",  # Malignant tumour of corpus spongiosum
    "Xa05A": "urological",  # Malignant tumour of corpus cavernosum
    "Xa0bM": "bladder",  # Sarcoma of bladder
    "Xa0bV": "testicular",  # Malignant Leydig cell tumour of testis
    "Xa0U5": "testicular",  # Malignant lymphoma of testis
    "Xa3eS": "testicular",  # Carcinoma of epididymis/spermatic cord
    "Xa0Dp": "brain",  # Malignant glioma of brain
    "XaC1Q": "brain",  # Malignant neoplasm, overlapping lesion of brain
    "Xa0bR": "thyroid",  # Malignant lymphoma of thyroid gland
    "Xa99k": "lymphoma",  # Malignant lymphoma
    "Xa99l": "lymphoma",  # Malignant lymphoma - small lymphocytic
    "Xa0T7": "lymphoma",  # Malignant lymphomatous polyposis
    "Xa0TP": "lymphoma",  # Malignant lymphoma - lymphoblastic
    "XaBAk": "haematological",  # Malignant mastocytosis
    "Xa0Ri": "haematological",  # Malignant white blood cell disorder
    "Xa0Di": "melanoma",  # Malignant melanoma of anus
    "Xa0Dj": "melanoma",  # Malignant melanoma of rectum
    "XaBAw": "melanoma",  # Malignant blue naevus of skin
    "XaCIv": "melanoma",  # Malignant melanoma of back
    "Xa0CD": "skin",  # Malignant tumour of skin with pilar differentiation
    # -- DI-LEO-AI-175: skin / melanoma vocabulary (2026-04-17 audit;
    #    lentigo maligna case had filed closed_benign until codes mapped) --
    "Xa99Y": "melanoma",  # Lentigo maligna melanoma
    # B32.. family - Malignant melanoma of skin (sourced verbatim
    # from configs/read codes/readcode.md). All map to "melanoma"
    # because the NCDA cancer_type vocabulary uses melanoma as the
    # umbrella site for cutaneous melanocytic malignancy.
    "B32..": "melanoma",  # Malignant melanoma of skin (parent)
    "B320.": "melanoma",  # Malignant melanoma of skin of lip
    "B321.": "melanoma",  # Malignant melanoma of eyelid (incl canthus)
    "B322.": "melanoma",  # Malignant melanoma of skin of ear/external auditory canal
    "B3220": "melanoma",  # Malignant melanoma of skin of ear
    "B3221": "melanoma",  # Malignant melanoma of skin of external auditory canal
    "B323.": "melanoma",  # Malignant melanoma of skin of other and unspecified parts of face
    "B3230": "melanoma",  # Malignant melanoma of skin of cheek
    "B3231": "melanoma",  # Malignant melanoma of chin
    "B324.": "melanoma",  # Malignant melanoma of scalp and neck
    "B3240": "melanoma",  # Malignant melanoma of scalp
    "B3241": "melanoma",  # Malignant melanoma of neck
    "B325.": "melanoma",  # Malignant melanoma of trunk (excluding scrotum)
    "B3250": "melanoma",  # Malignant melanoma of trunk NOS
    "B3251": "melanoma",  # Malignant melanoma of breast
    "B326.": "melanoma",  # Malignant melanoma of upper limb and shoulder
    "B3260": "melanoma",  # Malignant melanoma of shoulder
    "B3261": "melanoma",  # Malignant melanoma of arm
    "B327.": "melanoma",  # Malignant melanoma of lower limb and hip
    "B3270": "melanoma",  # Malignant melanoma of hip
    "B3271": "melanoma",  # Malignant melanoma of leg
    "B3280": "melanoma",  # Malignant melanoma of overlapping sites of skin
    "B3281": "melanoma",  # Malignant melanoma of contiguous skin sites
    "B32y.": "melanoma",  # Malignant melanoma of skin OS
    "B32z.": "melanoma",  # Malignant melanoma of skin NOS
    "Xa97z": "non_site_specific",  # Malignant tumour of unknown origin
}


# ---------------------------------------------------------------------------
# Cancer-treatment procedure codes (DI-LEO-AI-175)
# ---------------------------------------------------------------------------
# Procedure Read/CTV3 codes that, when present in a post-referral
# encounter, mean the patient has had treatment delivered for a
# confirmed cancer pathway. These typically appear in the only
# post-referral encounter when the GP receives the secondary-care
# operation note - the diagnosis Read code may not also be filed.
#
# When one of these codes appears the anchor detector treats the
# encounter as a treatment signal so the existing _RE_TREATMENT path
# fires a treatment_started anchor.
#
# Sourced verbatim from configs/read codes/readcode.md.
CANCER_TREATMENT_PROCEDURE_CODES: set[str] = {
    # -- DI-LEO-AI-175 (skin / general) --
    "7G055",  # Wide excision of skin lesion
    "X90PX",  # Biopsy - action (diagnostic / curative biopsy)
    # -- DI-LEO-AI-217 (Pattern M): cancer-surgery Read codes
    # observed in the live cohort (Major:/Problem: lines, "(New
    # Episode)" markers). Each code below is a definitive cancer
    # treatment / staging procedure -- presence in a post-referral
    # encounter MUST fire treatment_started so the pathway shows
    # an end-to-end milestone chain (referral -> first_seen ->
    # diagnosis -> treatment_started). --
    # Breast surgery
    "XacLJ",  # Mastectomy of right breast
    "XacLK",  # Mastectomy of left breast (sibling code)
    "X40EC",  # Wide local excision of breast lesion
    "7H601",  # Block dissection of axillary lymph nodes
    "XaF83",  # Biopsy of sentinel lymph node
    # Bowel / colorectal surgery
    "X20Y4",  # Anterior resection of rectum
    "XaFB2",  # Low anterior resection of rectum
    "XaCvE",  # Loop ileostomy stoma (cancer surgery accompaniment)
    "XaZVW",  # Laparoscopically assisted right hemicolectomy
    "77132",  # Right hemicolectomy and anastomosis NEC
    # Prostate / urology surgery
    "Y3c24",  # Robot assisted laparoscopic radical prostatectomy
    # Thyroid surgery
    "Xa8OS",  # Partial thyroidectomy
    "71102",  # Hemithyroidectomy
    # Generic chemotherapy / radiotherapy (also in
    # ACTIVE_CANCER_CARE_CODES; included here so the treatment
    # path fires on its own when present without any other
    # active-care marker)
    "8BAD0",  # Cancer chemotherapy
    "8BAD1",  # Cancer radiotherapy
    "ZV58A",  # Antineoplastic chemotherapy encounter
}

# ---------------------------------------------------------------------------
# Active cancer-care Read/CTV3 codes (rule 1, supplemental)
# ---------------------------------------------------------------------------
# Codes whose presence in a post-referral encounter unambiguously means
# the patient is being actively managed for a confirmed cancer (clinic
# attendance, MDT discussion, treatment delivery, surveillance). When
# one of these fires inside the active 2WW window we treat it as a
# diagnosis_confirmed signal even when no malignancy code is present.
#
# Site is NOT carried by these codes (they are activity descriptors,
# not site descriptors), so the episode builder must keep the site key
# from the referral and flag the episode HITL for site verification.
#
# Sourced verbatim from configs/read codes/readcode.md (Xa-prefix
# supplemental terms) and the 2025 closed_benign audit (DI-LEO-AI-171).
ACTIVE_CANCER_CARE_CODES: set[str] = {
    "XaIph",  # Cancer confirmed
    "XaIyc",  # Cancer review
    "XaXEV",  # Cancer care plan
    "XaJU6",  # Cancer multidisciplinary team meeting
    "XaN5C",  # Discussed at multidisciplinary team meeting
    "XaabR",  # Referral to cancer multidisciplinary team
    "XaKHe",  # Cancer care review
    "XaKI4",  # Cancer care review template
    "XaIl4",  # Suspected cancer - patient informed
    "XaIpL",  # Refer to cancer specialist
    "XaIpM",  # Cancer specialist appointment
    "XaIsg",  # Treatment for cancer started
    "XaIsh",  # Treatment for cancer in progress
    "8BAD0",  # Cancer chemotherapy
    "8BAD1",  # Cancer radiotherapy (informational)
    "ZV58A",  # Antineoplastic chemotherapy encounter
    "ZV67E",  # Cancer follow-up
    "8HBJ.",  # Discharge from cancer service
    "8HHE.",  # Referral to oncologist
}


# ---------------------------------------------------------------------------
# History-of-cancer prefixes (NOT a new diagnosis)
# ---------------------------------------------------------------------------
# Read code prefixes for "personal history of malignant neoplasm" - these
# encode that the patient HAS HAD cancer in the past, NOT that a new
# diagnosis has been made today. They must NEVER fire diagnosis_confirmed
# anchors. Each entry is a prefix - any code starting with it is treated
# as historic.
#
# Sourced from configs/read codes/readcode.md (sections "ZV10.", "XaXGk",
# "XE0q0..", "1421.-142Z." and "XM1R8" history templates) plus the 2025
# closed_benign audit (DI-LEO-AI-171) where one episode carried "B934."
# (history of breast cancer) inside the 2WW window.
HISTORY_OF_CANCER_CODE_PREFIXES: tuple[str, ...] = (
    "ZV10",  # Personal history of malignant neoplasm (V10.x family)
    "XaXGk",  # H/O: malignancy template
    "XE0q0",  # H/O: cancer template
    "X71Eu",  # H/O: cancer of breast
    "B934",  # History of malignant neoplasm of breast
    "B937W",  # History of malignant neoplasm of prostate
    "1421",  # H/O: cancer (legacy)
    "1422",  # H/O: cancer of cervix
    "1423",  # H/O: cancer of breast
    "1424",  # H/O: cancer of bowel
    "1425",  # H/O: cancer of lung
    "1426",  # H/O: cancer of prostate
    "1427",  # H/O: cancer of bladder
    "1428",  # H/O: cancer of kidney
    "1429",  # H/O: cancer of skin / melanoma
    "142A",  # H/O: cancer of stomach
    "142Z",  # H/O: cancer NOS
    "XM1R8",  # H/O: malignancy questionnaire template
)


# ---------------------------------------------------------------------------
# Free-text malignancy term patterns (rule 4)
# ---------------------------------------------------------------------------
# Some GP problem-list lines name a malignancy in plain English even
# when the surrounding Read code is generic ("Major: Carcinoma of
# prostate (Xxxxx)" with an unmapped code). We match these terms ONLY
# when they appear on a problem-list line (Major:/Problem:/Active
# Problem:) to avoid firing on free-prose discussion of cancer in
# letters or referral text.
#
# Each entry is (regex, site_key). Order matters - the first hit wins.
PROBLEM_LIST_LINE_PREFIX = re.compile(
    r"(?im)^\s*(?:major|problem|active\s+problem|active|"
    r"significant\s+problem|past\s+problem|past)\s*:\s*",
)

MALIGNANCY_TERM_PATTERNS: list[tuple[Pattern[str], str]] = [
    # Note: These look at the WHOLE line text after a problem-list prefix
    # has been confirmed. They are deliberately specific - no bare
    # "cancer" or "tumour" entries here (those words appear in 2WW
    # referral text and would over-fire).
    (re.compile(r"\binvasive (?:ductal|lobular) carcinoma\b", re.I), "breast"),
    (re.compile(r"\binvasive carcinoma of (?:the )?breast\b", re.I), "breast"),
    (re.compile(r"\bcarcinoma of (?:the )?breast\b", re.I), "breast"),
    (
        re.compile(r"\bmalignant (?:tumou?r|neoplasm) of (?:the )?breast\b", re.I),
        "breast",
    ),
    (re.compile(r"\bDCIS of (?:the )?breast\b", re.I), "breast"),
    (re.compile(r"\bcarcinoma of (?:the )?prostate\b", re.I), "prostate"),
    (
        re.compile(r"\bmalignant (?:tumou?r|neoplasm) of (?:the )?prostate\b", re.I),
        "prostate",
    ),
    (re.compile(r"\badenocarcinoma of (?:the )?prostate\b", re.I), "prostate"),
    (re.compile(r"\bcarcinoma of (?:the )?lung\b", re.I), "lung"),
    (re.compile(r"\bmalignant (?:tumou?r|neoplasm) of (?:the )?lung\b", re.I), "lung"),
    (re.compile(r"\bnon[- ]small cell lung (?:cancer|carcinoma)\b", re.I), "lung"),
    (re.compile(r"\bsmall cell lung (?:cancer|carcinoma)\b", re.I), "lung"),
    (re.compile(r"\bcarcinoma of (?:the )?colon\b", re.I), "colorectal"),
    (re.compile(r"\bcarcinoma of (?:the )?rectum\b", re.I), "colorectal"),
    (
        re.compile(
            r"\bmalignant (?:tumou?r|neoplasm) of (?:the )?(?:colon|rectum|"
            r"sigmoid|bowel)\b",
            re.I,
        ),
        "colorectal",
    ),
    (
        re.compile(r"\badenocarcinoma of (?:the )?(?:colon|rectum|sigmoid)\b", re.I),
        "colorectal",
    ),
    (re.compile(r"\bcarcinoma of (?:the )?(?:liver|hepat\w*)\b", re.I), "liver"),
    (re.compile(r"\bhepatocellular carcinoma\b", re.I), "liver"),
    (re.compile(r"\bcarcinoma of (?:the )?pancreas\b", re.I), "pancreatic"),
    (re.compile(r"\bcarcinoma of (?:the )?kidney\b", re.I), "renal"),
    (re.compile(r"\brenal cell carcinoma\b", re.I), "renal"),
    (re.compile(r"\bcarcinoma of (?:the )?bladder\b", re.I), "bladder"),
    (re.compile(r"\btransitional cell carcinoma\b", re.I), "bladder"),
    (re.compile(r"\bcarcinoma of (?:the )?(?:cervix|cervical)\b", re.I), "cervical"),
    (re.compile(r"\bendometrial (?:cancer|carcinoma)\b", re.I), "endometrial"),
    (re.compile(r"\bovarian (?:cancer|carcinoma)\b", re.I), "ovarian"),
    (re.compile(r"\bmalignant melanoma\b", re.I), "melanoma"),
    (re.compile(r"\bmelanoma in[- ]situ\b", re.I), "melanoma"),
    # DI-LEO-AI-175: histological melanoma subtypes (2026-04-17 audit)
    (re.compile(r"\blentigo maligna(?: melanoma)?\b", re.I), "melanoma"),
    (re.compile(r"\bsuperficial spreading melanoma\b", re.I), "melanoma"),
    (re.compile(r"\bnodular melanoma\b", re.I), "melanoma"),
    (re.compile(r"\bacral lentiginous melanoma\b", re.I), "melanoma"),
    (re.compile(r"\bdesmoplastic melanoma\b", re.I), "melanoma"),
    (re.compile(r"\bsquamous cell carcinoma of (?:the )?skin\b", re.I), "skin"),
    (re.compile(r"\bbasal cell carcinoma\b", re.I), "skin"),
    (re.compile(r"\bcarcinoma of (?:the )?larynx\b", re.I), "head_and_neck"),
    (
        re.compile(
            r"\bmalignant (?:tumou?r|neoplasm) of (?:the )?(?:larynx|"
            r"oropharynx|nasopharynx|tongue|tonsil)\b",
            re.I,
        ),
        "head_and_neck",
    ),
    (re.compile(r"\bnon[- ]hodgkin'?s? lymphoma\b", re.I), "lymphoma"),
    (re.compile(r"\bhodgkin'?s? (?:disease|lymphoma)\b", re.I), "lymphoma"),
    (re.compile(r"\bmultiple myeloma\b", re.I), "myeloma"),
    (
        re.compile(
            r"\b(?:acute|chronic) (?:myeloid|lymphoid|lymphocytic|"
            r"myeloblastic) leuk(?:a|e)mia\b",
            re.I,
        ),
        "leukaemia",
    ),
    (re.compile(r"\bglioblastoma\b", re.I), "brain"),
    (re.compile(r"\bmalignant glioma\b", re.I), "brain"),
]


# ---------------------------------------------------------------------------
# Adjuvant cancer-therapy drug patterns (rule 5)
# ---------------------------------------------------------------------------
# A long-running repeat prescription for one of these drugs almost
# always means the patient is being treated for a confirmed cancer
# (the drugs have very narrow non-cancer indications). When such a
# drug appears in a post-referral encounter, we infer a cancer
# diagnosis with the mapped site and flag the episode HITL because:
#
#   - The drug evidences the OUTCOME, not the diagnosis date.
#   - A clinic letter with the actual diagnosis date may still arrive.
#   - The drug's site indication may not match the referral site
#     (e.g. tamoxifen for prophylaxis, off-label uses).
#
# To avoid firing on every repeat-prescription review, the anchor
# detector requires either:
#   (a) the drug appears alongside a "started", "newly issued",
#       "initiated", "commenced", or first-issue marker, OR
#   (b) the drug appears alongside an active cancer-care code or
#       malignancy term in the same encounter text.
#
# Each entry is (drug_regex, site_key, restriction). The restriction
# is informational only - the anchor detector enforces the issue-event
# guard separately.
ADJUVANT_THERAPY_DRUG_PATTERNS: list[tuple[Pattern[str], str, str]] = [
    # -- Hormonal therapy: breast --
    (
        re.compile(r"\b(?:letrozole|femara)\b", re.I),
        "breast",
        "aromatase inhibitor - breast cancer adjuvant",
    ),
    (
        re.compile(r"\b(?:anastrozole|arimidex)\b", re.I),
        "breast",
        "aromatase inhibitor - breast cancer adjuvant",
    ),
    (
        re.compile(r"\b(?:exemestane|aromasin)\b", re.I),
        "breast",
        "aromatase inhibitor - breast cancer adjuvant",
    ),
    (
        re.compile(r"\b(?:tamoxifen|nolvadex)\b", re.I),
        "breast",
        "SERM - breast cancer adjuvant",
    ),
    (
        re.compile(r"\b(?:fulvestrant|faslodex)\b", re.I),
        "breast",
        "SERD - advanced breast cancer",
    ),
    # -- Hormonal therapy: prostate --
    (
        re.compile(r"\b(?:bicalutamide|casodex)\b", re.I),
        "prostate",
        "anti-androgen - prostate cancer",
    ),
    (
        re.compile(r"\b(?:flutamide|drogenil)\b", re.I),
        "prostate",
        "anti-androgen - prostate cancer",
    ),
    (
        re.compile(r"\b(?:enzalutamide|xtandi)\b", re.I),
        "prostate",
        "anti-androgen - prostate cancer",
    ),
    (
        re.compile(r"\b(?:abiraterone|zytiga)\b", re.I),
        "prostate",
        "CYP17 inhibitor - prostate cancer",
    ),
    (
        re.compile(r"\b(?:goserelin|zoladex)\b", re.I),
        "prostate",
        "LHRH agonist - prostate / breast cancer",
    ),
    (
        re.compile(r"\b(?:leuprorelin|prostap|lupron)\b", re.I),
        "prostate",
        "LHRH agonist - prostate cancer",
    ),
    (
        re.compile(r"\b(?:triptorelin|decapeptyl)\b", re.I),
        "prostate",
        "LHRH agonist - prostate cancer",
    ),
    (
        re.compile(r"\b(?:degarelix|firmagon)\b", re.I),
        "prostate",
        "GnRH antagonist - prostate cancer",
    ),
    # -- Cytotoxics / targeted (presence in primary care notes is
    #    almost always confirmation of cancer therapy) --
    (
        re.compile(r"\b(?:capecitabine|xeloda)\b", re.I),
        "non_site_specific",
        "fluoropyrimidine - GI / breast cancer",
    ),
    (
        re.compile(r"\b(?:imatinib|glivec|gleevec)\b", re.I),
        "haematological",
        "tyrosine kinase inhibitor - CML / GIST",
    ),
    (
        re.compile(r"\b(?:dasatinib|sprycel)\b", re.I),
        "haematological",
        "tyrosine kinase inhibitor - CML",
    ),
    (
        re.compile(r"\b(?:erlotinib|tarceva)\b", re.I),
        "lung",
        "EGFR inhibitor - lung cancer",
    ),
    (
        re.compile(r"\b(?:gefitinib|iressa)\b", re.I),
        "lung",
        "EGFR inhibitor - lung cancer",
    ),
    (
        re.compile(r"\b(?:trastuzumab|herceptin)\b", re.I),
        "breast",
        "HER2 inhibitor - breast cancer",
    ),
    (
        re.compile(r"\b(?:rituximab|mabthera)\b", re.I),
        "lymphoma",
        "CD20 inhibitor - NHL",
    ),
]

# Markers that the prescription is being NEWLY ISSUED rather than
# routinely repeated. Required (with the drug) to fire the adjuvant
# anchor unless there is also an active-cancer-care code or malignancy
# term in the same encounter text.
ADJUVANT_THERAPY_ISSUE_MARKERS: Pattern[str] = re.compile(
    r"\b(?:newly (?:issued|prescribed|started)|first issue|first prescription|"
    r"initiated|initiated on|commenced|started on|"
    r"new prescription|new repeat prescription|"
    r"acute issue|drug issued today)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Benign-explanation Read/CTV3 codes (rule 2)
# ---------------------------------------------------------------------------
# Codes that, if added as a Minor:/Major: problem inside the 2WW
# post-referral window, indicate the GP found a non-cancer explanation
# for the original presenting symptom and the pathway should close.
#
# These ONLY count when the encounter is inside the active referral
# window. Outside the window they are irrelevant comorbidity.
BENIGN_EXPLANATION_READ_CODES: set[str] = {
    # -- head & neck pathway --
    "XaK99",  # Laryngopharyngeal reflux
    "F5801",  # Presbyacusis
    "X40Gg",  # Thyroid nodule (benign)
    "XE104",  # Thyrotoxicosis
    "XE0Xx",  # Chronic rhinitis
    # -- breast pathway --
    "XaYQ7",  # Cyst of breast
    "Xa4ib",  # Lesion of breast (benign)
    "XE0Tg",  # Other viral warts
    "1A8..",  # Breast lump symptom (without malignancy)
    # -- urological pathway --
    "K276.",  # Balanitis xerotica obliterans
    "XE0e0",  # Urinary tract infection
    "XaFqt",  # Suspected UTI
    "K1A..",  # Benign prostatic hyperplasia (BPH)
    # -- colorectal / lower GI pathway --
    "J5105",  # Diverticulosis of the colon
    "Xa98X",  # Tubular adenoma (benign polyp)
    "J5701",  # Rectal polyp (benign)
    "XE0ag",  # Ulcerative colitis
    "G84..",  # Haemorrhoid
    # -- renal / urological --
    "PD10.",  # Single renal cyst
    # -- gynae --
    "X406j",  # Ovarian cyst (benign)
    "Xa6Yg",  # Atrophy of vagina
    # -- general lymphadenopathy / non-malignant --
    "Xa0Vr",  # Lymphadenopathy (NAD on 2WW)
    # -- screening normal --
    "68620",  # Breast neoplasm screening normal
    "XaPkd",  # BCSP faecal occult blood test normal
    "XaPVj",  # BCSP faecal occult blood result normal
}

# ---------------------------------------------------------------------------
# Fast-track referral Read codes -> NCDA cancer site (rule 4)
# ---------------------------------------------------------------------------
# When the encounter text contains "Fast track referral for suspected
# <site> cancer (<code>)" with one of these codes, we trust the site
# label encoded in the code over any surface-form heuristic.
FAST_TRACK_REFERRAL_READ_CODES: dict[str, str] = {
    "XaMeC": "breast",
    "XaMeB": "gynaecological",
    "XaMkD": "head_and_neck",
    "Xaalp": "colorectal",
    "XaMeF": "urological",
    "XaMeH": "lung",
    "XaMeK": "brain",
    "XaMeG": "haematological",
    "XaMeA": "melanoma",  # DI-LEO-AI-175: Fast track referral for suspected skin cancer
    # DI-LEO-AI-200: XaMeD is "Fast track referral for suspected
    # children's tumour", not NSS. Per the strict NSS rule, only the
    # SNOMED 1556551000000104 referral / explicit NSS surface forms
    # classify as non_site_specific.
    "XaMeD": "childrens_tumour",
    # XaMeL is "Malignant neoplasm of descended testis NOS" - this is
    # a testicular cancer; the NOS suffix only marks histology, not
    # site. Mapping it to non_site_specific was a bug.
    "XaMeL": "testicular",
}

# ---------------------------------------------------------------------------
# Specialist clinic attendance Read codes (informational - already
# detected by SEEN_BY_SPECIALIST_IDS but mirrored here for site mapping)
# ---------------------------------------------------------------------------
SPECIALIST_CLINIC_READ_CODES: dict[str, str] = {
    "XaPyQ": "breast",
    "XaPya": "head_and_neck",
    "XaPyb": "colorectal",
    "XaPyV": "gynaecological",
    "XaPyk": "urological",
    "XaPyc": "lung",
    "XaPyP": "brain",
    "XaPyd": "melanoma",  # DI-LEO-AI-175: Seen in fast track suspected skin cancer clinic
    # DI-LEO-AI-200: children's tumour clinic is NOT NSS.
    "XaPyS": "childrens_tumour",
    # Generic suspected cancer clinic IS the NSS clinic per the NHS
    # NG12 NSS pathway -- this stays NSS.
    "XaPyg": "non_site_specific",
}

# ---------------------------------------------------------------------------
# Benign-investigation phrases (rule 2, free-text fallback)
# ---------------------------------------------------------------------------
# Verbatim phrases extracted from the deep-read corpus that signal a
# benign outcome of a cancer investigation. Each tuple is (regex, label).
BENIGN_INVESTIGATION_PHRASES: list[tuple[Pattern[str], str]] = [
    # -- ORDER MATTERS: more specific phrases come first because
    # match_benign_investigation_phrase returns the first hit --
    # BIRADS / mammogram codes
    (re.compile(r"mammogram[^.\n]{0,80}\bnormal\b", re.I), "mammogram normal"),
    (
        re.compile(r"mammogram[^.\n]{0,80}\bm[12]\b", re.I),
        "mammogram M1/M2 (BIRADS benign)",
    ),
    # Breast USS
    (re.compile(r"us scan of breast[^.\n]{0,80}\bnormal\b", re.I), "breast USS normal"),
    (
        re.compile(r"us scan of breast[^.\n]{0,80}\bu[12]\b", re.I),
        "breast USS U1/U2 (benign)",
    ),
    # Cystoscopy / urology
    (
        re.compile(r"flexible cystoscopy[^.\n]{0,80}\bnormal\b", re.I),
        "flexible cystoscopy normal",
    ),
    (re.compile(r"\bcystoscop\w*[^.\n]{0,80}\bnormal\b", re.I), "cystoscopy normal"),
    # Colorectal screening
    (re.compile(r"\bfobt normal\b", re.I), "FOBT normal"),
    (re.compile(r"\bbcsp[^.\n]{0,80}\bnormal\b", re.I), "BCSP normal"),
    (re.compile(r"\bfit (?:test )?(?:result )?normal\b", re.I), "FIT normal"),
    # Nasendoscopy
    (
        re.compile(r"diagnostic nasendoscopy[^.\n]{0,80}\bnormal\b", re.I),
        "nasendoscopy normal",
    ),
    # Colonoscopy with benign result keywords
    (
        re.compile(
            r"colonoscopy[^.\n]{0,200}\b(?:diverticular|haemorrhoid|polyp removed[^.\n]{0,40}no cancer|no malignancy)\b",
            re.I,
        ),
        "colonoscopy benign finding",
    ),
    # Brain / triage explicit exclusion
    (
        re.compile(r"brain triage[^.\n]{0,80}cancer excluded", re.I),
        "brain triage - cancer excluded",
    ),
    # PSA monitoring (low PSA explicitly noted as no further action)
    (
        re.compile(
            r"prostate[- ]specific antigen[^.\n]{0,200}normal[, ]+no further action",
            re.I,
        ),
        "PSA normal, no further action",
    ),
    # -- General pathway-exclusion language (less specific, last) --
    (re.compile(r"\bcancer excluded\b", re.I), "cancer excluded - discharge to GP"),
    (re.compile(r"\bdischarged from care\b", re.I), "discharged from care"),
    (
        re.compile(r"\bdischarged from (?:clinic|hospital)\b", re.I),
        "discharged from clinic",
    ),
    (
        re.compile(r"\bdischarged from (?:2ww|two[- ]week|cancer) pathway\b", re.I),
        "discharged from 2WW pathway",
    ),
    (
        re.compile(r"\bno (?:evidence of )?(?:malignancy|cancer)\b", re.I),
        "no evidence of malignancy",
    ),
    (re.compile(r"\bnegative for malignancy\b", re.I), "negative for malignancy"),
    (re.compile(r"\bno further (?:action|follow[- ]up)\b", re.I), "no further action"),
]


# ---------------------------------------------------------------------------
# Letter-stub recognition (DQ alert rule 3)
# ---------------------------------------------------------------------------
# Encounter text that LOOKS like an incoming hospital letter where only
# the routing header was scanned in but the body was never transcribed.
# Pattern: "<Specialty> Clinic to <surgery name>" or
#          "<Specialty> to <surgery name>"
# These short stubs (typically <120 chars total, no medical content)
# need a follow-up letter-body ingestion.
LETTER_STUB_PATTERNS: list[Pattern[str]] = [
    # "<Specialty> Clinic to <surgery>"
    re.compile(
        r"^[\s\S]{0,200}\bclinic\s+to\s+[\w\s'.&-]{3,80}$",
        re.I,
    ),
    # "<Source>(Hospital|Surgery|Trust) to <surgery>"
    re.compile(
        r"^[\s\S]{0,200}\b(?:hospital|surgery|trust)\s+to\s+[\w\s'.&-]{3,80}$",
        re.I,
    ),
    # "<Specialty> to <surgery>" - bare speciality routing header
    # (e.g. "Urology to Greenfields Surgery", "Breast to St Mary's")
    re.compile(
        r"^[\s\S]{0,200}\b(?:breast|urology|colorectal|gynaecology|gynecology|"
        r"haematology|hematology|oncology|dermatology|ent|gastroenterology|"
        r"respiratory|endocrinology|neurology|skin|lung)\s+to\s+"
        r"[\w\s'.&-]{3,80}$",
        re.I,
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_CODE_TOKEN_RX: Pattern[str] = re.compile(r"\(([A-Za-z0-9.]{3,6})\)")


def extract_read_codes(text: str) -> list[str]:
    """Return every parenthesised Read/CTV3 code token from `text`.

    Matches tokens of length 3-6 alnum/dot wrapped in parentheses, e.g.
    "(X78WM)", "(BB5j2)", "(G84..)", "(PD10.)". Order is preserved.
    """
    if not text:
        return []
    return _CODE_TOKEN_RX.findall(text)


def find_malignancy_code(text: str) -> tuple[str, str] | None:
    """Return (code, site_key) for the first malignancy code in `text`.

    Returns None if no MALIGNANCY_READ_CODES match.
    """
    for code in extract_read_codes(text):
        site = MALIGNANCY_READ_CODES.get(code)
        if site:
            return code, site
    return None


def find_benign_explanation_code(text: str) -> str | None:
    """Return the first benign-explanation Read code in `text`, or None."""
    for code in extract_read_codes(text):
        if code in BENIGN_EXPLANATION_READ_CODES:
            return code
    return None


def find_fast_track_referral_site(text: str) -> tuple[str, str] | None:
    """Return (code, site_key) for the first explicit 2WW Read code."""
    for code in extract_read_codes(text):
        site = FAST_TRACK_REFERRAL_READ_CODES.get(code)
        if site:
            return code, site
    return None


def find_specialist_clinic_site(text: str) -> tuple[str, str] | None:
    """Return (code, site_key) for the first 'Seen in fast track' code."""
    for code in extract_read_codes(text):
        site = SPECIALIST_CLINIC_READ_CODES.get(code)
        if site:
            return code, site
    return None


def match_benign_investigation_phrase(text: str) -> str | None:
    """Return the matched-phrase label, or None if no match."""
    if not text:
        return None
    for rx, label in BENIGN_INVESTIGATION_PHRASES:
        if rx.search(text):
            return label
    return None


def looks_like_letter_stub(text: str, max_chars: int = 200) -> bool:
    """True if `text` looks like an unfilled incoming-letter stub."""
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > max_chars:
        return False
    return any(rx.search(stripped) for rx in LETTER_STUB_PATTERNS)


def is_history_of_cancer_code(code: str) -> bool:
    """True when `code` is a personal-history-of-cancer Read code.

    These codes encode that the patient HAS HAD cancer in the past,
    NOT that a new diagnosis has been made today. They must be excluded
    from new-diagnosis detection.
    """
    if not code:
        return False
    return any(code.startswith(prefix) for prefix in HISTORY_OF_CANCER_CODE_PREFIXES)


_PMHX_SECTION_RX = re.compile(
    r"(?im)^\s*(?:past\s+medical\s+history|past\s+medical\s+hx|"
    r"PMHx|PMH|background)\s*:\s*",
)


def _malignancy_under_pmhx_section(text: str) -> bool:
    """True when a malignancy term appears within a PMHx section.

    DI-LEO-AI-203 (Pattern E): community-care holistic assessments
    (and similar long-form templates) carry a PMHx bullet list
    beneath a 'Past medical history:' header. A bare entry like
    'Bowel cancer.' or 'Hypertension. Bowel cancer. Falls.' is a
    historical record, not a fresh diagnosis. The line does not
    carry a Read code so the existing problem-list code guard does
    not catch it.

    We treat any malignancy / cancer term that appears within ~600
    characters after a PMHx header (and before the next section
    header) as historical context.
    """
    if not text:
        return False
    matches = list(_PMHX_SECTION_RX.finditer(text))
    if not matches:
        return False
    cancer_word_rx = re.compile(
        r"\b(?:cancer|carcinoma|malignan\w+|tumou?r|melanoma|lymphoma|"
        r"leuk(?:a|e)mia|sarcoma|adenocarcinoma|DCIS|LCIS|BCC|SCC)\b",
        re.IGNORECASE,
    )
    for match in matches:
        start = match.end()
        next_header = re.search(
            r"(?im)^\s*(?:plan|examination|history|diagnosis|"
            r"treatment|impression|assessment|reason\s+for\s+referral|"
            r"observation|advice)\s*:\s*",
            text[start:],
        )
        end = start + (next_header.start() if next_header else 600)
        section = text[start:end]
        if cancer_word_rx.search(section):
            return True
    return False


# DI-LEO-AI-210 (Pattern H): family-history cancer markers used to
# block fresh-diagnosis emission when the only cancer mention is a
# relative's history (FH prostate ca - father diagnosed at 75). The
# regex is duplicated in anchor_detector.py for the referral
# suppression hook; keeping a copy here keeps code_inventories.py
# import-safe (no upstream dependencies on anchor_detector).
_FAMILY_HISTORY_CANCER_RX = re.compile(
    r"(?:"
    r"\bF[Hh][Xx]?\b\.?\s*(?:of\s+)?[A-Za-z\s]{0,40}?"
    r"\b(?:cancer|ca\b|carcinoma|malignan\w+|tumou?r|melanoma|"
    r"lymphoma|leuk(?:a|e)mia|sarcoma|adenocarcinoma)|"
    r"\bfamily\s+history\s+(?:of\s+)?[A-Za-z\s]{0,40}?"
    r"\b(?:cancer|ca\b|carcinoma|malignan\w+|tumou?r|melanoma|"
    r"lymphoma|leuk(?:a|e)mia|sarcoma)|"
    r"\b(?:father|mother|dad|mum|sister|brother|sibling|son|"
    r"daughter|aunt|uncle|cousin|grandfather|grandmother|"
    r"grandparent|relative|next\s+of\s+kin)\b"
    r"[^.\n]{0,80}?"
    r"\b(?:had|has|diagnosed\s+with|died\s+(?:from|of)|"
    r"history\s+of)\b"
    r"[^.\n]{0,40}?"
    r"\b(?:cancer|ca\b|carcinoma|malignan\w+|tumou?r|melanoma|"
    r"lymphoma|leuk(?:a|e)mia|sarcoma)"
    r")",
    re.IGNORECASE,
)


def text_contains_family_history_of_cancer(text: str) -> bool:
    """True when `text` mentions a family history of cancer.

    DI-LEO-AI-210 (Pattern H): used as a guard alongside the
    history-of-cancer check so that "FH prostate ca - father
    diagnosed at 75" does not get treated as a fresh patient
    diagnosis.
    """
    if not text:
        return False
    return bool(_FAMILY_HISTORY_CANCER_RX.search(text))


def text_contains_history_of_cancer(text: str) -> bool:
    """True when `text` contains any history-of-cancer Read code.

    Used as a guard before firing diagnosis anchors so that a problem
    line like "Major: H/O malignant neoplasm of breast (B934.)" does
    not get treated as a fresh breast-cancer diagnosis.
    """
    if not text:
        return False
    for code in extract_read_codes(text):
        if is_history_of_cancer_code(code):
            return True
    # Free-text history markers that may appear without a Read code.
    if re.search(r"\bH/?O[: ]+(?:cancer|malignan|carcinoma)", text, re.I):
        return True
    if re.search(r"\bhistory of (?:cancer|malignan|carcinoma)", text, re.I):
        return True
    if re.search(r"\bpersonal history of (?:cancer|malignan|carcinoma)", text, re.I):
        return True
    if _malignancy_under_pmhx_section(text):
        return True
    if text_contains_family_history_of_cancer(text):
        return True
    return False


def find_active_cancer_care_code(text: str) -> str | None:
    """Return the first active-cancer-care Read code in `text`, or None.

    Active-care codes (e.g. "XaIph - Cancer confirmed", "XaJU6 - MDT
    meeting") signal the patient is already being managed for confirmed
    cancer. They carry no site information so the caller must decide
    what site_key to use (typically the referral's site, with HITL).
    """
    if not text:
        return None
    if text_contains_history_of_cancer(text):
        return None
    for code in extract_read_codes(text):
        if code in ACTIVE_CANCER_CARE_CODES:
            return code
    return None


def _get_problem_list_lines(text: str) -> list[str]:
    """Return the full lines in `text` that begin with a problem-list
    prefix (Major:, Problem:, Active Problem:, etc.).

    The detector uses these to avoid firing on free-prose mentions of
    cancer in clinic letters or referral text.
    """
    if not text:
        return []
    out: list[str] = []
    for line in text.splitlines():
        if PROBLEM_LIST_LINE_PREFIX.search(line):
            out.append(line)
    return out


def find_malignancy_term_in_problem_line(
    text: str,
) -> tuple[str, str] | None:
    """Return (matched_term, site_key) for the first malignancy term that
    appears on a problem-list line in `text`, or None.

    History-of-cancer markers in the SAME line short-circuit the match
    so that "Major: H/O carcinoma of breast (B934.)" does not fire a
    fresh breast diagnosis.
    """
    if not text:
        return None
    for line in _get_problem_list_lines(text):
        if text_contains_history_of_cancer(line):
            continue
        for rx, site in MALIGNANCY_TERM_PATTERNS:
            match = rx.search(line)
            if match is not None:
                return match.group(0), site
    return None


def find_malignancy_code_in_problem_line(
    text: str,
) -> tuple[str, str] | None:
    """DI-LEO-AI-215 (Pattern K): return (code, site_key) for the first
    malignancy Read code that appears on a problem-list line in
    `text`, or None.

    Stricter than `find_malignancy_code` -- only matches when the
    code is added as part of an EMIS "Major:/Problem:/Active Problem:"
    addition, not when it appears inline as a free-prose qualifier
    ("Considering malignant tumour of breast (X78WM)") inside a
    referral note. This stricter form is the safe override for the
    DI-LEO-AI-145 same-encounter referral gate: only Major:/Problem:
    additions are strong enough evidence to fire diagnosis_confirmed
    on an encounter that ALSO carries a 2WW row.

    History-of-cancer markers in the SAME line short-circuit the
    match (same guard as the term-based variant).
    """
    if not text:
        return None
    for line in _get_problem_list_lines(text):
        if text_contains_history_of_cancer(line):
            continue
        for code in extract_read_codes(line):
            site = MALIGNANCY_READ_CODES.get(code)
            if site:
                return code, site
    return None


def find_adjuvant_therapy_drug(
    text: str,
) -> tuple[str, str, str] | None:
    """Return (drug_name, site_key, indication) for the first adjuvant
    cancer-therapy drug found in `text`, or None.

    This is a pure pattern match - the caller is responsible for the
    issue-event guard (newly issued / co-occurring active-care code /
    co-occurring malignancy term) before treating the hit as a
    diagnosis anchor.
    """
    if not text:
        return None
    for rx, site, indication in ADJUVANT_THERAPY_DRUG_PATTERNS:
        match = rx.search(text)
        if match is not None:
            return match.group(0), site, indication
    return None


def adjuvant_therapy_is_newly_issued(text: str) -> bool:
    """True when `text` contains a marker that an adjuvant-therapy drug
    was newly issued (rather than a routine repeat prescription)."""
    if not text:
        return False
    return bool(ADJUVANT_THERAPY_ISSUE_MARKERS.search(text))


def find_cancer_treatment_procedure_code(text: str) -> str | None:
    """DI-LEO-AI-175: return the first cancer-treatment procedure code
    in `text`, or None.

    Used by the anchor detector to fire a treatment_started anchor
    when a wide excision / biopsy code appears post-referral. Sites
    are not carried by these codes - the episode builder's existing
    site reconciliation handles that.
    """
    if not text:
        return None
    for code in extract_read_codes(text):
        if code in CANCER_TREATMENT_PROCEDURE_CODES:
            return code
    return None


# ---------------------------------------------------------------------------
# Cancer follow-up template phrases (DI-LEO-AI-177)
# ---------------------------------------------------------------------------
# Free-text template names used by secondary-care surveillance clinics.
# Their presence in an encounter is unambiguous evidence the patient
# has a confirmed cancer being actively monitored, even when no Read
# code records the diagnosis. Each entry is (regex, site_key).
#
# Patterns require the literal word "follow" within ~80 characters of
# the cancer / oncology / melanoma keyword to avoid firing on referral
# text like "fast track for suspected skin cancer".
#
# Sourced from 2026-04-17 skin/melanoma audit (Dermatology follow-up template).
CANCER_FOLLOW_UP_PHRASES: list[tuple[Pattern[str], str]] = [
    (re.compile(r"\bskin cancer follow[- ]?up\b", re.I), "melanoma"),
    (re.compile(r"\bmelanoma follow[- ]?up\b", re.I), "melanoma"),
    (re.compile(r"\bbreast cancer follow[- ]?up\b", re.I), "breast"),
    (re.compile(r"\bprostate cancer follow[- ]?up\b", re.I), "prostate"),
    (re.compile(r"\bcolorectal cancer follow[- ]?up\b", re.I), "colorectal"),
    (re.compile(r"\blung cancer follow[- ]?up\b", re.I), "lung"),
    (
        re.compile(
            r"\b(?:haem|hem)atology cancer follow[- ]?up\b",
            re.I,
        ),
        "haematological",
    ),
    (
        re.compile(
            r"\bgynaecolog\w* cancer follow[- ]?up\b",
            re.I,
        ),
        "gynaecological",
    ),
    (
        re.compile(
            r"\bhead and neck cancer follow[- ]?up\b",
            re.I,
        ),
        "head_and_neck",
    ),
    (re.compile(r"\bcancer follow[- ]?up clinic\b", re.I), "non_site_specific"),
    (re.compile(r"\boncology surveillance\b", re.I), "non_site_specific"),
]


def find_cancer_follow_up_phrase(
    text: str,
) -> tuple[str, str] | None:
    """DI-LEO-AI-177: return (phrase, site_key) for the first
    cancer-follow-up template phrase in `text`, or None.

    History-of-cancer markers in the same text suppress the match
    so that "H/O cancer of breast - patient enrolled in cancer follow
    up" does not fire as a fresh diagnosis.
    """
    if not text:
        return None
    if text_contains_history_of_cancer(text):
        return None
    for rx, site in CANCER_FOLLOW_UP_PHRASES:
        match = rx.search(text)
        if match is not None:
            return match.group(0), site
    return None


# ---------------------------------------------------------------------------
# Benign-investigation phrase scope guard (DI-LEO-AI-178)
# ---------------------------------------------------------------------------
# A small set of phrase labels in BENIGN_INVESTIGATION_PHRASES are
# intentionally broad so they catch the most common 2WW closure
# wording, but the same phrases also appear in unrelated encounters
# (CKD reviews, BP titrations, mental-health follow-ups). Without a
# scope guard these encounters silently close cancer episodes that
# share the same date window.
#
# This frozenset names the labels that REQUIRE cancer-pathway
# context in the same encounter to count as benign-closure signals.
# The Read-code path (find_benign_explanation_code) and the
# tier-1 cancer-specific phrases (mammogram normal, FOBT normal,
# breast USS normal, etc.) remain unconditional.
BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT: frozenset[str] = frozenset(
    {
        "discharged from care",
        "discharged from clinic",
        "no further action",
    }
)


# Compiled regex used by the anchor detector to decide whether the
# surrounding encounter text carries cancer-pathway context. Matches
# common cancer-domain tokens: cancer, carcinoma, malignan(t/cy/cies),
# tumour/tumor, melanoma, lymphoma, leuk(a|e)mia, 2WW, two-week wait,
# fast track, oncology, sarcoma, cytology, biopsy, suspected <site>
# cancer.
CANCER_PATHWAY_CONTEXT_REGEX: Pattern[str] = re.compile(
    r"\b(?:cancer|carcinoma|malignan\w*|tumou?r|melanoma|lymphoma|"
    r"leuk(?:a|e)mia|sarcoma|2ww|two[- ]week wait|fast track|"
    r"oncolog\w*|chemo(?:therapy)?|radiotherapy|2[- ]week wait|"
    r"suspected\s+\w+\s+cancer|MDT\s+(?:meeting|review))\b",
    re.IGNORECASE,
)


def text_has_cancer_pathway_context(text: str) -> bool:
    """DI-LEO-AI-178: True when `text` carries cancer-pathway tokens.

    Used to gate the broad benign-investigation phrases so that a
    phrase like "no further action" in an unrelated CKD review does
    not produce a benign_closure anchor for a parallel cancer
    episode. See R-LEO-AI-173 for the full rationale.
    """
    if not text:
        return False
    return bool(CANCER_PATHWAY_CONTEXT_REGEX.search(text))


# ---------------------------------------------------------------------------
# DI-LEO-AI-219 (Pattern N5): off-pathway non-cancer Problem-header guard
# ---------------------------------------------------------------------------
# When a primary-care encounter has explicit ``Problem:`` header(s)
# whose subject is unambiguously non-cancer (foreign travel, routine
# vaccination, repeat prescription, sick-note request, hot flushes
# without cancer context, etc.), incidental cancer mentions in the
# History/Plan body must NOT fire cancer-pathway milestones such as
# care_obstruction. The classic failure mode is a 2025-07-01
# MMR / Mexico travel-vaccine encounter whose body contained
# "unable to attend for vaccine ... Scheduled for mastectomy on
# 29.07.25". The care_obstruction regex matched "unable to attend" and
# emitted a phantom obstruction milestone on the breast pathway, when
# the encounter is in fact a routine travel-vaccine no-show.

_PROBLEM_HEADER_RX = re.compile(r"(?im)^\s*Problem\s*:\s*(.+?)$")

# Cancer / pathway tokens we look for INSIDE a Problem: header. If any
# header carries one of these the encounter is treated as cancer-
# pathway-relevant and the off-pathway guard does NOT fire.
_PROBLEM_HEADER_CANCER_TOKEN_RX = re.compile(
    r"\b(?:cancer|carcinoma|malignan\w+|tumou?r|melanoma|lymphoma|"
    r"leuk(?:a|e)mia|sarcoma|adenocarcinoma|DCIS|LCIS|BCC|SCC|"
    r"2WW|TWW|two[- ]week|fast[- ]?track|onco\w*|chemo\w*|"
    r"radiotherap\w*|biops\w*|mastectom\w*|lumpectom\w*|"
    r"prostatectom\w*|colectom\w*|gastrectom\w*|hysterectom\w*|"
    r"orchidectom\w*|nephrectom\w*|cystectom\w*|lobectom\w*|"
    r"pneumonectom\w*|sentinel\s+(?:lymph\s+)?node|"
    r"MDT|metasta\w+|neoplas\w+|"
    r"breast|prostate|colorectal|colon|rectal|bladder|kidney|renal|"
    r"hepatic|pancreas|pancreatic|ovarian|cervical|"
    r"uterine|endometrial|gastric|oesophageal|esophageal|"
    r"thyroid|head\s+and\s+neck)\b",
    re.IGNORECASE,
)

# Subjects we recognise as unambiguously non-cancer Problem headers.
# Conservative list: only matches when the header subject is clearly
# administrative, vaccination, travel, repeat-prescription, or a
# common non-cancer review template. New subjects can be added here
# as we encounter them. Order matters only for readability.
_OFF_PATHWAY_PROBLEM_RX = re.compile(
    r"(?:"
    r"advice\s+on\s+foreign\s+travel|"
    r"foreign\s+travel|"
    r"travel\s+(?:advice|vaccin\w*|consultation)|"
    r"(?:influenza|flu|MMR|hepatitis|covid|coronavirus|pneumococcal|"
    r"shingles|HPV|tetanus|pertussis|meningococcal|yellow\s+fever|"
    r"typhoid|cholera|rabies|polio|diphtheria|rotavirus|RSV)"
    r"(?:\s+(?:vaccin\w*|booster|jab|imm\w*))?|"
    r"(?:vaccin\w+|immunis\w+|immuniz\w+|booster|jab)|"
    r"(?:repeat|acute|new)\s+(?:medication|prescription|script)|"
    r"medication\s+review|"
    r"hot\s+flush\w*|"
    r"sick\s+note|"
    r"MED3|"
    r"fit\s+note|"
    r"failed\s+encounter|"
    r"telephone\s+(?:consultation|triage|encounter)|"
    r"administration|"
    r"summary\s+care\s+record"
    r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# DI-LEO-AI-220 (Pattern N3): structured-form-field restatement guard
# ---------------------------------------------------------------------------
# Receptionists and administrators routinely update structured proforma
# fields (``Date of First outpatient appointment: 07 Apr 2025``,
# ``Seen in 2WW Clinic?: Seen in fast track suspected breast cancer
# clinic (XaPyQ) 28 Apr 2025``) on encounters whose date is later than
# the date carried INSIDE the field. The detector previously treated
# these as fresh referrals / first_seens at the encounter date, opening
# duplicate milestones weeks after the real event already fired from
# the source encounter.

import datetime as _dt  # noqa: E402  -- module-internal helper

_DATE_DDMMMYYYY_RX = re.compile(
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[a-z]*\s+(\d{4})\b",
    re.IGNORECASE,
)
_DATE_NUMERIC_DMY_RX = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_DATE_ISO_RX = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")

_MONTH_ABBREV_TO_NUM = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _parse_iso_date(value: str) -> _dt.date | None:
    if not value:
        return None
    try:
        return _dt.date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _extract_form_field_dates(text: str) -> list[_dt.date]:
    """Return the list of explicit calendar dates that appear inside a
    structured form-field line (a line containing ``:`` AND an embedded
    calendar date).  Lines without ``:`` are NOT considered form
    fields, so a free-text clinic letter mentioning a past date does
    not trip the guard.
    """
    if not text:
        return []
    out: list[_dt.date] = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        for m in _DATE_DDMMMYYYY_RX.finditer(line):
            try:
                day = int(m.group(1))
                month = _MONTH_ABBREV_TO_NUM[m.group(2).lower()[:3]]
                year = int(m.group(3))
                out.append(_dt.date(year, month, day))
            except (ValueError, KeyError):
                continue
        for m in _DATE_NUMERIC_DMY_RX.finditer(line):
            try:
                day = int(m.group(1))
                month = int(m.group(2))
                year = int(m.group(3))
                # UK convention: DD/MM/YYYY. If month > 12 the line is
                # not a real date so skip.
                if month > 12 or day > 31:
                    continue
                out.append(_dt.date(year, month, day))
            except ValueError:
                continue
        for m in _DATE_ISO_RX.finditer(line):
            try:
                year = int(m.group(1))
                month = int(m.group(2))
                day = int(m.group(3))
                out.append(_dt.date(year, month, day))
            except ValueError:
                continue
    return out


def encounter_restates_past_event(
    text: str,
    encounter_date: str,
    *,
    lookback_days: int = 14,
) -> bool:
    """DI-LEO-AI-220 (Pattern N3): True when the encounter body
    contains at least one structured form-field line whose embedded
    calendar date is ``lookback_days`` or more BEFORE the encounter
    date.

    Used to suppress fresh ``referral`` and ``first_seen`` milestone
    emission from administrative form-field updates that restate a
    past event (e.g. ``Date of First outpatient appointment: 07 Apr
    2025`` entered on 13 May 2025, or ``Seen in 2WW Clinic?: ... 28
    Apr 2025`` entered on 10 Jun 2025). The real event will already
    have fired from the source encounter on its own date.

    The guard is INERT when:

      - The text has no ``:`` (no form-field shape).
      - The text contains no parsable calendar date.
      - The earliest embedded date is within ``lookback_days`` of the
        encounter date (i.e. the field date matches the encounter
        date, so it is a fresh event, not a restatement).
    """
    if not text or not encounter_date:
        return False
    enc_d = _parse_iso_date(encounter_date)
    if enc_d is None:
        return False
    cutoff = enc_d - _dt.timedelta(days=lookback_days)
    for d in _extract_form_field_dates(text):
        if d <= cutoff:
            return True
    return False


def encounter_problem_is_off_pathway(text: str) -> bool:
    """DI-LEO-AI-219 (Pattern N5): True when the encounter's Problem
    header(s) are unambiguously non-cancer and so cancer-pathway
    milestones should not be emitted from incidental body text.

    Returns True only when ALL of:
      1. ``text`` contains at least one ``Problem:`` header.
      2. NONE of the Problem headers carry a cancer / pathway token
         (cancer terms, 2WW, oncology, chemo/radio, sentinel node,
         a known cancer-site word).
      3. At least one Problem header matches the off-pathway list
         (foreign travel, vaccination, repeat prescription, sick
         note, hot flushes, etc.).

    The narrow scope is deliberate -- the guard MUST NOT suppress
    care_obstruction when the patient really does refuse / DNA a
    cancer-pathway investigation. Encounters without an explicit
    ``Problem:`` header (e.g. clinic letters, document_transfer
    rows, free-text notes) are NOT treated as off-pathway and
    continue to be evaluated normally.
    """
    if not text:
        return False
    headers = _PROBLEM_HEADER_RX.findall(text)
    if not headers:
        return False
    if any(_PROBLEM_HEADER_CANCER_TOKEN_RX.search(h) for h in headers):
        return False
    return any(_OFF_PATHWAY_PROBLEM_RX.search(h) for h in headers)


# ---------------------------------------------------------------------------
# DI-LEO-AI-401 (Pattern N1): narrative-restatement diagnosis guard
# ---------------------------------------------------------------------------
# Sick notes (eMED3 / fit notes) and "known X cancer" / "history of X"
# narratives in routine GP encounters routinely cause Pattern K and the
# soft diagnosis sources (cancer_follow_up_template, adjuvant_therapy_drug)
# to fire `diagnosis_confirmed` on encounters that merely RESTATE an
# existing cancer diagnosis. When such a diagnosis anchor has no
# referral to attach to, the episode builder still synthesises a
# floating diagnosis-led EpisodeOfCare, producing a phantom episode
# with no real clinical events.
#
# The N1 guard tags a diagnosis_confirmed anchor as
# ``is_narrative_restatement: True`` when the encounter body shows the
# unambiguous shape of a sick note OR a "known cancer" narrative
# restatement. The episode builder then rejects floating diagnosis-led
# groups whose anchors are ALL narrative restatements (see
# ``services/analysis_worker/app/analyzers/episode_builder/_grouping.py``).

# Sick-note shape: eMED3 / MED3 statements, fit notes, sick certificates,
# "not fit for work" phrases. The eMED3 form is the canonical NHS
# electronic statement and almost never appears outside a sick-note
# encounter, so a single hit is sufficient.
_SICK_NOTE_RX = re.compile(
    r"(?:"
    r"\beMED3\b|"
    r"\bMED3\b|"
    r"\bfit\s+note\b|"
    r"\bsick\s+note\b|"
    r"\bsickness\s+(?:certificate|note)\b|"
    r"\bunfit\s+for\s+work\b|"
    r"\bnot\s+fit\s+for\s+work\b|"
    r"\bfitness\s+(?:to|for)\s+work\b|"
    r"\bstatement\s+of\s+fitness\s+for\s+work\b"
    r")",
    re.IGNORECASE,
)

# Cancer-site tokens used to anchor the "known X cancer" narrative.
# Kept aligned with _PROBLEM_HEADER_CANCER_TOKEN_RX so we do not invent
# new site vocabulary in the N1 path.
_KNOWN_CANCER_SITE_TOKEN = (
    r"breast|prostate|colorectal|colon|rectal|bladder|kidney|renal|"
    r"hepatic|pancreas|pancreatic|ovarian|cervical|uterine|endometrial|"
    r"gastric|oesophageal|esophageal|thyroid|head\s+and\s+neck|lung|"
    r"skin|liver|gynaecological|melanoma|lymphoma|leuk(?:a|e)mia"
)

# "known breast ca", "known case of prostate cancer", "history of breast
# carcinoma" -- the canonical narrative restatement shapes used in GP
# routine notes, sick notes, and primary-care follow-up correspondence
# AFTER a cancer diagnosis has already been recorded elsewhere.
_KNOWN_CANCER_RESTATEMENT_RX = re.compile(
    r"\b(?:"
    rf"known\s+(?:case\s+of\s+|h(?:istor)?y\s+of\s+)?(?:{_KNOWN_CANCER_SITE_TOKEN})"
    r"\s*(?:cancer|carcinoma|ca\b|tumou?r|malignancy)|"
    rf"(?:PMH(?:x)?|past|previous)\s*:?\s*(?:medical\s+)?h(?:istor)?y\s+of\s+"
    rf"(?:{_KNOWN_CANCER_SITE_TOKEN})\s*(?:cancer|carcinoma|ca\b)|"
    rf"history\s+of\s+(?:{_KNOWN_CANCER_SITE_TOKEN})\s*(?:cancer|carcinoma|ca\b)|"
    rf"previous(?:ly)?\s+(?:diagnosed|treated)\s+(?:with|for)\s+"
    rf"(?:{_KNOWN_CANCER_SITE_TOKEN})\s*(?:cancer|carcinoma|ca\b)|"
    r"post[-\s]+(?:mastectom\w+|prostatectom\w+|chemotherap\w+|radiotherap\w+)"
    r"\s+(?:recovery|follow[-\s]+up|review)|"
    rf"recovering\s+from\s+(?:{_KNOWN_CANCER_SITE_TOKEN})\s*(?:cancer|carcinoma|ca\b)|"
    r"referred\s+by\s+me\s+(?:on\s+2ww\s+)?(?:earlier\s+this\s+year|previously|"
    r"in\s+\d{4}|last\s+year)\s*(?:,?\s*confirmed\s+(?:breast|prostate|colorectal|"
    r"colon|rectal|bladder|kidney|renal|hepatic|pancreas|pancreatic|ovarian|"
    r"cervical|uterine|endometrial|gastric|oesophageal|esophageal|thyroid|"
    r"head\s+and\s+neck|lung|skin|liver|gynaecological|melanoma|lymphoma|"
    r"leuk(?:a|e)mia)?\s*(?:cancer|ca\b)?)?"
    r")",
    re.IGNORECASE,
)


def encounter_diagnosis_is_narrative_restatement(text: str) -> bool:
    """DI-LEO-AI-401 (Pattern N1): True when the encounter body has the
    unambiguous shape of a sick note (eMED3, MED3, "not fit for work")
    OR a "known X cancer" / "history of X" narrative restatement of an
    existing cancer diagnosis.

    Used by the diagnosis_confirmed anchor emission to tag the anchor
    with ``is_narrative_restatement: True``. The episode builder then
    rejects floating diagnosis-led EpisodeOfCare groups whose anchors
    are ALL narrative restatements -- preventing phantom episodes built
    from sick-note text and historical-mention text alone.

    The guard is INERT when the text is empty or when neither the
    sick-note nor the known-cancer pattern matches. It is intentionally
    NARROW: a real fresh diagnosis encounter (Problem: ... cancer ...,
    "newly diagnosed ...", "diagnosis confirmed today ...") will NOT
    match, so genuine first-time diagnosis_confirmed anchors are not
    suppressed.
    """
    if not text:
        return False
    return bool(
        _SICK_NOTE_RX.search(text) or _KNOWN_CANCER_RESTATEMENT_RX.search(text)
    )


# ---------------------------------------------------------------------------
# DI-LEO-AI-402 (Pattern N4): cancer-care-review restatement guard
# ---------------------------------------------------------------------------
# Pattern K (problem_list_code / malignancy_term_problem_line /
# active_cancer_care_code) fires diagnosis_confirmed on routine annual
# cancer-care-review encounters whose only "evidence" is the GP keeping
# the problem list current and writing a narrative that restates the
# already-known cancer history. A 2025-09-24 cancer-care-review
# encounter (restatement only, no new diagnosis) attached a phantom
# diagnosis_confirmed to the real referral-anchored episode, polluting
# the timeline with a duplicate diagnosis months after the genuine one.
#
# N1 only protects against FLOATING phantom episodes built entirely
# from restatements. N4 sits one layer deeper and stops the
# diagnosis_confirmed anchor from being EMITTED in the first place
# whenever the encounter is a cancer-care-review restatement that
# carries no fresh-diagnosis marker.
#
# The guard is INERT when the encounter explicitly marks a new
# diagnosis ("(New Episode)" on a problem-list line, "newly
# diagnosed", "new diagnosis of") so genuine fresh diagnoses on
# review encounters are still emitted.

# Cancer care review template marker. EMIS templates and free-text
# notes use the literal phrase "Cancer care review" (codes XaKHe /
# XaKI4 in ACTIVE_CANCER_CARE_CODES). Single hit is sufficient.
_CANCER_CARE_REVIEW_RX = re.compile(
    r"\bcancer\s+(?:care\s+)?review\b",
    re.IGNORECASE,
)

# Fresh-diagnosis markers. When any of these appear in the encounter
# the N4 guard is suppressed so a genuine new diagnosis on the same
# day as a review template still emits diagnosis_confirmed. The
# "(New Episode)" parenthetical is the canonical EMIS problem-list
# marker for a freshly added problem.
_NEW_EPISODE_MARKER_RX = re.compile(
    r"(?:"
    r"\(\s*new\s+episode\s*\)|"
    r"\bnewly\s+diagnosed\b|"
    r"\bnew\s+diagnosis\s+of\b|"
    r"\bdiagnosis\s+confirmed\s+today\b|"
    r"\bfirst\s+presentation\s+of\b|"
    r"\bnew\s+presentation\s+of\b"
    r")",
    re.IGNORECASE,
)


def encounter_has_new_episode_marker(text: str) -> bool:
    """DI-LEO-AI-402 (Pattern N4): True when the encounter text carries
    an unambiguous fresh-diagnosis marker -- the EMIS "(New Episode)"
    parenthetical on a problem-list line, or a phrase like "newly
    diagnosed", "new diagnosis of", "diagnosis confirmed today",
    "first presentation of", "new presentation of".

    Used by the cancer-care-review restatement guard to STAY INERT
    when the encounter really is recording a fresh diagnosis. Without
    this exception, a GP who runs a cancer care review template AND
    also adds a brand-new cancer to the problem list on the same
    encounter would lose the diagnosis_confirmed anchor.
    """
    if not text:
        return False
    return bool(_NEW_EPISODE_MARKER_RX.search(text))


def encounter_is_cancer_care_review_restatement(text: str) -> bool:
    """DI-LEO-AI-402 (Pattern N4): True when the encounter body is
    clearly a cancer-care-review restatement of a known cancer
    diagnosis and so any diagnosis_confirmed anchor emitted from a
    soft source (problem_list_code, active_cancer_care_code,
    cancer_follow_up_template, adjuvant_therapy_drug,
    malignancy_term_problem_line) should be SUPPRESSED.

    True when:
      - The text contains the explicit "Cancer care review" /
        "Cancer review" template marker, OR
      - The text matches the N1 known-cancer narrative restatement
        regex (``_KNOWN_CANCER_RESTATEMENT_RX``: "known X cancer",
        "history of X cancer", "PMHx history of X cancer", "post-
        mastectomy recovery review", etc.).

    INERT when:
      - Text is empty.
      - Neither the cancer-care-review template marker NOR the known-
        cancer narrative regex matches.
      - The encounter carries an unambiguous fresh-diagnosis marker
        (``encounter_has_new_episode_marker`` returns True). This
        keeps the guard safe on legitimate "review + new diagnosis"
        encounters where the GP runs the review template AND adds
        a brand-new cancer to the problem list on the same day.

    The sick-note signal is intentionally NOT included here -- N1
    already handles sick-note-only restatements via the floating-
    group filter, and a real fresh diagnosis recorded inside a sick-
    note encounter would otherwise be lost.
    """
    if not text:
        return False
    if encounter_has_new_episode_marker(text):
        return False
    return bool(
        _CANCER_CARE_REVIEW_RX.search(text)
        or _KNOWN_CANCER_RESTATEMENT_RX.search(text)
    )
