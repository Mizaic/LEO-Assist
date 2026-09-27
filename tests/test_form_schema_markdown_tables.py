"""Form teacher against a markdown pipe-table referral bundle.

Real NHS referral letters reach LEO as markdown tables, not plain lines.
Section headings sit inside table cells, separator rows (``| --- |``)
follow every heading, labels and answers live in different cells, and a
second document is appended to the same bundle.

Fixture: tests/fixtures/form_schema/gynae_2ww_markdown_chunks.json
(synthetic, de-identified).

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from libs.llm_client import form_schema_detector
from libs.pipeline.document_chunk_loader import (
    CHUNK_TEXT_SEPARATOR,
    bundle_fingerprint,
    strip_pdf_attachments,
)
from libs.pipeline.document_quality import form_fingerprint
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    normalise_chunks_with_schema,
)
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities
from libs.pipeline.form_section_splitter import split_form_sections

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "gynae_2ww_markdown_chunks.json"
)


@pytest.fixture(scope="module")
def chunks() -> list[str]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [c["text"] for c in payload["chunks"]]


@pytest.fixture(scope="module")
def letter_text(chunks: list[str]) -> str:
    """Primary referral text, as the teach dialog receives it."""
    return strip_pdf_attachments(CHUNK_TEXT_SEPARATOR.join(chunks))


def _section(section_id: str, start_pattern: str, **kw) -> FormSection:
    return FormSection(
        section_id=section_id,
        section_type=kw.pop("section_type", "checkbox_single"),
        label=kw.pop("label", section_id),
        start_pattern=start_pattern,
        **kw,
    )


# -- Defect 1: an uncompilable start pattern must not raise -----------------


def test_invalid_start_pattern_does_not_raise() -> None:
    """An unbalanced bracket in a taught pattern must not crash extraction."""
    section = _section("ECOG", r"(?i)Patient\s+Fitness\s+(ECOG")
    assert section.matches_header("| Patient Fitness (ECOG STATUS) : 1 [X] |") is True


def test_invalid_start_pattern_returns_false_when_absent() -> None:
    section = _section("ECOG", r"(?i)Patient\s+Fitness\s+(ECOG")
    assert section.matches_header("| Section B: Signs/symptoms |") is False


def test_a_broken_box_pattern_does_not_match_every_zero() -> None:
    """``0 [`` is an unclosed class. Its leftover token must not be '0'."""
    from libs.pipeline.form_pattern_match import safe_search

    assert safe_search("0 [", "[X] 0 - Fully active") is None


def test_literal_label_with_brackets_matches_its_own_row() -> None:
    """Teachers often paste the raw label; it is not valid regex."""
    section = _section("PMB", "(Please put a X in appropriate boxes)")
    assert section.matches_header("| (Please put a X in appropriate boxes) |") is True


def test_splitter_start_patterns_are_valid_regex(letter_text: str) -> None:
    """The auto-detect splitter must not propose uncompilable patterns."""
    bad: list[str] = []
    for section in split_form_sections(letter_text):
        try:
            re.compile(section["start_pattern"])
        except re.error:
            bad.append(section["start_pattern"])
    assert bad == []


# -- Defect 2: separator rows are structure, not content --------------------


@pytest.mark.parametrize(
    "row", ["| --- |", "| --- | --- |", "|---|---|---|", "| :--- | ---: |"]
)
def test_table_separator_row_is_never_a_section_header(row: str) -> None:
    section = _section("A", r"(?i)-")
    assert section.matches_header(row) is False


def test_markdown_cell_heading_still_matches() -> None:
    section = _section("A", r"(?i)Section A: Gynaecological Cancer type suspected")
    assert (
        section.matches_header("| Section A: Gynaecological Cancer type suspected |")
        is True
    )


# -- Defect 3: fingerprint must be scoped to the primary document -----------


def test_runtime_fingerprint_matches_taught_fingerprint(
    chunks: list[str], letter_text: str
) -> None:
    """A bundle with a PDF attachment must fingerprint like the letter alone.

    The teach dialog fingerprints the PDF-stripped letter. If the runtime
    loader fingerprints the whole bundle the taught schema never loads.
    """
    assert bundle_fingerprint(chunks) == form_fingerprint(letter_text)


def test_fingerprint_is_stable_when_attachments_differ(chunks: list[str]) -> None:
    without_attachment = chunks[:-1]
    assert bundle_fingerprint(chunks) == bundle_fingerprint(
        without_attachment + ["--- Document: Other.pdf ---\n\nNo Information Provided"]
    )


# -- Defect 4: chunk_section_map binding ------------------------------------


def test_chunk_map_built_over_another_segmentation_does_not_misroute(
    chunks: list[str],
) -> None:
    """A map whose indexes exceed the chunk count must be ignored, not applied.

    The map is built in the teach dialog by splitting the letter on blank
    lines, which yields far more parts than there are stored chunks.
    Applying those indexes positionally routes clinical chunks into admin
    sections.
    """
    admin = _section("ADMIN", r"(?i)Patient Details", section_type="admin")
    site = _section(
        "A",
        r"(?i)Section A: Gynaecological Cancer type suspected",
        items=[
            FormSchemaItem(pattern="Cervix", entity_text="Cervical cancer suspected")
        ],
    )
    schema = FormSchema(
        schema_id="s",
        fingerprint="f",
        form_name="x",
        sections=[admin, site],
        created_by="t",
        chunk_section_map=[{"chunk_idx": i, "section_id": "ADMIN"} for i in range(40)],
    )
    parts = normalise_chunks_with_schema(schema, chunks, schema.chunk_section_map)
    assert "Cervix" in parts[2]
    assert "Cervical cancer suspected" not in parts[2]


def test_chunk_map_with_null_chunk_idx_falls_back_to_position(
    chunks: list[str],
) -> None:
    """Stored chunks carry no chunk_idx, so a null entry must use its order."""
    site = _section(
        "A",
        r"(?i)Section A: Gynaecological Cancer type suspected",
        items=[
            FormSchemaItem(pattern="Cervix", entity_text="Cervical cancer suspected")
        ],
    )
    schema = FormSchema(
        schema_id="s",
        fingerprint="f",
        form_name="x",
        sections=[site],
        created_by="t",
    )
    entries = [{"chunk_idx": None, "section_id": "A"} for _ in chunks]
    parts = normalise_chunks_with_schema(schema, chunks, entries)
    assert len(parts) == len(chunks)
    assert "Cervix" in parts[2]
    assert "Cervical cancer suspected" not in parts[2]


def test_normalise_returns_one_part_per_chunk(chunks: list[str]) -> None:
    """Chunks contain blank lines, so a joined result cannot be re-split."""
    site = _section("A", r"(?i)Section A: Gynaecological Cancer type suspected")
    schema = FormSchema(
        schema_id="s",
        fingerprint="f",
        form_name="x",
        sections=[site],
        created_by="t",
    )
    parts = normalise_chunks_with_schema(schema, chunks, [])
    assert len(parts) == len(chunks)


# -- Defect 5: analytes inside pipe cells -----------------------------------


def _blood_section() -> FormSection:
    fbc = FormSchemaItem(
        pattern="FBC",
        entity_text="Full blood count",
        procedure_snomed="26604007",
        analytes=[
            {"label": "Hb", "snomed_code": "441689006", "display": "Haemoglobin"},
            {"label": "WCC", "snomed_code": "767002", "display": "White cell count"},
            {"label": "Plts", "snomed_code": "61928009", "display": "Platelet count"},
        ],
    )
    esr = FormSchemaItem(pattern="ESR", entity_text="ESR", procedure_snomed="165416008")
    return _section(
        "BLOOD",
        r"(?i)Blood Results",
        section_type="ordered_tests",
        items=[fbc, esr],
    )


def _blood_schema() -> FormSchema:
    return FormSchema(
        schema_id="s",
        fingerprint="f",
        form_name="x",
        sections=[_blood_section()],
        created_by="t",
    )


# The same table shape as fixture chunk 9, once the laboratory reports
# results: a specimen-date cell, values beside their analytes, and two
# batteries sharing one row.
RESULTED_BLOOD_TABLE = """\
Blood Results (Last ):

| FBC | 23.06.26 | Hb 118 g/L , WCC 7.2 x10^9/L , Plts 250 |  |  |
| CRP | 23.06.26 | 4 mg/L | ESR | 12 mm/hr |
"""


def test_battery_and_analytes_seed_from_comma_separated_pipe_cell() -> None:
    seeded = seed_ordered_tests_entities(RESULTED_BLOOD_TABLE, _blood_schema())
    labels = {e["label"] for e in seeded}
    assert {"FBC", "Hb", "WCC", "Plts", "ESR"} <= labels


def test_battery_seeds_from_a_later_column_of_a_shared_row() -> None:
    """A resulted ``| CRP | ... | ESR | ... |`` row seeds the taught ESR."""
    seeded = seed_ordered_tests_entities(RESULTED_BLOOD_TABLE, _blood_schema())
    esr = [e for e in seeded if e["label"] == "ESR"]
    assert esr and esr[0]["snomed_code"] == "165416008"


def test_untaught_battery_is_not_seeded() -> None:
    seeded = seed_ordered_tests_entities(RESULTED_BLOOD_TABLE, _blood_schema())
    assert "CRP" not in {e["label"] for e in seeded}


def test_printed_table_with_no_results_seeds_nothing(chunks: list[str]) -> None:
    """Fixture chunk 9 prints the table with every result cell empty."""
    seeded = seed_ordered_tests_entities(chunks[9], _blood_schema())
    assert seeded == []


# -- Defect 6: the detector must be told the input is markdown --------------


def test_detector_prompt_describes_markdown_tables() -> None:
    prompt = form_schema_detector._SYSTEM_PROMPT.lower()
    assert "markdown" in prompt
    assert "separator" in prompt
    assert "cell" in prompt
