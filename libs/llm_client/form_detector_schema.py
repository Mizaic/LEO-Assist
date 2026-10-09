"""Strict JSON schema for the form-structure detector's answer.

Azure runs this schema in strict mode, so every property is required and
no extra keys are allowed.

Atlas trace: DI-5C9CA57B, DO-D0C19842, DI-9BF69EC9, DO-F120628C
"""

from __future__ import annotations

from typing import Any

from libs.llm_client.form_completeness_rules import RULE_KINDS
from libs.pipeline.form_schema_section_types import VALID_SECTION_TYPES


def _strict(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


_STRING = {"type": "string"}
_STRINGS = {"type": "array", "items": _STRING}

_ANALYTE = _strict({"label": _STRING, "snomed_code": _STRING, "display": _STRING})

_ITEM = _strict(
    {
        "pattern": _STRING,
        "entity_text": _STRING,
        "semantic_tag": _STRING,
        "assertion": _STRING,
        "procedure_snomed": _STRING,
        "procedure_display": _STRING,
        "analytes": {"type": "array", "items": _ANALYTE},
        "value_placeholder": _STRING,
    }
)

_SECTION = _strict(
    {
        "section_id": _STRING,
        "label": _STRING,
        "section_type": {"type": "string", "enum": sorted(VALID_SECTION_TYPES)},
        "start_pattern": _STRING,
        "items": {"type": "array", "items": _ITEM},
        "default_semantic_tags": _STRINGS,
    }
)

_TARGET = _strict({"section_id": _STRING, "item_pattern": _STRING})

_RULE = _strict(
    {
        "name": _STRING,
        "kind": {"type": "string", "enum": sorted(RULE_KINDS)},
        "targets": {"type": "array", "items": _TARGET},
        "min_count": {"type": "integer"},
        "evidence": _STRING,
    }
)

OUTPUT_SCHEMA: dict[str, Any] = _strict(
    {
        "sections": {"type": "array", "items": _SECTION},
        "completeness_rules": {"type": "array", "items": _RULE},
    }
)

__all__ = ["OUTPUT_SCHEMA"]
