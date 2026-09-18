"""Dated test lines in a plain-text results summary get coded.

PDF-extracted clinical summaries do not always give us a markdown
table. The Nottingham bowel-screening report on NHS 4568668417 printed
one test per line as ``DD/MM/YYYY <test name>`` with the result on the
following line:

    02/06/2026 Bone profile
    02/06/2026 Urea and electrolytes
    08/06/2026 Quantitative faecal immunochemical test
    < 4 ug/g

The table scanners never looked at this shape, so a completed faecal
immunochemical test (FIT) stayed invisible and NICE NG12 1.3.1 kept
asking for it.

Atlas: DI-B3B44F09.
"""

from __future__ import annotations

from libs.guidelines.investigation_family_catalog import FIT_MEMBER_IDS
from libs.pipeline.blood_panel_table import extract_blood_panel_table_entities

_REAL_SUMMARY = (
    "NHS Confidential\n"
    "Clinical Information Summary\n"
    "02/06/2026 Bone profile\n"
    "02/06/2026 Urea and electrolytes\n"
    "08/06/2026 Quantitative faecal immunochemical test\n"
    "< 4 ug/g\n"
    "CRC risk <0.2%. The risk of colorectal cancer is\n"
    "very low and 2WW investigation is not indicated in\n"
    "the absence of a rectal mass (please do a PR).\n"
)


def _by_concept(entities: list[dict]) -> dict[str, dict]:
    return {str(e.get("concept_id")): e for e in entities if e.get("concept_id")}


def test_a_dated_fit_line_codes_the_test_as_done() -> None:
    entities = extract_blood_panel_table_entities(_REAL_SUMMARY, [])
    coded = _by_concept(entities)

    assert "149421000000109" in coded, f"FIT not coded: {sorted(coded)}"
    assert coded["149421000000109"]["assertion"] == "present"


def test_the_coded_fit_proves_the_guideline_action_is_done() -> None:
    coded = _by_concept(extract_blood_panel_table_entities(_REAL_SUMMARY, []))
    assert set(coded) & set(FIT_MEMBER_IDS)


def test_the_result_on_the_next_line_is_attached() -> None:
    """``< 4 ug/g`` belongs to the FIT above it, not to the next test."""
    coded = _by_concept(extract_blood_panel_table_entities(_REAL_SUMMARY, []))
    fit = coded["149421000000109"]
    assert fit.get("value") == "< 4"
    assert fit.get("unit") == "ug/g"


def test_the_date_on_the_line_is_kept() -> None:
    coded = _by_concept(extract_blood_panel_table_entities(_REAL_SUMMARY, []))
    assert coded["149421000000109"].get("observed_at") == "2026-06-08"


def test_the_other_dated_batteries_are_coded_too() -> None:
    """Bone profile and U&E are real completed tests on the same block."""
    coded = _by_concept(extract_blood_panel_table_entities(_REAL_SUMMARY, []))
    assert "167036008" in coded, "Bone profile missing"
    assert "252167001" in coded, "Urea and electrolytes missing"


def test_prose_that_merely_names_a_test_is_not_coded_as_done() -> None:
    """Only a dated result line counts. Advice text must not."""
    prose = (
        "If rectal mass is present please make a 2WW referral.\n"
        "Consider a quantitative faecal immunochemical test.\n"
    )
    coded = _by_concept(extract_blood_panel_table_entities(prose, []))
    assert "149421000000109" not in coded


def test_a_dated_line_with_no_known_battery_is_ignored() -> None:
    """The scanner must not invent a test from any dated line."""
    other = "15/05/2026 Temperature check\n36.8 C\n"
    coded = _by_concept(extract_blood_panel_table_entities(other, []))
    assert not coded
