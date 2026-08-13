"""VT-CEA3194E -- form checkbox normalizer acceptance verification."""

from __future__ import annotations

from pathlib import Path

from libs.ner.form_checkbox_normalizer import (
    NON_EXTRACTABLE_MARKER,
    extractable_clinical_lines,
    normalize_form_checkbox_text,
)
from libs.pipeline.document_chunk_loader import build_document_chunk_state


def test_unchecked_criteria_rows_are_non_extractable() -> None:
    text = (
        "| Unexplained DVT | [ ] | | New, unexplained and unintentional "
        "weight loss | [ ] |"
    )
    normalised = normalize_form_checkbox_text(text)
    assert NON_EXTRACTABLE_MARKER in normalised
    lines = extractable_clinical_lines(text)
    assert not any("weight loss" in line.lower() for line in lines)
    assert not any("dvt" in line.lower() for line in lines)


def test_checked_gut_feeling_row_remains_extractable() -> None:
    text = (
        "| Unexplained DVT | [ ] | | GP gut feeling of cancer diagnosis - | "
        "[X] | | Worrying symptoms | [X] |"
    )
    lines = extractable_clinical_lines(text)
    joined = " ".join(lines).lower()
    assert "gut feeling" in joined
    assert "worrying symptoms" in joined
    assert "dvt" not in joined


def test_all_unchecked_table_yields_zero_extractable_lines() -> None:
    text = (
        "| Symptoms pathway | | [ ] New unexplained and unintentional "
        "weight loss | | [ ] New unexplained vague abdominal pain | | "
        "[ ] GP intuition or gut feeling |"
    )
    lines = extractable_clinical_lines(text)
    joined = " ".join(lines).lower()
    assert "weight loss" not in joined
    assert "abdominal pain" not in joined
    assert "gut feeling" not in joined


def test_multiline_unchecked_row_marked() -> None:
    text = "| Unexplained DVT | [ ] |\n| Haematuria | [X] |"
    lines = extractable_clinical_lines(text)
    assert any("Haematuria" in line for line in lines)
    assert not any("DVT" in line for line in lines)


def test_appendix_criteria_block_suppressed_until_clinical_section() -> None:
    text = (
        "Appendix A - Referral criteria\n"
        "[ ] Bone pain\n"
        "[ ] Appetite loss\n"
        "The reason I am concerned\n"
        "New nipple discharge for 3 weeks"
    )
    lines = extractable_clinical_lines(text)
    joined = " ".join(lines).lower()
    assert "nipple discharge" in joined
    assert "bone pain" not in joined
    assert "appetite" not in joined


def test_admin_questions_are_non_extractable() -> None:
    text = (
        "Has the patient consented to referral? [X] Yes\n"
        "Is an interpreter required? [ ] No\n"
        "Patient reports new breast lump"
    )
    lines = extractable_clinical_lines(text)
    joined = " ".join(lines).lower()
    assert "breast lump" in joined
    assert "consented" not in joined
    assert "interpreter" not in joined


def test_yes_no_unchecked_yes_not_treated_as_present() -> None:
    text = "Current Smoker: | [ ] Yes [X] No |"
    normalised = normalize_form_checkbox_text(text)
    lines = extractable_clinical_lines(text)
    assert NON_EXTRACTABLE_MARKER in normalised or "Yes" not in " ".join(lines)
    assert not any(re_yes_present(line) for line in lines)


def re_yes_present(line: str) -> bool:
    lower = line.lower()
    return "yes" in lower and NON_EXTRACTABLE_MARKER not in line


def test_referral_criteria_header_table_all_unchecked() -> None:
    text = (
        "| REFERRAL CRITERIA (mandatory field): |\n"
        "| --- |\n"
        "| [ ] New unexplained weight loss |\n"
        "| [ ] Fatigue |\n"
        "| [ ] Bloating |"
    )
    assert extractable_clinical_lines(text) == []


def test_build_document_chunk_state_sets_text_raw_and_normalised_text() -> None:
    rows = [
        {
            "chunk_id": "c1",
            "text": "| Unexplained DVT | [ ] |\n| Haematuria | [X] |",
            "char_start": 0,
            "char_end": 40,
        }
    ]
    state = build_document_chunk_state(rows)
    sent = state["sentences"][0]
    assert sent["text_raw"] == rows[0]["text"]
    assert NON_EXTRACTABLE_MARKER in sent["text"]
    assert "Haematuria" in sent["text"]
    assert NON_EXTRACTABLE_MARKER not in sent["text_raw"]
    # Full document join stays on raw source text for span offsets.
    assert state["encounter_text"] == rows[0]["text"]


def test_extraction_path_invokes_normalizer() -> None:
    windowed = Path("libs/pipeline/windowed_llm_extraction.py").read_text(
        encoding="utf-8"
    )
    extraction = Path("libs/pipeline_graph/subgraphs/extraction.py").read_text(
        encoding="utf-8"
    )
    loader = Path("libs/pipeline/document_chunk_loader.py").read_text(encoding="utf-8")
    assert "normalize_form_checkbox_text" in windowed
    assert "normalise_chunks_for_llm" in windowed
    assert "_normalise_chunks_for_llm" in extraction
    assert "normalize_form_checkbox_text" in loader
