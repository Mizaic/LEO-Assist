"""Situation skeleton builder + FE parity fixtures.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.guidance.situation_skeleton import (
    build_situation_skeleton,
    looks_like_table_thresholds,
    parse_list_structure,
)

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "situation_skeleton_parity.json"
)


def _load_cases() -> list[dict]:
    return json.loads(_FIXTURE.read_text())["cases"]


def test_parity_fixture_counts_and_sources():
    for case in _load_cases():
        shells = build_situation_skeleton(case["text"], case.get("structure"))
        assert len(shells) == case["expected_count"], case["id"]
        assert all(s.source == case["expected_source"] for s in shells), case["id"]


def test_table_marker_does_not_invent_prose_situations():
    text = "Refer according to the thresholds in table 1 for people with a raised PSA."
    assert looks_like_table_thresholds(text)
    shells = build_situation_skeleton(text, None)
    assert len(shells) == 1
    assert shells[0].source == "tree"


def test_table_marker_with_threshold_rows_emits_tree_shells():
    text = "Refer according to the thresholds in table 1."
    shells = build_situation_skeleton(
        text, None, threshold_rows=["row A", "row B", "row C"]
    )
    assert len(shells) == 3
    assert all(s.source == "tree" for s in shells)


def test_parse_list_structure_accepts_json_string():
    raw = json.dumps({"lead_text": "x", "items": [{"text": "a", "start": 0, "end": 1}]})
    parsed = parse_list_structure(raw)
    assert parsed is not None
    assert parsed["lead_text"] == "x"


def test_and_joined_structure_collapses_to_single():
    text = "Offer A and B and C."
    structure = {
        "lead_text": "Offer ",
        "items": [
            {"text": "A", "start": 6, "end": 7},
            {"text": "B", "start": 12, "end": 13},
            {"text": "C", "start": 18, "end": 19},
        ],
    }
    # Force and-joined connectors between items.
    text = "Offer A and B and C."
    structure = {
        "lead_text": "Offer ",
        "items": [
            {"text": "A", "start": 6, "end": 7},
            {"text": "B", "start": 12, "end": 13},
            {"text": "C", "start": 18, "end": 19},
        ],
    }
    shells = build_situation_skeleton(text, structure)
    assert len(shells) == 1
    assert shells[0].source == "single"


def test_foreign_list_structure_is_not_a_situation_split():
    """NG12 1.5.12 must not inherit 1.5.13's vaginal-discharge list."""
    text = (
        "1.5.12 Refer women, and trans men and non-binary people with female "
        "reproductive organs using a suspected cancer pathway referral for "
        "endometrial cancer if they are aged 55 and over with unexplained "
        "postmenopausal bleeding that cannot be attributed to hormone "
        "replacement therapy (HRT). [2015, amended 2026]"
    )
    structure = {
        "lead_text": "Consider an urgent ultrasound scan",
        "items": [
            {
                "text": "unexplained symptoms of vaginal discharge who:",
                "start": 200,
                "end": 246,
            },
            {"text": "visible haematuria, and:", "start": 351, "end": 375},
        ],
    }
    shells = build_situation_skeleton(text, structure)
    assert len(shells) == 1
    assert "vaginal discharge" not in shells[0].text
