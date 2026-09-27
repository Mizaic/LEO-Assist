"""Neither production :FormSchema node stores a chunk_section_map.

Both active Sherwood Forest schema nodes (`sfh-gynae-2ww-v1` and
`e61c4289e199cfb5`) have no ``chunk_section_map`` property, so
``_record_to_schema`` builds an empty list and
``normalise_chunks_with_schema`` falls back to header-driven binding.

These tests pin the answer to "the absence does not degrade taught-form
normalisation for this bundle". Every taught section heading sits inside
its own stored chunk, so the header scan plus the carried-section rule
reproduce the correct binding. Forcing the blood-results continuation
chunk into the ordered_tests section would instead inject placeholder
analyte rows for tests that were never resulted.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
  DO: DO-020C7B5C
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    _apply_chunk_text_stateful,
    normalise_chunks_with_schema,
)
from libs.pipeline.form_schema_request import dict_to_section

FIXTURES = Path(__file__).parent / "fixtures" / "form_schema"
TEMPLATE_FIXTURE = FIXTURES / "sfh_gynae_2ww_template.json"
CHUNKS_FIXTURE = FIXTURES / "sherwood_gynae_2ww_chunks_deid.json"

SECTION_C_INDEX = 6
BLOOD_TABLE_INDEX = 9
SECTION_C_CHARS = 928

# The binding a hand-built map would assert, one entry per section chunk.
HAND_BUILT_MAP = [
    {"chunk_idx": 2, "section_id": "section_a_cancer_type"},
    {"chunk_idx": 3, "section_id": "section_b_symptoms"},
    {"chunk_idx": 4, "section_id": "primary_care_pathway"},
    {"chunk_idx": 5, "section_id": "patient_awareness"},
    {"chunk_idx": 6, "section_id": "section_c_clinical_details"},
    {"chunk_idx": 7, "section_id": "section_d_investigations"},
]

EXPECTED_HEADER_BINDING = [
    None,
    None,
    "section_a_cancer_type",
    "section_b_symptoms",
    "primary_care_pathway",
    "patient_awareness",
    "section_c_clinical_details",
    "section_e_performance",
    "ecog_status",
    "ecog_status",
    "ecog_status",
]


def _taught_schema() -> FormSchema:
    payload = json.loads(TEMPLATE_FIXTURE.read_text(encoding="utf-8"))
    return FormSchema(
        schema_id="sfh-gynae-2ww",
        fingerprint="e61c4289e199cfb5",
        form_name=str(payload["form_name"]),
        sections=[dict_to_section(s) for s in payload["sections"]],
        created_by="seed",
        organization_id="RK5",
        service_id="7980224",
    )


def _stored_chunks() -> list[str]:
    payload = json.loads(CHUNKS_FIXTURE.read_text(encoding="utf-8"))
    return [str(c["text"]) for c in payload["chunks"]]


def test_headers_recover_section_binding_without_a_chunk_map() -> None:
    """Each stored chunk resolves to its true section from its heading."""
    schema = _taught_schema()
    carried = None
    resolved: list[str | None] = []
    for chunk in _stored_chunks():
        _text, carried = _apply_chunk_text_stateful(chunk, schema.sections, carried)
        resolved.append(carried.section_id if carried else None)
    assert resolved == EXPECTED_HEADER_BINDING


def test_empty_chunk_map_matches_hand_built_map_on_every_form_section() -> None:
    """Sections A to D and Section C narrative normalise identically."""
    schema = _taught_schema()
    chunks = _stored_chunks()
    without_map = normalise_chunks_with_schema(schema, chunks, [])
    with_map = normalise_chunks_with_schema(schema, chunks, HAND_BUILT_MAP)
    assert without_map[:BLOOD_TABLE_INDEX] == with_map[:BLOOD_TABLE_INDEX]


def test_section_c_narrative_survives_without_a_chunk_map() -> None:
    """The free-text clinical narrative is passed through unchanged."""
    schema = _taught_schema()
    chunks = _stored_chunks()
    section_c = normalise_chunks_with_schema(schema, chunks, [])[SECTION_C_INDEX]
    assert len(section_c) == SECTION_C_CHARS
    for marker in (
        "vaginal discharge",
        "dyspareunia",
        "post menopausal for 1.5yrs",
        "swabs taken",
        "polyp noted",
    ):
        assert marker in section_c.lower()


def test_forcing_blood_table_into_ordered_tests_invents_nothing() -> None:
    """Binding the unresulted blood table to Section D fabricates no value.

    This once emitted a value slot per taught analyte, so mapping the
    table to its own section invented somewhere to put results the
    letter never carried. Result gating closes that off: an unresulted
    row is marked non-extractable whether or not the map binds it.
    """
    schema = _taught_schema()
    chunks = _stored_chunks()
    without_map = normalise_chunks_with_schema(schema, chunks, [])
    forced = normalise_chunks_with_schema(
        schema,
        chunks,
        [{"chunk_idx": BLOOD_TABLE_INDEX, "section_id": "section_d_investigations"}],
    )
    for text in (without_map[BLOOD_TABLE_INDEX], forced[BLOOD_TABLE_INDEX]):
        assert "{{NUMERIC_VALUE}}" not in text
        assert "{{UNIT}}" not in text
