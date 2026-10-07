"""Load the labelled form-recognition set for tests.

The manifest is ``tests/fixtures/form_recognition/expected.json``. Two
transforms stand in for variation we cannot hold locally: ``fill_in``
adds values and ticks to a blank form, and ``flatten`` strips table
pipes the way pdfplumber text from a flattened PDF looks.

Atlas trace: DI-E21DF9EF, VT-B13F7C48.
"""

from __future__ import annotations

import re
from typing import Any

from libs.form_recognition.labelled_set import (  # noqa: F401 (re-exported)
    MANIFEST,
    REPO,
    document_text,
    load_manifest,
)
from libs.form_recognition.schema_files import load_schema_file
from libs.pipeline.form_schema_normalizer import FormSchema

_LABEL_CELL = re.compile(r"(\|\s*[^|\n]*?:\s*)(\|)")
_EMPTY_BOX = re.compile(r"\[ \]")
_SEPARATOR = re.compile(r"^\|\s*(?:---\s*\|\s*)+$")


def load_schemas() -> list[FormSchema]:
    return [
        load_schema_file(REPO / entry["path"], fingerprint=entry["fingerprint"])
        for entry in load_manifest()["schemas"]
    ]


def documents() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (entry["id"], document_text(entry["source"]), entry)
        for entry in load_manifest()["documents"]
    ]


def document_by_id(doc_id: str) -> str:
    for entry in load_manifest()["documents"]:
        if entry["id"] == doc_id:
            return document_text(entry["source"])
    raise KeyError(doc_id)


def bundle_chunks(bundle: dict[str, Any]) -> list[str]:
    """Build stored-chunk style text: one chunk per document, with markers."""
    return [
        f"--- Document: {part['title']} ---\n\n{document_by_id(part['ref'])}"
        for part in bundle["documents"]
    ]


def fill_in(text: str) -> str:
    """Add invented values and ticks to a blank form, deterministically."""
    filled = _LABEL_CELL.sub(r"\1 Sample entry 0042 \2", text)
    filled = _EMPTY_BOX.sub("[X]", filled, count=3)
    filled = filled.replace("Yes No", "Yes [X] No [ ]")
    narrative = (
        "Thank you for seeing this patient. Symptoms began six weeks ago and "
        "have slowly worsened. Examination today was otherwise unremarkable. "
        "Bloods were taken on 01/02/2026 and are attached."
    )
    return f"{filled}\n\n{narrative}\n"


def flatten(text: str) -> str:
    """Strip table pipes and use box glyphs, like flattened-PDF text."""
    lines: list[str] = []
    for line in text.splitlines():
        if _SEPARATOR.match(line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        lines.extend(c for c in cells if c)
    flat = "\n".join(lines)
    return flat.replace("[X]", "\u2612").replace("[ ]", "\u2610")
