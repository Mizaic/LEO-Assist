"""Regex patterns for NCDA-style extraction from raw encounter text.

All patterns are applied to the free-text ``e['text']`` of :Encounter
nodes. They deliberately do NOT rely on any derived graph artefacts
(:EpisodeOfCare, :Disease domain tags, staging_confidence) which are
outputs of an earlier pipeline and cannot be trusted for ground truth.
"""

import re


# ---------------------------------------------------------------------------
# Presenting symptoms per cancer type -- captures the specific phrase match
# (not just presence/absence).
# ---------------------------------------------------------------------------
SYMPTOM_PATTERNS = {
    "breast": [
        (r"breast\s+lump", "Breast lump"),
        (r"breast.{0,30}pain", "Breast pain"),
        (r"nipple.{0,20}(discharge|change|inversion)", "Nipple change"),
        (r"breast.{0,20}(change|thickening|swelling|asymmetr)",
         "Breast change"),
    ],
    "lower_gi": [
        (r"rectal.{0,10}bleed|PR.{0,10}bleed|blood.{0,15}(stool|bowel|rectum)",
         "Rectal bleeding"),
        (r"change.{0,20}bowel|altered.{0,10}bowel|bowel.{0,15}(change|habit)",
         "Change in bowel habit"),
        (r"diarrhoea|loose.stool", "Diarrhoea"),
        (r"iron.deficien|anaemia.{0,15}iron", "Anaemia - iron deficiency"),
        (r"weight.loss", "Weight loss"),
        (r"FIT.{0,20}(positive|abnormal|raised|>)", "Abnormal FIT test"),
    ],
    "upper_gi": [
        (r"dysphagia|difficulty.{0,15}swallow|swallow.{0,20}(difficult|problem)",
         "Dysphagia"),
        (r"weight.loss", "Weight loss"),
        (r"epigastric", "Epigastric pain"),
        (r"vomiting|haematemesis", "Vomiting"),
        (r"melaena", "Melaena"),
        (r"heartburn.{0,30}(worsen|concern|alarm)", "Dyspepsia"),
    ],
    "lung": [
        (r"haemoptysis|blood.{0,10}cough|cough.{0,10}blood", "Haemoptysis"),
        (r"(persistent|chronic|ongoing).{0,15}cough", "Persistent cough"),
        (r"breathless.{0,20}(worsen|new|unexplain)", "Breathlessness"),
        (r"chest.{0,10}pain", "Chest pain"),
        (r"weight.loss|unexplained.{0,15}weight", "Weight loss"),
        (r"hoarse", "Hoarseness"),
    ],
    "prostate": [
        (r"PSA.{0,20}(raised|elevated|high|above)|raised.{0,10}PSA",
         "Raised PSA"),
        (r"urinary.{0,20}(frequency|hesitancy|stream|symptom)|LUTS|nocturia",
         "Urinary symptoms"),
        (r"haematuria|blood.{0,10}urine", "Haematuria"),
    ],
    "skin": [
        (r"(suspicious|changing|new).{0,15}(mole|lesion)",
         "Suspicious skin lesion"),
        (r"skin.{0,20}(lesion|lump|mole|growth|ulcer|nodule)", "Skin lesion"),
        (r"BCC|basal.cell", "Suspected basal cell carcinoma"),
        (r"SCC|squamous.cell", "Suspected squamous cell carcinoma"),
        (r"pigment.{0,15}(change|lesion)", "Pigmented lesion"),
    ],
    "head_neck": [
        (r"neck.{0,15}(lump|swelling|mass)|lump.{0,15}neck", "Neck lump"),
        (r"hoarse|voice.{0,15}change", "Hoarseness"),
        (r"mouth.{0,15}(ulcer|lump|problem)|tongue.{0,15}(ulcer|lump)",
         "Oral lesion"),
        (r"thyroid.{0,15}(lump|nodule|mass)", "Thyroid lump"),
        (r"difficulty.{0,10}swallow|globus", "Dysphagia"),
    ],
    "gynaecology": [
        (r"postmenopaus.{0,15}bleed|PMB", "Postmenopausal bleeding"),
        (r"vaginal.{0,15}bleed", "Abnormal vaginal bleeding"),
        (r"intermenstrual.{0,15}bleed", "Intermenstrual bleeding"),
        (r"pelvic.{0,15}(pain|mass|lump)", "Pelvic mass"),
        (r"cervical.{0,15}(lesion|abnormal|bleed)", "Cervical abnormality"),
        (r"vulval.{0,15}(itch|lump|ulcer)", "Vulval lesion"),
    ],
    "urology": [
        (r"haematuria|blood.{0,10}urine|frank.{0,5}haematuria", "Haematuria"),
        (r"testicular.{0,15}(lump|swelling|pain)|scrotal.{0,15}lump",
         "Testicular lump"),
        (r"bladder.{0,15}(lesion|tumour)", "Bladder lesion"),
        (r"renal.{0,15}(mass|lesion)", "Renal mass"),
    ],
    "haematology": [
        (r"lymph.{0,10}(node|adenopathy|swelling)|lymphadenopathy",
         "Lymphadenopathy"),
        (r"night.{0,5}sweat", "Night sweats"),
        (r"unexplained.{0,15}(fatigue|weight.loss|bruising)", "B symptoms"),
        (r"splenomegaly|hepatomegaly", "Organomegaly"),
        (r"FBC.{0,20}(abnormal|concern)|abnormal.{0,10}FBC",
         "Abnormal blood count"),
    ],
    "nss": [
        (r"weight.loss", "Unexplained weight loss"),
        (r"fatigue|malaise", "Unexplained fatigue"),
        (r"appetite", "Loss of appetite"),
        (r"unexplained.{0,20}symptom", "Non-specific symptoms"),
    ],
}


