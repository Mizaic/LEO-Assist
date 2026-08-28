"""Normalise Teach-this-form request dicts into FormSection objects.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.form_schema_normalizer import FormSchemaItem, FormSection
from libs.pipeline.form_schema_section_types import validate_section_type


def dict_to_section(raw: dict[str, Any]) -> FormSection:
    """Build a :class:`FormSection`, rejecting an unusable section type.

    Raises:
        ValueError: When ``section_type`` is not one the normaliser can
            dispatch on. Storing such a value would leave the section's
            tick boxes unprocessed.
    """
    items = [dict_to_item(i) for i in (raw.get("items") or [])]
    return FormSection(
        section_id=raw.get("section_id") or "",
        section_type=validate_section_type(  # type: ignore[arg-type]
            raw.get("section_type") or "free_text"
        ),
        label=raw.get("label") or "",
        start_pattern=raw.get("start_pattern") or "",
        items=items,
        semantic_tags=_load_semantic_tags(raw),
    )


def _load_semantic_tags(raw: dict[str, Any]) -> list[str]:
    """Return semantic_tags list, handling the old singular semantic_tag field."""
    if "semantic_tags" in raw and raw["semantic_tags"]:
        val = raw["semantic_tags"]
        if isinstance(val, list):
            return [str(t) for t in val]
    if "semantic_tag" in raw and raw["semantic_tag"]:
        return [str(raw["semantic_tag"])]
    return ["finding"]


def dict_to_item(raw: dict[str, Any]) -> FormSchemaItem:
    analytes = raw.get("analytes") or []
    if not isinstance(analytes, list):
        analytes = []
    return FormSchemaItem(
        pattern=raw.get("pattern") or "",
        entity_text=raw.get("entity_text") or "",
        semantic_tag=raw.get("semantic_tag") or "finding",
        assertion=raw.get("assertion") or "present",
        procedure_snomed=raw.get("procedure_snomed") or "",
        procedure_display=raw.get("procedure_display") or "",
        analytes=[dict(a) for a in analytes if isinstance(a, dict)],
        value_placeholder=raw.get("value_placeholder") or "",
    )


def _ordered_tests_item_has_content(item: dict[str, Any]) -> bool:
    pattern = str(item.get("pattern") or "").strip()
    procedure = str(item.get("procedure_snomed") or "").strip()
    if pattern or procedure:
        return True
    analytes = item.get("analytes") or []
    if not isinstance(analytes, list):
        return False
    return any(
        isinstance(a, dict)
        and (
            str(a.get("label") or "").strip() or str(a.get("snomed_code") or "").strip()
        )
        for a in analytes
    )


def _normalize_item_for_request(
    item: dict[str, Any],
    section_type: str,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    pattern = str(item.get("pattern") or "").strip()
    entity_text = str(item.get("entity_text") or "").strip()
    if section_type == "ordered_tests":
        if not _ordered_tests_item_has_content(item):
            return None
        if not entity_text:
            display = str(item.get("procedure_display") or "").strip()
            entity_text = display or pattern
        return {**item, "pattern": pattern, "entity_text": entity_text}
    if not pattern or not entity_text:
        return None
    return {**item, "pattern": pattern, "entity_text": entity_text}


def normalize_sections_for_request(
    raw_sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop blank items and fill missing start patterns before validation."""
    normalized: list[dict[str, Any]] = []
    for section in raw_sections:
        section_type = str(section.get("section_type") or "").strip()
        label = str(section.get("label") or "").strip()
        section_id = str(section.get("section_id") or "").strip()
        start = str(section.get("start_pattern") or "").strip()
        if not start:
            start = label or section_id
        if not start:
            continue
        items: list[dict[str, Any]] = []
        for item in section.get("items") or []:
            normalized_item = _normalize_item_for_request(item, section_type)
            if normalized_item is not None:
                items.append(normalized_item)
        normalized.append({**section, "start_pattern": start, "items": items})
    return normalized


def schema_to_dict(schema: Any) -> dict[str, Any]:
    """JSON shape returned by GET/PUT /form-schemas."""
    return {
        "schema_id": schema.schema_id,
        "fingerprint": schema.fingerprint,
        "form_name": schema.form_name,
        "version": schema.version,
        "status": schema.status,
        "sections": [
            {
                "section_id": s.section_id,
                "section_type": s.section_type,
                "label": s.label,
                "start_pattern": s.start_pattern,
                "semantic_tags": list(s.semantic_tags),
                "items": [
                    {
                        "pattern": i.pattern,
                        "entity_text": i.entity_text,
                        "semantic_tag": i.semantic_tag,
                        "assertion": i.assertion,
                        "procedure_snomed": i.procedure_snomed,
                        "procedure_display": i.procedure_display,
                        "analytes": list(i.analytes),
                        "value_placeholder": i.value_placeholder,
                    }
                    for i in s.items
                ],
            }
            for s in schema.sections
        ],
        "created_at": schema.created_at,
        "created_by": schema.created_by,
        "organization_id": schema.organization_id,
        "service_id": schema.service_id,
        "organization_name": schema.organization_name,
        "service_name": schema.service_name,
    }


def build_sections_from_request(
    raw_sections: list[dict[str, Any]],
) -> list[FormSection]:
    """Convert API request dicts to ``FormSection`` dataclasses."""
    return [dict_to_section(s) for s in normalize_sections_for_request(raw_sections)]


def schema_summary_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map a LIST_FORM_SCHEMAS Cypher row to the list API shape."""
    return {
        "schema_id": row["schema_id"],
        "fingerprint": row["fingerprint"],
        "form_name": row["form_name"],
        "version": row["version"],
        "status": row["status"],
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "organization_id": row.get("organization_id") or "",
        "service_id": row.get("service_id") or "",
    }


def filter_schema_summaries(
    schemas: list[dict[str, Any]],
    organization_id: str = "",
    service_id: str = "",
) -> list[dict[str, Any]]:
    """Keep summaries whose Organization.id and Service.id match the caller."""
    org = organization_id.strip()
    service = service_id.strip()
    filtered = schemas
    if org:
        filtered = [
            row for row in filtered if (row.get("organization_id") or "") == org
        ]
    if service:
        filtered = [row for row in filtered if (row.get("service_id") or "") == service]
    return filtered
