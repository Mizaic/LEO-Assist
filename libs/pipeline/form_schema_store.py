"""Load and save :FormSchema nodes for per-form extraction normalisation.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)

The store keeps a process-level cache of known schemas keyed by fingerprint.
The pipeline normaliser checks this cache before falling back to generic rules.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

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


def reset_schema_cache() -> None:
    """Clear the in-process schema cache. Used in tests."""
    _SCHEMA_CACHE.clear()


def get_cached_schema(fingerprint: str) -> FormSchema | None:
    """Return a cached schema for *fingerprint*, or ``None`` if unknown."""
    return _SCHEMA_CACHE.get(fingerprint)


def _record_to_schema(record: dict[str, Any]) -> FormSchema:
    raw_sections: list[dict[str, Any]] = json.loads(record.get("sections_json") or "[]")
    sections = [_dict_to_section(s) for s in raw_sections]
    return FormSchema(
        schema_id=record.get("schema_id") or "",
        fingerprint=record.get("fingerprint") or "",
        form_name=record.get("form_name") or "",
        sections=sections,
        created_by=record.get("created_by") or "",
        version=int(record.get("version") or 1),
        status=record.get("status") or "active",
        created_at=str(record.get("created_at") or ""),
    )


def _dict_to_section(raw: dict[str, Any]) -> FormSection:
    items = [_dict_to_item(i) for i in (raw.get("items") or [])]
    return FormSection(
        section_id=raw.get("section_id") or "",
        section_type=raw.get("section_type") or "free_text",  # type: ignore[arg-type]
        label=raw.get("label") or "",
        start_pattern=raw.get("start_pattern") or "",
        items=items,
    )


def _dict_to_item(raw: dict[str, Any]) -> FormSchemaItem:
    return FormSchemaItem(
        pattern=raw.get("pattern") or "",
        entity_text=raw.get("entity_text") or "",
        semantic_tag=raw.get("semantic_tag") or "finding",
        assertion=raw.get("assertion") or "present",
    )


def _schema_to_sections_json(schema: FormSchema) -> str:
    sections = [
        {
            "section_id": s.section_id,
            "section_type": s.section_type,
            "label": s.label,
            "start_pattern": s.start_pattern,
            "items": [
                {
                    "pattern": i.pattern,
                    "entity_text": i.entity_text,
                    "semantic_tag": i.semantic_tag,
                    "assertion": i.assertion,
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


def save_form_schema(
    client: Any,
    *,
    fingerprint: str,
    form_name: str,
    sections: list[FormSection],
    created_by: str,
    schema_id: str | None = None,
    status: str = "active",
) -> FormSchema:
    """Persist or update a :FormSchema in Neo4j.

    Returns the saved :FormSchema dataclass. Also updates the in-process cache
    so the normaliser picks it up immediately without a reload.
    """
    sid = schema_id or str(uuid.uuid4())
    schema = FormSchema(
        schema_id=sid,
        fingerprint=fingerprint,
        form_name=form_name,
        sections=sections,
        created_by=created_by,
        status=status,
    )
    sections_json = _schema_to_sections_json(schema)
    client.run(
        UPSERT_FORM_SCHEMA,
        schema_id=sid,
        fingerprint=fingerprint,
        form_name=form_name,
        status=status,
        sections_json=sections_json,
        created_by=created_by,
    )
    _SCHEMA_CACHE[fingerprint] = schema
    logger.info("Saved FormSchema %s for fingerprint %s", sid, fingerprint)
    return schema


def build_sections_from_request(
    raw_sections: list[dict[str, Any]],
) -> list[FormSection]:
    """Convert API request dicts to ``FormSection`` dataclasses."""
    return [_dict_to_section(s) for s in raw_sections]
