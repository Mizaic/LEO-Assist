"""Shape the /form-schemas/detect response from a model detection.

Borrowed sections from saved forms take priority over model sections for
the same heading. Skip-section tick boxes are filled from the letter, and
the model's completeness rules are re-pointed at the merged section ids.

Atlas trace: DI-9BF69EC9, DO-F120628C.
"""

from __future__ import annotations

from typing import Any

from libs.llm_client.form_completeness_rules import (
    build_completeness_groups,
    section_id_map,
)
from libs.llm_client.form_detection import FormDetection
from libs.pipeline.form_schema_similarity import (
    SectionMatch,
    find_similar_sections,
    merge_borrowed_and_detected,
)
from libs.pipeline.form_skip_boxes import fill_skip_section_boxes


def build_detect_response(
    detection: FormDetection,
    letter: str,
    known_schemas: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge borrowed and detected sections and attach proposed rules."""
    borrowed: list[SectionMatch] = []
    merged = detection.sections
    if known_schemas:
        borrowed = find_similar_sections(letter.split("\n\n"), known_schemas)
        merged = merge_borrowed_and_detected(borrowed, detection.sections)
    sections = fill_skip_section_boxes(merged, letter)
    groups = build_completeness_groups(
        detection.completeness_rules,
        sections,
        letter,
        section_id_map(detection.sections, sections),
    )
    return {
        "sections": sections,
        "borrowed_count": len(borrowed),
        "detection": detection.to_payload(),
        "completeness_groups": groups,
    }
