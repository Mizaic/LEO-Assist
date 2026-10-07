"""Compose taught hits from the recognised forms of one referral bundle.

Each recognised document brings its own form's hits. A filled national
e-RS Findings section also credits the specialty form's bloods group.
The SBAR situation stays on the specialty form's sections.

Atlas trace:
  DI: DI-1A1943BB, DI-E21DF9EF
  DO: DO-E3AF3879, DO-E458EEC5
  UN: UN-AF530E8E
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_section_hits import collect_section_hits

ERS_FINGERPRINT = "nhs-ers-clinical-information-v1"
_BLOODS_SECTION_RE = re.compile(r"investigat|bloods|findings", re.IGNORECASE)
_NEXT_DOC_SECTION = {
    "section_id": "next_document_boundary",
    "section_type": "admin",
    "label": "Next document",
    "start_pattern": "--- Document:",
}


@dataclass(frozen=True)
class BoundDocument:
    """One recognised document: its form and its own chunk texts."""

    schema: FormSchema
    texts: list[str]
    chunk_section_map: list[dict[str, Any]] | None = None


def is_ers_schema(schema: FormSchema | None) -> bool:
    """True when *schema* is the seeded national e-RS form."""
    if schema is None:
        return False
    if str(schema.fingerprint or "") == ERS_FINGERPRINT:
        return True
    return "clinical information" in str(schema.form_name or "").lower()


def hits_for_documents(
    bound: list[BoundDocument], primary: FormSchema | None
) -> list[dict[str, Any]]:
    """Union each document's hits, then credit specialty bloods from e-RS."""
    hits: list[dict[str, Any]] = []
    for doc in bound:
        hits.extend(collect_section_hits(doc.schema, doc.texts, doc.chunk_section_map))
    specialty = None if is_ers_schema(primary) else primary
    return _credit_specialty_bloods(hits, specialty)


def sections_for_documents(
    bound: list[BoundDocument], primary: FormSchema | None
) -> list[dict[str, str]]:
    """Return the primary form's sections, ending at the next document."""
    sections = _section_dicts(primary)
    others = [doc for doc in bound if doc.schema is not primary]
    if primary is not None and not is_ers_schema(primary) and others:
        sections.append(dict(_NEXT_DOC_SECTION))
    return sections


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
