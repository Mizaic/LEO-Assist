"""MedSpaCy runtime inference service. Stub until model is built from gold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InferredEntity:
    text: str
    span_start: int
    span_end: int
    concept_id: str | None
    term: str | None
    confidence: float
    semantic_tag: str


def infer_encounter(
    encounter_text: str,
    encounter_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Run MedSpaCy inference on encounter text.
    Stub: returns empty until model is built from gold.
    """
    # TODO: Load MedSpaCy pipeline and run inference when model exists
    return {
        "encounter_id": encounter_id,
        "entities": [],
        "written": False,
        "message": "MedSpaCy model not yet built. Export gold and train first.",
    }
