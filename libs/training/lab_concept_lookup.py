"""Lookup surface variants for deterministic lab-triple entities.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

import re
from typing import Any

from libs.terminology.surface_normalize import (
    canonicalize_finding_span,
    strip_observable_value,
)

_OBS_SUFFIX_RE = re.compile(r"\s+-\s+observation\s*$", re.IGNORECASE)


def lab_lookup_texts(entity: dict[str, Any]) -> list[str]:
    """Return terminology lookup texts, preserving source text as first choice."""

    raw = str(entity.get("text") or "").strip()
    label = str(entity.get("label") or entity.get("semantic_tag") or "").lower()
    if not raw:
        return []
    lookups = [raw]
    if label == "finding":
        lookups.extend(_finding_lookup_texts(raw))
    elif label == "observable_entity":
        lookups.extend(_observable_lookup_texts(raw))
    elif label == "procedure":
        lookups.extend(_procedure_lookup_texts(raw))
    return list(dict.fromkeys(text for text in lookups if text))


def _finding_lookup_texts(raw: str) -> list[str]:
    canonical = canonicalize_finding_span(raw)
    lookups = [canonical] if canonical != raw else []
    if canonical:
        simplified = _simplify_lab_analyte_finding(canonical)
        if simplified != canonical:
            lookups.append(simplified)
    return lookups


def _observable_lookup_texts(raw: str) -> list[str]:
    stripped = strip_observable_value(raw)
    return [stripped] if stripped != raw else []


def _procedure_lookup_texts(raw: str) -> list[str]:
    normalised = _normalise_test_name(raw)
    variants = _specific_procedure_variants(normalised)
    variants.extend(_generic_procedure_variants(normalised))
    return variants


def _normalise_test_name(raw: str) -> str:
    text = _OBS_SUFFIX_RE.sub("", raw).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _simplify_lab_analyte_finding(text: str) -> str:
    simplified = re.sub(r"^(?:serum|plasma|blood)\s+", "", text, flags=re.IGNORECASE)
    simplified = re.sub(
        r"\s+level\s+(outside|above|below|within)\s+reference\s+range\b",
        r" \1 reference range",
        simplified,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", simplified).strip()


def _specific_procedure_variants(text: str) -> list[str]:
    key = text.lower()
    if key == "egfr using creatinine (ckd-epi) per 1.73 square metres":
        return [
            "Calculation of quantitative volume rate of glomerular filtration "
            "based on creatinine concentration in serum or plasma specimen"
        ]
    if key == "serum adjusted calcium concentration":
        return ["Corrected serum calcium measurement"]
    if key == "pulse rate":
        return ["Pulse taking", "Peripheral pulse taking"]
    if key == "temperature":
        return ["Temperature taking", "Measurement of temperature"]
    if key == "respiratory rate":
        return ["Respiratory rate taking", "Taking respiratory rate"]
    return []


def _generic_procedure_variants(text: str) -> list[str]:
    variants: list[str] = []
    lower = text.lower()
    if lower.endswith("level"):
        base = text[: -len("level")].strip(" -")
        variants.append(f"{base} measurement")
        variants.append(f"Measurement of {base}")
    if lower.endswith("count"):
        variants.append(f"{text} procedure")
        variants.append(f"{text} measurement")
        variants.append(f"{text} in blood measurement")
    if lower.endswith("rate"):
        variants.append(f"{text} taking")
        variants.append(f"Taking {text}")
        variants.append(f"{text} measurement")
    variants.append(f"Measurement of {text}")
    return variants
