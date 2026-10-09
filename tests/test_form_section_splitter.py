"""TDD tests for server-side form section splitting.

When the LLM returns nothing, detect must still find Section A / B
on Sherwood 2WW gynae letters -- including markdown tables and HTML.

Atlas trace: DI-5C9CA57B, DO-D0C19842
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

from libs.llm_client.form_schema_detector import detect_form_sections
from libs.pipeline.form_pattern_match import section_matches
from libs.pipeline.form_section_splitter import (
    is_incomplete_schema,
    split_form_sections,
)

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


def test_splitter_keeps_minimum_dataset_when_only_admin_fields() -> None:
    sections = split_form_sections(SHERWOOD_TABLE)
    dataset = [s for s in sections if "minimum dataset" in s["label"].lower()]
    assert dataset
    assert dataset[0]["section_type"] == "admin"


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


def test_is_incomplete_schema_empty() -> None:
    assert is_incomplete_schema([]) is True


def test_is_incomplete_schema_all_admin() -> None:
    sections = [{"section_type": "admin", "label": "Patient details"}]
    assert is_incomplete_schema(sections) is True


def test_is_incomplete_schema_clinical_with_label() -> None:
    sections = [
        {"section_type": "admin", "label": "Patient details"},
        {"section_type": "checkbox_single", "label": "Section A: Cancer type"},
    ]
    assert is_incomplete_schema(sections) is False


def test_is_incomplete_schema_clinical_empty_labels_treated_as_incomplete() -> None:
    """LLM returned correct section_types but empty label strings -- must fall back."""
    sections = [
        {"section_type": "checkbox_single", "label": ""},
        {"section_type": "checkbox_yesno", "label": "   "},
        {"section_type": "free_text", "label": ""},
    ]
    assert is_incomplete_schema(sections) is True


def test_is_incomplete_schema_admin_skip_does_not_count_for_labels() -> None:
    """Admin sections with labels must not rescue an otherwise empty clinical block."""
    sections = [
        {"section_type": "admin", "label": "Patient details"},
        {"section_type": "checkbox_single", "label": ""},
    ]
    assert is_incomplete_schema(sections) is True


def test_detect_falls_back_when_llm_returns_empty_label_sections() -> None:
    """LLM returns checkbox_single sections but with empty labels -- use splitter."""
    empty_content = {
        "sections": [
            {
                "section_id": "A",
                "label": "",
                "section_type": "checkbox_single",
                "start_pattern": "",
                "items": [
                    {
                        "pattern": "",
                        "entity_text": "",
                        "semantic_tag": "finding",
                        "assertion": "present",
                    }
                ],
            },
            {
                "section_id": "B",
                "label": "",
                "section_type": "checkbox_yesno",
                "start_pattern": "",
                "items": [],
            },
        ]
    }
    client = type("C", (), {})()

    def converse(**_kwargs):
        resp = type("R", (), {})()
        resp.text = json.dumps(empty_content)
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
    section_a = next(s for s in result if s["section_id"] == "A")
    assert section_a["label"].strip(), "label must not be empty after fallback"


SHERWOOD_SECTION_C_DATA = """
Section C: Further Clinical details
BMI: 20.2 Kg/m2 Co-morbidities including mobility concerns

Section D: Investigations performed
"""

SHERWOOD_SECTION_E_PIPES = """
Section E: PERFORMANCE STATUS | | | | | | | |
1. Very Fit [X]
2. Fit [ ]
3. Managing well [ ]
"""

SHERWOOD_MEDICATIONS = """
Section D: Investigations performed
FBC [ ]

Medication: 1. Acutes None
2. Repeats None
Allergies: None

Section E: PERFORMANCE STATUS
"""

SHERWOOD_CFS = """
Section E: PERFORMANCE STATUS

Clinical Frailty Scale (please tick one):
1. Very Fit [X]
2. Fit [ ]
3. Managing well [ ]
4. Very Mild [ ]
5. Mild [ ]
6. Moderate [ ]
7. Severe [ ]
8. Very Severe [ ]

