"""Ticked-checkbox facts are seeded at raw-letter offsets.

Atlas:
  DI: DI-0B907354
  DO: DO-AC2014F7
  VT: VT-24D1E4F6
  Risk: R-3926E48D
"""

from __future__ import annotations

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.form_checkbox_seed import seed_checkbox_entities
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    apply_schema_to_text,
)

_RAW = (
    "Section A: Gynaecological Cancer type suspected\n"
    "Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]\n"
)

_SECTION = FormSection(
    section_id="A",
    section_type="checkbox_single",
    label="Section A: Gynaecological Cancer type suspected",
    start_pattern=r"(?i)section\s+a:",
    items=[
        FormSchemaItem(
            pattern="Ovary",
            entity_text="Ovarian cancer suspected",
            semantic_tag="situation",
            assertion="present",
        ),
        FormSchemaItem(
            pattern="Cervix",
            entity_text="Cervical cancer suspected",
            semantic_tag="situation",
            assertion="present",
        ),
    ],
)


def _schema() -> FormSchema:
    return FormSchema(
        schema_id="test-checkbox-seed",
        fingerprint="abc123",
        form_name="Gynaecology 2WW Referral",
        sections=[_SECTION],
        created_by="test",
    )


def test_ticked_checkbox_is_seeded_at_raw_letter_offset() -> None:
    seeded = seed_checkbox_entities(_RAW, _schema())
    assert len(seeded) == 1
    ent = seeded[0]
    start = int(ent["start"])
    end = int(ent["end"])
    assert _RAW[start:end].lower() == "cervix"
    assert "Cervical cancer suspected" not in _RAW


def test_normaliser_does_not_insert_synthesised_entity_text() -> None:
    result = apply_schema_to_text(_RAW, _schema())
    extractable = [ln for ln in result.splitlines() if NON_EXTRACTABLE_MARKER not in ln]
    assert not any("Cervical cancer suspected" in ln for ln in extractable)
    assert not any("Ovarian cancer suspected" in ln for ln in extractable)


def test_ticked_b2_seeds_lookup_term_from_entity_text() -> None:
    raw = "Section B: Signs/symptoms\nB2. Lesion on vulva Yes [X] No [ ]\n"
    schema = FormSchema(
        schema_id="test-b2-seed",
        fingerprint="b2test",
        form_name="Gynaecology 2WW Referral",
        created_by="test",
        sections=[
            FormSection(
                section_id="B",
                section_type="checkbox_yesno",
                label="Section B",
                start_pattern=r"(?i)section\s+b",
                items=[
                    FormSchemaItem(
                        pattern="B2.",
                        entity_text="vulval lump",
                        semantic_tag="finding",
                        assertion="present",
                    )
                ],
            )
        ],
    )
    seeded = seed_checkbox_entities(raw, schema)
    assert len(seeded) == 1
    assert seeded[0]["text"] == "B2."
    assert seeded[0]["entity_text"] == "vulval lump"
    assert seeded[0]["lookup_term"] == "vulval lump"
