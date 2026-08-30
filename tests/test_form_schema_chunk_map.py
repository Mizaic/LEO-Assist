"""TDD tests for chunk-to-section mapping and section-level semantic tags.

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
"""

from __future__ import annotations

import pytest

from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    SECTION_TYPE_SEMANTIC_TAG,
    normalise_with_schema,
)
from libs.pipeline.form_schema_template import build_chunk_section_map

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

CANCER_SITE_SECTION = FormSection(
    section_id="A",
    section_type="checkbox_single",
    label="Section A",
    start_pattern=r"(?i)section\s+a:",
    items=[
        FormSchemaItem(
            pattern="Cervix",
            entity_text="Cervical cancer suspected",
            semantic_tag="situation",
            assertion="present",
        ),
    ],
)

CRITERIA_SECTION = FormSection(
    section_id="B",
    section_type="checkbox_yesno",
    label="Section B",
    start_pattern=r"(?i)section\s+b:",
    items=[
        FormSchemaItem(
            pattern=r"B1\.",
            entity_text="Suspicious lesion on cervix",
            semantic_tag="finding",
            assertion="present",
        ),
    ],
)

NARRATIVE_SECTION = FormSection(
    section_id="C",
    section_type="free_text",
    label="Section C",
    start_pattern=r"(?i)section\s+c:",
    items=[],
)


def _make_schema(*sections: FormSection) -> FormSchema:
    return FormSchema(
        schema_id="test-id",
        fingerprint="fp",
        form_name="Test Form",
        sections=list(sections),
        created_by="test",
    )


# ---------------------------------------------------------------------------
# build_chunk_section_map
# ---------------------------------------------------------------------------


def test_chunk_map_assigns_header_chunk_to_section() -> None:
    """A chunk containing a section header is assigned to that section."""
    chunks = [
        "URGENT CANCER REFERRAL",
        "Section A: Gynaecological Cancer type suspected\nCervix [ ]",
        "Section B: Signs and symptoms\nB1. Lesion Yes [X] No [ ]",
    ]
    sections = [
        {"section_id": "A", "start_pattern": r"(?i)section\s+a:"},
        {"section_id": "B", "start_pattern": r"(?i)section\s+b:"},
    ]
    result = build_chunk_section_map(chunks, sections)
    idx_map = {entry["chunk_idx"]: entry["section_id"] for entry in result}
    assert idx_map.get(1) == "A"
    assert idx_map.get(2) == "B"


def test_chunk_map_subsequent_chunks_inherit_section() -> None:
    """Chunks after a section header inherit that section until the next header."""
    chunks = [
        "Section A: Cancer type\nCervix [ ]",
        "Ovary [ ] Vagina [ ]",
        "Section B: Criteria\nB1. Yes [X]",
    ]
    sections = [
        {"section_id": "A", "start_pattern": r"(?i)section\s+a:"},
        {"section_id": "B", "start_pattern": r"(?i)section\s+b:"},
    ]
    result = build_chunk_section_map(chunks, sections)
    idx_map = {entry["chunk_idx"]: entry["section_id"] for entry in result}
    assert idx_map.get(0) == "A"
    assert idx_map.get(1) == "A", "Chunk 1 should inherit Section A"
    assert idx_map.get(2) == "B"


def test_chunk_map_pre_first_section_chunks_excluded() -> None:
    """Chunks before the first section header are excluded from the map."""
    chunks = [
        "NHS REFERRAL FORM",
        "Section A: Cancer type\nCervix [ ]",
    ]
    sections = [{"section_id": "A", "start_pattern": r"(?i)section\s+a:"}]
    result = build_chunk_section_map(chunks, sections)
    idx_map = {entry["chunk_idx"]: entry["section_id"] for entry in result}
    assert 0 not in idx_map, "Pre-section chunk should not be in map"
    assert idx_map.get(1) == "A"


def test_chunk_map_empty_chunks_returns_empty() -> None:
    sections = [{"section_id": "A", "start_pattern": r"(?i)section\s+a:"}]
    assert build_chunk_section_map([], sections) == []


def test_chunk_map_invalid_pattern_is_skipped() -> None:
    """A bad regex pattern does not raise; it is silently skipped."""
    chunks = ["Section A: Type\nCervix [ ]"]
    sections = [
        {"section_id": "BAD", "start_pattern": r"[invalid[regex"},
        {"section_id": "A", "start_pattern": r"(?i)section\s+a:"},
    ]
    result = build_chunk_section_map(chunks, sections)
    idx_map = {entry["chunk_idx"]: entry["section_id"] for entry in result}
    assert idx_map.get(0) == "A"


# ---------------------------------------------------------------------------
# normalise_with_schema
# ---------------------------------------------------------------------------


def test_normalise_with_schema_uses_chunk_map() -> None:
    """When chunk_section_map is provided the normaliser routes directly."""
    chunks = [
        "Section A: Cancer type\nCervix [X]",
        "B1. Lesion | Yes [ ] No [X]",
    ]
    chunk_section_map = [
        {"chunk_idx": 0, "section_id": "A"},
        {"chunk_idx": 1, "section_id": "B"},
    ]
    schema = _make_schema(CANCER_SITE_SECTION, CRITERIA_SECTION)
    result = normalise_with_schema(schema, chunks, chunk_section_map)
    assert "Cervical cancer suspected" not in result
    assert "Suspicious lesion on cervix" not in result


