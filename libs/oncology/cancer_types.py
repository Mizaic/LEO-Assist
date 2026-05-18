"""Canonical NCDA cancer-type vocabulary (DI-5CAC6D73).

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Single source of truth for every cancer-site / cancer-type string the
EpisodeOfCare nodes may carry on ``cancer_type`` or ``suspected_site``.
Producers (the segmenter LLM and the writer) MUST emit a value from
``CANONICAL_CANCER_TYPES``. Consumers (audit endpoints, dashboards, UI)
MUST run any ingested string through :func:`normalise_cancer_type` so
historic data and any escape-hatch free-text are coerced into the
canonical spelling.

The list mirrors the NCDA / NHS Cancer Waiting Times tumour categories
shown to clinicians in the data-entry forms, plus three sentinel values
for the cases the form does not enumerate:

  - ``Other``           cancer outside the standard NCDA list (e.g.
                         salivary gland, anal-canal-only context where
                         lower-GI mapping is wrong).
  - ``Unknown Primary``  the site genuinely cannot be determined from
                         the encounter text.
  - ``No Information``   no clinical evidence at all (timeline contains
                         only admin echoes).

Mirrored in TypeScript at ``services/ui/src/lib/cancerTypes.ts``. The
contract test ``tests/contracts/test_cancer_type_vocabulary.py`` parses
the TS file and asserts the two stay aligned, and asserts no production
file outside an allowlist contains a forbidden hardcoded site string.
"""

from __future__ import annotations

from enum import Enum


class CancerType(str, Enum):
    """Every legal value of ``EpisodeOfCare.cancer_type``."""

    BLADDER = "Bladder"
    BRAIN = "Brain"
    BREAST = "Breast"
    CERVICAL = "Cervical"
    COLORECTAL = "Colorectal"
    ENDOMETRIAL = "Endometrial"
    GALLBLADDER = "Gallbladder"
    LARYNGEAL = "Laryngeal"
    LEUKAEMIA = "Leukaemia"
    LIVER = "Liver"
    LUNG = "Lung"
    LYMPHOMA = "Lymphoma"
    MELANOMA = "Melanoma"
    MESOTHELIOMA = "Mesothelioma"
    MYELOMA = "Myeloma"
    OESOPHAGEAL = "Oesophageal"
    OROPHARYNGEAL = "Oropharyngeal"
    OVARIAN = "Ovarian"
    PANCREATIC = "Pancreatic"
    PROSTATE = "Prostate"
    RENAL = "Renal"
    SARCOMA = "Sarcoma"
    SMALL_INTESTINE = "Small Intestine"
    STOMACH = "Stomach"
    TESTICULAR = "Testicular"
    THYROID = "Thyroid"
    VULVAL = "Vulval"
    OTHER = "Other"
    UNKNOWN_PRIMARY = "Unknown Primary"
    NO_INFORMATION = "No Information"


CANONICAL_CANCER_TYPES: tuple[str, ...] = tuple(c.value for c in CancerType)
"""Display order matches the NCDA data-entry form shown to clinicians."""


CANONICAL_CANCER_TYPE_SET: frozenset[str] = frozenset(CANONICAL_CANCER_TYPES)


# -- Raw -> canonical map --------------------------------------------------
#
# Every key here is the lower-cased, whitespace-stripped form of a value
# observed on the live graph (or a near-synonym we expect a producer to
# emit). Keep this map together with the migration script so the two
# definitions cannot drift.