Patient summary
Performance Status
Patient Fitness (ECOG STATUS): No ECOG 0 [ ] 1 [X] 3 [ ] 4 [ ]
"""


def test_splitter_does_not_treat_bmi_data_line_as_section_header() -> None:
    """BMI: 20.2 Kg/m2 Co-morbidities... must not become a separate section."""
    sections = split_form_sections(SHERWOOD_SECTION_C_DATA)
    labels = [s["label"] for s in sections]
    assert not any(
        "20.2" in lbl for lbl in labels
    ), f"data line leaked into section labels: {labels}"
    c = next((s for s in sections if "Section C" in s["label"]), None)
    assert c is not None, "Section C must still be detected"


def test_splitter_strips_trailing_pipes_from_section_name() -> None:
    """Section E name must not contain pipe characters from the table."""
    sections = split_form_sections(SHERWOOD_SECTION_E_PIPES)
    e = next((s for s in sections if s["section_id"] == "E"), None)
    assert e is not None, "Section E must be detected"
    assert "|" not in e["label"], f"Pipe found in label: {e['label']!r}"


def test_splitter_detects_medications_section() -> None:
    """A Medication / Medications line must produce a section."""
    sections = split_form_sections(SHERWOOD_MEDICATIONS)
    ids = {s["section_id"] for s in sections}
    assert any(
        "med" in s["label"].lower() for s in sections
    ), f"No medication section found. sections={[s['label'] for s in sections]}"
    assert "D" in ids
    assert "E" in ids


def test_splitter_detects_cfs_scale_within_section_e() -> None:
    """Clinical Frailty Scale items must be captured as an ordinal section."""
    sections = split_form_sections(SHERWOOD_CFS)
    cfs = next(
        (s for s in sections if re.search(r"(?i)frailty|cfs", s["label"])),
        None,
    )
    assert cfs is not None, "Clinical Frailty Scale section must be detected"
    assert cfs["section_type"] in {"scale", "checkbox_single", "checkbox_multi"}


def test_splitter_detects_ecog_ordinal_in_text() -> None:
    """ECOG ordinal row in Section E body must produce an ordinal section."""
    sections = split_form_sections(SHERWOOD_CFS)
    ecog = next(
        (s for s in sections if re.search(r"(?i)ecog", s["label"])),
        None,
    )
    assert ecog is not None, "ECOG section must be detected"


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


# -- Numbered sections (VT-25098971, DI-C1744ED5) -----------------------------

_LOWER_GI = (
    Path(__file__).parent / "fixtures" / "form_schema" / "sfh_lower_gi_2ww_full_deid.md"
).read_text(encoding="utf-8")
_SKIP = {"admin", "template_noise"}


def _by_id(sections: list[dict]) -> dict[str, dict]:
    return {s["section_id"]: s for s in sections}


def test_splitter_finds_numbered_sections_in_order() -> None:
    sections = split_form_sections(_LOWER_GI)
    numbered = [
        s["section_id"] for s in sections if re.match(r"(?i)section\s+\d", s["label"])
    ]

    assert numbered == ["1", "2", "3"]


def test_splitter_section_ids_are_unique_on_numbered_forms() -> None:
    ids = [s["section_id"] for s in split_form_sections(_LOWER_GI)]

    assert len(ids) == len(set(ids)), ids


def test_splitter_types_demographics_section_as_admin() -> None:
    section_1 = _by_id(split_form_sections(_LOWER_GI))["1"]

    assert section_1["section_type"] == "admin"


def test_splitter_keeps_numbered_clinical_sections() -> None:
    sections = _by_id(split_form_sections(_LOWER_GI))

    assert sections["2"]["section_type"] not in _SKIP
    assert sections["3"]["section_type"] == "free_text"


def test_splitter_numbered_start_pattern_matches_its_own_heading_only() -> None:
    pattern = _by_id(split_form_sections(_LOWER_GI))["2"]["start_pattern"]

    assert section_matches(
        pattern, "SECTION 2: Symptoms suggesting colorectal cancer- GP to complete"
    )
    assert not section_matches(pattern, "SECTION 1 - PATIENT DEMOGRAPHIC DETAILS")
    assert not section_matches(pattern, "SECTION 21: Other")


def test_splitter_never_types_medicines_or_allergies_as_admin() -> None:
    sections = split_form_sections(_LOWER_GI)
    clinical = [s for s in sections if re.search(r"(?i)medication|allerg", s["label"])]

    assert clinical
    assert all(s["section_type"] not in _SKIP for s in clinical)


def test_splitter_types_hospital_use_block_as_admin() -> None:
    sections = split_form_sections(_LOWER_GI)
    hospital = [s for s in sections if "hospital use" in s["label"].lower()]

    assert hospital
    assert hospital[0]["section_type"] == "admin"
