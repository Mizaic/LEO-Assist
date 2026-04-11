"""Semantic-tag canonicalisation helpers for terminology data."""

from __future__ import annotations

import re

_WS_RE = re.compile(r"\s+")

# Canonical concept semantic tags in our knowledge graph.
_ALLOWED: set[str] = {
    "disorder",
    "finding",
    "procedure",
    "observable_entity",
    "qualifier_value",
    "substance",
    "medicinal_product",
    "clinical_drug",
    "situation",
    "event",
    "body_structure",
    "tumor_staging",
    "assessment_scale",
    "staging_scale",
    "regime_therapy",
    "record_artifact",
    "physical_object",
    "organism",
    "morphologic_abnormality",
    "occupation",
    "attribute",
    "environment",
    "product",
}

_ALIASES: dict[str, str] = {
    "clinical_finding": "finding",
    "clinical finding": "finding",
    "observable entity": "observable_entity",
    "observable_entity": "observable_entity",
    "qualifier value": "qualifier_value",
    "qualifier_value": "qualifier_value",
    "medicinal product": "medicinal_product",
    "medicinal_product": "medicinal_product",
    "clinical drug": "clinical_drug",
    "clinical_drug": "clinical_drug",
    "body structure": "body_structure",
    "body_structure": "body_structure",
    "tumor staging": "tumor_staging",
    "tumour staging": "tumor_staging",
    "tumor_staging": "tumor_staging",
    "assessment scale": "assessment_scale",
    "assessment_scale": "assessment_scale",
    "staging scale": "staging_scale",
    "staging_scale": "staging_scale",
    "regime/therapy": "regime_therapy",
    "regime therapy": "regime_therapy",
    "regime_therapy": "regime_therapy",
    "record artifact": "record_artifact",
    "record_artifact": "record_artifact",
    "physical object": "physical_object",
    "physical_object": "physical_object",
    "morphologic abnormality": "morphologic_abnormality",
    "morphologic_abnormality": "morphologic_abnormality",
}


def normalise_semantic_tag(raw: str | None) -> str:
    """Return canonical underscore semantic tag for Concept nodes."""
    if not raw:
        return "unknown"
    cleaned = _WS_RE.sub(" ", str(raw).strip().lower())
    direct = _ALIASES.get(cleaned)
    if direct:
        return direct
    candidate = cleaned.replace("-", "_").replace("/", "_").replace(" ", "_")
    if candidate in _ALIASES:
        return _ALIASES[candidate]
    if candidate in _ALLOWED:
        return candidate
    return candidate or "unknown"