# ---------------------------------------------------------------------------
# Investigations ordered (pre-referral window)
# ---------------------------------------------------------------------------
INVESTIGATION_PATTERNS = [
    (re.compile(r"\bFBC\b|full\s+blood\s+count", re.I), "Blood test - FBC"),
    (re.compile(r"\bU&E\b|urea\s+and\s+electrolytes", re.I),
     "Blood test - U&E, eGFR"),
    (re.compile(r"\bLFT\b|liver\s+function", re.I),
     "Blood test - Liver function tests"),
    (re.compile(r"\bTFT\b|thyroid\s+function", re.I),
     "Blood test - Thyroid function"),
    (re.compile(r"\bPSA\b|prostate.specific", re.I),
     "Blood test - Cancer biomarker (PSA, CEA, CA125, CA19.9, other)"),
    (re.compile(r"\bCA125\b|\bCA\s*125\b", re.I),
     "Blood test - Cancer biomarker (PSA, CEA, CA125, CA19.9, other)"),
    (re.compile(r"\bCA19\.9\b|\bCA\s*19", re.I),
     "Blood test - Cancer biomarker (PSA, CEA, CA125, CA19.9, other)"),
    (re.compile(r"\bCEA\b", re.I),
     "Blood test - Cancer biomarker (PSA, CEA, CA125, CA19.9, other)"),
    (re.compile(r"\bCRP\b|\bESR\b|inflammatory\s+marker", re.I),
     "Blood test - Inflammatory marker (ESR, CRP)"),
    (re.compile(r"\bHbA1c\b|haemoglobin\s+a1c", re.I), "Blood test - HbA1c"),
    (re.compile(r"ferritin", re.I), "Blood test - Ferritin"),
    (re.compile(r"FIT.{0,10}(test|sample|result)|faecal\s+immunochem", re.I),
     "FIT test (Faecal immunochemical test)"),
    (re.compile(r"urine.{0,10}(sample|dipstick|MSU)|urinalysis", re.I),
     "Urine test"),
    (re.compile(r"\bECG\b|electrocardiogram", re.I), "Other - ECG"),
    (re.compile(r"(plain\s+)?(chest\s+)?x.ray|\bCXR\b", re.I),
     "Imaging - X-ray"),
    (re.compile(r"ultrasound|\bUSS\b|ultrasonogr", re.I),
     "Imaging - Ultrasound"),
    (re.compile(r"\bCT\s+scan|computed\s+tomography|CT\s+(chest|abdomen)",
                re.I), "Imaging - CT scan"),
    (re.compile(r"\bMRI\b|magnetic\s+resonance", re.I), "Imaging - MRI"),
    (re.compile(r"mammogram|mammograph", re.I), "Imaging - Mammogram"),
    (re.compile(r"colonoscop", re.I), "Endoscopy - Colonoscopy"),
    (re.compile(r"gastroscop|\bOGD\b", re.I), "Endoscopy - Gastroscopy"),
    (re.compile(r"sigmoidoscop", re.I), "Endoscopy - Sigmoidoscopy"),
    (re.compile(r"cystoscop", re.I), "Endoscopy - Cystoscopy"),
    (re.compile(r"bronchoscop", re.I), "Endoscopy - Bronchoscopy"),
    (re.compile(r"biops", re.I), "Biopsy"),
]


