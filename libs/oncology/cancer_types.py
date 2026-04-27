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
    "lymphoid": CancerType.LYMPHOMA.value,
    "lymph node / mediastinal mass (pediatric)": CancerType.LYMPHOMA.value,
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