_RAW_TO_CANONICAL: dict[str, str] = {
    # already-canonical (case-insensitive)
    **{c.lower(): c for c in CANONICAL_CANCER_TYPES},
    # Single-site, single-word forms produced by the legacy LLM segmenter
    "breast": CancerType.BREAST.value,
    "colorectal": CancerType.COLORECTAL.value,
    "lung": CancerType.LUNG.value,
    "prostate": CancerType.PROSTATE.value,
    "brain": CancerType.BRAIN.value,
    "liver": CancerType.LIVER.value,
    "thyroid": CancerType.THYROID.value,
    "cervix": CancerType.CERVICAL.value,
    "endometrium": CancerType.ENDOMETRIAL.value,
    "endometrial": CancerType.ENDOMETRIAL.value,
    "kidney": CancerType.RENAL.value,
    "renal": CancerType.RENAL.value,
    "oesophagus": CancerType.OESOPHAGEAL.value,
    "stomach": CancerType.STOMACH.value,
    "ovary": CancerType.OVARIAN.value,
    "ovarian": CancerType.OVARIAN.value,
    "vulva": CancerType.VULVAL.value,
    "vulval": CancerType.VULVAL.value,
    "testis": CancerType.TESTICULAR.value,
    "testicular": CancerType.TESTICULAR.value,
    "bladder": CancerType.BLADDER.value,
    "pancreas": CancerType.PANCREATIC.value,
    "pancreatic": CancerType.PANCREATIC.value,
    "gallbladder": CancerType.GALLBLADDER.value,
    "small intestine": CancerType.SMALL_INTESTINE.value,
    "small bowel": CancerType.SMALL_INTESTINE.value,
    "larynx": CancerType.LARYNGEAL.value,
    "laryngeal": CancerType.LARYNGEAL.value,
    "oropharynx": CancerType.OROPHARYNGEAL.value,
    "oropharyngeal": CancerType.OROPHARYNGEAL.value,
    "melanoma": CancerType.MELANOMA.value,
    "mesothelioma": CancerType.MESOTHELIOMA.value,
    "myeloma": CancerType.MYELOMA.value,
    "leukaemia": CancerType.LEUKAEMIA.value,
    "leukemia": CancerType.LEUKAEMIA.value,
    "lymphoma": CancerType.LYMPHOMA.value,
    "sarcoma": CancerType.SARCOMA.value,
    # Skin -- in the current cohort every "skin" episode is dermatology
    # / suspected melanoma. Non-melanoma skin cancers are rare in the
    # data; if they appear the LLM will emit Other under the constrained
    # enum.
    "skin": CancerType.MELANOMA.value,
    # Head & neck -- map to Oropharyngeal as the most common subsite
    # unless the more-specific rule below routes elsewhere.
    "head and neck": CancerType.OROPHARYNGEAL.value,
    "head & neck": CancerType.OROPHARYNGEAL.value,
    "head_neck": CancerType.OROPHARYNGEAL.value,
    "thyroid/neck (non-site-specific pathway)": CancerType.THYROID.value,
    # Anal cancer sits under the lower-GI / colorectal MDT pathway.
    "anal": CancerType.COLORECTAL.value,
    # Upper-GI is a referral pathway, not a site. Surface as Other and
    # let the constrained LLM pick a specific site for new episodes.
    "upper gi": CancerType.OTHER.value,
    "upper_gi": CancerType.OTHER.value,
    "upper gastrointestinal": CancerType.OTHER.value,
    # Gastric / oesophageal junction -- record under Oesophageal because
    # the dominant body of evidence in the audited records was the
    # oesophageal subsite.
    "gastric/oesophageal": CancerType.OESOPHAGEAL.value,
    "stomach/oesophagus (junctional)": CancerType.OESOPHAGEAL.value,
    # Urological pathway covers Bladder/Renal/Testicular -- without
    # site-specific evidence we record Other rather than guess. Specific
    # combos like "urinary bladder / prostate" go to Prostate (the
    # tumour confirmed for that patient in the audit data).
    "urological": CancerType.OTHER.value,
    "prostate_urological": CancerType.OTHER.value,
    "urinary bladder / prostate": CancerType.PROSTATE.value,
    # Gynaecological pathway covers Cervical/Endometrial/Ovarian/Vulval.
    # Generic gynae goes to Other; site-specific subforms route to the
    # right canonical entry.
    "gynaecological": CancerType.OTHER.value,
    "gynae": CancerType.OTHER.value,
    "gynaecological (cervix)": CancerType.CERVICAL.value,
    # Haematology -- best fit is Lymphoma for the existing cohort
    # entries; future episodes will go through the constrained enum.
    "haematology": CancerType.LYMPHOMA.value,
    "hematology": CancerType.LYMPHOMA.value,
    "haematology (lymphoma)": CancerType.LYMPHOMA.value,
    "haematological": CancerType.LYMPHOMA.value,
    "lymphoid": CancerType.LYMPHOMA.value,
    "lymph node / mediastinal mass (pediatric)": CancerType.LYMPHOMA.value,
    # Non-site-specific (NSS) 2WW pathway -- not a tumour site, surface as Other.
    "nss": CancerType.OTHER.value,
    "non-site-specific": CancerType.OTHER.value,
    "non_site_specific": CancerType.OTHER.value,
    # Salivary gland -- not in the NCDA list; surface as Other.
    "salivary gland": CancerType.OTHER.value,
    # Cardiac -- almost certainly mis-classified as a cancer. Surface
    # as Other so it shows up for clinical review rather than getting
    # silently dropped.
    "cardiac": CancerType.OTHER.value,
    "brain_cns": CancerType.BRAIN.value,
    "lower_gi": CancerType.COLORECTAL.value,
    # Catch-all sentinels.
    "unknown": CancerType.UNKNOWN_PRIMARY.value,
    "unknown primary": CancerType.UNKNOWN_PRIMARY.value,
    "no information": CancerType.NO_INFORMATION.value,
    "other": CancerType.OTHER.value,
    "": CancerType.NO_INFORMATION.value,
}


