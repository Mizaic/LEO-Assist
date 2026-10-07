"""Taught-form extraction contract: verbatim fills only, empty is valid.

Atlas trace:
  DI: DI-9D76A65C
  DO: DO-1E60B1D4
  VT: VT-12EBF8F0
  Risk: R-3B38CA10
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.form_schema_normalizer import FormSchema, FormSection

_ALLOWED_MATCH = frozenset({"recognised"})
_SKIP_TYPES = frozenset({"admin", "template_noise"})


def build_form_contract(schema: FormSchema, *, match: str) -> str:
    """Return the prompt contract, or empty when the form flag is off."""
    if not bool(getattr(schema, "prompt_contract", False)):
        return ""
    if str(match or "").strip() not in _ALLOWED_MATCH:
        return ""
    lines = [
        "FORM CONTRACT",
        "This letter uses a taught form.",
        "Fill each section only with words from the letter.",
        "Empty is a valid answer. Do not invent facts.",
        "Clinical sections:",
    ]
    for section in schema.sections:
        line = _section_line(section)
        if line:
            lines.append(line)
    if len(lines) == 5:
        return ""
    return "\n".join(lines)


def _section_line(section: FormSection) -> str:
    if section.section_type in _SKIP_TYPES:
        return ""
    label = str(section.label or section.section_id or "").strip()
    if not label:
        return ""
    kind = _expected_kind(section)
    return f"- {label} -- expected: {kind}. Empty is valid."


def contract_for_state(schema_fields: dict[str, Any]) -> str:
    """Build the contract from a cached taught form, or return empty."""
    from libs.pipeline.form_schema_store import get_cached_schema

    fingerprint = str(schema_fields.get("form_schema_fingerprint") or "").strip()
    if not fingerprint or fingerprint == "none":
        return ""
    schema = get_cached_schema(fingerprint)
    if schema is None:
        return ""
    return build_form_contract(
        schema, match=str(schema_fields.get("form_schema_match") or "")
    )


def _expected_kind(section: FormSection) -> str:
    tags = [str(tag).strip() for tag in section.semantic_tags if str(tag).strip()]
    if tags:
        return ", ".join(tags)
    if section.section_type.startswith("checkbox"):
        return "finding"
    return "clinical fact"