# ---------------------------------------------------------------------------
# Co-morbidities -- detected from pre-referral encounter text directly,
# not from derived :Disease domain tags (which we do not trust).
# ---------------------------------------------------------------------------
COMORBIDITY_PATTERNS = [
    (re.compile(
        r"hypertensi|high\s+blood\s+pressure|\bG2\.\.|\bG20\.\.|\bG21\.\.",
        re.I), "Hypertension"),
    (re.compile(
        r"diabet(es|ic)|\bT1DM\b|\bT2DM\b|\bC10\.\.|HbA1c.{0,30}(diagno|target)",
        re.I), "Diabetes"),
    (re.compile(
        r"\bCOPD\b|chronic\s+obstructive|emphysema|chronic\s+bronchitis",
        re.I), "COPD or other chronic respiratory illness"),
    (re.compile(
        r"\basthma\b|asthmat",
        re.I), "COPD or other chronic respiratory illness"),
    (re.compile(
        r"ischaemic.heart|\bIHD\b|angina|myocardial.infarct|\bMI\b|"
        r"heart.failure|\bCHF\b|atrial.fibrillat|\bAF\b|cardiovascular",
        re.I), "Cardiovascular disease"),
    (re.compile(
        r"stroke|\bCVA\b|cerebrovascular|\bTIA\b|transient.ischaemic",
        re.I), "Cerebrovascular disease"),
    (re.compile(
        r"chronic.kidney|\bCKD\b|renal.failure|renal.insuffic",
        re.I), "Chronic kidney disease"),
    (re.compile(
        r"depression|anxiety|bipolar|schizophren|psychosis|mental.health",
        re.I), "Mental health condition"),
    (re.compile(
        r"previous.{0,15}(cancer|malign|carcin)|history.{0,15}(cancer|malign)|"
        r"prior.{0,10}cancer",
        re.I), "Previous cancer"),
    (re.compile(
        r"dementia|alzheimer|cognitive.impair",
        re.I), "Dementia or cognitive impairment"),
]


# Note: cancer-stage detection lives in ``scripts/ncda_staging_adapter.py``
# which delegates to ``libs/staging/engine.py`` and the authoritative UICC
# 8th edition rules in ``configs/staging_rules``. We intentionally do NOT
# keep a parallel coarse stage regex here -- staging must go through the
# rule engine so TNM triplets are mapped correctly per cancer site.


# ---------------------------------------------------------------------------
# Safety netting -- detected from Read code Y281b or phrase
# ---------------------------------------------------------------------------
SAFETY_NETTING = re.compile(
    r"Y281b|Cancer\s+safety\s+netting|safety[- ]net\w+|safety.net.{0,30}"
    r"(advice|given|documented|plan)",
    re.I,
)


# ---------------------------------------------------------------------------
# Administrative / non-clinical encounter headers (skip these when counting
# clinical consultations).
# ---------------------------------------------------------------------------
ADMIN_HEADER = re.compile(
    r"^(Auto-filed|Surgery: Auto|Sent online|Scheduled Task|ETP2 FP10|"
    r"Short message|Administration|Reception|Medication review|"
    r"Presenting to non-clinical team|Activity: Clinical Intervention\s+"
    r"Unsuccessful)",
    re.I,
)


def detect_first_match(text, patterns):
    """Return first (label, match_text) from a list of (regex, label) pairs.

    Use for ordered pattern lists where the first match wins.
    """
    if not text:
        return None, None
    for pattern, label in patterns:
        m = pattern.search(text)
        if m:
            return label, m.group(0)
    return None, None


def detect_all_matches(text, patterns):
    """Return list of distinct labels for all matching patterns in text."""
    if not text:
        return []
    labels = []
    for pattern, label in patterns:
        if pattern.search(text) and label not in labels:
            labels.append(label)
    return labels


def detect_symptoms_for_type(text, cancer_type):
    """Return list of distinct presenting symptom labels for the cancer type."""
    patterns = SYMPTOM_PATTERNS.get(cancer_type, [])
    if not text or not patterns:
        return []
    labels = []
    for raw_pat, label in patterns:
        if re.search(raw_pat, text, re.I) and label not in labels:
            labels.append(label)
    return labels