import re as _re

# ---------------------------------------------------------------------------
# Dx-text → specific NCDA type inference
# ---------------------------------------------------------------------------
#
# Each tuple is (compiled_regex, canonical_CancerType_value).
# Patterns are ordered from most-specific Read code first, then text phrases.
# The function returns the FIRST match so order matters: prostate before
# general urological, oesophageal before general upper-GI, etc.

_DX_TEXT_TYPE_PATTERNS: list[tuple["_re.Pattern[str]", str]] = [
    # Prostate
    (_re.compile(r"B46\b|X78Y6|malignant tumour of prostate|carcinoma of prostate"
                 r"|prostate\s+(?:cancer|carcinoma|adenocarcinoma)", _re.I), CancerType.PROSTATE.value),
    # Bladder
    (_re.compile(r"X78j2|transitional cell carcinoma of bladder"
                 r"|bladder\s+(?:cancer|tcc|carcinoma|tumor|tumour)|TURBT\b", _re.I), CancerType.BLADDER.value),
    # Renal / Kidney
    (_re.compile(r"X78Yx|clear cell carcinoma of kidney"
                 r"|renal\s+cell\s+carcinoma|renal\s+(?:cancer|carcinoma)"
                 r"|kidney\s+(?:cancer|carcinoma)", _re.I), CancerType.RENAL.value),
    # Testicular
    (_re.compile(r"testicular\s+(?:cancer|carcinoma|tumour|tumor)"
                 r"|germ\s+cell\s+(?:cancer|tumour|tumor)", _re.I), CancerType.TESTICULAR.value),
    # Oesophageal (before general stomach/gastric to catch GOJ adenocarcinoma)
    (_re.compile(r"Xa0DF|adenocarcinoma of oesophag"
                 r"|oesophag(?:us|eal)\s+(?:cancer|carcinoma|adenocarcinoma)"
                 r"|GOJ.*adenocarcinoma|oesophagectomy.*adenocarcinoma"
                 r"|adenocarcinoma.*oesophag", _re.I), CancerType.OESOPHAGEAL.value),
    # Stomach / Gastric
    (_re.compile(r"X78gA|carcinoma of stomach"
                 r"|gastric\s+(?:cancer|carcinoma)|stomach\s+(?:cancer|carcinoma)", _re.I), CancerType.STOMACH.value),
    # Pancreatic
    (_re.compile(r"pancrea(?:tic|s)\s+(?:cancer|carcinoma|adenocarcinoma)", _re.I), CancerType.PANCREATIC.value),
    # Liver
    (_re.compile(r"hepatocellular\s+carcinoma"
                 r"|liver\s+(?:cancer|carcinoma)|hepatic\s+(?:cancer|carcinoma)", _re.I), CancerType.LIVER.value),
    # Colorectal (colon / rectum / caecum / anal)
    (_re.compile(r"B13\b|XE1vW|X78gM|X78gS"
                 r"|malignant tumour of (?:colon|rectum)"
                 r"|carcinoma of (?:colon|caecum|rectum|sigmoid|ascending)"
                 r"|colorectal|colon\s+(?:cancer|carcinoma)"
                 r"|rectal\s+(?:cancer|carcinoma)|anal\s+(?:cancer|carcinoma|margin)"
                 r"|squamous cell carcinoma of anal", _re.I), CancerType.COLORECTAL.value),
    # Endometrial / Uterine
    (_re.compile(r"B4302|BB5j2|endometri(?:um|al|oid)"
                 r"|uterine?\s+(?:cancer|carcinoma)|corpus\s+uteri", _re.I), CancerType.ENDOMETRIAL.value),
    # Cervical
    (_re.compile(r"X78Xg|adenocarcinoma of cervix"
                 r"|cervix\s+(?:cancer|carcinoma)|cervical\s+(?:cancer|carcinoma)|CGIN\b", _re.I), CancerType.CERVICAL.value),
    # Ovarian
    (_re.compile(r"ovari(?:an|um)\s+(?:cancer|carcinoma)"
                 r"|ovary\s+(?:cancer|carcinoma)", _re.I), CancerType.OVARIAN.value),
    # Vulval
    (_re.compile(r"vulv(?:al|a)\s+(?:cancer|carcinoma)", _re.I), CancerType.VULVAL.value),
    # Thyroid
    (_re.compile(r"X78cQ|B53\b|papillary thyroid"
                 r"|thyroid\s+(?:cancer|carcinoma)|thyroidectomy.*carcinoma"
                 r"|hemithyroidectomy.*(?:papillary|carcinoma)", _re.I), CancerType.THYROID.value),
    # Leukaemia (before Lymphoma — CLL is more specific)
    (_re.compile(r"B641\b|chronic lymphoid leukaemia|leuka?emia|CLL\b", _re.I), CancerType.LEUKAEMIA.value),
    # Lymphoma
    (_re.compile(r"Xa99l|malignant lymphoma|small lymphocytic|B.cell lymphoma"
                 r"|T.cell lymphoma|Hodgkin|lymphoma", _re.I), CancerType.LYMPHOMA.value),
    # Myeloma
    (_re.compile(r"multiple myeloma|myeloma", _re.I), CancerType.MYELOMA.value),
    # Mesothelioma
    (_re.compile(r"mesothelioma", _re.I), CancerType.MESOTHELIOMA.value),
    # Sarcoma
    (_re.compile(r"sarcoma", _re.I), CancerType.SARCOMA.value),
    # Gallbladder
    (_re.compile(r"gallbladder.*carcinoma|carcinoma of gallbladder", _re.I), CancerType.GALLBLADDER.value),
    # Lung (before Melanoma — avoid matching "lung metastasis" text)
    (_re.compile(r"lung\s+(?:cancer|carcinoma|adenocarcinoma)"
                 r"|pulmonary\s+(?:cancer|carcinoma)"
                 r"|non.small.cell\s+lung|NSCLC\b|small.cell\s+lung", _re.I), CancerType.LUNG.value),
    # Breast
    (_re.compile(r"X78WM|X78WW|BB91\b"
                 r"|malignant tumour of breast|malignant neoplasm of breast"
                 r"|infiltrating duct carcinoma|intraductal carcinoma"
                 r"|ductal\s+carcinoma|breast\s+(?:cancer|carcinoma)", _re.I), CancerType.BREAST.value),
    # Oropharyngeal (catch-all for head-and-neck SCC) MUST run BEFORE the
    # Melanoma/skin SCC catch-all below, so that "squamous cell carcinoma
    # of buccal mucosa" (X78Ig) is correctly typed as Oropharyngeal rather
    # than Melanoma.  Without this ordering the Melanoma regex's
    # "squamous.cell.carcinoma.*(?:...|lip|buccal mucosa)" branch wins
    # because it appears earlier in the list, and the resulting episode
    # carries cancer_type='Melanoma' for a clinically head-and-neck cancer
    # (see patient 4802297327: SCC buccal mucosa was being typed as
    # Melanoma in the graph).  We also strip "buccal" / "buccal mucosa"
    # from the Melanoma branch so the two regexes do not silently fight.
    (_re.compile(r"X78Ig|squamous cell carcinoma of buccal"
                 r"|oropharyn|nasopharyn|laryn(?:x|geal)"
                 r"|oral\s+(?:cancer|carcinoma)|buccal\s+mucosa", _re.I), CancerType.OROPHARYNGEAL.value),
    # Melanoma / Skin (BCC, SCC, lentigo — catch-all for skin malignancies)
    (_re.compile(r"XaCIv|Xa99Y|7G03J|XaXD8|XaXCZ|Xa98G"
                 r"|malignant melanoma|lentigo.maligna|melanoma"
                 r"|basal.cell.carcinoma"
                 r"|squamous.cell.carcinoma.*(?:scalp|skin|back|face|arm|ear|neck|lip)"
                 r"|excision of melanoma|squamous cell carcinoma.*mucosal", _re.I), CancerType.MELANOMA.value),
]


