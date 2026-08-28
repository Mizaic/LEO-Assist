"""Ordered-test rows must reach the model as written, never as a template.

The runtime normaliser rewrites each taught ``ordered_tests`` row using
``expand_ordered_tests_row``, which is a template generator: it emits the
taught analyte labels followed by ``{{NUMERIC_VALUE}} {{UNIT}}``. Two
things go wrong when that runs on a real letter.

A blank table gains fifteen placeholder tokens that no value can ever
fill, and the real row is discarded. The Sherwood letter loses its
"MANDATORY -- the following tests must be undertaken" line this way,
because the words "FBC LFTs, UEs and Calcium" inside that sentence match
three taught batteries.

Worse, a GP who types results into the table has them deleted. "Hb 118
g/L" is replaced by "Hb {{NUMERIC_VALUE}} {{UNIT}}" before the model
sees it, so a reported result cannot be extracted.

The rule under test: a row that reports a result reaches the model
verbatim, and a row that reports none is marked non-extractable so the
model cannot invent one. No placeholder token is ever emitted at runtime.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    normalise_chunks_with_schema,
)

FIXTURES = Path(__file__).parent / "fixtures" / "form_schema"
TEMPLATE_FIXTURE = FIXTURES / "sfh_gynae_2ww_template.json"

PLACEHOLDERS = ("{{NUMERIC_VALUE}}", "{{UNIT}}")

ORDERED_TESTS_SECTION_ID = "section_d_investigations"

# The Section D line as it appears in the Sherwood letter. The battery
# names sit inside the sentence, so all three taught patterns match it.
MANDATORY_LINE = (
    "Blood Results (Last ):\n"
    "MANDATORY - the following tests must be undertaken and results "
    "provided with referral:- FBC LFTs, UEs and Calcium See Below "
    "BLOODS DONE TODAY 23.6.26\n"
)

# The same table once a GP has typed the results in.
RESULTED_ROW = (
    "Blood Results (Last ):\n"
    "| FBC | 23.06.26 | Hb 118 g/L , WCC 7.2 x10^9/L , Plts 250 |\n"
)


def _normalise(chunk: str) -> str:
    """Normalise one chunk bound to Section D, as the runtime binds it.

    Production reaches this section through the stored chunk-to-section
    map, not through the ``Section D`` start pattern, because the blood
    table is segmented into its own chunk with no heading in it.
    """
    out = normalise_chunks_with_schema(
        _taught_schema(),
        [chunk],
        [{"chunk_idx": 0, "section_id": ORDERED_TESTS_SECTION_ID}],
    )
    return out[0]


def _taught_item(raw: dict) -> FormSchemaItem:
    return FormSchemaItem(
        pattern=str(raw.get("pattern") or ""),
        entity_text=str(raw.get("entity_text") or ""),
        semantic_tag=str(raw.get("semantic_tag") or "finding"),
        assertion=str(raw.get("assertion") or "present"),
        procedure_snomed=str(raw.get("procedure_snomed") or ""),
        procedure_display=str(raw.get("procedure_display") or ""),
        analytes=list(raw.get("analytes") or []),
        value_placeholder=str(raw.get("value_placeholder") or ""),
    )


def _taught_schema() -> FormSchema:
    """Build the taught ``ordered_tests`` sections from the seeded template."""
    payload = json.loads(TEMPLATE_FIXTURE.read_text(encoding="utf-8"))
    sections = [
        FormSection(
            section_id=str(raw["section_id"]),
            section_type="ordered_tests",
            label=str(raw.get("label") or ""),
            start_pattern=str(raw.get("start_pattern") or ""),
            items=[_taught_item(i) for i in (raw.get("items") or [])],
        )
        for raw in payload["sections"]
        if raw.get("section_type") == "ordered_tests"
    ]
    return FormSchema(
        schema_id="sfh-gynae-2ww",
        fingerprint="e61c4289e199cfb5",
        form_name=str(payload["form_name"]),
        sections=sections,
        created_by="seed",
        organization_id="RK5",
        service_id="7980224",
    )


def test_unresulted_row_emits_no_placeholder_tokens() -> None:
    """A row with no result must not gain slots the letter cannot fill."""
    out = _normalise(MANDATORY_LINE)
    for token in PLACEHOLDERS:
        assert token not in out


def test_resulted_row_keeps_the_values_the_gp_typed() -> None:
    """A reported result must survive normalisation so it can be coded."""
    out = _normalise(RESULTED_ROW)
    assert "118" in out
    assert "g/L" in out
    assert "7.2" in out


def test_resulted_row_emits_no_placeholder_tokens() -> None:
    """Real values must not be swapped for template slots."""
    out = _normalise(RESULTED_ROW)
    for token in PLACEHOLDERS:
        assert token not in out


def test_unresulted_row_stays_non_extractable() -> None:
    """The blank-table safety control still holds: nothing to extract."""
    out = _normalise(MANDATORY_LINE)
    assert "[NON_EXTRACTABLE]" in out
