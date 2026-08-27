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
    DELETE_FORM_SCHEMA,
    GET_ACTIVE_FORM_SCHEMA_BY_ORG_SERVICE,
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
    organization_name: str = ""
    service_name: str = ""
    organization_ods_code: str = ""
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
        organization_name=record.get("organization_name") or "",
        service_name=record.get("service_name") or "",
        organization_ods_code=record.get("organization_ods_code") or "",
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


def _load_schema_by_org_service(
    client: Any,
    organization_id: str,
    service_id: str,
) -> FormSchema | None:
    """Return the newest active schema for this organisation and service."""
    org = organization_id.strip()
    service = service_id.strip()
    if not org or not service:
        return None
    try:
        rows = client.run(
            GET_ACTIVE_FORM_SCHEMA_BY_ORG_SERVICE,
            organization_id=org,
            service_id=service,
        )
        if not rows:
            return None
        return _record_to_schema(dict(rows[0]))
    except Exception:
        logger.warning(
            "Could not load FormSchema for org=%s service=%s",
            org,
            service,
            exc_info=True,
        )
        return None


def _load_schema_by_node_ids(
    client: Any,
    organization_id: str,
    service_id: str,
    ers_service_id: str = "",
) -> FormSchema | None:
    """Match FormSchema to Organization.id and Service.id or ers_service_id."""
    schema = _load_schema_by_org_service(client, organization_id, service_id)
    if schema is not None:
        return schema
    ers = ers_service_id.strip()
    if not ers or ers == service_id.strip():
        return None
    return _load_schema_by_org_service(client, organization_id, ers)


def _schema_label(schema: FormSchema) -> str:
    name = (schema.form_name or "").strip()
    if name:
        return name
    org = (schema.organization_id or "").strip()
    service = (schema.service_id or "").strip()
    if org and service:
        return f"{org}/{service}"
    return org or service


def form_schema_state_fields(
    match: str,
    loaded_key: str = "none",
    label: str = "",
) -> dict[str, str]:
    """Top-level extraction-state keys for Validation Lab INPUT KEYS chips."""
    if match == "none":
        return {
            "form_schema_fingerprint": "none",
            "form_schema_match": "none",
            "form_schema_label": "",
        }
    return {
        "form_schema_fingerprint": loaded_key or "none",
        "form_schema_match": match,
        "form_schema_label": label,
    }


def form_schema_fields_from_state(
    state: dict[str, Any],
    encounter_text: str,
    organization_id: str = "",
    service_id: str = "",
) -> dict[str, str]:
    """Reuse a resolved form key, or look it up from the letter text."""
    existing = str(state.get("form_schema_fingerprint") or "").strip()
    if existing and existing != "none":
        return {
            "form_schema_fingerprint": existing,
            "form_schema_match": str(state.get("form_schema_match") or "none"),
            "form_schema_label": str(state.get("form_schema_label") or ""),
        }
    from libs.neo4j_client.client import PatientGraphClient
    from libs.pipeline.document_quality import form_fingerprint

    client = PatientGraphClient()
    try:
        _schema, match, loaded_key, label = resolve_form_schema_traced(
            client,
            form_fingerprint(encounter_text),
            organization_id=organization_id,
            service_id=service_id,
            ers_service_id=str(state.get("healthcare_service_ers_id") or ""),
        )
    finally:
        client.close()
    return form_schema_state_fields(match, loaded_key, label)


