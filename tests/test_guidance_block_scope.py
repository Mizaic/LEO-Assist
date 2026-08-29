"""Red tests for DI-5C9CA57B: guidance blocks must be block-scoped.

Covers two defects identified against existing acceptance criteria:

1. _mark_non_extractable_chunk marks only the first line of a multi-line
   block.  Every line in the block must be marked so llm_facing_text removes
   them all.

2. The gynae template has no template_noise section for its 'Points to
   remember' block, so guidance text reaches the LLM as clinical prose.

Atlas trace: DI-5C9CA57B (form checkbox markup must not become present findings)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.ner.form_layout_rules import NON_EXTRACTABLE_MARKER, llm_facing_text
from libs.pipeline.document_chunk_loader import _mark_non_extractable_chunk

_POINTS_BLOCK = (
    "Points to remember:\n\n"
    "Remember endometrial cancer nearly always occurs in post-menopausal "
    "women and high BMI is a risk factor.\n\n"
    "Think of possible ovarian cancer in a post-menopausal woman with new "
    "onset bloating, constipation, abdominal pain, urinary symptoms that "
    "do not go away after 3 weeks (Check CA125 and consider scan as per "
    "NICE guidelines)\n\n"
    "Do not check CA125 in premenopausal women as it is not a reliable "
    "marker of ovarian cancer and may result in unnecessary investigations "
    "and patient anxiety."
)

_GUIDANCE_SENTENCES = [
    "high BMI is a risk factor",
    "bloating, constipation, abdominal pain, urinary symptoms",
    "Check CA125 and consider scan",
    "Do not check CA125 in premenopausal women",
    "unnecessary investigations",
]


# ---------------------------------------------------------------------------
# Block-scope: every line of a guidance block must be marked
# ---------------------------------------------------------------------------


def test_mark_non_extractable_chunk_marks_every_line() -> None:
    """Every line of a guidance block must carry the marker, not just line 1."""
    marked = _mark_non_extractable_chunk(_POINTS_BLOCK)
    lines = [ln for ln in marked.splitlines() if ln.strip()]
    unmarked = [ln for ln in lines if not ln.strip().startswith(NON_EXTRACTABLE_MARKER)]
    assert not unmarked, (
        f"These lines were not marked and will reach the model: {unmarked}"
    )


def test_llm_facing_text_removes_all_lines_of_a_guidance_block() -> None:
    """llm_facing_text must remove the full guidance block, not only the heading."""
    marked = _mark_non_extractable_chunk(_POINTS_BLOCK)
    facing = llm_facing_text(marked)
    for sentence in _GUIDANCE_SENTENCES:
        assert sentence not in facing, (
            f"Guidance sentence leaked to LLM-facing text: {sentence!r}"
        )


def test_mark_non_extractable_chunk_preserves_words_in_marked_output() -> None:
    """Marking must not delete words - they must survive in marked form."""
    marked = _mark_non_extractable_chunk(_POINTS_BLOCK)
    for sentence in _GUIDANCE_SENTENCES:
        assert sentence in marked, (
            f"Word removed by normaliser (must only be marked): {sentence!r}"
        )


def test_mark_non_extractable_chunk_no_op_on_clinical_text() -> None:
    """Clinical text that does not match the regex is returned unchanged."""
    clinical = "Cervix [X] Ovary [ ]\nAbdominal pain for 3 weeks\nCA125 raised"
    assert _mark_non_extractable_chunk(clinical) == clinical


# ---------------------------------------------------------------------------
# Gynae template: 'Points to remember' must be a template_noise section
# ---------------------------------------------------------------------------

_GYNAE_TEMPLATE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "sfh_gynae_2ww_template.json"
)


def _gynae_sections() -> list[dict]:
    return json.loads(_GYNAE_TEMPLATE_PATH.read_text())["sections"]


def test_gynae_template_has_template_noise_section() -> None:
    """The gynae template must include a template_noise section."""
    section_types = [s["section_type"] for s in _gynae_sections()]
    assert "template_noise" in section_types, (
        "Gynae template has no template_noise section - guidance text is unclaimed"
    )


def test_gynae_template_noise_section_covers_points_to_remember() -> None:
    """The template_noise section must match the 'Points to remember' heading."""
    from libs.pipeline.form_schema_normalizer import FormSection

    noise_sections = [
        s for s in _gynae_sections() if s["section_type"] == "template_noise"
    ]
    assert noise_sections, "No template_noise section found"
    # At least one noise section must fire on the guidance heading
    heading = "Points to remember:"
    matched = any(
        FormSection(
            section_id=s["section_id"],
            section_type=s["section_type"],
            label=s["label"],
            start_pattern=s["start_pattern"],
        ).matches_header(heading)
        for s in noise_sections
    )
    assert matched, (
        f"No template_noise section matches {heading!r}. "
        f"Sections: {[s['start_pattern'] for s in noise_sections]}"
    )


def test_gynae_guidance_sentences_sealed_after_schema_applied() -> None:
    """After applying the gynae schema, guidance sentences are non-extractable."""
    from libs.pipeline.form_schema_normalizer import FormSchema, apply_schema_to_text
    from libs.pipeline.form_schema_request import (
        build_sections_from_request,
        normalize_sections_for_request,
    )

    data = json.loads(_GYNAE_TEMPLATE_PATH.read_text())
    sections = build_sections_from_request(
        normalize_sections_for_request(data["sections"])
    )
    schema = FormSchema(
        schema_id="gynae-test",
        fingerprint="test",
        form_name=data["form_name"],
        sections=sections,
        created_by="test",
    )
    normalised = apply_schema_to_text(_POINTS_BLOCK, schema)
    facing = llm_facing_text(normalised)
    for sentence in _GUIDANCE_SENTENCES:
        assert sentence not in facing, (
            f"Guidance sentence reached LLM-facing text via schema: {sentence!r}"
        )
