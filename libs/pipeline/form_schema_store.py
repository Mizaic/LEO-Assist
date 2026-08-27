"""Load and save :FormSchema nodes for per-form extraction normalisation.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
  DI: DI-26546721  (organisation and service bind)
  DO: DO-020C7B5C

The store keeps a process-level cache of known schemas keyed by fingerprint.
The pipeline normaliser checks this cache before falling back to generic rules.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from libs.completeness.service_domain import ensure_service_completeness_domain
from libs.cypher.form_schema_queries import (
    GET_FORM_SCHEMA_BY_FINGERPRINT,
    UPSERT_FORM_SCHEMA,
)
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)

logger = logging.getLogger(__name__)

_SCHEMA_CACHE: dict[str, FormSchema | None] = {}


@dataclass
class FormSchemaWrite:
    """Inputs for persisting a taught form and its service dataset."""

    fingerprint: str
    form_name: str
    sections: list[FormSection]
    created_by: str
    schema_id: str | None = None
    status: str = "active"
    organization_id: str = ""
    service_id: str = ""
    completeness_groups: list[dict[str, Any]] = field(default_factory=list)


def reset_schema_cache() -> None:
    """Clear the in-process schema cache. Used in tests."""
    _SCHEMA_CACHE.clear()


def get_cached_schema(fingerprint: str) -> FormSchema | None:
    """Return a cached schema for *fingerprint*, or ``None`` if unknown."""
    return _SCHEMA_CACHE.get(fingerprint)


def _record_to_schema(record: dict[str, Any]) -> FormSchema:
    raw_sections: list[dict[str, Any]] = json.loads(record.get("sections_json") or "[]")
    sections = [_dict_to_section(s) for s in raw_sections]
    raw_map = record.get("chunk_section_map") or "[]"
    chunk_section_map: list[dict[str, Any]] = (
        json.loads(raw_map) if isinstance(raw_map, str) else []
    )
    return FormSchema(
        schema_id=record.get("schema_id") or "",
        fingerprint=record.get("fingerprint") or "",
        form_name=record.get("form_name") or "",
        sections=sections,
        created_by=record.get("created_by") or "",
        version=int(record.get("version") or 1),
        status=record.get("status") or "active",
        created_at=str(record.get("created_at") or ""),
        organization_id=record.get("organization_id") or "",
        service_id=record.get("service_id") or "",
        chunk_section_map=chunk_section_map,
    )


def _dict_to_section(raw: dict[str, Any]) -> FormSection:
    items = [_dict_to_item(i) for i in (raw.get("items") or [])]
    semantic_tags = _load_semantic_tags(raw)
    return FormSection(
        section_id=raw.get("section_id") or "",
        section_type=raw.get("section_type") or "free_text",  # type: ignore[arg-type]
        label=raw.get("label") or "",
        start_pattern=raw.get("start_pattern") or "",
        items=items,
        semantic_tags=semantic_tags,
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


def _dict_to_item(raw: dict[str, Any]) -> FormSchemaItem:
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


def _schema_to_sections_json(schema: FormSchema) -> str:
    sections = [
        {
            "section_id": s.section_id,
            "section_type": s.section_type,
            "label": s.label,
            "start_pattern": s.start_pattern,
            "semantic_tags": s.semantic_tags,
            "items": [
                {
                    "pattern": i.pattern,
                    "entity_text": i.entity_text,
                    "semantic_tag": i.semantic_tag,
                    "assertion": i.assertion,
                    "procedure_snomed": i.procedure_snomed,
                    "procedure_display": i.procedure_display,
                    "analytes": i.analytes,
                    "value_placeholder": i.value_placeholder,
                }
                for i in s.items
            ],
        }
        for s in schema.sections
    ]
    return json.dumps(sections, ensure_ascii=True)


def load_form_schema(client: Any, fingerprint: str) -> FormSchema | None:
    """Fetch :FormSchema from Neo4j for *fingerprint*, or ``None``."""
    if fingerprint in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[fingerprint]
    try:
        rows = client.run(GET_FORM_SCHEMA_BY_FINGERPRINT, fingerprint=fingerprint)
        if not rows:
            _SCHEMA_CACHE[fingerprint] = None
            return None
        schema = _record_to_schema(dict(rows[0]))
        _SCHEMA_CACHE[fingerprint] = schema
        logger.info(
            "Loaded FormSchema for fingerprint %s (%s)", fingerprint, schema.form_name
        )
        return schema
    except Exception:
        logger.warning("Could not load FormSchema for %s", fingerprint, exc_info=True)
        return None


def is_known_schema(client: Any, fingerprint: str) -> bool:
    """Return True when a taught :FormSchema exists in cache or Neo4j."""
    return load_form_schema(client, fingerprint) is not None


def save_form_schema(client: Any, write: FormSchemaWrite) -> FormSchema:
    """Persist a :FormSchema and, when scoped, its service completeness domain."""
    schema = _build_schema(write)
    client.run(
        UPSERT_FORM_SCHEMA,
        schema_id=schema.schema_id,
        fingerprint=schema.fingerprint,
        form_name=schema.form_name,
        status=schema.status,
        sections_json=_schema_to_sections_json(schema),
        created_by=schema.created_by,
        organization_id=schema.organization_id,
        service_id=schema.service_id,
    )
    if schema.service_id and write.completeness_groups:
        ensure_service_completeness_domain(
            client,
            organization_id=schema.organization_id,
            service_id=schema.service_id,
            form_name=schema.form_name,
            groups=write.completeness_groups,
            require_blocking_groups=False,
        )
    _SCHEMA_CACHE[schema.fingerprint] = schema
    logger.info(
        "Saved FormSchema %s for fingerprint %s",
        schema.schema_id,
        schema.fingerprint,
    )
    return schema


def _build_schema(write: FormSchemaWrite) -> FormSchema:
    return FormSchema(
        schema_id=write.schema_id or str(uuid.uuid4()),
        fingerprint=write.fingerprint,
        form_name=write.form_name,
        sections=write.sections,
        created_by=write.created_by,
        status=write.status,
        organization_id=write.organization_id,
        service_id=write.service_id,
    )


def normalize_sections_for_request(
    raw_sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop blank items and fill missing start patterns before validation."""
    normalized: list[dict[str, Any]] = []
    for section in raw_sections:
        label = str(section.get("label") or "").strip()
        section_id = str(section.get("section_id") or "").strip()
        start = str(section.get("start_pattern") or "").strip()
        if not start:
            start = label or section_id
        if not start:
            continue
        items: list[dict[str, Any]] = []
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            pattern = str(item.get("pattern") or "").strip()
            entity_text = str(item.get("entity_text") or "").strip()
            if not pattern or not entity_text:
                continue
            items.append({**item, "pattern": pattern, "entity_text": entity_text})
        normalized.append({**section, "start_pattern": start, "items": items})
    return normalized


def build_sections_from_request(
    raw_sections: list[dict[str, Any]],
) -> list[FormSection]:
    """Convert API request dicts to ``FormSection`` dataclasses."""
    return [_dict_to_section(s) for s in normalize_sections_for_request(raw_sections)]
