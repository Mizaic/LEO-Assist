"""Read the labelled form-recognition set.

The manifest is ``tests/fixtures/form_recognition/expected.json``. It names
each document, where its text lives, and what the recogniser must say about
it. The corpus tests use it, and so does the teach-time clash check: a new
form must not take over a labelled letter or another form's document.

Reading fails loudly with ``LabelledSetUnavailable``. The teach check then
refuses to save, so a missing set can never let a form through unchecked.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from libs.form_recognition.bundle import split_documents

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "tests" / "fixtures" / "form_recognition" / "expected.json"


class LabelledSetUnavailable(RuntimeError):
    """The labelled set could not be read."""


@dataclass(frozen=True)
class LabelledDocument:
    doc_id: str
    text: str
    expect: str
    schema: str = ""


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    try:
        return json.loads(MANIFEST.read_text(encoding="ascii"))
    except (OSError, ValueError) as exc:
        raise LabelledSetUnavailable(f"cannot read {MANIFEST.name}") from exc


def _bundle_text(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return "\n\n".join(chunk["text"] for chunk in payload["chunks"])


def _read_source(source: dict[str, Any]) -> str:
    path = REPO / source["path"]
    kind = source["kind"]
    if kind == "fixture":
        return json.loads(path.read_text(encoding="ascii"))["text"]
    if kind == "markdown":
        return path.read_text(encoding="utf-8")
    if kind == "bundle_document":
        docs = [d for d in split_documents(_bundle_text(path)) if d.text.strip()]
        return docs[source["document"]].text
    raise ValueError(f"unknown source kind {kind!r}")


def document_text(source: dict[str, Any]) -> str:
    try:
        return _read_source(source)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        raise LabelledSetUnavailable(f"cannot read {source.get('path')}") from exc


@lru_cache(maxsize=1)
def labelled_documents() -> tuple[LabelledDocument, ...]:
    return tuple(
        LabelledDocument(
            doc_id=entry["id"],
            text=document_text(entry["source"]),
            expect=entry["expect"],
            schema=entry.get("schema", ""),
        )
        for entry in load_manifest()["documents"]
    )
