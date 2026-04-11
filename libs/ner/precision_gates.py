"""Precision hardening rules for NER entity candidates.

These rules gate or down-rank extracted entities to reduce false-positive
rates, particularly for the cancer_types domain where body-part tokens
frequently appear in non-malignant contexts.

Each rule returns a list of rejection/warning reasons (empty = pass).
Callers can treat any non-empty list as grounds for rejection.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Word lists
# ---------------------------------------------------------------------------

MALIGNANCY_WORDS: tuple[str, ...] = (
    "cancer",
    "malignant",
    "malignancy",
    "neoplasm",
    "tumour",
    "tumor",
    "carcinoma",
    "metast",
    "lymphoma",
    "sarcoma",
    "myeloma",
    "leukaemia",
    "leukemia",
    "adenocarcinoma",
    "squamous",
    "2ww",
    "two-week",
    "two week wait",
    "fast track referral",
    "urgent referral",
    "suspected cancer",
)

NON_CANCER_CONTEXT_WORDS: tuple[str, ...] = (
    "smear",
    "cervical screening",
    "breast screening",
    "breast feeding",
    "breast-feeding",
    "shingles",
    "spondylosis",
    "herpes zoster",
    "home visit",
    "normal delivery",
    "acute inflammation",
    "cyst and pseudocyst",
    "menopause",
    "menopausal",
    "post-menopausal",
    "hrt",
    "hormone replacement",
    "fibrocystic",
    "mastalgia",
)

# These terms are so generic that they must NOT be mapped to a malignant concept
# unless an explicit malignancy signal also appears in the same sentence/context.
GENERIC_BODY_PART_TERMS: frozenset[str] = frozenset(
    {
        "cervical",
        "breast",
        "eye",
        "bladder",
        "pancreatic",
        "thyroid",
        "uterus",
        "uterine",
        "ovarian",
        "endometrial",
        "testicular",
        "prostatic",
        "rectal",
        "colonic",
        "hepatic",
        "pulmonary",
        "renal",
        "skin",
    }
)

# Surface forms that are very frequently false positives across all domains
GLOBAL_FP_SURFACE_FORMS: frozenset[str] = frozenset(
    {
        "mass",  # too generic — needs qualifier
        "lesion",  # too generic
        "lump",  # too generic without malignancy context
        "node",  # lymph node — too generic
        "change",  # "change in bowel habit" is fine but bare "change" is not
    }
)

# SNOMED semantic tags that in isolation (without malignancy context) should be
# blocked for cancer_types domain
BLOCKED_SEMANTIC_TAGS_WITHOUT_CONTEXT: frozenset[str] = frozenset(
    {
        "morphologic_abnormality",
        "body_structure",
        "qualifier_value",
    }
)

_MALIGNANCY_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in MALIGNANCY_WORDS) + r")\b",
    re.IGNORECASE,
)
_NON_CANCER_RE = re.compile(
    r"(?i)(" + "|".join(re.escape(w) for w in NON_CANCER_CONTEXT_WORDS) + r")",
)

_FIT_NOTE_CONTEXT_RE = re.compile(
    r"\b(fit\s+notes?|not\s+fit\s+for\s+work|fit\s+for\s+work|eMED3|"
    r"statement\s+issued|sick\s*notes?|fit\s+note\s+document)\b",
    re.IGNORECASE,
)

_CKD_EPI_FORMULA_RE = re.compile(r"\bCKD[- ]?EPI\b", re.IGNORECASE)
_CKD_ENTITY_TERMS = frozenset(
    {
        "ckd",
        "chronic kidney disease",
        "kidney disease",
        "renal disease",
        "renal failure",
        "kidney failure",
        "nephropathy",
        "renal impairment",
    }
)

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

# Location/organisation names that must not be tagged as clinical entities
LOCATION_BLOCKLIST: frozenset[str] = frozenset(
    {
        "lri",
        "leicester",
        "rutland",
        "leicestershire",
        "qmc",
        "nottingham",
        "charnwood",
        "nhs south central and west csu",
        "leicester, leicestershire & rutland chis - nhs south central and west csu",
    }
)

# Person names that leaked through de-id; records containing these are rejected
PERSON_BLOCKLIST: frozenset[str] = frozenset(
    {
        "naynaben",
        "dr d p ryan",
        "dr t",
        "dr j lisle",
        "dr j lisle (gpst2)",
        "dr a p taylor",
        "dr noble",
        "dr m al-attar",
        "dr m al-attar, gh",
        "dr r s patel",
        "dr j bennett",
        "john",
    }
)


def _has_malignancy_signal(text: str) -> bool:
    return bool(_MALIGNANCY_RE.search(text))


def _has_non_cancer_context(text: str) -> bool:
    return bool(_NON_CANCER_RE.search(text))


# ---------------------------------------------------------------------------
# Per-entity gate
# ---------------------------------------------------------------------------


def check_entity(
    entity: dict[str, Any],
    sentence_text: str,
    window_text: str | None = None,
) -> list[str]:
    """Return rejection reasons for a single entity given its sentence context.

    Parameters
    ----------
    entity       : canonical entity dict (after schema_mapper)
    sentence_text: the sentence the entity was extracted from
    window_text  : optional broader context (e.g. paragraph)
    """
    reasons: list[str] = []
    domain = (entity.get("domain") or "").lower()
    label = (entity.get("label") or "").lower()
    etext = (entity.get("text") or "").strip().lower()
    snomed_term = ""
    nc = entity.get("normalised_code")
    if nc and isinstance(nc, dict):
        snomed_term = (nc.get("display") or "").lower()

    context = sentence_text.lower()
    if window_text:
        context = window_text.lower() + " " + context

    # ---- cancer_types domain hardening ----
    if domain == "cancer_types" or label == "disorder":
        malignant_mapping = any(w in snomed_term for w in MALIGNANCY_WORDS)

        if malignant_mapping:
            has_cancer_signal = _has_malignancy_signal(context)
            has_non_cancer = _has_non_cancer_context(context)

            # Reject: malignant mapping but no cancer signal in sentence
            if not has_cancer_signal and has_non_cancer:
                reasons.append("cancer_types_mapped_in_non_cancer_context")

            # Reject: generic body part term mapped malignantly without malignancy context
            if etext in GENERIC_BODY_PART_TERMS and not has_cancer_signal:
                reasons.append(
                    "cancer_types_generic_body_part_without_malignancy_context"
                )

            # Reject: screening context without cancer signal
            if "screening" in context and not _has_malignancy_signal(
                sentence_text.lower()
            ):
                if "2ww" not in context and "suspected" not in context:
                    reasons.append(
                        "cancer_types_screening_context_without_cancer_signal"
                    )

        # Block semantic-only global FP terms
        if etext in GLOBAL_FP_SURFACE_FORMS and not _has_malignancy_signal(
            sentence_text.lower()
        ):
            reasons.append("generic_fp_surface_form_without_malignancy_context")

    # ---- Lab-value diagnostic inference hardening ----

    if label == "disorder" or label == "finding":
        # CKD extracted from CKD-EPI formula name (not a diagnosis)
        if etext in _CKD_ENTITY_TERMS and _CKD_EPI_FORMULA_RE.search(context):
            reasons.append("ckd_extracted_from_ckd_epi_formula")

    # ---- General cross-domain hardening ----

    # "GP Surgery" as a bare entity is always an administrative/location
    # reference, not a clinical finding.  The valid SNOMED concept
    # "Seen in GP surgery" requires the full phrase, not "GP Surgery" alone.
    if etext == "gp surgery":
        reasons.append("gp_surgery_header_boilerplate")

    # "fit"/"FIT" meaning fitness-to-work certificate (eMED3), not the
    # Faecal Immunochemical Test.  Reject when nearby context indicates a
    # fit-note / sick-note administrative action.
    if etext == "fit" and _FIT_NOTE_CONTEXT_RE.search(context):
        reasons.append("fit_note_false_positive")

    # Entity text matches a blocklisted location/organisation name
    if etext in LOCATION_BLOCKLIST:
        reasons.append("entity_text_blocklisted_location")

    # Very short entities (≤2 chars) are almost always spurious, EXCEPT for
    # modifier labels (X_DOSAGE, X_ROUTE etc.) where short tokens
    # are clinically valid and intentional.
    # qualifier_value is also exempt: staging codes (T1, N0, M0, G1, G2) are
    # intentionally short and clinically meaningful.
    _MODIFIER_LABELS = frozenset(
        {
            "x_negation_cue",
            "x_temporal",
            "x_dosage",
            "x_frequency",
            "x_route",
            "qualifier_value",
        }
    )
    if len(etext) <= 2 and label not in _MODIFIER_LABELS:
        reasons.append("entity_text_too_short")

    # Entities that are purely numeric are not valid NER spans
    if etext.replace(".", "").replace(",", "").isdigit():
        reasons.append("entity_text_purely_numeric")

    # Placeholder tokens leaked into entity text
    if re.search(
        r"\[(PERSON|DATE|POSTCODE|ADDRESS|NHS_NUMBER|EMAIL|PHONE|ORGANISATION)\]",
        entity.get("text") or "",
    ):
        reasons.append("entity_text_contains_deid_placeholder")

    # Zero-confidence entities with no SNOMED mapping are low value
    confidence = float(entity.get("confidence") or 0.0)
    if confidence < 0.01 and not entity.get("normalised_code"):
        reasons.append("zero_confidence_and_no_snomed")

    return reasons


# ---------------------------------------------------------------------------
# Record-level gate
# ---------------------------------------------------------------------------


def check_record_entities(record: dict[str, Any]) -> list[str]:
    """Check all entities in a canonical record; return aggregated reasons.

    A non-empty return means at least one entity triggered a precision rule.
    """
    text = str(record.get("text") or "")
    all_reasons: list[str] = []

    # Record-level: reject if text contains a URL (web addresses are not clinical)
    if _URL_RE.search(text):
        all_reasons.append("record_contains_url")

    # Record-level: reject if text contains leaked person names (de-id failure)
    text_lower = text.lower()
    for name in PERSON_BLOCKLIST:
        if name in text_lower:
            all_reasons.append("record_contains_blocklisted_person")
            break

    for ent in record.get("entities", []):
        reasons = check_entity(ent, text)
        all_reasons.extend(reasons)
    return sorted(set(all_reasons))
