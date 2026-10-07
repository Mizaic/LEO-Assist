"""Taught-form text must reach the model unmodified on the windowed path.

Regression guard for the Sherwood Forest Gynaecology two-week-wait
referral. Document-chunks mode routes through the windowed extractor,
which re-applied the generic checkbox normaliser and cut the Section C
narrative from 928 characters to 113 characters.

The normaliser no longer shortens a line, so the untaught path keeps the
narrative too. It marks the checkbox instead of deleting what follows it.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
  DO: DO-020C7B5C
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline.document_chunk_loader import DOCUMENT_CHUNKS_MODE
from libs.pipeline.form_schema_store import (
    _schema_to_sections_json,
    reset_schema_cache,
)
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
from libs.pipeline_graph.subgraphs.extraction import (
    _run_windowed_llm_extraction,
    load_document_chunks,
)
from tests.form_recognition_corpus import load_schemas

FIXTURES = Path(__file__).parent / "fixtures" / "form_schema"
CHUNKS_FIXTURE = FIXTURES / "sherwood_gynae_2ww_chunks_deid.json"

TAUGHT_FINGERPRINT = "e61c4289e199cfb5"
ORG_ID = "RK5"
SERVICE_ID = "7980224"
SECTION_C_CHARS = 928
SECTION_C_MARKERS = ("vaginal discharge", "polyp noted")


def _sherwood_chunks() -> list[SentenceChunk]:
    """Return the 11 de-identified referral chunks in stored order."""
    payload = json.loads(CHUNKS_FIXTURE.read_text(encoding="utf-8"))
    chunks: list[SentenceChunk] = []
    offset = 0
    for index, raw in enumerate(payload["chunks"]):
        text = str(raw.get("text") or "")
        chunks.append(
            SentenceChunk(
                sentence_id=f"c{index}",
                text=text,
                start=offset,
                end=offset + len(text),
            )
        )
        offset += len(text) + 2
    return chunks


def _section_c_id(chunks: list[SentenceChunk]) -> str:
    for chunk in chunks:
        if "Section C" in chunk.text:
            return str(chunk.sentence_id)
    raise AssertionError("Section C chunk missing from Sherwood fixture")


def _capture_llm_chunk_texts(state: dict[str, Any]) -> dict[str, str]:
    """Run the windowed extractor and return the text the model saw."""
    chunks = _sherwood_chunks()
    seen: dict[str, str] = {}

    def _fake_llm(_context, window_chunks, _state, **_kwargs):
        for chunk in window_chunks:
            seen[str(chunk.sentence_id)] = str(chunk.text or "")
        return {"entities": [], "llm_tokens": {"input_tokens": 1}}

    with patch(
        "libs.pipeline_graph.subgraphs.extraction._run_llm_extraction",
        side_effect=_fake_llm,
    ):
        _run_windowed_llm_extraction(
            "\n\n".join(c.text for c in chunks),
            chunks,
            state,
            window_size=1,
            window_overlap=0,
            context_mode="window_local",
            max_window_input_tokens=3500,
        )
    assert len(seen) == len(chunks)
    return seen


def _base_state(**overrides: str) -> dict[str, Any]:
    state: dict[str, Any] = {
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "healthcare_service_org_id": ORG_ID,
        "healthcare_service_id": SERVICE_ID,
        "form_schema_match": "none",
        "form_schema_fingerprint": "none",
        "form_schema_label": "",
    }
    state.update(overrides)
    return state


def _taught_schema() -> FormSchema:
    return FormSchema(
        schema_id="sherwood-1",
        fingerprint=TAUGHT_FINGERPRINT,
        form_name="SFH Gynae 2WW",
        sections=[
            FormSection(
                section_id="section_c_clinical_details",
                section_type="free_text",
                label="Section C: Further Clinical details",
                start_pattern="Section C",
                items=[],
            )
        ],
        created_by="seed",
        status="active",
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )


def _schema_row(schema: FormSchema) -> dict[str, Any]:
    return {
        "schema_id": schema.schema_id,
        "fingerprint": schema.fingerprint,
        "form_name": schema.form_name,
        "sections_json": _schema_to_sections_json(schema),
        "chunk_section_map": "[]",
        "created_by": schema.created_by,
        "version": 1,
        "status": schema.status,
        "organization_id": schema.organization_id,
        "service_id": schema.service_id,
    }


def test_taught_form_section_c_reaches_model_unmodified() -> None:
    """A bound taught schema keeps all 928 Section C characters."""
    reset_schema_cache()
    state = _base_state(
        form_schema_match="recognised",
        form_schema_fingerprint=TAUGHT_FINGERPRINT,
        form_schema_label="SFH Gynae 2WW",
    )
    seen = _capture_llm_chunk_texts(state)
    section_c = seen[_section_c_id(_sherwood_chunks())]
    assert len(section_c) == SECTION_C_CHARS
    for marker in SECTION_C_MARKERS:
        assert marker in section_c.lower()


def test_untaught_form_still_gets_generic_normalisation() -> None:
    """With no taught schema the generic checkbox normaliser still runs.

    Running it must mark the unticked checkbox and keep the narrative, so
    an untaught form still yields the referral reason.
    """
    reset_schema_cache()
    seen = _capture_llm_chunk_texts(_base_state())
    section_c = seen[_section_c_id(_sherwood_chunks())]
    assert "[NON_EXTRACTABLE] Cognitive Impairment" in section_c
    for marker in SECTION_C_MARKERS:
        assert marker in section_c.lower()


def test_orphan_fingerprint_without_match_still_normalises() -> None:
    """A stale fingerprint with no match is not a taught form."""
    reset_schema_cache()
    state = _base_state(form_schema_fingerprint=TAUGHT_FINGERPRINT)
    seen = _capture_llm_chunk_texts(state)
    section_c = seen[_section_c_id(_sherwood_chunks())]
    assert "[NON_EXTRACTABLE] Cognitive Impairment" in section_c
    for marker in SECTION_C_MARKERS:
        assert marker in section_c.lower()


def test_chunk_loader_publishes_recognised_schema_keys() -> None:
    """The loader pins the recognised taught-form keys onto pipeline state."""
    reset_schema_cache()
    client = MagicMock()
    client.run.return_value = [_schema_row(s) for s in load_schemas()]
    sentences = [
        {"sentence_id": c.sentence_id, "text": c.text, "start": c.start, "end": c.end}
        for c in _sherwood_chunks()
    ]
    with patch("libs.neo4j_client.client.PatientGraphClient", return_value=client):
        loaded = load_document_chunks(
            {
                "sentences": sentences,
                "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
                "healthcare_service_org_id": ORG_ID,
                "healthcare_service_id": SERVICE_ID,
            }
        )
    assert loaded["form_schema_match"] == "recognised"
    assert loaded["form_schema_fingerprint"] == "sfh-gynae-2ww-v1"
