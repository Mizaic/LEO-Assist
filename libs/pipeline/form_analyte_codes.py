"""Taught analyte SNOMED codes for extracted ordered-test entities.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.form_schema_normalizer import FormSchema


def apply_schema_analyte_codes(
    entities: list[dict[str, Any]],
    schema: FormSchema,
    chunk_section_map: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Override inferred observable SNOMED codes with taught analyte codes.

    For each entity whose label matches an analyte in a taught
    ``ordered_tests`` section, replaces the entity's ``snomed_code``
    with the taught value.  Entities with no matching taught code are
    returned unchanged.

    Args:
        entities: Extracted entity dicts (each must have ``label`` and
            ``snomed_code`` keys).
        schema: The FormSchema containing the taught analyte lists.
        chunk_section_map: ``{chunk_idx, section_id}`` map used to scope
            which sections are active for the current document chunks.

    Returns:
        A new list of entity dicts (originals are not mutated).
    """
    taught_codes = _build_analyte_code_index(schema, chunk_section_map)
    if not taught_codes:
        return list(entities)
    return [_apply_code(e, taught_codes) for e in entities]


def _build_analyte_code_index(
    schema: FormSchema,
    chunk_section_map: list[dict[str, Any]],
) -> dict[str, str]:
    """Build a label -> snomed_code lookup from active ordered_tests sections."""
    active_ids = (
        {entry.get("section_id") for entry in chunk_section_map}
        if chunk_section_map
        else None
    )
    codes: dict[str, str] = {}
    for section in schema.sections:
        if section.section_type != "ordered_tests":
            continue
        if active_ids is not None and section.section_id not in active_ids:
            continue
        for item in section.items:
            for analyte in item.analytes:
                label = analyte.get("label", "")
                code = analyte.get("snomed_code", "")
                if label and code:
                    codes[label] = code
    return codes


def _apply_code(entity: dict[str, Any], taught_codes: dict[str, str]) -> dict[str, Any]:
    """Return a copy of entity with snomed_code replaced if a taught code exists."""
    label = entity.get("label", "")
    code = taught_codes.get(label)
    if code is None:
        return dict(entity)
    return {**entity, "snomed_code": code}
