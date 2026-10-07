"""Load taught form schemas from JSON files, for the harness and tests.

The JSON shape is the PUT /form-schemas/{fingerprint} request body, so a
schema exported from the Teach screen can be scored offline.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5.
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_schema_request import (
    build_sections_from_request,
    normalize_sections_for_request,
)


def load_schema_file(path: Path, *, fingerprint: str = "") -> FormSchema:
    """Build a FormSchema from one JSON file of taught sections."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    sections = build_sections_from_request(
        normalize_sections_for_request(payload["sections"])
    )
    fp = fingerprint or payload.get("fingerprint") or Path(path).stem
    return FormSchema(
        schema_id=payload.get("schema_id") or fp,
        fingerprint=fp,
        form_name=payload.get("form_name") or fp,
        sections=sections,
        created_by=payload.get("created_by") or "file",
    )


def _is_schema_file(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("sections"), list)


def load_schema_dir(directory: Path) -> list[FormSchema]:
    """Load every taught-schema JSON file in *directory*, sorted by name."""
    paths = sorted(Path(directory).glob("*.json"))
    return [load_schema_file(path) for path in paths if _is_schema_file(path)]
