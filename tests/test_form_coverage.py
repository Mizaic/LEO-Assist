"""Red tests: taught-form coverage must claim every extractable region.

Unclaimed narrative still reaches the extractor (we must not lose it).
The run is flagged form_coverage_incomplete and degraded so a person
can see the control did not finish.

Atlas trace:
  DI: DI-71B94A23
  DO: DO-80754861
  VT: VT-1655FF7B
  Risk: R-7D193158
"""

from __future__ import annotations

from unittest.mock import patch

from libs.ner.form_layout_rules import llm_facing_text
from libs.pipeline.form_coverage import measure_form_coverage
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    apply_schema_to_text,
)

_SECTION_A = FormSection(
    section_id="A",
    section_type="checkbox_single",
    label="Section A: cancer type suspected",
    start_pattern=r"(?i)section\s+a:",
    items=[
        FormSchemaItem(
            pattern="Cervix",
            entity_text="Cervical cancer suspected",
        )
    ],
)


def _schema() -> FormSchema:
    return FormSchema(
        schema_id="cov-1",
        fingerprint="cov",
        form_name="Coverage test form",
        sections=[_SECTION_A],
        created_by="test",
    )


def test_claimed_section_is_not_incomplete() -> None:
    text = (
        "Section A: cancer type suspected\n"
        "Cervix [X] Ovary [ ]\n"
    )
    report = measure_form_coverage(_schema(), [text])
    assert report.incomplete is False
    assert any(region.section_id == "A" for region in report.claimed_regions)


def test_unclaimed_narrative_makes_coverage_incomplete() -> None:
    text = (
        "GP narrative: postmenopausal bleeding for 6 weeks.\n"
        "Section A: cancer type suspected\n"
        "Cervix [X]\n"
    )
    report = measure_form_coverage(_schema(), [text])
    assert report.incomplete is True
    assert any(
        "postmenopausal bleeding" in line.lower() for line in report.unclaimed_lines
    )


def test_unclaimed_narrative_still_extractable() -> None:
    text = (
        "GP narrative: postmenopausal bleeding for 6 weeks.\n"
        "Section A: cancer type suspected\n"
        "Cervix [X]\n"
    )
    facing = llm_facing_text(apply_schema_to_text(text, _schema()))
    assert "postmenopausal bleeding" in facing.lower()


def test_document_banner_is_not_unclaimed_narrative() -> None:
    text = (
        "--- Document: 23 Jun 2026 Two Week Wait Referral.doc ---\n"
        "Section A: cancer type suspected\n"
        "Cervix [X]\n"
    )
    report = measure_form_coverage(_schema(), [text])
    assert report.incomplete is False


def test_blank_lines_do_not_make_coverage_incomplete() -> None:
    text = (
        "\n\n"
        "Section A: cancer type suspected\n"
        "Cervix [X]\n"
    )
    report = measure_form_coverage(_schema(), [text])
    assert report.incomplete is False


def test_chunk_state_degrades_when_coverage_incomplete() -> None:
    from libs.pipeline.document_chunk_loader import build_document_chunk_state
    from libs.pipeline.form_schema_store import form_schema_state_fields

    rows = [
        {
            "chunk_id": "chunk-0",
            "text": (
                "Unclaimed free text about a breast lump.\n"
                "Section A: cancer type suspected\n"
                "Cervix [X]\n"
            ),
            "ordinal": 0,
            "char_start": None,
            "char_end": None,
        }
    ]
    fields = form_schema_state_fields("exact_hash", "cov", "Coverage test form")
    with patch(
        "libs.pipeline.document_chunk_loader._resolve_chunk_schema",
        return_value=(_schema(), fields),
    ):
        state = build_document_chunk_state(rows)
    assert state.get("form_coverage_incomplete") is True
    assert state.get("degraded") is True
    assert "breast lump" in llm_facing_text(state["sentences"][0]["text"])