def test_normalise_with_schema_fallback_when_map_absent() -> None:
    """When chunk_section_map is absent, falls back to header-scan."""
    chunks = [
        "Section A: Cancer type",
        "Cervix [X]",
    ]
    schema = _make_schema(CANCER_SITE_SECTION)
    result = normalise_with_schema(schema, chunks, chunk_section_map=None)
    assert "Cervical cancer suspected" not in result
    assert "Cervix [X]" in result or "Cervix" in result


def test_normalise_with_schema_fallback_when_map_empty() -> None:
    """When chunk_section_map is an empty list, falls back to header-scan."""
    chunks = ["Section A: Cancer type\nCervix [X]"]
    schema = _make_schema(CANCER_SITE_SECTION)
    result = normalise_with_schema(schema, chunks, chunk_section_map=[])
    assert "Cervical cancer suspected" not in result


def test_normalise_with_schema_unmapped_chunk_passes_through() -> None:
    """Chunks with no mapping entry are returned unchanged."""
    chunks = [
        "HEADER TEXT",
        "Section A: Cancer type\nCervix [X]",
    ]
    chunk_section_map = [{"chunk_idx": 1, "section_id": "A"}]
    schema = _make_schema(CANCER_SITE_SECTION)
    result = normalise_with_schema(schema, chunks, chunk_section_map)
    assert "HEADER TEXT" in result
    assert "Cervical cancer suspected" not in result


FREE_TEXT_SECTION = FormSection(
    section_id="ACI",
    section_type="free_text",
    label="Additional clinical information",
    start_pattern=r"(?i)additional\s+clinical\s+information",
    items=[],
)

ADMIN_SECTION = FormSection(
    section_id="ADMIN",
    section_type="admin",
    label="Patient details",
    start_pattern=r"(?i)patient\s+details",
    items=[],
)


def test_free_text_body_below_header_stays_extractable_in_chunk_map() -> None:
    """Interior free_text headers inside an admin-mapped chunk keep body lines."""
    from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER

    text = (
        "Patient details\n"
        "Name: John Smith\n"
        "Additional clinical information\n"
        "Patient has postmenopausal bleeding for 3 months.\n"
        "Polyp noted on examination."
    )
    chunks = [text]
    chunk_section_map = [{"chunk_idx": 0, "section_id": "ADMIN"}]
    schema = _make_schema(ADMIN_SECTION, FREE_TEXT_SECTION)
    result = normalise_with_schema(schema, chunks, chunk_section_map)
    assert "postmenopausal bleeding" in result
    assert "Polyp noted" in result
    clinical_lines = [
        ln
        for ln in result.splitlines()
        if "postmenopausal" in ln or "Polyp noted" in ln
    ]
    assert clinical_lines
    assert all(NON_EXTRACTABLE_MARKER not in ln for ln in clinical_lines)


def test_free_text_header_with_body_on_following_lines_in_same_chunk() -> None:
    """A free_text label on one line and prose on the next lines stays intact."""
    text = (
        "Additional clinical information\n"
        "Patient has postmenopausal bleeding for 3 months.\n"
        "Polyp noted on examination."
    )
    chunks = [text]
    chunk_section_map = [{"chunk_idx": 0, "section_id": "ACI"}]
    schema = _make_schema(FREE_TEXT_SECTION)
    result = normalise_with_schema(schema, chunks, chunk_section_map)
    assert "postmenopausal bleeding" in result
    assert "Polyp noted" in result


# ---------------------------------------------------------------------------
# Section-level semantic_tags
#
# A blood results section can carry both procedure and observable, so the
# field is a list. These tests pin the plural API.
# ---------------------------------------------------------------------------


def test_form_section_has_semantic_tags_field() -> None:
    """FormSection has a semantic_tags list defaulting to ['finding']."""
    section = FormSection(
        section_id="X",
        section_type="free_text",
        label="Test",
        start_pattern="test",
        items=[],
    )
    assert section.semantic_tags == ["finding"]


def test_form_section_semantic_tags_can_be_set() -> None:
    section = FormSection(
        section_id="X",
        section_type="checkbox_single",
        label="Test",
        start_pattern="test",
        items=[],
        semantic_tags=["situation"],
    )
    assert section.semantic_tags == ["situation"]


@pytest.mark.parametrize(
    "section_type,expected_tags",
    [
        ("admin", ["none"]),
        ("template_noise", ["none"]),
        ("checkbox_single", ["situation"]),
        ("checkbox_yesno", ["finding"]),
        ("checkbox_multi", ["finding"]),
        ("free_text", ["finding"]),
        ("scale", ["observable"]),
        ("ordered_tests", ["procedure"]),
        ("observable", ["observable"]),
    ],
)
def test_section_type_semantic_tag_map(
    section_type: str, expected_tags: list[str]
) -> None:
    """SECTION_TYPE_SEMANTIC_TAG maps each section type to its tag list."""
    assert SECTION_TYPE_SEMANTIC_TAG.get(section_type) == expected_tags
