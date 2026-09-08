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


def test_cis_only_letter_binds_national_form_on_quality_reresolve() -> None:
    """A Clinical Information Summary with no 2WW page must still bind.

    Quality scoring re-resolves from letter text. If that path skips the
    national e-RS bind, CIS-only referrals pause as unlike training
    examples even though nhs-ers-clinical-information-v1 is taught.
    """
    from unittest.mock import MagicMock, patch

    from libs.pipeline.form_schema_store import (
        form_schema_fields_from_state,
        reset_schema_cache,
    )

    reset_schema_cache()
    ers = _schema()
    with (
        patch(
            "libs.neo4j_client.client.PatientGraphClient",
            return_value=MagicMock(),
        ),
        patch(
            "libs.pipeline.form_schema_store.resolve_form_schema_traced",
            return_value=(None, "none", "none", ""),
        ),
        patch(
            "libs.pipeline.form_schema_store.load_form_schema",
            return_value=ers,
        ),
    ):
        fields = form_schema_fields_from_state({}, _FILLED_ERS)

    assert fields["form_schema_match"] != "none"
    assert fields["form_schema_fingerprint"] == "nhs-ers-clinical-information-v1"


def test_cis_only_quality_gate_does_not_pause_when_national_form_binds() -> None:
    from unittest.mock import MagicMock, patch

    from libs.pipeline.form_schema_store import reset_schema_cache
    from libs.pipeline_graph.subgraphs.extraction import merge_results

    reset_schema_cache()
    ers = _schema()
    with (
        patch(
            "libs.neo4j_client.client.PatientGraphClient",
            return_value=MagicMock(),
        ),
        patch(
            "libs.pipeline.form_schema_store.resolve_form_schema_traced",
            return_value=(None, "none", "none", ""),
        ),
        patch(
            "libs.pipeline.form_schema_store.load_form_schema",
            return_value=ers,
        ),
    ):
        out = merge_results(
            {
                "encounter_text": _FILLED_ERS,
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
