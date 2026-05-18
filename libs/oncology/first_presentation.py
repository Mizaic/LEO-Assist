"""First-presentation date inference for NCDA detector episodes.

Uses a text-keyword scan backwards from the episode anchor date (referral_date
for cohort 1a/1b; end_date for cohort 3) to find the earliest GP encounter
where the patient mentioned symptoms relevant to their cancer site.

This complements the SNOMED-anchored approach in
``services/analysis_worker/app/analyzers/episode_builder/_first_presentation.py``
for episodes that lack DOCUMENTS relationship links (all ncda_detector episodes).

NCDA definition: the date the patient first attended a healthcare professional
with the symptom(s) that led to the cancer diagnosis — typically a GP
consultation before the fast-track referral was issued.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Window constants — kept in sync with episode_builder/_config.py
# ---------------------------------------------------------------------------

#: Initial backwards scan from the episode anchor date (days).
LOOKBACK_DAYS: int = 90

#: Retry window if no match found within LOOKBACK_DAYS (days).
EXTENDED_LOOKBACK_DAYS: int = 180

# ---------------------------------------------------------------------------
# Site-specific symptom keyword sets
# ---------------------------------------------------------------------------
# Keywords are lowercase; matched via ``toLower(enc.text) CONTAINS 'kw'``.
# Each list is ordered: more specific / discriminating terms first so that
# the Cypher WHERE clause short-circuits on the most likely hits.
# The tokens differ from _SITE_TOKENS in silver_labeller.py — those target
# the FTR encounter; these target symptom-bearing GP consultations *before*
# the referral was issued.

_SITE_SYMPTOM_KEYWORDS: dict[str, list[str]] = {
    "urological": [
        "haematuria",
        "blood in urine",
        "blood in his urine",
        "blood in her urine",
        "nocturia",
        "frequency",
        "hesitancy",
        "luts",
        "weak stream",
        "urinary symptoms",
        "psa",
        "prostate",
        "bladder",
        "haematospermia",
        "loin pain",
        "renal mass",
    ],
    "breast": [
        "breast lump",
        "lump in breast",
        "breast pain",
        "nipple discharge",
        "breast change",
        "breast swelling",
        "breast mass",
        "skin change",
        "breast tenderness",
    ],
    "lung": [
        "haemoptysis",
        "coughing up blood",
        "persistent cough",
        "breathlessness",
        "shortness of breath",
        "chest pain",
        "dry cough",
        "recurrent chest infection",
        "wheezing",
        "hoarseness",
    ],
    "lower_gi": [
        "rectal bleeding",
        "blood in stool",
        "blood in his stool",
        "blood in her stool",
        "change in bowel habit",
        "altered bowel habit",
        "looser stools",
        "diarrhoea",
        "constipation",
        "fit positive",
        "iron deficiency",
        "iron deficient",
        "anaemia",
        "rectal mass",
        "abdominal mass",
    ],
    "upper_gi": [
        "dysphagia",
        "difficulty swallowing",
        "difficulty in swallowing",
        "heartburn",
        "indigestion",
        "dyspepsia",
        "epigastric pain",
        "weight loss",
        "vomiting",
        "nausea and vomiting",
        "haematemesis",
        "melaena",
        "oesophag",
        "gastric",
    ],
    "skin": [
        "skin lesion",
        "suspicious lesion",
        "mole",
        "pigmented lesion",
        "changing mole",
        "lump on skin",
        "skin lump",
        "basal cell",
        "squamous cell",
        "melanoma",
        "dermoscopy",
        "itching lesion",
    ],
    "head_neck": [
        "neck lump",
        "cervical lymph node",
        "lymph node in neck",
        "hoarseness",
        "voice change",
        "change in voice",
        "sore throat",
        "tongue",
        "dysphagia",
        "thyroid swelling",
        "thyroid lump",
        "epistaxis",
        "nasal obstruction",
        "otalgia",
    ],
    "gynaecological": [
        "postmenopausal bleeding",
        "post menopausal bleeding",
        "vaginal bleeding",
        "abnormal bleeding",
        "intermenstrual bleeding",
        "pelvic pain",
        "vaginal discharge",
        "pelvic mass",
        "bloating",
        "endometri",
        "ovarian",
        "cervix",
        "vulval",
    ],
    "haematological": [
        "lymphadenopathy",
        "lymph node",
        "night sweat",
        "night sweats",
        "splenomegaly",
        "lymphoma",
        "leukaemia",
        "myeloma",
        "bone pain",
        "fatigue",
        "weight loss",
        "pallor",
    ],
    "brain": [
        "headache",
        "seizure",
        "fit",
        "visual disturbance",
        "blurred vision",
        "weakness",
        "neurological",
        "confusion",
        "personality change",
        "memory loss",
        "focal neurology",
    ],
    "nss": [
        "weight loss",
        "unexplained weight loss",
        "fatigue",
        "night sweat",
        "malaise",
        "tiredness",
        "loss of appetite",
        "anorexia",
        "cachexia",
        "general deterioration",
    ],
}

# Generic fallback — used when site is absent or unrecognised.
_GENERIC_SYMPTOM_KEYWORDS: list[str] = [
    "pain",
    "bleeding",
    "lump",
    "mass",
    "weight loss",
    "fatigue",
    "haematuria",
    "dysphagia",
    "night sweat",
    "cough",
    "bowel",
    "headache",
    "nausea",
    "skin lesion",
    "mole",
    "hoarseness",
    "jaundice",
]


# ---------------------------------------------------------------------------
# Canonical cancer_type → symptom_site mapping
# ---------------------------------------------------------------------------
# Maps the NCDA CancerType string values (ep.cancer_type) to the symptom site
# key used in _SITE_SYMPTOM_KEYWORDS.  When cancer_type is known and specific,
# this takes precedence over ep.site (which reflects the referral pathway site
# and can be wrong when the FTR site differs from the final cancer type).

_CANCER_TYPE_TO_SYMPTOM_SITE: dict[str, str] = {
    "Prostate": "urological",
    "Bladder": "urological",
    "Renal": "urological",
    "Testicular": "urological",
    "Breast": "breast",
    "Lung": "lung",
    "Colorectal": "lower_gi",
    "Oesophageal": "upper_gi",
    "Stomach": "upper_gi",
    "Pancreatic": "upper_gi",
    "Liver": "upper_gi",
    "Gallbladder": "upper_gi",
    "Melanoma": "skin",
    "Cervical": "gynaecological",
    "Endometrial": "gynaecological",
    "Ovarian": "gynaecological",
    "Vulval": "gynaecological",
    "Lymphoma": "haematological",
    "Leukaemia": "haematological",
    "Myeloma": "haematological",
    "Brain": "brain",
    "Laryngeal": "head_neck",
    "Oropharyngeal": "head_neck",
    "Thyroid": "head_neck",
    # Sarcoma, Mesothelioma, Small Intestine etc. fall through to site-based lookup
}


def resolve_symptom_site(cancer_type: str, pathway_site: str) -> str:
    """Return the best symptom-keyword site key for this episode.

    cancer_type (the NCDA-classified type, e.g. "Colorectal") is authoritative
    when it maps cleanly.  pathway_site (the FTR linker site, e.g. "lower_gi")
    is used as fallback, which handles rarer types not in the explicit map.

    Args:
        cancer_type: Value of ``ep.cancer_type``.
        pathway_site: Value of ``ep.site``.

    Returns:
        A key present in ``_SITE_SYMPTOM_KEYWORDS``, or ``""`` (generic fallback).
    """
    if cancer_type and cancer_type in _CANCER_TYPE_TO_SYMPTOM_SITE:
        return _CANCER_TYPE_TO_SYMPTOM_SITE[cancer_type]
    site = (pathway_site or "").lower()
    if site in _SITE_SYMPTOM_KEYWORDS:
        return site
    return ""


# ---------------------------------------------------------------------------
# Cypher fragment builder
# ---------------------------------------------------------------------------


def build_fp_cypher_filter(site: str) -> str:
    """Return a Cypher boolean expression for encounter keyword matching.

    The expression operates on ``enc.text`` and can be embedded directly in a
    ``WHERE`` clause.  Keywords are lowercased and matched case-insensitively
    via ``toLower(enc.text) CONTAINS 'kw'``.

    Args:
        site: The episode ``site`` field (e.g. ``"urological"``, ``"breast"``).
              Unknown/empty values fall back to generic symptom keywords.

    Returns:
        A non-empty Cypher boolean expression string, always wrapped in
        parentheses, ready for use after ``AND``.
    """
    keywords = _SITE_SYMPTOM_KEYWORDS.get(site, _GENERIC_SYMPTOM_KEYWORDS)
    # Escape single quotes defensively (keywords are hardcoded constants, but
    # belt-and-braces avoids a syntax error if a keyword ever contains one).
    clauses = [
        f"toLower(enc.text) CONTAINS '{kw.replace(chr(39), chr(39) + chr(39))}'"
        for kw in keywords
    ]
    return "(" + " OR ".join(clauses) + ")"