def infer_cancer_type_from_dx_text(site: str, dx_text: str) -> str:
    """Derive a specific NCDA cancer type from a diagnosis encounter text.

    Uses Read-code patterns and clinical phrases in ``dx_text`` to narrow a
    pathway-group site (e.g. ``'urological'``) down to a specific NCDA type
    (e.g. ``'Prostate'``).  Falls back to :func:`normalise_cancer_type` when
    no pattern matches.

    Suitable for use at write-back time when the dx encounter text is available.
    """
    for pattern, canonical in _DX_TEXT_TYPE_PATTERNS:
        if pattern.search(dx_text):
            return canonical
    return normalise_cancer_type(site)


def normalise_cancer_type(raw: str | None) -> str:
    """Coerce any raw ``cancer_type`` / ``suspected_site`` string to canonical.

    Returns ``CancerType.NO_INFORMATION`` for ``None`` or empty input,
    a matching canonical value for known synonyms, and
    ``CancerType.OTHER`` for any unrecognised non-empty value. Pure
    function, safe to call on every read path.
    """

    if raw is None:
        return CancerType.NO_INFORMATION.value
    key = str(raw).strip().lower()
    if not key:
        return CancerType.NO_INFORMATION.value
    canonical = _RAW_TO_CANONICAL.get(key)
    if canonical is not None:
        return canonical
    return CancerType.OTHER.value


