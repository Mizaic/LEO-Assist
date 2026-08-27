"""Tests for HCCP referral document-chunk extraction mode."""

from __future__ import annotations

from libs.pipeline.document_chunk_loader import (
    DOCUMENT_CHUNKS_MODE,
    build_document_chunk_state,
    is_document_chunks_mode,
    merge_referral_message_fields,
    strip_pdf_attachments,
)

# ---------------------------------------------------------------------------
# strip_pdf_attachments
# ---------------------------------------------------------------------------

_GP_FORM = (
    "--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology .doc ---\n\n"
    "Section A: cancer type suspected\n"
    "Cervix [ ] Ovary [ ]\n"
    "Section B: 14-day rule criteria\n"
    "B1 PMB [ ]"
)

_ERS_WRAPPER = (
    "--- Document: Clinical Information.pdf ---\n\n"
    "NHS Confidential\n"
    "Clinical Information Summary\n"
    "UBRN: 000481914514\n"
    "No information provided"
)

_BUNDLE = _GP_FORM + "\n\n" + _ERS_WRAPPER


def test_strip_pdf_attachments_removes_pdf_section() -> None:
    result = strip_pdf_attachments(_BUNDLE)
    assert "Clinical Information Summary" not in result
    assert "UBRN: 000481914514" not in result
    assert "No information provided" not in result


def test_strip_pdf_attachments_keeps_doc_content() -> None:
    result = strip_pdf_attachments(_BUNDLE)
    assert "Section A: cancer type suspected" in result
    assert "Cervix [ ]" in result
    assert "Section B: 14-day rule criteria" in result


def test_strip_pdf_attachments_no_op_when_no_pdf() -> None:
    text = "Section A\nCervix [ ] Ovary [ ]\nSection B\nB1 PMB [ ]"
    assert strip_pdf_attachments(text) == text


def test_strip_pdf_attachments_case_insensitive() -> None:
    text = "GP Form content\n\n--- Document: report.PDF ---\nAdmin noise"
    result = strip_pdf_attachments(text)
    assert "Admin noise" not in result
    assert "GP Form content" in result


def test_strip_pdf_attachments_empty_string() -> None:
    assert strip_pdf_attachments("") == ""


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


def test_build_encounter_text_strips_pdf_wrapper() -> None:
    rows = _make_rows(_DOC_CHUNK, _PDF_CHUNK)
    state = build_document_chunk_state(rows)
    assert "Clinical Information Summary" not in state["encounter_text"]
    assert "No information provided" not in state["encounter_text"]


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


def test_build_document_chunk_state_writes_form_schema_none() -> None:
    rows = _make_rows(_DOC_CHUNK)
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    client.run.return_value = []
    with patch(
        "libs.neo4j_client.client.PatientGraphClient",
        return_value=client,
    ):
        state = build_document_chunk_state(rows)
    assert state["form_schema_fingerprint"] == "none"
    assert state["form_schema_match"] == "none"
    assert state["form_schema_label"] == ""


def test_build_document_chunk_state_writes_loaded_schema_key() -> None:
    from unittest.mock import MagicMock, patch

    from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
    from libs.pipeline.form_schema_store import (
        _schema_to_sections_json,
        reset_schema_cache,
    )

    reset_schema_cache()
    schema = FormSchema(
        schema_id="seed-1",
        fingerprint="sfh-gynae-2ww-v1",
        form_name="SFH Gynae 2WW",
        sections=[
            FormSection(
                section_id="A",
                section_type="checkbox",
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
    client.run.side_effect = [
        [],
        [
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
        ],
    ]
    rows = _make_rows(_DOC_CHUNK)
    try:
        with patch(
            "libs.neo4j_client.client.PatientGraphClient",
            return_value=client,
        ):
            state = build_document_chunk_state(
                rows,
                organization_id="RK5",
                service_id="7980224",
            )
        assert state["form_schema_fingerprint"] == "sfh-gynae-2ww-v1"
        assert state["form_schema_match"] == "org_service"
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
