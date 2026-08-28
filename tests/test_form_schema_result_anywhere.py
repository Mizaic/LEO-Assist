"""A reported result must survive whatever section the schema calls it.

The normaliser decides what to keep from the section type the schema was
taught, not from what the referrer actually wrote. Six of the seven
Sherwood section types delete the line they are given:

* ``admin`` and ``template_noise`` mark every line unconditionally.
* ``checkbox_single``, ``checkbox_multi``, ``checkbox_yesno`` and ``scale``
  mark the whole row once a box is found on it, keeping only the taught
  entity text for the ticked box.

That is right for the printed form. It is wrong the moment a referrer
types a measurement onto one of those lines, which they do: results turn
up beside a tick, in a minimum-dataset block, and in the margin of a
performance-status scale, not only in the taught blood table.

The value the referrer typed is the only place that result exists in the
letter. Deleting the line deletes the result before extraction can see
it, and no later layer can recover it.

The rule under test: no section type may delete a line where a whole
table cell is a measurement. Filling a cell is what a referrer does and
what a printed form does not, so the printed thresholds these forms quote
in prose -- "endometrial thickness <4mm", "BMI over 30" -- stay
non-extractable and cannot become findings. Section type still governs
everything else.

Keeping the row extractable can let the model re-read a ticked label the
deterministic pass already emitted. That duplicate collapses in
``_dedup_by_concept_id`` once both copies resolve to one concept, whereas
a deleted result is gone for good.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996
"""

from __future__ import annotations

import pytest

from libs.pipeline.form_schema_normalizer import (
    NON_EXTRACTABLE_MARKER,
    FormSchema,
    FormSchemaItem,
    FormSection,
    normalise_chunks_with_schema,
)

SECTION_ID = "s1"


def _schema(section_type: str, items: list[FormSchemaItem]) -> FormSchema:
    return FormSchema(
        schema_id="schema-result-anywhere",
        created_by="test",
        fingerprint="fp-result-anywhere",
        form_name="result anywhere",
        sections=[
            FormSection(
                section_id=SECTION_ID,
                section_type=section_type,  # type: ignore[arg-type]
                label="Section",
                start_pattern="Section",
                items=items,
            )
        ],
    )


def _normalise(section_type: str, body: str, items: list[FormSchemaItem]) -> str:
    """Run the production chunk path with the section forced on the body."""
    out = normalise_chunks_with_schema(
        _schema(section_type, items),
        [f"Section\n{body}"],
        [{"chunk_index": 0, "section_id": SECTION_ID}],
    )
    return "\n".join(out)


def _line_holding(text: str, needle: str) -> str:
    return next(ln for ln in text.splitlines() if needle in ln)


# A referrer has typed a real haemoglobin into a cell on a line the
# schema does not expect to carry one.
RESULT = "96 g/L"

ANAEMIA = FormSchemaItem(pattern="Anaemia", entity_text="Anaemia")
PMB = FormSchemaItem(
    pattern="Postmenopausal bleeding", entity_text="Postmenopausal bleeding"
)
WHO1 = FormSchemaItem(pattern="WHO 1", entity_text="WHO performance status 1")


@pytest.mark.parametrize(
    "section_type,body,items",
    [
        pytest.param(
            "admin",
            f"| Referring practice | Ashfield | Hb | {RESULT} |",
            [],
            id="admin",
        ),
        pytest.param(
            "template_noise",
            f"| Please fax to 01623 000000 | Hb | {RESULT} |",
            [],
            id="template_noise",
        ),
        pytest.param(
            "checkbox_yesno",
            f"| Anaemia Yes [X] No [ ] | Hb | {RESULT} |",
            [ANAEMIA],
            id="checkbox_yesno",
        ),
        pytest.param(
            "checkbox_multi",
            f"| [X] Postmenopausal bleeding | Hb | {RESULT} |",
            [PMB],
            id="checkbox_multi",
        ),
        pytest.param(
            "scale",
            f"| [X] WHO 1 -- restricted activity | Hb | {RESULT} |",
            [WHO1],
            id="scale",
        ),
    ],
)
def test_a_typed_result_is_never_deleted(
    section_type: str, body: str, items: list[FormSchemaItem]
) -> None:
    """The measurement reaches the model whatever the section is called."""
    text = _normalise(section_type, body, items)
    assert (
        RESULT in text
    ), f"{section_type} deleted a reported result. Normalised text:\n{text}"
    assert NON_EXTRACTABLE_MARKER not in _line_holding(text, RESULT), (
        f"{section_type} kept the result but marked it non-extractable, "
        f"so the model still cannot read it"
    )


def test_a_ticked_box_still_yields_its_taught_entity() -> None:
    """Keeping the result must not cost us the deterministic tick."""
    text = _normalise(
        "checkbox_multi", f"| [X] Postmenopausal bleeding | Hb | {RESULT} |", [PMB]
    )
    assert "Postmenopausal bleeding" in text
    assert RESULT in text


# -- controls: printed form text must not become a finding ---------------


def test_a_printed_threshold_in_prose_stays_non_extractable() -> None:
    """The Sherwood form quotes decision thresholds it never resulted.

    "<4mm" is the rule the GP is asked to apply, not the patient's scan.
    It shares a cell with the sentence around it, so no cell is a
    measurement and the row stays sealed.
    """
    body = (
        "| On TV USS the endometrial thickness <4mm and regular "
        "(refer USC if abnormal) | Yes [ ] |"
    )
    text = _normalise("checkbox_yesno", body, [])
    assert (
        NON_EXTRACTABLE_MARKER in text
    ), "a printed threshold must not become extractable text"


@pytest.mark.parametrize(
    "section_type,body",
    [
        ("admin", "Referring practice: Ashfield Health Centre, Kirkby"),
        ("template_noise", "Please fax this form to 01623 000000"),
    ],
)
def test_printed_template_text_is_still_marked(section_type: str, body: str) -> None:
    """No result on the line means the old behaviour is unchanged."""
    text = _normalise(section_type, body, [])
    assert NON_EXTRACTABLE_MARKER in text


def test_an_unticked_box_with_no_result_is_still_marked() -> None:
    """A blank form row must not become extractable text."""
    text = _normalise("checkbox_yesno", "Anaemia Yes [ ] No [ ]", [ANAEMIA])
    assert NON_EXTRACTABLE_MARKER in text
