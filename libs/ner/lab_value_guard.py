"""Defence-in-depth guard: suppress disorder entities inferred from lab values.

Clinical safety rule: lab results (eGFR, creatinine, HbA1c, etc.) are
observations — the pipeline must NEVER infer a diagnosis from a numeric
measurement.  If the LLM returns a disorder whose evidence text is a lab
result line, this guard removes it before terminology resolution.

This is a post-extraction filter, not a replacement for prompt-level rules.
It exists as a safety net in case the LLM ignores its instructions.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_LAB_TEST_RE = re.compile(
    r"\b("
    r"e?gfr|creatinine|sodium|potassium|haemoglobin|hemoglobin|hba1c|hb\b|"
    r"cholesterol|triglyceride|albumin|bilirubin|ferritin|"
    r"platelet|neutrophil|lymphocyte|white\s*cell|red\s*cell|"
    r"urea|calcium|phosphate|magnesium|glucose|tsh|"
    r"alt\b|ast\b|alp\b|ggt|inr\b|aptt|fibrinogen|crp\b|esr\b|"
    r"vitamin\s*d|folate|b12|iron|transferrin|"
    r"hct\b|mcv\b|mch\b|mchc|rdw\b|mpv\b|"
    r"psa\b|bnp\b|nt[\s-]*pro[\s-]*bnp|troponin|d-dimer|"
    r"ldl|hdl|vldl|haematocrit|hematocrit|"
    r"ldh\b|amylase|lipase|procalcitonin|"
    r"ck\b|cpk\b|creatine\s*kinase|lactate|"
    r"afp\b|alpha[\s-]*fetoprotein|ca[\s-]*125|cea\b|hcg\b|"
    r"ammonia|"
    r"alanine\s*aminotransferase|"
    r"aspartate\s*aminotransferase|"
    r"alkaline\s*phosphatase|"
    r"gamma\s*glutamyl\s*transferase|"
    r"glomerular\s*filtration"
    r")\b",
    re.IGNORECASE,
)

_MEASUREMENT_RE = re.compile(
    r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*"
    r"(?:mL/min|mmol/L|mmol/mol|umol/L|nmol/L|pmol/L|g/L|mg/L|iu/L|u/L|"
    r"mmHg|kPa|g/dL|pg|fL|10\^?\d+/L|10\*\d+/L|ng/mL|ug/L|"
    r"mg/dL|mU/L|seconds?|ratio|%|bpm|kg|cm|m2|L)\b",
    re.IGNORECASE,
)

_EXPLICIT_DX_RE = re.compile(
    r"\b("
    r"diagnos[ei]s|diagnos(?:ed|ing)|dx[:\s]"
    r"|has\s+(?:been\s+)?diagnosed"
    r"|problem\s+list|active\s+problem"
    r"|impression[:\s]|assessment[:\s]"
    r"|(?:patient|pt)\s+has\s+\w+"
    r"|known\s+\w+"
    r"|suffers?\s+from"
    r"|presents?\s+with"
    r"|on\s+treatment\s+for"
    r"|managed\s+for"
    r"|being\s+treated\s+for"
    r"|confirmed?\b"
    r"|established\b"
    r")\b",
    re.IGNORECASE,
)

_FORMULA_NAME_RE = re.compile(r"\bCKD[- ]?EPI\b", re.IGNORECASE)

_DISORDER_TAGS = frozenset({"disorder", "finding"})


def is_lab_result_sentence(sentence_text: str) -> bool:
    """Return True if the sentence is primarily a lab/test result line."""
    return bool(_LAB_TEST_RE.search(sentence_text) and _MEASUREMENT_RE.search(sentence_text))


def _has_explicit_diagnosis(sentence_text: str) -> bool:
    """Return True if the sentence explicitly states a diagnosis."""
    return bool(_EXPLICIT_DX_RE.search(sentence_text))


def should_suppress_disorder(
    *,
    entity_text: str,
    entity_semantic_tag: str,
    entity_normalized: str,
    sentence_text: str,
    entity_numeric_value: str = "",
    entity_unit: str = "",
) -> bool:
    """Return True if a disorder entity should be suppressed as lab-inferred.

    This catches two failure modes:
    1. The LLM extracts "CKD" from "CKD-EPI" (formula name, not a diagnosis).
    2. The LLM infers a disorder (e.g. CKD stage 1) from a lab value
       (e.g. eGFR 69 mL/min) when no explicit diagnosis is stated.
    """
    tag = (entity_semantic_tag or "").lower().replace("_", " ")
    if tag not in _DISORDER_TAGS:
        return False

    if not is_lab_result_sentence(sentence_text):
        return False

    if _has_explicit_diagnosis(sentence_text):
        return False

    norm_lower = (entity_normalized or "").lower()
    text_lower = (entity_text or "").lower()

    if _FORMULA_NAME_RE.search(sentence_text):
        ckd_terms = ("chronic kidney disease", "ckd", "renal failure", "renal disease",
                     "kidney disease", "kidney failure", "nephropathy")
        if any(t in norm_lower for t in ckd_terms) or any(t in text_lower for t in ckd_terms):
            logger.info(
                "lab_value_guard: suppressed disorder %r (normalised=%r) "
                "inferred from CKD-EPI formula in: %r",
                entity_text, entity_normalized, sentence_text[:120],
            )
            return True

    if entity_numeric_value or entity_unit:
        logger.info(
            "lab_value_guard: suppressed disorder %r with measurement "
            "fields (value=%r unit=%r) from lab sentence: %r",
            entity_text, entity_numeric_value, entity_unit, sentence_text[:120],
        )
        return True

    lab_match = _LAB_TEST_RE.search(text_lower) or _LAB_TEST_RE.search(norm_lower)
    if lab_match:
        return False

    if _is_inferred_disorder(norm_lower, sentence_text.lower()):
        logger.info(
            "lab_value_guard: suppressed inferred disorder %r (normalised=%r) "
            "from lab result sentence: %r",
            entity_text, entity_normalized, sentence_text[:120],
        )
        return True

    return False


_INFERRED_DISORDER_MAP: dict[str, tuple[str, ...]] = {
    "egfr": (
        "chronic kidney disease", "ckd", "renal failure", "renal impairment",
        "renal disease", "kidney disease", "kidney failure", "nephropathy",
    ),
    "creatinine": (
        "chronic kidney disease", "ckd", "renal failure", "renal impairment",
        "renal disease", "kidney disease", "kidney failure", "nephropathy",
    ),
    "hba1c": (
        "diabetes", "diabetic", "impaired glucose", "pre-diabetes",
        "prediabetes", "glucose intolerance",
    ),
    "glucose": (
        "diabetes", "diabetic", "impaired glucose", "hyperglycaemia",
        "hypoglycaemia", "pre-diabetes",
    ),
    "sodium": (
        "hyponatraemia", "hyponatremia", "hypernatraemia", "hypernatremia",
    ),
    "potassium": (
        "hyperkalaemia", "hyperkalemia", "hypokalaemia", "hypokalemia",
    ),
    "haemoglobin": (
        "anaemia", "anemia", "polycythaemia", "polycythemia",
    ),
    "hemoglobin": (
        "anaemia", "anemia", "polycythaemia", "polycythemia",
    ),
    "cholesterol": (
        "hypercholesterolaemia", "hypercholesterolemia",
        "hyperlipidaemia", "hyperlipidemia", "dyslipidaemia",
    ),
    "tsh": (
        "hypothyroidism", "hyperthyroidism", "thyrotoxicosis",
    ),
    "platelet": (
        "thrombocytopenia", "thrombocytosis",
    ),
    "troponin": (
        "myocardial infarction", "acute coronary",
    ),
    "psa": (
        "prostate cancer", "prostatic cancer", "prostate neoplasm",
    ),
}


def _is_inferred_disorder(normalised_term: str, sentence_lower: str) -> bool:
    """Check if the disorder term is a known inference from a lab test in the sentence."""
    for lab_keyword, disorder_terms in _INFERRED_DISORDER_MAP.items():
        if lab_keyword in sentence_lower:
            if any(d in normalised_term for d in disorder_terms):
                return True
    return False


def filter_inferred_diagnoses(
    sentence_text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove disorder entities that were inferred from lab values.

    Designed to operate on a list of entity dicts with keys:
    text, label/semantic_tag, normalized/lookup_term, numeric_value, unit.

    Returns the filtered list (entities are removed, not modified).
    """
    return [
        ent for ent in entities
        if not should_suppress_disorder(
            entity_text=str(ent.get("text", "")),
            entity_semantic_tag=str(ent.get("label", ent.get("semantic_tag", ""))),
            entity_normalized=str(ent.get("normalized", ent.get("lookup_term", ""))),
            sentence_text=sentence_text,
            entity_numeric_value=str(ent.get("numeric_value", ent.get("value", "")) or ""),
            entity_unit=str(ent.get("unit", "") or ""),
        )
    ]
