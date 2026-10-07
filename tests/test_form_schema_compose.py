"""Compose e-RS Clinical Information hits with a specialty 2WW form.

A specialty bloods group that is empty on the 2WW form must still match
when the national e-RS Findings section is filled. The SBAR situation
must stay on the specialty clinical section.

Each recognised document brings its own form. Here the recognition
outcomes are given directly, so the tests pin composition only.

Atlas trace:
  UN: UN-AF530E8E, UN-89E2AE36
  DI: DI-1A1943BB, DI-E21DF9EF
  DO: DO-E3AF3879, DO-E458EEC5
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.completeness.evaluator import evaluate_completeness_groups
from libs.form_recognition.recogniser import Recognised
from libs.pipeline.form_recognition_apply import recognition_fields
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_schema_request import build_sections_from_request
from libs.sbar.situation_source import build_structured_situation

_ERS_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "nhs_ers_clinical_information.json"
)

_SPECIALTY_BLOODS = (
    "| Section D: Investigations performed |\n"
    "| MANDATORY |\n"
    "| FBC |  | Hb , WCC , Plts , MCV , Neut |  |  |  |\n"
)

_SPECIALTY_CLINICAL = (
    "| Section B: Examination |\n"
    "| Affected side a 1 cm fixed lump in the left breast. |\n"
)

_ERS_FILLED_BLOODS = (
    "--- Document: Clinical Information.pdf ---\n"
    "Clinical Information Summary\n"
    "Reason for referral\n"
    "See attachment\n"
    "Findings\n"
    "FBC Hb 128 g/L WCC 6.2 Plts 240\n"
    "UE Na 139 K 4.1 Urea 5.2\n"
)

_ERS_PLACEHOLDER = (
    "--- Document: Clinical Information.pdf ---\n"
    "Clinical Information Summary\n"
    "Patient Information\n"
    "See attachment\n"
    "Findings\n"
    "No Information Provided\n"
)


def _ers_schema() -> FormSchema:
    payload = json.loads(_ERS_FIXTURE.read_text(encoding="ascii"))
    return FormSchema(
        schema_id="ers-ci",
        fingerprint=str(payload["fingerprint"]),
        form_name=str(payload["form_name"]),
        sections=build_sections_from_request(payload["sections"]),
        created_by="test",
        completeness_groups=list(payload.get("completeness_groups") or []),
    )


def _specialty_schema() -> FormSchema:
    return FormSchema(
        schema_id="breast-2ww",
        fingerprint="sfh-breast-2ww-v1",
        form_name="Breast Unit 2WW",
        created_by="test",
        sections=build_sections_from_request(
            [
                {
                    "section_id": "section_b_examination",
                    "section_type": "free_text",
                    "label": "Section B: Clinical examination",
                    "start_pattern": "Section B",
                    "items": [],
                    "semantic_tags": ["finding"],
                },
                {
                    "section_id": "section_d_investigations",
                    "section_type": "ordered_tests",
                    "label": "Section D: Investigations performed",
                    "start_pattern": "Section D: Investigations",
                    "items": [
                        {
                            "pattern": "FBC",
                            "entity_text": "Complete blood count",
                            "semantic_tag": "procedure",
                        }
                    ],
                    "semantic_tags": [],
                },
            ]
        ),
        completeness_groups=[
            {
                "name": "investigations_or_bloods_required",
                "kind": "required_section",
                "required": True,
                "min_count": 1,
                "semantic_categories": [],
                "concept_ids": [],
                "members": [{"section_id": "section_d_investigations"}],
            }
        ],
    )


def _both_recognised(chunks: list[str]) -> dict:
    specialty, ers = _specialty_schema(), _ers_schema()
    outcomes = [Recognised(schema=specialty), Recognised(schema=ers)]
    return recognition_fields(chunks, outcomes)


def test_specialty_bloods_group_matches_from_ers_findings() -> None:
    specialty = _specialty_schema()
    chunks = [
        "--- Document: Breast Unit Referral Form.doc ---\n" + _SPECIALTY_BLOODS,
        _ERS_FILLED_BLOODS,
    ]
    hits = _both_recognised(chunks)["section_hits"]
    result = evaluate_completeness_groups(
        specialty.completeness_groups,
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=hits,
    )
    names = [row["name"] for row in result["matched_groups"]]
    assert "investigations_or_bloods_required" in names
    assert result["complete"] is True


def test_placeholder_ers_findings_does_not_match_specialty_bloods() -> None:
    specialty = _specialty_schema()
    chunks = [
        "--- Document: Breast Unit Referral Form.doc ---\n" + _SPECIALTY_BLOODS,
        _ERS_PLACEHOLDER,
    ]
    hits = _both_recognised(chunks)["section_hits"]
    result = evaluate_completeness_groups(
        specialty.completeness_groups,
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=hits,
    )
    assert result["complete"] is False


def test_sbar_situation_stays_on_specialty_clinical_section() -> None:
    letter = (
        "--- Document: Breast Unit Referral Form.doc ---\n"
        f"{_SPECIALTY_CLINICAL}\n"
        f"{_ERS_FILLED_BLOODS}"
    )
    sections = _both_recognised([letter])["form_sections"]
    result = build_structured_situation(
        referral_request=None,
        referral_reason=None,
        trigger_scoped_letter=letter,
        form_sections=sections,
    )
    assert result.source_precedence == ["form_clinical_section"]
    assert "1 cm fixed lump" in result.headline
    assert "See attachment" not in result.headline
    assert "Patient Information" not in result.headline
