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
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
from libs.pipeline.form_schema_request import (
    build_sections_from_request,
    dict_to_section,
    normalize_sections_for_request,
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
    sections = [dict_to_section(s) for s in raw_sections]
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


_dict_to_section = dict_to_section


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
    resolved_match = str(match or "none").strip() or "none"
    resolved_key = str(loaded_key or "").strip()
    if resolved_match != "none" and (not resolved_key or resolved_key == "none"):
        logger.warning(
            "form_schema_state inconsistent match=%s fingerprint=%r; using none",
            resolved_match,
            loaded_key,
        )
        resolved_match = "none"
        resolved_key = "none"
    if resolved_match == "none":
        return {
            "form_schema_fingerprint": "none",
            "form_schema_match": "none",
            "form_schema_label": "",
        }
    return {
        "form_schema_fingerprint": resolved_key,
        "form_schema_match": resolved_match,
        "form_schema_label": str(label or ""),
    }


def has_taught_form_schema(state: dict[str, Any]) -> bool:
    """True when a taught FormSchema is bound on pipeline state.

    Reads the resolved keys that :func:`form_schema_state_fields` writes,
    so this is the same signal the non-windowed extractor derives from
    ``form_schema_match``. Both keys must agree: a stale fingerprint on
    its own is not a taught form, and treating it as one would switch off
    generic checkbox normalisation for an untaught referral form.
    """
    match = str(state.get("form_schema_match") or "none").strip()
    fingerprint = str(state.get("form_schema_fingerprint") or "none").strip()
    if match in ("", "none"):
        return False
    return fingerprint not in ("", "none")


def form_schema_fields_from_state(
    state: dict[str, Any],
    encounter_text: str,
    organization_id: str = "",
    service_id: str = "",
) -> dict[str, str]:
    """Reuse a resolved form key, or look it up from the letter text."""
    existing = str(state.get("form_schema_fingerprint") or "").strip()
    existing_match = str(state.get("form_schema_match") or "none").strip() or "none"
    if existing and existing != "none" and existing_match != "none":
        return {
            "form_schema_fingerprint": existing,
            "form_schema_match": existing_match,
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
    loaded_fp = str(schema.fingerprint or "").strip()
    if not loaded_fp:
        logger.warning(
            "form_schema_resolve org_service hit but FormSchema.fingerprint is empty "
            "org_id=%s service_id=%s schema_id=%s",
            organization_id,
            service_id,
            schema.schema_id,
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
    return schema, "org_service", loaded_fp, _schema_label(schema)


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
    rows = client.run(DELETE_FORM_SCHEMA, fingerprint=fp)
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


__all__ = [
    "FormSchemaWrite",
    "build_sections_from_request",
    "delete_form_schema",
    "form_schema_fields_from_state",
    "form_schema_state_fields",
    "get_cached_schema",
    "has_taught_form_schema",
    "is_known_schema",
    "load_form_schema",
    "normalize_sections_for_request",
    "rebind_form_schema_ids",
    "reset_schema_cache",
    "resolve_form_schema",
    "resolve_form_schema_traced",
    "save_form_schema",
]
