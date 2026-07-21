"""LangGraph state definition for the cohort annotation pipeline.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict


class EncounterClass(str, Enum):
    EMPTY = "EMPTY"
    STRUCTURED = "STRUCTURED"
    NARRATIVE = "NARRATIVE"
    LETTER = "LETTER"
    MIXED = "MIXED"


VALID_LABELS: frozenset[str] = frozenset(
    {
        "PROCEDURE",
        "DISORDER",
        "FINDING",
        "OBSERVABLE_ENTITY",
        "SITUATION",
        "BODY_STRUCTURE",
        "SUBSTANCE",
        "MEDICINAL_PRODUCT",
        "CLINICAL_DRUG",
        "QUALIFIER_VALUE",
        "REGIME_THERAPY",
        "RECORD_ARTIFACT",
    }
)

VALID_ASSERTIONS: frozenset[str] = frozenset(
    {
        "present",
        "absent",
        "historical",
        "family",
        "planned",
        "possible",
        "conditional",
        "hypothetical",
    }
)

VALID_RELATION_TYPES: frozenset[str] = frozenset(
    {
        "finding_site",
        "interprets",
        "component_of",
        "associated_finding",
        "qualifies",
    }
)


class AnnotationState(TypedDict, total=False):
    # --- input ---
    patient_id: str
    encounter_id: str
    encounter_date: str
    encounter_flags: str
    encounter_class: str
    text: str
    sentences: list[dict[str, Any]]
    existing_coded_concepts: list[dict[str, Any]]
    patient_context: dict[str, Any]

    # --- working ---
    structured_entities: list[dict[str, Any]]
    structured_missing: list[dict[str, Any]]
    narrative_entities: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    relations: list[dict[str, Any]]

    # --- control ---
    retry_count: int
    errors: list[str]
    qa_drops: list[dict[str, Any]]

    # --- output ---
    annotation_complete: bool
    llm_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
