"""Ticked-checkbox facts are seeded at raw-letter offsets.

Atlas:
  DI: DI-0B907354
  DO: DO-AC2014F7
  VT: VT-24D1E4F6
  Risk: R-3926E48D
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.form_checkbox_seed import (
    merge_checkbox_seed_entities,
    seed_checkbox_entities,
)
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    apply_schema_to_text,
)
from libs.pipeline.form_schema_request import build_sections_from_request

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

_FORM = Path(__file__).resolve().parents[1] / (
    "tests/fixtures/form_schema/sfh_gynae_2ww_template.json"
)

_PACKED_YES = (
    "| B7. HRT: Unexpected or prolonged bleeding persisting for more "
    "than 4 weeks after STOPPING HRT B8. HRT: bleeding persisting AFTER "
    "6 months of HRT use, if on continuous combined HRT. | [X] Yes [ ] No |"
)

_PACKED_NO = _PACKED_YES.replace("[X] Yes [ ] No", "[ ] Yes [X] No")

_B7_TICK = (
    "unexpected or prolonged bleeding persisting more than 4 weeks "
    "after stopping hrt"
)
_B8_TICK = "bleeding persisting after 6 months of continuous combined hrt"


def _schema() -> FormSchema:
    return FormSchema(
        schema_id="test-checkbox-seed",
        fingerprint="abc123",
        form_name="Gynaecology 2WW Referral",
        sections=[_SECTION],
        created_by="test",
    )


def _sfh_schema() -> FormSchema:
    payload = json.loads(_FORM.read_text())
    return FormSchema(
        schema_id="sfh-probe",
        fingerprint="sfh-gynae-2ww-v1",
        form_name=str(payload.get("form_name") or "SFH gynae"),
        sections=build_sections_from_request(list(payload.get("sections") or [])),
        created_by="test",
        completeness_groups=list(payload.get("completeness_groups") or []),
    )


def test_bare_x_on_packed_row_seeds_endometrium() -> None:
    raw = (
        "Section A: Gynaecological Cancer type suspected\n"
        "Ovary [ ] Cervix [ ] Endometrium X Vagina [ ] Vulva [ ]\n"
    )
    schema = FormSchema(
        schema_id="bare-x-seed",
        fingerprint="bare-x",
        form_name="Gynaecology 2WW Referral",
        created_by="test",
        sections=[
            FormSection(
                section_id="A",
                section_type="checkbox_multi",
                label="Section A",
                start_pattern=r"(?i)section\s+a",
                items=[
                    FormSchemaItem(
                        pattern="Ovary",
                        entity_text="Suspected ovarian cancer",
                    ),
                    FormSchemaItem(
                        pattern="Endometrium",
                        entity_text="Suspected endometrial cancer",
                    ),
                ],
            )
        ],
    )
    seeded = seed_checkbox_entities(raw, schema)
    texts = {str(row.get("entity_text") or "") for row in seeded}
    assert "Suspected endometrial cancer" in texts
    assert "Suspected ovarian cancer" not in texts


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


def test_ticked_b7_seeds_pmb_lookup_term() -> None:
    raw = (
        "Section B: Signs/symptoms\n"
        "B7. HRT: Unexpected bleeding after stopping HRT Yes [X] No [ ]\n"
    )
    schema = FormSchema(
        schema_id="test-b7-seed",
        fingerprint="b7test",
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
                        pattern="B7.",
                        entity_text=(
                            "Unexpected or prolonged bleeding persisting "
                            "more than 4 weeks after stopping HRT"
                        ),
                        semantic_tag="finding",
                        assertion="present",
                    )
                ],
            )
        ],
    )
    seeded = seed_checkbox_entities(raw, schema)
    assert len(seeded) == 1
    assert seeded[0]["lookup_term"].lower() == _B7_TICK


def test_packed_b7_b8_yes_seeds_distinct_present_bleed_meanings() -> None:
    seeded = seed_checkbox_entities(_PACKED_YES, _sfh_schema())
    lookups = {str(row.get("lookup_term") or "").lower() for row in seeded}
    assert lookups == {_B7_TICK, _B8_TICK}
    assert all(row.get("assertion") == "present" for row in seeded)
    assert {str(row.get("text") or "") for row in seeded} <= {"B7.", "B8."}


def test_packed_b7_b8_no_does_not_seed() -> None:
    seeded = seed_checkbox_entities(_PACKED_NO, _sfh_schema())
    assert seeded == []


def test_checkbox_seed_replaces_llm_absent_on_same_label() -> None:
    seeded = seed_checkbox_entities(_PACKED_YES, _sfh_schema())
    llm = [{"text": "B7.", "assertion": "absent", "label": "finding"}]
    merged = merge_checkbox_seed_entities(llm, seeded)
    b7 = next(row for row in merged if row.get("text") == "B7.")
    assert b7["assertion"] == "present"
    assert b7.get("__source") == "form_schema_checkbox"


def test_long_ecog_box_before_zero_seeds_fully_active() -> None:
    raw = (
        "ECOG PERFORMANCE STATUS (please tick one): - [X] 0 - Fully active, "
        "able to carry on all pre-disease activity [ ] 1 - Restricted in "
        "physically strenuous activity [ ] 2 - Ambulatory and capable of all "
        "selfcare [ ] 3 - Capable of only limited selfcare, confined to bed "
        "or chair more than 50% [ ] 4 - Completely disabled. Totally "
        "confined to bed or chair\n"
    )
    seeded = seed_checkbox_entities(raw, _sfh_schema())
    lookups = {str(row.get("lookup_term") or "") for row in seeded}
    assert "ECOG 0 fully active" in lookups
    assert all(row.get("assertion") == "present" for row in seeded)


def test_pmb_first_episode_yes_seeds_despite_paren_in_print() -> None:
    raw = (
        "For post menopausal bleeding\n"
        "| New presentation with PMB (first episode - for representations "
        "please refer 2ww | Yes [X] |\n"
    )
    seeded = seed_checkbox_entities(raw, _sfh_schema())
    lookups = {str(row.get("lookup_term") or "").lower() for row in seeded}
    assert "new first-episode postmenopausal bleeding" in lookups


def test_awareness_two_box_table_yes_seeds() -> None:
    raw = (
        "Does the patient know?\n"
        "| Is the patient aware that they have been referred on an urgent "
        "basis? | [X] | [ ] |\n"
    )
    seeded = seed_checkbox_entities(raw, _sfh_schema())
    lookups = {str(row.get("lookup_term") or "").lower() for row in seeded}
    assert "patient aware of urgent referral" in lookups


def test_compact_ecog_one_seeds_restricted_activity() -> None:
    raw = (
        "Patient Fitness (ECOG STATUS) : No ECOG in patient record "
        "0 [ ] 1 [X] 3 [ ] 4 [ ]\n"
    )
    schema = FormSchema(
        schema_id="ecog-compact",
        fingerprint="ecog",
        form_name="Gynae 2WW",
        created_by="test",
        sections=[
            FormSection(
                section_id="ecog_status",
                section_type="scale",
                label="ECOG",
                start_pattern="ECOG",
                items=[
                    FormSchemaItem(
                        pattern="0 [",
                        entity_text="ECOG 0 fully active",
                        semantic_tag="finding",
                        assertion="present",
                    ),
                    FormSchemaItem(
                        pattern="1 [",
                        entity_text="ECOG 1 restricted in strenuous activity",
                        semantic_tag="finding",
                        assertion="present",
                    ),
                    FormSchemaItem(
                        pattern="3 [",
                        entity_text="ECOG 3 limited selfcare",
                        semantic_tag="finding",
                        assertion="present",
                    ),
                    FormSchemaItem(
                        pattern="4 [",
                        entity_text="ECOG 4 completely disabled",
                        semantic_tag="finding",
                        assertion="present",
                    ),
                ],
            )
        ],
    )
    seeded = seed_checkbox_entities(raw, schema)
    assert len(seeded) == 1
    assert seeded[0]["lookup_term"] == "ECOG 1 restricted in strenuous activity"


def test_seed_replaces_longer_extractor_span_with_same_printed_label() -> None:
    """A taught tick replaces an extractor row that quoted the whole scale line."""
    raw = (
        "ECOG PERFORMANCE STATUS; [X] 0 - Fully active, able to carry on "
        "all pre-disease and performance without restriction [ ] 1 - "
        "Restricted in physically strenuous activity\n"
    )
    schema = FormSchema(
        schema_id="ecog-merge",
        fingerprint="ecog-merge",
        form_name="Breast 2WW",
        created_by="test",
        sections=[
            FormSection(
                section_id="performance_status",
                section_type="scale",
                label="Performance status",
                start_pattern="ECOG",
                items=[
                    FormSchemaItem(
                        pattern="Fully active",
                        entity_text="ECOG 0 fully active without restriction",
                        semantic_tag="finding",
                        assertion="present",
                    ),
                    FormSchemaItem(
                        pattern="Restricted in physically strenuous",
                        entity_text="ECOG 1 restricted in strenuous activity",
                        semantic_tag="finding",
                        assertion="present",
                    ),
                ],
            )
        ],
    )
    seeded = seed_checkbox_entities(raw, schema)
    extractor = [
        {
            "text": (
                "0 - Fully active, able to carry on all pre-disease "
                "and performance without restriction"
            ),
            "assertion": "present",
            "label": "finding",
            "concept_id": "373803006",
        }
    ]
    merged = merge_checkbox_seed_entities(extractor, seeded)
    assert len(merged) == 1
    assert merged[0].get("__source") == "form_schema_checkbox"
    assert merged[0]["lookup_term"] == "ECOG 0 fully active without restriction"
    assert merged[0].get("concept_id") != "373803006"


def test_ticked_b6_seeds_taught_pcb_concept() -> None:
    """A ticked B6 box must publish the FormSchema PCB code.

    Atlas: DI-0B907354 / DI-50BE367C / VT-24D1E4F6
    """
    raw = (
        "| B6. Postcoital bleeding persisting more than 4 weeks, age over 35 "
        "| Yes [X] No [ ] |"
    )
    seeded = seed_checkbox_entities(raw, _sfh_schema())
    pcb = [
        row
        for row in seeded
        if "postcoital" in str(row.get("entity_text") or "").lower()
    ]
    assert pcb
    assert str(pcb[0].get("concept_id")) == "48880000"
    assert pcb[0].get("assertion") == "present"


def test_ticked_b5_and_b2_seed_taught_finding_codes() -> None:
    raw = (
        "| B2. vulval mass | Yes [X] No [ ] |\n"
        "| B5. Postmenopausal bleeding in woman aged over 55 not on HRT "
        "| Yes [X] No [ ] |"
    )
    seeded = seed_checkbox_entities(raw, _sfh_schema())
    by_code = {str(row.get("concept_id") or "") for row in seeded}
    assert "289477004" in by_code
    assert "76742009" in by_code


def test_packed_yes_seed_stays_present_beside_empty_no_box() -> None:
    from libs.ner.context_engine import apply_context_detection_to_dicts

    letter = "| B6. Postcoital bleeding | [ ] Yes [ ] No |\n" + _PACKED_YES
    seeded = seed_checkbox_entities(letter, _sfh_schema())
    apply_context_detection_to_dicts(letter, seeded)
    assert seeded
    assert all(row.get("assertion") == "present" for row in seeded)


_B4_RAW = (
    "Section B: Symptoms\n"
    "| B4. Suspicious pelvic mass on pelvic ultrasound | [X] Yes [ ] No |\n"
)

_B4_SECTION = FormSection(
    section_id="section_b_symptoms",
    section_type="checkbox_yesno",
    label="Section B: Symptoms",
    start_pattern=r"(?i)section\s+b:",
    items=[
        FormSchemaItem(
            pattern="B4.",
            entity_text="Suspicious pelvic mass on ultrasound",
            semantic_tag="finding",
            assertion="present",
            procedure_snomed="24848001",
            procedure_display="Pelvic echography",
        ),
    ],
)


def _b4_schema(section: FormSection) -> FormSchema:
    return FormSchema(
        schema_id="b4-scan-seed",
        fingerprint="sfh-gynae-2ww-v1",
        form_name="Gynaecology 2WW Referral",
        sections=[section],
        created_by="test",
    )


def test_a_ticked_box_that_names_a_scan_records_the_scan() -> None:
    """Ticking B4 asserts a pelvic ultrasound was carried out.

    B4 reads "Suspicious pelvic mass on pelvic ultrasound". A tick there
    says two things: the mass is suspicious, and somebody scanned her to
    find it. Only the finding was ever coded, so NICE NG12 1.5.2 kept
    asking for the ultrasound the form had already reported.

    The schema already carries ``procedure_snomed`` for exactly this,
    described as "filled by the teacher". This asserts the seeder
    honours it.
    """
    schema = _b4_schema(_B4_SECTION)
    text = apply_schema_to_text(_B4_RAW, schema)

    entities = seed_checkbox_entities(text, schema)
    procedures = [e for e in entities if e.get("concept_id") == "24848001"]

    assert procedures, f"no pelvic ultrasound entity in {entities}"
    assert procedures[0]["semantic_tag"] == "procedure"
    assert procedures[0]["assertion"] == "present"


def test_an_unticked_box_records_no_scan() -> None:
    """A blank B4 is not evidence anyone scanned her."""
    schema = _b4_schema(_B4_SECTION)
    raw = (
        "Section B: Symptoms\n"
        "| B4. Suspicious pelvic mass on pelvic ultrasound | [ ] Yes [X] No |\n"
    )
    text = apply_schema_to_text(raw, schema)

    entities = seed_checkbox_entities(text, schema)

    assert not [e for e in entities if e.get("concept_id") == "24848001"]


def test_a_ticked_box_with_no_taught_scan_adds_nothing_extra() -> None:
    """Most ticks name no procedure, and must stay single-fact."""
    section = FormSection(
        section_id="section_b_symptoms",
        section_type="checkbox_yesno",
        label="Section B: Symptoms",
        start_pattern=r"(?i)section\s+b:",
        items=[
            FormSchemaItem(
                pattern="B4.",
                entity_text="Suspicious pelvic mass on ultrasound",
                semantic_tag="finding",
                assertion="present",
            ),
        ],
    )
    schema = _b4_schema(section)
    text = apply_schema_to_text(_B4_RAW, schema)

    entities = seed_checkbox_entities(text, schema)

    assert len(entities) == 1
    assert entities[0]["semantic_tag"] == "finding"
