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
from libs.ner.form_layout_rules import NON_EXTRACTABLE_MARKER, llm_facing_text
from libs.pipeline.document_chunk_loader import build_document_chunk_state
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_schema_request import build_sections_from_request
from libs.pipeline.form_schema_store import form_schema_state_fields
from libs.pipeline.form_section_hits import collect_section_hits

_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "nhs_ers_clinical_information.json"
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
    fields = form_schema_state_fields(
        "exact_hash",
        "nhs-ers-clinical-information-v1",
        "NHS e-RS Clinical Information",
    )
    with patch(
        "libs.pipeline.document_chunk_loader._resolve_chunk_schema",
        return_value=(_schema(), fields),
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