def is_canonical(raw: str | None) -> bool:
    """True when ``raw`` is already an exact canonical value."""

    return raw in CANONICAL_CANCER_TYPE_SET


def synonyms_for(canonical_types: list[str]) -> list[str]:
    """Return all raw graph values that normalise to any of the given canonical types.

    Use this when building Cypher ``IN`` filters so that both ``'breast'`` and
    ``'Breast'`` (and any other legacy spelling) are matched when the caller
    asks for ``CancerType.BREAST``.

    The returned list always includes the canonical values themselves, so the
    result is safe to use as a drop-in replacement for the input list.
    """
    targets: frozenset[str] = frozenset(
        normalise_cancer_type(c) for c in canonical_types
    )
    expanded: set[str] = set(canonical_types)
    for raw, canonical in _RAW_TO_CANONICAL.items():
        if canonical in targets:
            expanded.add(raw)
            # Also add title-cased form in case graph has e.g. "Head_Neck"
            expanded.add(raw.title())
    return list(expanded)


# -- Canonical cancer-type -> NCDA pathway / detector site key ---------------
#
# The detector emits ``EpisodeOfCare.site`` from a small enum of NCDA
# pathway-group keys (see services/analysis_worker/app/ncda_detector site
# resolvers): breast, lower_gi, upper_gi, urological, gynaecological,
# head_neck, haematological, lung, brain, sarcoma, skin, nss, unknown.
# Reviewed episodes carry only ``cancer_type`` (canonical or free-text);
# this map projects a cancer_type to its detector-site key so the two can
# be compared in the reviewed-guard / cross-site checks.
_CANCER_TYPE_TO_DETECTOR_SITE: dict[str, str] = {
    CancerType.BLADDER.value: "urological",
    CancerType.BRAIN.value: "brain",
    CancerType.BREAST.value: "breast",
    CancerType.CERVICAL.value: "gynaecological",
    CancerType.COLORECTAL.value: "lower_gi",
    CancerType.ENDOMETRIAL.value: "gynaecological",
    CancerType.GALLBLADDER.value: "upper_gi",
    CancerType.LARYNGEAL.value: "head_neck",
    CancerType.LEUKAEMIA.value: "haematological",
    CancerType.LIVER.value: "upper_gi",
    CancerType.LUNG.value: "lung",
    CancerType.LYMPHOMA.value: "haematological",
    CancerType.MELANOMA.value: "skin",
    CancerType.MESOTHELIOMA.value: "lung",
    CancerType.MYELOMA.value: "haematological",
    CancerType.OESOPHAGEAL.value: "upper_gi",
    CancerType.OROPHARYNGEAL.value: "head_neck",
    CancerType.OVARIAN.value: "gynaecological",
    CancerType.PANCREATIC.value: "upper_gi",
    CancerType.PROSTATE.value: "urological",
    CancerType.RENAL.value: "urological",
    CancerType.SARCOMA.value: "sarcoma",
    CancerType.SMALL_INTESTINE.value: "lower_gi",
    CancerType.STOMACH.value: "upper_gi",
    CancerType.TESTICULAR.value: "urological",
    CancerType.THYROID.value: "head_neck",
    CancerType.VULVAL.value: "gynaecological",
    CancerType.OTHER.value: "unknown",
    CancerType.UNKNOWN_PRIMARY.value: "unknown",
    CancerType.NO_INFORMATION.value: "unknown",
}


def cancer_type_to_detector_site(raw: str | None) -> str:
    """Map any cancer_type / suspected_site string to a detector-site key.

    Coerces ``raw`` through :func:`normalise_cancer_type` first, then maps
    the canonical cancer type to the detector pathway-group key (e.g.
    ``"Prostate" -> "urological"``, ``"Melanoma" -> "skin"``).  Returns
    ``"unknown"`` for ``Other``, ``Unknown Primary`` or unrecognised input.
    """
    canonical = normalise_cancer_type(raw)
    return _CANCER_TYPE_TO_DETECTOR_SITE.get(canonical, "unknown")