def resolve_form_schema_traced(
    client: Any,
    fingerprint: str,
    organization_id: str = "",
    service_id: str = "",
    ers_service_id: str = "",
) -> tuple[FormSchema | None, str, str, str]:
    """Resolve a taught schema from letter hash, then live node ids.

    Returns ``(schema, match, loaded_key, label)``. ``match`` is
    ``exact_hash``, ``org_service``, or ``none``. ``loaded_key`` is the
    fingerprint that was actually used, or ``none``.

    Organisation and service ids are :Organization.id and :Service.id
    (or Service.ers_service_id). They are not invented slugs.
    """
    schema = load_form_schema(client, fingerprint)
    if schema is not None:
        return schema, "exact_hash", schema.fingerprint, _schema_label(schema)
    schema = _load_schema_by_node_ids(
        client,
        organization_id,
        service_id,
        ers_service_id=ers_service_id,
    )
    if schema is None:
        logger.info(
            "form_schema_resolve known_schema=false match=none "
            "fingerprint=%s org_id=%s service_id=%s ers_service_id=%s",
            fingerprint,
            organization_id,
            service_id,
            ers_service_id,
        )
        return None, "none", "none", ""
    _SCHEMA_CACHE[fingerprint] = schema
    logger.info(
        "form_schema_resolve known_schema=true match=org_service "
        "fingerprint=%s loaded=%s org_id=%s service_id=%s",
        fingerprint,
        schema.fingerprint,
        organization_id,
        service_id,
    )
    return schema, "org_service", schema.fingerprint, _schema_label(schema)


def resolve_form_schema(
    client: Any,
    fingerprint: str,
    organization_id: str = "",
    service_id: str = "",
    ers_service_id: str = "",
) -> FormSchema | None:
    """Load a taught schema by letter hash, then by Organisation and Service ids.

    Extraction hashes the letter. Seeded templates may use a stable alias
    such as ``sfh-gynae-2ww-v1``. When the hash misses, an active schema
    bound to the same Organization.id and Service.id (or ers_service_id)
    is used. The alias is then cached under the letter hash.
    """
    schema, _match, _key, _label = resolve_form_schema_traced(
        client,
        fingerprint,
        organization_id=organization_id,
        service_id=service_id,
        ers_service_id=ers_service_id,
    )
    return schema


def is_known_schema(
    client: Any,
    fingerprint: str,
    organization_id: str = "",
    service_id: str = "",
    ers_service_id: str = "",
) -> bool:
    """Return True when a taught :FormSchema exists in cache or Neo4j."""
    return (
        resolve_form_schema(
            client,
            fingerprint,
            organization_id=organization_id,
            service_id=service_id,
            ers_service_id=ers_service_id,
        )
        is not None
    )


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
        organization_name=schema.organization_name,
        service_name=schema.service_name,
        organization_ods_code=schema.organization_ods_code,
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


def rebind_form_schema_ids(client: Any, write: FormSchemaWrite) -> str:
    """Create, skip, or rebind a schema's Organization.id and Service.id.

    Returns ``seeded``, ``skipped``, or ``updated``. Existing sections
    are kept when only the live node ids change.
    """
    existing = load_form_schema(client, write.fingerprint)
    if existing is None:
        save_form_schema(client, write)
        return "seeded"
    same_org = existing.organization_id == write.organization_id
    same_svc = existing.service_id == write.service_id
    if same_org and same_svc:
        return "skipped"
    rebound = FormSchemaWrite(
        fingerprint=existing.fingerprint,
        form_name=existing.form_name,
        sections=existing.sections,
        created_by=write.created_by,
        schema_id=existing.schema_id,
        status=existing.status,
        organization_id=write.organization_id,
        service_id=write.service_id,
        organization_name=write.organization_name,
        service_name=write.service_name,
        organization_ods_code=write.organization_ods_code,
    )
    save_form_schema(client, rebound)
    return "updated"


def delete_form_schema(client: Any, fingerprint: str) -> bool:
    """Remove a taught :FormSchema and drop it from the in-process cache."""
    fp = fingerprint.strip()
    if not fp or fp == "unknown":
        return False
    rows = client.run(DELETE_FORM_SCHEMA, {"fingerprint": fp})
    deleted = bool(rows and rows[0].get("schema_id"))
    _SCHEMA_CACHE.pop(fp, None)
    if deleted:
        logger.info("Deleted FormSchema for fingerprint %s", fp)
    return deleted


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
        organization_name=write.organization_name,
        service_name=write.service_name,
        organization_ods_code=write.organization_ods_code or write.organization_id,
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


def build_sections_from_request(
    raw_sections: list[dict[str, Any]],
) -> list[FormSection]:
    """Convert API request dicts to ``FormSection`` dataclasses."""
    return [_dict_to_section(s) for s in normalize_sections_for_request(raw_sections)]
