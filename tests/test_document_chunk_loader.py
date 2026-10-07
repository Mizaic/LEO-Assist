"""Tests for HCCP referral document-chunk extraction mode.

Atlas trace (recognition cases): DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.pipeline.document_chunk_loader import (
    DOCUMENT_CHUNKS_MODE,
    build_document_chunk_state,
    is_document_chunks_mode,
    merge_referral_message_fields,
)
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
from libs.pipeline.form_schema_store import (
    _schema_to_sections_json,
    reset_schema_cache,
)


def test_merge_referral_message_fields_copies_top_level_into_context() -> None:
    body = {
        "chunk_ids": ["c1", "c2"],
        "document_reference_id": "dr-1",
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "referral_id": "ref-1",
        "context": {"patient_id": "p1"},
    }
    context = merge_referral_message_fields(body)
    assert context["chunk_ids"] == ["c1", "c2"]
    assert context["document_reference_id"] == "dr-1"
    assert context["text_segmentation_mode"] == DOCUMENT_CHUNKS_MODE
    assert context["referral_id"] == "ref-1"
    assert context["patient_id"] == "p1"


# ---------------------------------------------------------------------------
# build_document_chunk_state -- PDF wrapper stripping
# ---------------------------------------------------------------------------

_DOC_CHUNK = (
    "--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology .doc ---\n"
    "Section A: cancer type suspected\nCervix [ ] Ovary [ ]"
)
_PDF_CHUNK = (
    "--- Document: Clinical Information.pdf ---\n"
    "NHS Confidential\nClinical Information Summary\nNo information provided"
)


def _make_rows(*texts: str) -> list[dict]:
    return [
        {
            "chunk_id": f"chunk-{i}",
            "text": t,
            "ordinal": i,
            "char_start": None,
            "char_end": None,
        }
        for i, t in enumerate(texts)
    ]


def test_build_encounter_text_keeps_the_pdf_attachment() -> None:
    """encounter_text carries every chunk, so quotes stay resolvable.

    This used to assert the opposite. Stripping the attachment here while
    ``sentences`` kept it (see the test below) split the coordinate space:
    the model could quote a phrase that SpanResolver could not then find,
    the span fell open to offset 0 -- the document banner -- and ConText
    decided the assertion from the banner instead of the real sentence.
    """
    rows = _make_rows(_DOC_CHUNK, _PDF_CHUNK)
    state = build_document_chunk_state(rows)
    assert "Clinical Information Summary" in state["encounter_text"]
    assert "No information provided" in state["encounter_text"]


def test_every_sentence_is_findable_in_encounter_text() -> None:
    """The invariant the coordinate space rests on."""
    rows = _make_rows(_DOC_CHUNK, _PDF_CHUNK)
    state = build_document_chunk_state(rows)
    for sentence in state["sentences"]:
        assert sentence["text_raw"] in state["encounter_text"]


def test_build_encounter_text_keeps_gp_form_content() -> None:
    rows = _make_rows(_DOC_CHUNK, _PDF_CHUNK)
    state = build_document_chunk_state(rows)
    assert "Section A: cancer type suspected" in state["encounter_text"]
    assert "Cervix" in state["encounter_text"]


def test_build_sentences_keeps_all_chunks_including_wrapper() -> None:
    """Individual sentences must keep wrapper text for SNOMED provenance."""
    rows = _make_rows(_DOC_CHUNK, _PDF_CHUNK)
    state = build_document_chunk_state(rows)
    assert len(state["sentences"]) == 2
    wrapper_sentence = state["sentences"][1]
    assert "Clinical Information" in wrapper_sentence["text_raw"]


def test_build_encounter_text_unchanged_when_no_pdf_chunk() -> None:
    rows = _make_rows(_DOC_CHUNK)
    state = build_document_chunk_state(rows)
    assert "Section A: cancer type suspected" in state["encounter_text"]


def test_build_document_chunk_state_preserves_table_text() -> None:
    table_text = "| Test | Result |\n| Hb | 120 g/L |"
    rows = [
        {
            "chunk_id": "chunk-a",
            "text": table_text,
            "ordinal": 1,
            "char_start": 0,
            "char_end": len(table_text),
        }
    ]
    loaded = build_document_chunk_state(rows)
    assert len(loaded["sentences"]) == 1
    assert loaded["sentences"][0]["text"] == table_text
    assert "| Hb |" in loaded["encounter_text"]
    assert loaded["text_segmentation_mode"] == DOCUMENT_CHUNKS_MODE


def test_no_taught_forms_writes_no_form_key() -> None:
    rows = _make_rows(_DOC_CHUNK)
    client = MagicMock()
    client.run.return_value = []
    with patch(
        "libs.neo4j_client.client.PatientGraphClient",
        return_value=client,
    ):
        state = build_document_chunk_state(rows)
    assert state["form_schema_fingerprint"] == "none"
    assert state["form_schema_match"] in {"unrecognised", "not_a_form"}
    assert state["form_schema_label"] == ""


_LOWER_GI_CHUNK = (
    "--- Document: Lower GI referral.doc ---\n"
    "Section 1: Bowel symptoms\n"
    "[ ] Rectal bleeding\n[x] Change in bowel habit\n[ ] Weight loss\n"
    "Section 2: Examination\n[ ] Abdominal mass\n[ ] Rectal mass"
)


def test_a_form_for_the_same_service_is_not_bound_by_service() -> None:
    """DI-E21DF9EF: organisation and service never choose the form."""
    reset_schema_cache()
    schema = FormSchema(
        schema_id="seed-1",
        fingerprint="sfh-gynae-2ww-v1",
        form_name="SFH Gynae 2WW",
        sections=[
            FormSection(
                section_id="A",
                section_type="checkbox_multi",
                label="Cancer type",
                start_pattern="Section A: cancer type suspected",
                items=[],
            )
        ],
        created_by="seed",
        organization_id="RK5",
        service_id="7980224",
    )
    client = MagicMock()
    client.run.return_value = [
        {
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
    ]
    rows = _make_rows(_LOWER_GI_CHUNK)
    try:
        with patch(
            "libs.neo4j_client.client.PatientGraphClient",
            return_value=client,
        ):
            state = build_document_chunk_state(rows, organization_id="RK5")
        assert state["form_schema_fingerprint"] == "none"
        assert state["form_schema_match"] == "unrecognised"
    finally:
        reset_schema_cache()


def test_a_taught_form_is_recognised_from_its_own_text() -> None:
    reset_schema_cache()
    gynae = FormSchema(
        schema_id="seed-1",
        fingerprint="sfh-gynae-2ww-v1",
        form_name="SFH Gynae 2WW",
        sections=[
            FormSection(
                section_id="A",
                section_type="checkbox_multi",
                label="Cancer type",
                start_pattern="Section A: cancer type suspected",
                items=[],
            )
        ],
        created_by="seed",
    )
    row = {
        "schema_id": gynae.schema_id,
        "fingerprint": gynae.fingerprint,
        "form_name": gynae.form_name,
        "sections_json": _schema_to_sections_json(gynae),
        "chunk_section_map": "[]",
        "created_by": gynae.created_by,
        "version": 1,
        "status": "active",
    }
    client = MagicMock()
    client.run.return_value = [row]
    try:
        with patch(
            "libs.neo4j_client.client.PatientGraphClient",
            return_value=client,
        ):
            state = build_document_chunk_state(_make_rows(_DOC_CHUNK))
        assert state["form_schema_fingerprint"] == "sfh-gynae-2ww-v1"
        assert state["form_schema_match"] == "recognised"
        assert state["form_schema_label"] == "SFH Gynae 2WW"
    finally:
        reset_schema_cache()


def test_is_document_chunks_mode() -> None:
    assert is_document_chunks_mode({"text_segmentation_mode": DOCUMENT_CHUNKS_MODE})
    assert not is_document_chunks_mode(
        {"text_segmentation_mode": "encounter_sentences"}
    )
    assert not is_document_chunks_mode({})


def test_load_document_chunks_skips_sentence_splitter(monkeypatch) -> None:
    from libs.pipeline_graph.subgraphs.extraction import (
        load_document_chunks,
        split_sentences,
    )

    table_text = "| WBC | 5.2 |\n| RBC | 4.1 |"
    state = {
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "sentences": [
            {
                "sentence_id": "chunk-1",
                "text": table_text,
                "start": 0,
                "end": len(table_text),
            }
        ],
    }
    loaded = load_document_chunks(state)
    assert loaded["sentences"][0]["text"] == table_text
    assert "\n|" in loaded["encounter_text"]

    split_called: list[bool] = []

    def _track_split(_state):
        split_called.append(True)
        return split_sentences(_state)

    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.extraction.split_sentences",
        _track_split,
    )
    load_document_chunks(state)
    assert not split_called
