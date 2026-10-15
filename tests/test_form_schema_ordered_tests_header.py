"""An ordered-tests heading line follows the same result rule as its rows.

The Sherwood Forest lower GI 2WW form starts its blood section on a
printed guidance sentence: "if older please arrange FBC, U&Es & eGFR".
The normaliser passed every section heading line through untouched, so
the model read that sentence and recorded three planned blood tests the
GP never asked for. Every other ordered-tests row is already sealed when
it names a taught test but reports no result.

The rule under test: a heading line is sealed only when it names a taught
test and reports no result. A heading that carries a result (the FIT
line) still reaches the model, and a plain heading that names no taught
test is left exactly as it is, so other taught forms do not change.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996
"""

from __future__ import annotations

from pathlib import Path

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    apply_schema_to_text,
)

LETTER = Path(__file__).parent / "fixtures" / "form_schema"
LETTER = LETTER / "sfh_lower_gi_2ww_full_deid.md"

PLAIN_HEADING = "| Section D: Investigations performed |"
FBC_RESULT_ROW = "| FBC | 01.01.26 | Hb 118 g/L |"


def _line(startswith: str) -> str:
    for line in LETTER.read_text(encoding="utf-8").splitlines():
        if line.startswith(startswith):
            return line
    raise AssertionError(f"fixture has no line starting {startswith!r}")


def _guidance_line() -> str:
    return _line("| * Blood results within 12 weeks")


def _fit_line() -> str:
    return _line("| Faecal Immunochemical test result")


def _battery(pattern: str, label: str, code: str) -> FormSchemaItem:
    return FormSchemaItem(
        pattern=pattern,
        entity_text=label,
        semantic_tag="observable entity",
        analytes=[{"label": label, "snomed_code": code}],
    )


def _section(section_id: str, start: str, items: list) -> FormSection:
    return FormSection(
        section_id=section_id,
        section_type="ordered_tests",
        label=section_id,
        start_pattern=start,
        items=items,
    )


def _schema() -> FormSchema:
    fit = _battery(
        "Faecal Immunochemical test result ug/g",
        "Faecal Immunochemical test result ug/g",
        "1049361000000101",
    )
    bloods = [
        _battery("Haemoglobin", "Haemoglobin", "1022431000000105"),
        _battery("EGFR", "EGFR", "1107411000000104"),
    ]
    return FormSchema(
        schema_id="lower-gi-header",
        fingerprint="lower-gi-header",
        form_name="Lower GI header test",
        created_by="test",
        sections=[
            _section("fit_result", "Faecal Immunochemical test result ug/g", [fit]),
            _section("blood_results", "Blood results within 12 weeks", bloods),
            _section(
                "investigations",
                "Section D: Investigations",
                [_battery("FBC", "FBC", "26604007")],
            ),
        ],
    )


def _normalised_line(text: str, line: str) -> str:
    out = apply_schema_to_text(text, _schema()).splitlines()
    index = text.splitlines().index(line)
    return out[index]


def test_guidance_heading_that_names_a_taught_test_is_sealed() -> None:
    """'please arrange ... eGFR' must not reach the model as clinical text."""
    line = _guidance_line()
    assert _normalised_line(line, line).startswith(NON_EXTRACTABLE_MARKER)


def test_heading_that_reports_a_result_still_reaches_the_model() -> None:
    """The FIT result is printed on the FIT heading line; it must survive."""
    line = _fit_line()
    assert _normalised_line(line, line) == line


def test_plain_heading_that_names_no_taught_test_is_unchanged() -> None:
    """Other taught forms keep their headings exactly as they are today."""
    text = f"{PLAIN_HEADING}\n{FBC_RESULT_ROW}"
    assert _normalised_line(text, PLAIN_HEADING) == PLAIN_HEADING
    assert _normalised_line(text, FBC_RESULT_ROW) == FBC_RESULT_ROW
