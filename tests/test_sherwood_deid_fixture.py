"""Regression tests against the de-identified Sherwood 2WW Gynaecology fixture.

Fixture: tests/fixtures/form_schema/sherwood_gynae_2ww_chunks_deid.json
Do NOT copy clinical content from the fixture into this file -- always
reference it by path.

All four tests were written RED first (TDD) and then greened by verifying
the behaviour in libs/pipeline/form_pattern_match.py and
libs/pipeline/form_schema_normalizer.py.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.pipeline.form_pattern_match import is_table_separator, section_matches
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    _resolve_default_sections,
)
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "sherwood_gynae_2ww_chunks_deid.json"
)


@pytest.fixture(scope="module")
def sherwood_chunks() -> list[dict]:
    """Return all chunk dicts from the de-identified Sherwood fixture."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return payload["chunks"]


@pytest.fixture(scope="module")
def chunk_texts(sherwood_chunks) -> list[str]:
    return [c["text"] for c in sherwood_chunks]


# ---------------------------------------------------------------------------
# 1. chunk_idx null falls back to positional index
# ---------------------------------------------------------------------------


def test_chunk_idx_null_falls_back_to_positional_index(sherwood_chunks):
    """chunk_idx is null on every chunk in the real fixture.

    _resolve_default_sections must bind map entries by their position in
    chunk_section_map, not by a stored numeric index, so that the schema
    still routes each chunk to its correct section even when chunk_idx was
    never written.
    """
    # Every chunk in the fixture has null chunk_idx (root cause confirmed).
    null_indices = [c for c in sherwood_chunks if c["chunk_idx"] is not None]
    assert null_indices == [], (
        "Expected all chunks to have chunk_idx=null in the de-identified fixture, "
        f"but these had a value: {null_indices}"
    )

    # Build a tiny schema with two sections so we can prove binding works.
    sec_a = FormSection(
        section_id="SECA",
        section_type="admin",
        label="Admin",
        start_pattern="Patient Details",
    )
    sec_b = FormSection(
        section_id="SECB",
        section_type="checkbox_single",
        label="Cancer type",
        start_pattern="Section A",
    )
    schema = FormSchema(
        schema_id="s",
        fingerprint="fp",
        form_name="Sherwood test",
        sections=[sec_a, sec_b],
        created_by="pytest",
    )

    # Map built with null chunk_idx (mirrors the real fixture).
    chunk_section_map = [
        {"chunk_idx": None, "section_id": "SECA"},  # positional index 0
        {"chunk_idx": None, "section_id": "SECB"},  # positional index 1
    ]
    chunk_count = len(sherwood_chunks)

    defaults = _resolve_default_sections(schema, chunk_count, chunk_section_map)

    # Positional binding: index 0 -> SECA, index 1 -> SECB, rest -> None.
    assert defaults[0] is not None and defaults[0].section_id == "SECA"
    assert defaults[1] is not None and defaults[1].section_id == "SECB"
    for i in range(2, chunk_count):
        assert defaults[i] is None


# ---------------------------------------------------------------------------
# 2. Markdown header lines match with surrounding pipe characters
# ---------------------------------------------------------------------------


def test_markdown_header_matches_with_pipe_syntax(chunk_texts):
    """Section headers in the fixture sit inside markdown table cells.

    section_matches must return True when the taught pattern text appears
    inside a line like "| Section A: ... |".
    """
    # Chunk 2 starts with the Section A heading.
    chunk2 = chunk_texts[2]
    header_line = chunk2.splitlines()[0]

    assert (
        "|" in header_line
    ), f"Expected chunk 2 first line to be a pipe-table row; got: {header_line!r}"

    # The start_pattern is the heading text WITHOUT surrounding pipes.
    assert section_matches("Section A", header_line)
    assert section_matches("Gynaecological Cancer type suspected", header_line)

    # A line that does not contain the pattern must not match.
    assert not section_matches("Section B", header_line)


# ---------------------------------------------------------------------------
# 3. Separator rows are never treated as section headers
# ---------------------------------------------------------------------------


def test_separator_rows_are_skipped(chunk_texts):
    """Every heading in the fixture is followed by a '| --- |' separator row.

    is_table_separator must identify these rows and section_matches must
    return False for them regardless of the supplied pattern.
    """
    separator_examples: list[str] = []
    for text in chunk_texts:
        for line in text.splitlines():
            if is_table_separator(line):
                separator_examples.append(line)

    # There must be separator rows in the fixture.
    assert (
        separator_examples
    ), "No separator rows found in fixture -- fixture may have changed"

    # None of them should be matchable as a section header.
    for sep in separator_examples:
        assert not section_matches(
            "Section A", sep
        ), f"Separator row was incorrectly matched as a section: {sep!r}"
        assert not section_matches("---", sep)


# ---------------------------------------------------------------------------
# 4. Battery matching inside pipe-table rows (chunk 9 blood panel)
# ---------------------------------------------------------------------------


def test_battery_matching_in_pipe_table_row(chunk_texts):
    """Chunk 9 is the blood-results table with pipe-delimited battery rows.

    Every result cell in the fixture is empty, so the printed table must
    seed nothing at all. The same rows carrying results must seed the
    battery named in the first cell and each analyte from a later cell,
    including a battery whose analyte list lives in column 3.
    """
    blood_chunk = chunk_texts[9]
    assert "FBC" in blood_chunk, "Fixture chunk 9 no longer contains FBC"
    assert "CRP" in blood_chunk, "Fixture chunk 9 no longer contains CRP"

    fbc_item = FormSchemaItem(
        pattern="FBC",
        entity_text="Full blood count",
        procedure_snomed="26604007",
        procedure_display="Full blood count",
        semantic_tag="procedure",
        analytes=[
            {"label": "Hb", "snomed_code": "59058009"},
            {"label": "WCC", "snomed_code": "767002"},
            {"label": "Plts", "snomed_code": "61928009"},
        ],
    )
    crp_item = FormSchemaItem(
        pattern="CRP",
        entity_text="C-reactive protein measurement",
        procedure_snomed="55235003",
        procedure_display="CRP",
        semantic_tag="procedure",
        analytes=[
            {"label": "CRP", "snomed_code": "55235003"},
        ],
    )

    blood_section = FormSection(
        section_id="BLOOD",
        section_type="ordered_tests",
        label="Blood results",
        start_pattern="Date specimen collected",
        items=[fbc_item, crp_item],
    )
    schema = FormSchema(
        schema_id="s",
        fingerprint="fp",
        form_name="Sherwood test",
        sections=[blood_section],
        created_by="pytest",
    )

    # The fixture prints the table with no results, so nothing is seeded.
    assert seed_ordered_tests_entities(blood_chunk, schema) == []

    # The same rows, once resulted, seed the battery and its analytes.
    resulted = (
        "| FBC | 23.06.26 | Hb 118 g/L , WCC 7.2 x10^9/L , Plts 250 |  |  |\n"
        "| CRP | 23.06.26 | CRP 4 mg/L |  |  |\n"
    )
    labels = {e["label"] for e in seed_ordered_tests_entities(resulted, schema)}
    assert "FBC" in labels, f"FBC procedure not seeded; got {labels}"
    assert "CRP" in labels, f"CRP procedure not seeded; got {labels}"
    assert "Hb" in labels, f"Hb analyte not seeded; got {labels}"
    assert "WCC" in labels, f"WCC analyte not seeded; got {labels}"
