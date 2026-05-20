"""Deterministic lab-panel abbreviation extraction (template-agnostic)."""

from __future__ import annotations

from pathlib import Path

import pytest

from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline.blood_panel_table import extract_blood_panel_table_entities

_FIXTURE_MARKDOWN = (
    Path(__file__).resolve().parent / "fixtures/clinical_extraction_scenarios/markdown"
)


def test_extracts_abbrevs_from_fixture_markdown_table() -> None:
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures/clinical_extraction_scenarios/markdown/brain_cns_email_001.md"
    )
    text = fixture.read_text(encoding="utf-8")
    entities = extract_blood_panel_table_entities(text, [])
    names = {e["text"] for e in entities}
    assert "Hb" in names
    assert "Ferritin" in names
    assert "HbA1c" in names
    assert len(names) >= 16


def test_extracts_without_blood_results_heading() -> None:
    text = """# Referral summary

## Recent investigations

| Panel | Date | Result |
| --- | --- | --- |
| FBC | 2026-04-20 | Hb 140.0 g/L, WCC 7.0 x10^9/L, Plts 250.0 x10^9/L |
| U&E | 2026-04-20 | Na 140.0 mmol/L, K 4.2 mmol/L, Creat 80.0 umol/L |
"""
    entities = extract_blood_panel_table_entities(text, [])
    names = {e["text"] for e in entities}
    assert "Hb" in names
    assert "Na" in names
    assert "Creat" in names


def test_ignores_single_abbrev_in_narrative() -> None:
    text = (
        "Patient has anaemia. Hb 98 g/L was discussed. "
        "Refer under 2WW lower GI pathway."
    )
    entities = extract_blood_panel_table_entities(text, [])
    assert entities == []


def test_extracts_from_dense_chunk_without_heading() -> None:
    line = "Hb 151.5 g/L, WCC 6.8 x10^9/L, Plts 465.0 x10^9/L, MCV 88.6 fL"
    chunk = SentenceChunk(sentence_id="s1", text=line, start=100, end=100 + len(line))
    entities = extract_blood_panel_table_entities("", [chunk])
    names = {e["text"] for e in entities}
    assert {"Hb", "WCC", "Plts", "MCV"}.issubset(names)


def test_extracts_from_two_column_table() -> None:
    text = """# Urology referral

| Investigation | Result |
| --- | --- |
| FBC | Hb 120.0 g/L, Ferritin 18.0 ug/L |
| U&E | Na 140.0 mmol/L, Creat 75.0 umol/L |
"""
    names = {e["text"] for e in extract_blood_panel_table_entities(text, [])}
    assert {"Hb", "Ferritin", "Na", "Creat"}.issubset(names)


def test_extracts_from_template_blood_tests_section() -> None:
    """Matches ``Blood Tests (if available...)`` blocks in ``templates/`` renders."""
    text = """# NSS referral

## Clinical Summary

Blood Tests (if available - last 3 months):
<Pathology & Radiology Reports(table)>

| FBC | 2026-04-20 | Hb 140.0 g/L, WCC 7.0 x10^9/L |
| Endocrine/Other | 2026-04-20 | HBA1c 45.0 mmol/mol |
"""
    names = {e["text"] for e in extract_blood_panel_table_entities(text, [])}
    assert "Hb" in names
    assert "HbA1c" in names


def test_single_abbrev_in_blood_tests_section() -> None:
    text = """Blood Tests (if available - last 3 months):

PSA 4.2 ng/mL on repeat testing.
"""
    names = {e["text"] for e in extract_blood_panel_table_entities(text, [])}
    assert names == {"PSA"}


@pytest.mark.parametrize(
    "case_id",
    [
        "lower_gi_letter_001",
        "nss_systmone_medication_safety_001",
        "lung_form_001",
        "urology_form_001",
        "haematology_semistructured_001",
    ],
)
def test_corpus_formats_yield_core_lab_abbrevs(case_id: str) -> None:
    text = (_FIXTURE_MARKDOWN / f"{case_id}.md").read_text(encoding="utf-8")
    names = {e["text"] for e in extract_blood_panel_table_entities(text, [])}
    assert "Ferritin" in names
    assert "HbA1c" in names
    assert len(names) >= 12
