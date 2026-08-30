"""Compose taught hits from the national e-RS form and a specialty form.

Atlas trace:
  DI: DI-1A1943BB
  DO: DO-E3AF3879
  UN: UN-AF530E8E
"""

from __future__ import annotations

import re
from typing import Any

from libs.pipeline.document_role import _iter_documents
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_section_hits import collect_section_hits

ERS_FINGERPRINT = "nhs-ers-clinical-information-v1"
_ERS_MARKER_RE = re.compile(
    r"clinical information(?:\.pdf| summary)",
    re.IGNORECASE,
)
_BLOODS_SECTION_RE = re.compile(r"investigat|bloods|findings", re.IGNORECASE)
_NEXT_DOC_SECTION = {
    "section_id": "next_document_boundary",
    "section_type": "admin",
    "label": "Next document",
    "start_pattern": "--- Document:",
}


def is_ers_clinical_information(text: str) -> bool:
    """True when the text is the national Clinical Information form."""
    return bool(_ERS_MARKER_RE.search(text or ""))


def is_ers_schema(schema: FormSchema | None) -> bool:
    """True when *schema* is the seeded national e-RS form."""
    if schema is None:
        return False
    if str(schema.fingerprint or "") == ERS_FINGERPRINT:
        return True
    return "clinical information" in str(schema.form_name or "").lower()


def split_bundle_documents(chunks: list[str]) -> tuple[list[str], list[str]]:
    """Split bundle chunks into (specialty texts, e-RS texts)."""
    specialty: list[str] = []
    ers: list[str] = []
    for title, header, body in _iter_bundle_documents(chunks):
        block = f"{header}{body}"
        if is_ers_clinical_information(f"{title}\n{block}"):
            ers.append(block)
        elif block.strip():
            specialty.append(block)
    return specialty, ers


def compose_section_hits(
    specialty: FormSchema | None,
    ers: FormSchema | None,
    chunks: list[str],
) -> list[dict[str, Any]]:
    """Union taught hits, then credit specialty bloods from filled e-RS Findings."""
    specialty_texts, ers_texts = split_bundle_documents(chunks)
    hits: list[dict[str, Any]] = []
    if specialty is not None and specialty_texts:
        hits.extend(collect_section_hits(specialty, specialty_texts))
    if ers is not None and ers_texts:
        hits.extend(collect_section_hits(ers, ers_texts))
    return _credit_specialty_bloods(hits, specialty)


def compose_form_sections(
    specialty: FormSchema | None,
    ers: FormSchema | None,
    chunks: list[str],
) -> list[dict[str, str]]:
    """Return specialty sections when that form is present."""
    specialty_texts, ers_texts = split_bundle_documents(chunks)
    owner = specialty if specialty is not None and specialty_texts else ers
    sections = _section_dicts(owner)
    if owner is specialty and ers_texts:
        sections.append(dict(_NEXT_DOC_SECTION))
    return sections


def _iter_bundle_documents(chunks: list[str]):
    joined = "\n\n".join(chunk for chunk in chunks if str(chunk or "").strip())
    yield from _iter_documents(joined)


def _section_dicts(schema: FormSchema | None) -> list[dict[str, str]]:
    if schema is None:
        return []
    return [
        {
            "section_id": section.section_id,
            "section_type": section.section_type,
            "label": section.label,
            "start_pattern": section.start_pattern,
        }
        for section in schema.sections
    ]


def _credit_specialty_bloods(
    hits: list[dict[str, Any]],
    specialty: FormSchema | None,
) -> list[dict[str, Any]]:
    if specialty is None or not _filled_ers_findings(hits):
        return hits
    credited = list(hits)
    seen = {
        (str(row.get("section_id") or ""), str(row.get("item_pattern") or ""))
        for row in hits
    }
    for member in _bloods_members(specialty):
        key = (member["section_id"], member["item_pattern"])
        if key in seen:
            continue
        seen.add(key)
        credited.append(
            {
                "section_id": member["section_id"],
                "item_pattern": member["item_pattern"],
                "entity_text": "e-RS findings",
                "checked": True,
            }
        )
    return credited


def _filled_ers_findings(hits: list[dict[str, Any]]) -> bool:
    return any(
        str(hit.get("section_id") or "") == "findings" and bool(hit.get("checked"))
        for hit in hits
    )


def bind_national_ers_if_needed(
    client: Any,
    schema: FormSchema | None,
    raw_texts: list[str],
    resolved: tuple[str, str, str],
) -> tuple[FormSchema | None, str, str, str]:
    """Load the national e-RS schema. Prefer it on wrapper-only bundles."""
    match, loaded_key, label = resolved
    if not any(is_ers_clinical_information(text) for text in raw_texts):
        return schema, match, loaded_key, label
    from libs.pipeline.form_schema_store import load_form_schema

    ers = load_form_schema(client, ERS_FINGERPRINT)
    specialty_texts, ers_texts = split_bundle_documents(raw_texts)
    wrapper_only = bool(ers_texts) and not specialty_texts
    if ers is not None and (wrapper_only or schema is None):
        return ers, "known_fingerprint", ers.fingerprint, ers.form_name
    return schema, match, loaded_key, label


def taught_hits_for_bundle(
    schema: FormSchema, raw_texts: list[str]
) -> list[dict[str, Any]]:
    """Collect hits, composing the national e-RS form when it is also present."""
    wrapper = _wrapper_schema(schema, raw_texts)
    if wrapper is not None:
        return compose_section_hits(schema, wrapper, raw_texts)
    from libs.pipeline.form_section_hits import collect_section_hits

    return collect_section_hits(schema, raw_texts, schema.chunk_section_map)


def taught_sections_for_bundle(
    schema: FormSchema, raw_texts: list[str]
) -> list[dict[str, str]]:
    """Return the form sections that should own the SBAR situation."""
    wrapper = _wrapper_schema(schema, raw_texts)
    if wrapper is not None:
        return compose_form_sections(schema, wrapper, raw_texts)
    return _section_dicts(schema)


def _wrapper_schema(schema: FormSchema, raw_texts: list[str]) -> FormSchema | None:
    if is_ers_schema(schema):
        return None
    if not any(is_ers_clinical_information(text) for text in raw_texts):
        return None
    from libs.pipeline.form_schema_store import get_cached_schema

    return get_cached_schema(ERS_FINGERPRINT)


def _bloods_members(specialty: FormSchema) -> list[dict[str, str]]:
    members: list[dict[str, str]] = []
    for group in specialty.completeness_groups:
        for member in group.get("members") or []:
            if not isinstance(member, dict):
                continue
            section_id = str(member.get("section_id") or "")
            if not _BLOODS_SECTION_RE.search(section_id):
                continue
            members.append(
                {
                    "section_id": section_id,
                    "item_pattern": str(member.get("item_pattern") or ""),
                }
            )
    return members
