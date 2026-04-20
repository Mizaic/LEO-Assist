"""Cancer-type specialty markers for clinical text scoping.

Maps canonical NCDA cancer-site keys (as produced by
``services.analysis_worker.app.analyzers.episode_builder._site_resolution``)
to compiled regex patterns that identify specialty-specific terminology.
Used to filter encounter text to only those records relevant to a given
cancer type - e.g. to prevent prostate Gleason scores from contaminating
a lower-GI episode's stage derivation.

See DI-LEO-AI-126 and R-LEO-AI-086.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# NOTE: Site keys MUST match the canonical set produced by
# _site_resolution._SITE_MAP + _SITE_BY_CONCEPT_ID. If a site key appears
# on an EpisodeOfCare.cancer_type but has no marker here the code must
# gracefully fall back to unfiltered matching (see filter_rows_by_specialty).
SPECIALTY_MARKERS: dict[str, re.Pattern[str]] = {
    # DI-LEO-AI-138 (legacy local id; canonical in Atlas via
    # compliance/atlas-migration-evidence/atlas-id-mapping.csv).
    # Broadens the breast marker. Derived from an audit of 60 breast-
    # episode encounter texts (see compliance/atlas-migration-evidence/
    # audits-source-evidence/snapshots/2026-04-pre-fragmentation-fix.md).
    # The extra anchors cover: endocrine therapy names (letrozole,
    # anastrozole, tamoxifen, exemestane) which index-date many breast
    # pathways; "infiltrating duct" phrasing that stops short of
    # "ductal"; BRCA-mutation, triple-negative and axilla / sentinel
    # node phrases that are almost exclusively breast-care. Kept
    # greedy enough to catch clinician free-text but never generic
    # enough to fire on unrelated domains.
    "breast": re.compile(
        r"\bbreast\b|\bnipple\b|mammogra|mastectom|lumpectom|oncoplas"
        r"|\bDCIS\b|\bLCIS\b|invasive\s+(?:ductal|lobular)"
        r"|\bHER2\b|oestrogen\s+receptor|\bER\s*[+\-/]\s*ve\b"
        r"|\bPR\s*[+\-/]\s*ve\b|Ca\s+breast"
        r"|\b(?:letrozole|anastrozole|exemestane|tamoxifen)\b"
        r"|infiltrating\s+duct(?:al)?|triple[\s-]?negative"
        r"|\bBRCA\s*[12]?\b|\baxilla(?:ry)?\b|sentinel\s+(?:node|lymph)"
        r"|tumour\s+bed|fast\s+track\s+[^\n]*breast",
        re.I,
    ),
    "lung": re.compile(
        r"\blung\b|respirator|bronchosc|\bCT\s+chest\b|pulmonar|thoraci"
        r"|haemoptys|mesotheli",
        re.I,
    ),
    "colorectal": re.compile(
        r"\bbowel\b|colorectal|\bcolon\b|\brectu?m\b|\brectal\b|sigmoid"
        r"|colonoscop|flexible\s+sig|\bFIT\b|\banal\b|\banus\b|caecum|cecum"
        r"|\bLGI\b|lower\s+gi|lower\s+gastrointestinal",
        re.I,
    ),
    "upper_gi": re.compile(
        r"upper\s+gi|\bUGI\b|upper\s+gastrointestinal|oesophag|esophag"
        r"|gastric|stomach|gastroscop|endoscop|\bOGD\b|dysphagia",
        re.I,
    ),
    "prostate": re.compile(
        r"\bprostate\b|prostatic|\bPSA\b|transurethral|\bTRUS\b|gleason" r"|\bDRE\b",
        re.I,
    ),
    "bladder": re.compile(
        r"\bbladder\b|urothelial|haematuri|\bureter\w*\b|urethra" r"|cystoscop|urolog",
        re.I,
    ),
    "renal": re.compile(
        r"\brenal\b|\bkidney\b|nephre[ct]tom|\bRCC\b|nephrolog",
        re.I,
    ),
    "testicular": re.compile(
        r"testic|testis|scrot|\borch|epididym",
        re.I,
    ),
    "melanoma": re.compile(
        r"\bskin\b|dermatol|melanoma|\bBCC\b|\bSCC\b|pigmented\s+lesion"
        r"|suspicious\s+(?:mole|lesion|naev)",
        re.I,
    ),
    "head_and_neck": re.compile(
        r"head\s+and\s+neck|head.?and.?neck|\bENT\b|ear.?nose.?throat"
        r"|laryng|pharyng|oropharyn|hypopharyn|nasopharyn|tonsil|salivary"
        r"|parotid|hoarse|tongue|oral\s+cavity|thyroid"
        r"|neck\s+(?:lump|swelling|mass|node)",
        re.I,
    ),
    "thyroid": re.compile(
        r"\bthyroid\b|goitre|goiter|thyroidec|\bTSH\b|thyroxine",
        re.I,
    ),
    "laryngeal": re.compile(
        r"laryng|\bvocal\b|glottis|epiglott",
        re.I,
    ),
    "oropharyngeal": re.compile(
        r"pharyng|oropharyn|hypopharyn|nasopharyn|tonsil|salivary|parotid"
        r"|oral\s+cavity|\btongue\b|\blip\b",
        re.I,
    ),
    "gynaecological": re.compile(
        r"gynae|gyneco|cervi[cx]|ovar|uter|endometri|vulva|vagin|fallopian"
        r"|colposcop",
        re.I,
    ),
    "cervical": re.compile(
        r"cervi[cx]|colposcop|\bsmear\b|\bCIN\s?\d",
        re.I,
    ),
    "endometrial": re.compile(
        r"endometr|uter|menopaus.{0,20}bleed|post.{0,5}menopausal\s+bleed" r"|\bPMB\b",
        re.I,
    ),
    "ovarian": re.compile(
        r"ovar|fallopian|\bCA[\s-]?125\b|pelvic\s+mass",
        re.I,
    ),
    "vulval": re.compile(
        r"vulva|vagin",
        re.I,
    ),
    "haematological": re.compile(
        r"haematol|hematol|lympho|leuka?emi|myelo|plasma\s+cell" r"|Haem\s+Triage",
        re.I,
    ),
    "lymphoma": re.compile(
        r"lympho|hodgkin|non.?hodgkin|\bNHL\b|\bHL\b",
        re.I,
    ),
    "leukaemia": re.compile(
        r"leuka?emi|\bAML\b|\bCML\b|\bCLL\b"
        r"|\bALL\s+(?:leukaemia|leukemia)\b"
        r"|lymphoblast|myeloblast|\bblasts?\s+(?:in|seen|present)\b",
        re.I,
    ),
    "myeloma": re.compile(
        r"myeloma|plasma\s+cell|paraprotein|\bMGUS\b",
        re.I,
    ),
    "pancreatic": re.compile(
        r"pancrea",
        re.I,
    ),
    "oesophageal": re.compile(
        r"oesophag|esophag|dysphagia",
        re.I,
    ),
    "stomach": re.compile(
        r"\bgastric\b|\bstomach\b|Ca\s+(?:of\s+)?stomach|gastroscop" r"|\bOGD\b",
        re.I,
    ),
    "liver": re.compile(
        r"\bliver\b|hepat|\bHCC\b|cirrho",
        re.I,
    ),
    "gallbladder": re.compile(
        r"gallbladder|biliary|cholangio",
        re.I,
    ),
    "sarcoma": re.compile(
        r"sarcoma|\bGIST\b|soft\s+tissue\s+(?:mass|tumour|tumor)",
        re.I,
    ),
    "brain": re.compile(
        r"\bbrain\b|glioma|meningioma|intracran|\bCT\s+head\b|\bMRI\s+head\b"
        r"|astrocytoma",
        re.I,
    ),
    "mesothelioma": re.compile(
        r"mesotheli|asbestos",
        re.I,
    ),
    "small_intestine": re.compile(
        r"small\s+(?:bowel|intestin)|duoden",
        re.I,
    ),
    "non_site_specific": re.compile(
        r"non.?site.?specific|\bNSS\b|unexplained\s+weight|vague\s+symptom"
        r"|fast\s+track|\b2WW\b|two.?week.?wait|suspected\s+cancer"
        r"|non.?specific\s+(?:signs|symptoms)",
        re.I,
    ),
    "childrens_tumour": re.compile(
        r"paediatr|pediatr|child(?:ren)?'?s?\s*(?:tumour|tumor|cancer|oncolog)",
        re.I,
    ),
    "urological": re.compile(
        r"urolog|\bbladder\b|prostat|renal|\bkidney\b|testic|haematuri",
        re.I,
    ),
}


def specialty_for(cancer_type: str) -> re.Pattern[str] | None:
    """Return the compiled specialty marker for a cancer_type, or None if unknown.

    Accepts None / empty string gracefully.
    """
    if not cancer_type:
        return None
    return SPECIALTY_MARKERS.get(cancer_type)


def filter_rows_by_specialty(
    rows: Iterable[dict[str, Any]],
    cancer_type: str,
    text_key: str = "encounter_text",
) -> list[dict[str, Any]]:
    """Filter a sequence of row dicts to only those whose ``text_key`` field
    matches the cancer_type's specialty marker.

    Fallback behaviour:
      - If no marker is defined for ``cancer_type``, log DEBUG and return
        the unfiltered list so staging coverage is preserved for rare
        cancer types without markers.
      - If a marker exists but zero rows match, log WARNING and return
        the unfiltered list so we do not lose evidence entirely.

    The caller is expected to treat a WARNING fallback as a signal that
    the specialty marker library may need extending for that cancer type.
    """
    rows_list = list(rows)
    if not cancer_type:
        return rows_list
    marker = SPECIALTY_MARKERS.get(cancer_type)
    if marker is None:
        logger.debug(
            "No specialty marker defined for cancer_type=%s; "
            "staging will use unfiltered evidence",
            cancer_type,
        )
        return rows_list
    matched = [r for r in rows_list if marker.search(str(r.get(text_key) or ""))]
    if not matched:
        logger.warning(
            "Specialty marker for cancer_type=%s matched 0 rows out of %d; "
            "falling back to unfiltered evidence",
            cancer_type,
            len(rows_list),
        )
        return rows_list
    return matched
