"""The chunk loader recognises each document; nothing falls back.

Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
Risk R-B88CCFD6. Fail-closed boundary: DI-B7A69F26.
"""

from __future__ import annotations

import pytest

from libs.pipeline import document_chunk_loader
from libs.pipeline.document_chunk_loader import build_document_chunk_state
from libs.pipeline.form_schema_store import FormSchemaLookupError, reset_schema_cache
from tests.form_recognition_corpus import bundle_chunks, load_manifest, load_schemas

_BUNDLES = {b["id"]: b for b in load_manifest()["bundles"]}


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_schema_cache()
    yield
    reset_schema_cache()


def _rows(bundle_id: str) -> list[dict]:
    return [
        {"chunk_id": f"c{index}", "text": text, "ordinal": index}
        for index, text in enumerate(bundle_chunks(_BUNDLES[bundle_id]))
    ]


def _use_candidates(monkeypatch, loader) -> list[str]:
    seen: list[str] = []

    def fake(organization_id: str):
        seen.append(organization_id)
        return loader()

    monkeypatch.setattr(document_chunk_loader, "_candidate_schemas", fake)
    return seen


def test_untaught_form_plus_ers_is_unrecognised(monkeypatch) -> None:
    seen = _use_candidates(monkeypatch, load_schemas)
    state = build_document_chunk_state(
        _rows("ubrn-shaped-untaught-lower-gi-plus-ers"), organization_id="RK5"
    )
    kinds = [row["outcome"] for row in state["form_recognition"]]
    assert kinds == ["unrecognised", "recognised"]
    assert state["form_schema_match"] == "unrecognised"
    assert state["form_schema_fingerprint"] == "none"
    assert seen == ["RK5"]


def test_taught_form_plus_ers_is_recognised(monkeypatch) -> None:
    _use_candidates(monkeypatch, load_schemas)
    state = build_document_chunk_state(_rows("taught-gynae-plus-ers"))
    assert state["form_schema_match"] == "recognised"
    assert state["form_schema_fingerprint"] == "sfh-gynae-2ww-v1"
    assert state["form_layout_matched"] is True


def test_a_failed_lookup_is_failed_not_untaught(monkeypatch) -> None:
    def boom():
        raise FormSchemaLookupError("We could not check the taught forms.")

    _use_candidates(monkeypatch, boom)
    state = build_document_chunk_state(_rows("taught-gynae-plus-ers"))
    assert state["form_schema_match"] == "failed"
    kinds = {row["outcome"] for row in state["form_recognition"]}
    assert kinds == {"recognition_failed"}
    assert state["sentences"], "the letter is still loaded for a person to read"


def test_attachments_skip_recognition(monkeypatch) -> None:
    seen = _use_candidates(monkeypatch, load_schemas)
    state = build_document_chunk_state(
        _rows("taught-gynae-plus-ers"), resolve_schema=False
    )
    assert state["form_schema_match"] == "not_applicable"
    assert seen == []
