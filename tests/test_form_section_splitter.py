"""TDD tests for server-side form section splitting.

When the LLM returns nothing, detect must still find Section A / B
on Sherwood 2WW gynae letters -- including markdown tables and HTML.

Atlas trace: DI-5C9CA57B, DO-D0C19842
"""

from __future__ import annotations

import json
from unittest.mock import patch

from libs.llm_client.form_schema_detector import detect_form_sections
from libs.pipeline.form_section_splitter import split_form_sections

SHERWOOD_TABLE = """
Minimum Dataset
NHS Number: 718 563 0207
Surname: Bennett

| Section A: Gynaecological Cancer type suspected |
| --- |
| Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ] |

| Section B: Signs/symptoms for 14-day rule criteria |
| --- |
| B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ] |
"""

SHERWOOD_HTML = (
    "<table><tr><td>Section A: Gynaecological Cancer type suspected</td></tr>"
    "<tr><td>Ovary [ ] Cervix [X]</td></tr>"
    "<tr><td>Section B: Signs/symptoms</td></tr></table>"
)

SHERWOOD_INLINE = (
    "Patient details Joe Bloggs Section A: Gynaecological Cancer type "
    "suspected Ovary [ ] Cervix [X] Section B: Signs/symptoms "
    "B1. Lesion | Yes [X] No [ ]"
)


def test_splitter_finds_section_a_and_b_in_markdown_table() -> None:
    sections = split_form_sections(SHERWOOD_TABLE)
    ids = {s["section_id"] for s in sections}
    assert "A" in ids
    assert "B" in ids


def test_splitter_finds_section_a_in_html_table() -> None:
    sections = split_form_sections(SHERWOOD_HTML)
    assert any(s["section_id"] == "A" for s in sections)


def test_splitter_finds_section_a_mid_line() -> None:
    sections = split_form_sections(SHERWOOD_INLINE)
    assert any(s["section_id"] == "A" for s in sections)


def test_splitter_keeps_yes_no_pipe_on_same_line() -> None:
    sections = split_form_sections(SHERWOOD_TABLE)
    section_b = next(s for s in sections if s["section_id"] == "B")
    assert section_b["section_type"] == "checkbox_yesno"


def test_splitter_keeps_minimum_dataset_as_admin() -> None:
    sections = split_form_sections(SHERWOOD_TABLE)
    admin = [s for s in sections if "minimum dataset" in s["label"].lower()]
    assert admin
    assert admin[0]["section_type"] == "admin"


def test_detect_falls_back_to_splitter_when_llm_returns_empty() -> None:
    client = type("C", (), {})()

    def converse(**_kwargs):
        resp = type("R", (), {})()
        resp.text = json.dumps({"sections": []})
        return resp

    client.converse = converse
    with patch(
        "libs.llm_client.form_schema_detector.create_llm",
        return_value=client,
    ):
        result = detect_form_sections(SHERWOOD_TABLE)

    ids = {s["section_id"] for s in result}
    assert "A" in ids
    assert "B" in ids


def test_detect_falls_back_to_splitter_when_llm_throws() -> None:
    client = type("C", (), {})()
    client.converse = lambda **_k: (_ for _ in ()).throw(RuntimeError("no big model"))
    with patch(
        "libs.llm_client.form_schema_detector.create_llm",
        return_value=client,
    ):
        result = detect_form_sections(SHERWOOD_TABLE)

    assert any(s["section_id"] == "A" for s in result)


def test_detect_replaces_admin_only_llm_result_with_splitter() -> None:
    admin_only = {
        "sections": [
            {
                "section_id": "MDS",
                "label": "Minimum Dataset",
                "section_type": "admin",
                "start_pattern": "(?i)minimum\\s+dataset",
                "items": [],
            }
        ]
    }
    client = type("C", (), {})()

    def converse(**_kwargs):
        resp = type("R", (), {})()
        resp.text = json.dumps(admin_only)
        return resp

    client.converse = converse
    with patch(
        "libs.llm_client.form_schema_detector.create_llm",
        return_value=client,
    ):
        result = detect_form_sections(SHERWOOD_TABLE)

    ids = {s["section_id"] for s in result}
    assert "A" in ids
    assert "B" in ids
