"""Load and save :FormSchema nodes for per-form extraction normalisation.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
  DI: DI-26546721  (organisation and service select the completeness dataset)
  DI: DI-E21DF9EF  (form recognition; no hash or service fallback)
  DO: DO-020C7B5C

A schema is loaded here only by its own key. Which form a document is,
is decided by ``libs.form_recognition``, never by a letter hash or by the
organisation and service. A service may have several active forms.
The store keeps a process-level cache of loaded schemas keyed by key.
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


class FormSchemaLookupError(RuntimeError):
    """We could not ask the database whether this form was taught.

    This is a third answer, and it is not "the form was never taught".
    A caller must degrade the run rather than fall back to generic
    checkbox rules: a taught form read with generic rules loses ticked
    boxes, so real findings never reach the record. See rule 2 of
    .cursor/rules/fail-closed-boundary.mdc.
    """


def _lookup_failed(what: str, exc: Exception) -> FormSchemaLookupError:
    """Build the plain-English error a person may end up reading."""
    return FormSchemaLookupError(
        f"We could not check whether {what} has a taught form. The form "
        f"database did not answer. Nothing was changed. Please try again, "
        f"and tell support if it keeps happening. Cause: {exc}"
    )


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
    prompt_contract: bool = False


def _parse_completeness_groups(raw: Any) -> list[dict[str, Any]]:
    """Read taught completeness groups from a FormSchema record."""
    if not raw:
        return []
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def reset_schema_cache() -> None:
    """Clear the in-process schema cache. Used in tests."""
    _SCHEMA_CACHE.clear()


def get_cached_schema(fingerprint: str) -> FormSchema | None:
    """Return a cached schema for *fingerprint*, or ``None`` if unknown."""
    return _SCHEMA_CACHE.get(fingerprint)


def remember_schema(schema: FormSchema) -> None:
    """Keep a taught schema in the process cache for local onboarding."""
    _SCHEMA_CACHE[schema.fingerprint] = schema


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
        prompt_contract=bool(record.get("prompt_contract")),
        completeness_groups=_parse_completeness_groups(
            record.get("completeness_groups_json")
        ),
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


def _first_row(client: Any, query: str, what: str, **params: Any) -> dict[str, Any]:
    """Run a schema query and return the first row, or {} for a real miss.

    Raises :class:`FormSchemaLookupError` when the database could not be
    asked, so "we do not know" is never mistaken for "not there".
    """
    try:
        rows = client.run(query, **params)
    except Exception as exc:
        logger.warning("FormSchema lookup failed for %s", what, exc_info=True)
        raise _lookup_failed(what, exc) from exc
    return dict(rows[0]) if rows else {}


def load_form_schema(client: Any, fingerprint: str) -> FormSchema | None:
    """Fetch :FormSchema from Neo4j for *fingerprint*, or ``None``.

    ``None`` means the form was definitely never taught. A database error
    raises :class:`FormSchemaLookupError` instead.
    """
    if fingerprint in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[fingerprint]
    row = _first_row(
        client,
        GET_FORM_SCHEMA_BY_FINGERPRINT,
        f"form {fingerprint}",
        fingerprint=fingerprint,
    )
    if not row:
        _SCHEMA_CACHE[fingerprint] = None
        return None
    try:
        schema = _record_to_schema(row)
    except Exception:
        # A stored schema we cannot parse is deliberately not trusted, so
        # the generic checkbox control takes over. That is a separate
        # decision from a failed lookup -- see
        # tests/test_form_schema_section_type_validation.py.
        logger.warning(
            "Stored FormSchema for %s is unusable; ignoring it",
            fingerprint,
            exc_info=True,
        )
        return None
    _SCHEMA_CACHE[fingerprint] = schema
    logger.info(
        "Loaded FormSchema for fingerprint %s (%s)", fingerprint, schema.form_name
    )
    return schema


MATCH_RECOGNISED = "recognised"
MATCH_UNRECOGNISED = "unrecognised"
MATCH_NOT_A_FORM = "not_a_form"
MATCH_FAILED = "failed"
_MATCHES_WITHOUT_KEY = frozenset(
    {"none", "not_applicable", MATCH_UNRECOGNISED, MATCH_NOT_A_FORM, MATCH_FAILED}
)


def form_schema_state_fields(
    match: str,
    loaded_key: str = "none",
    label: str = "",
) -> dict[str, str]:
    """Top-level extraction-state keys for Validation Lab INPUT KEYS chips.

    ``match`` is the bundle's recognition result: ``recognised``,
    ``unrecognised``, ``not_a_form`` or ``failed``. ``not_applicable``
    means recognition was not attempted, because these chunks are not a
    referral form bundle. ``none`` means there was nothing to recognise.
    Only ``recognised`` names a taught form. Any other value -- including
    the retired ``exact_hash`` and ``org_service`` -- reads as ``none``.
    """
    resolved_match = str(match or "none").strip() or "none"
    resolved_key = str(loaded_key or "").strip() or "none"
    if resolved_match == MATCH_RECOGNISED and resolved_key != "none":
        return {
            "form_schema_fingerprint": resolved_key,
            "form_schema_match": MATCH_RECOGNISED,
            "form_schema_label": str(label or ""),
        }
    if resolved_match not in _MATCHES_WITHOUT_KEY:
        logger.warning(
            "form_schema_state unusable match=%s fingerprint=%r; using none",
            resolved_match,
            loaded_key,
        )
        resolved_match = "none"
    return {
        "form_schema_fingerprint": "none",
        "form_schema_match": resolved_match,
        "form_schema_label": "",
    }


def has_taught_form_schema(state: dict[str, Any]) -> bool:
    """True only when every form-like document in the bundle was recognised.

    Reads the keys that :func:`form_schema_state_fields` writes. An
    unrecognised, failed or legacy match is never a taught form: treating
    it as one would switch off generic checkbox normalisation and the
    document-quality check for a form nobody taught.
    """
    match = str(state.get("form_schema_match") or "none").strip()
    fingerprint = str(state.get("form_schema_fingerprint") or "none").strip()
    return match == MATCH_RECOGNISED and fingerprint not in ("", "none")


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
        prompt_contract=bool(schema.prompt_contract),
        completeness_groups_json=json.dumps(
            write.completeness_groups, ensure_ascii=True
        ),
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
    if same_org and same_svc and not write.completeness_groups:
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
        completeness_groups=write.completeness_groups,
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
        prompt_contract=bool(write.prompt_contract),
        completeness_groups=list(write.completeness_groups),
    )


__all__ = [
    "FormSchemaLookupError",
    "FormSchemaWrite",
    "MATCH_FAILED",
    "MATCH_NOT_A_FORM",
    "MATCH_RECOGNISED",
    "MATCH_UNRECOGNISED",
    "build_sections_from_request",
    "delete_form_schema",
    "form_schema_state_fields",
    "get_cached_schema",
    "has_taught_form_schema",
    "load_form_schema",
    "normalize_sections_for_request",
    "rebind_form_schema_ids",
    "remember_schema",
    "reset_schema_cache",
    "save_form_schema",
]
