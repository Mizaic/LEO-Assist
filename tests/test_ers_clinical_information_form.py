"""National e-RS Clinical Information form must be scored, not sealed.

The e-RS Clinical Information.pdf is the national wrapper used across
most NHS specialties. When the reason-for-referral field is filled, the
taught form must emit section hits, satisfy the completeness group, and
leave that narrative extractable. Marking the whole PDF as
[NON_EXTRACTABLE] is a product defect.

Atlas trace:
  DI: DI-C2C1E3E8, DI-50BE367C
  DO: DO-BB31F9A5, DO-85BBD932
  VT: VT-6FE171F8, VT-8426C84D
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from libs.completeness.evaluator import evaluate_completeness_groups
from libs.form_recognition.bundle import split_chunks
from libs.ner.form_layout_rules import NON_EXTRACTABLE_MARKER, llm_facing_text
from libs.pipeline.document_chunk_loader import (
    build_document_chunk_state,
    recognition_fields_from_state,
)
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_schema_request import build_sections_from_request
from libs.pipeline.form_schema_store import reset_schema_cache
from libs.pipeline.form_section_hits import collect_section_hits
from libs.pipeline_graph.subgraphs.extraction import merge_results
from tests.form_recognition_stubs import recognise_all_as

_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "nhs_ers_clinical_information.json"
)

_SHERWOOD_BUNDLE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "sherwood_gynae_2ww_chunks_deid.json"
)

_REASON = "Patchy erythematous rash on the lower part of the left breast."

_FILLED_ERS = (
    "--- Document: Clinical Information.pdf ---\n\n"
    "NHS Confidential\n"
    "Clinical Information Summary\n"
    "UBRN Information\n"
    "Priority: 2 week wait\n"
    "Patient Information\n"
    "Reason for referral\n"
    f"{_REASON}\n"
    "Medication and medical devices\n"
    "No Information Provided\n"
    "Past medical history\n"
    "Appendicectomy.\n"
)

_EMPTY_REASON_ERS = (
    "--- Document: Clinical Information.pdf ---\n\n"
    "NHS Confidential\n"
    "Clinical Information Summary\n"
    "Reason for referral\n"
    "No Information Provided\n"
)


def _payload() -> dict:
    return json.loads(_FIXTURE.read_text())


def _schema() -> FormSchema:
    payload = _payload()
    return FormSchema(
        schema_id="ers-ci-test",
        fingerprint=str(payload.get("fingerprint") or "nhs-ers-ci"),
        form_name=str(payload["form_name"]),
        sections=build_sections_from_request(payload["sections"]),
        created_by="test",
        completeness_groups=list(payload.get("completeness_groups") or []),
    )


def _rows(text: str) -> list[dict]:
    return [
        {
            "chunk_id": "chunk-0",
            "text": text,
            "ordinal": 0,
            "char_start": None,
            "char_end": None,
        }
    ]


def _state(text: str) -> dict:
    with patch(
        "libs.pipeline.document_chunk_loader._recognise_chunks",
        recognise_all_as(_schema()),
    ):
        return build_document_chunk_state(_rows(text))


def test_filled_reason_is_not_wholly_non_extractable() -> None:
    state = _state(_FILLED_ERS)
    facing = llm_facing_text(state["sentences"][0]["text"])
    assert _REASON in facing
    marked_lines = [
        ln
        for ln in state["sentences"][0]["text"].splitlines()
        if ln.strip().startswith(NON_EXTRACTABLE_MARKER)
    ]
    assert len(marked_lines) < len(
        [ln for ln in state["sentences"][0]["text"].splitlines() if ln.strip()]
    )


def test_filled_reason_produces_section_hits() -> None:
    hits = collect_section_hits(_schema(), [_FILLED_ERS])
    assert any(
        hit["section_id"] == "reason_for_referral" and hit["checked"] is True
        for hit in hits
    )


def test_filled_reason_satisfies_taught_completeness_group() -> None:
    schema = _schema()
    hits = collect_section_hits(schema, [_FILLED_ERS])
    result = evaluate_completeness_groups(
        schema.completeness_groups,
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=hits,
    )
    assert result["complete"] is True
    names = [row["name"] for row in result["matched_groups"]]
    assert "reason_for_referral_required" in names


def test_placeholder_reason_does_not_satisfy_completeness() -> None:
    schema = _schema()
    hits = collect_section_hits(schema, [_EMPTY_REASON_ERS])
    result = evaluate_completeness_groups(
        schema.completeness_groups,
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=hits,
    )
    assert result["complete"] is False


def _production_cis_only() -> str:
    """The de-identified production e-RS summary, on its own (labelled set)."""
    payload = json.loads(_SHERWOOD_BUNDLE.read_text(encoding="utf-8"))
    return split_chunks([chunk["text"] for chunk in payload["chunks"]])[1].text


def test_cis_only_letter_is_recognised_as_the_national_form() -> None:
    """A Clinical Information Summary with no 2WW page is recognised.

    Recognition reads the letter's own headings (DI-E21DF9EF). There is no
    whole-bundle e-RS bind any more: the national form must earn its match.
    """
    reset_schema_cache()
    with patch(
        "libs.pipeline.document_chunk_loader._candidate_schemas",
        return_value=[_schema()],
    ):
        fields = recognition_fields_from_state({}, _production_cis_only())

    assert fields["form_schema_match"] == "recognised"
    assert fields["form_schema_fingerprint"] == "nhs-ers-clinical-information-v1"


def test_a_trimmed_summary_with_most_headings_missing_is_not_recognised() -> None:
    """Six of fourteen headings is too little to name the form: it pauses."""
    with patch(
        "libs.pipeline.document_chunk_loader._candidate_schemas",
        return_value=[_schema()],
    ):
        fields = recognition_fields_from_state({}, _FILLED_ERS)
    assert fields["form_schema_match"] == "unrecognised"


def test_cis_only_quality_gate_does_not_pause_when_national_form_is_recognised() -> (
    None
):
    reset_schema_cache()
    with (
        patch(
            "libs.pipeline.document_chunk_loader._candidate_schemas",
            return_value=[_schema()],
        ),
        patch(
            "libs.pipeline.form_fingerprint_registry.known_fingerprints",
            return_value={},
        ),
    ):
        out = merge_results(
            {
                "encounter_text": _production_cis_only(),
                "entities": [{"text": "Appendicectomy", "label": "procedure"}],
                "few_shot_max_similarity": 0.0,
            }
        )

    quality = out["document_quality"]
    assert quality["document_quality_score"] == 1.0
    assert "few_shot_ood" not in quality["quality_reasons"]


def test_dated_pmh_list_few_shot_keeps_each_historical_fact() -> None:
    from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES

    example = next(
        row
        for row in EXTRACTION_EXAMPLES
        if row.get("description") == "e-RS dated past medical history list"
    )
    terms = json.loads(example["output"])["terms"]
    texts = {term["text"] for term in terms}
    assert texts == {"Asthma", "Cholecystectomy"}
    assert {term["assertion"] for term in terms} == {"historical"}
