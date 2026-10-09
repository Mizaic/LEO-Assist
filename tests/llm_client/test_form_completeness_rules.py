"""VT: proposed completeness rules come only from the form's own wording.

A rule the form does not say is required must never block a referral.
Weak proposals are optional and marked for a person to check.

Atlas trace: VT-BFDEDB18, DI-9BF69EC9, DO-F120628C, R-A3BD3AC7
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from libs.llm_client.form_completeness_rules import (
    MAX_RULES,
    build_completeness_groups,
    parse_rules,
    section_id_map,
)
from libs.llm_client.form_schema_detector import (
    _OUTPUT_SCHEMA,
    _SYSTEM_PROMPT,
    detect_form_schema,
)

LETTER = (
    "| SECTION 4: Blood results |\n"
    "| Blood results are mandatory | FBC, U&E, eGFR. Bloods taken 25/6/26 |\n"
    "| SECTION 2: Symptoms |\n"
    "| Please tick at least one | Rectal bleeding [X] | Weight loss [ ] |\n"
)

SECTIONS = [
    {
        "section_id": "bloods",
        "label": "Blood results",
        "section_type": "free_text",
        "start_pattern": "SECTION 4: Blood results",
        "items": [],
    },
    {
        "section_id": "symptoms",
        "label": "Symptoms",
        "section_type": "checkbox_multi",
        "start_pattern": "SECTION 2: Symptoms",
        "items": [
            {"pattern": "Rectal bleeding", "entity_text": "Rectal bleeding"},
            {"pattern": "Weight loss", "entity_text": "Weight loss"},
        ],
    },
]


def _rule(**over):
    rule = {
        "name": "Blood results",
        "kind": "mandatory",
        "targets": [{"section_id": "bloods", "item_pattern": ""}],
        "min_count": 1,
        "evidence": "Blood results are mandatory",
    }
    rule.update(over)
    return rule


def _build(*rules, id_map=None):
    return build_completeness_groups(list(rules), SECTIONS, LETTER, id_map)


def test_a_quoted_mandatory_rule_is_kept_and_points_at_the_section():
    (group,) = _build(_rule())
    assert group["kind"] == "mandatory"
    assert group["required"] is True
    assert group["section_id"] == "bloods"
    assert group["evidence"] == "Blood results are mandatory"
    assert group["needs_review"] is False


def test_a_mandatory_rule_whose_quote_is_not_in_the_letter_becomes_optional():
    (group,) = _build(_rule(evidence="All bloods must be within 4 weeks"))
    assert group["kind"] == "optional"
    assert group["required"] is False
    assert group["needs_review"] is True


def test_a_mandatory_rule_with_no_quote_becomes_optional():
    (group,) = _build(_rule(evidence=""))
    assert group["kind"] == "optional"
    assert group["needs_review"] is True


def test_a_rule_whose_quote_has_a_date_becomes_optional():
    (group,) = _build(_rule(evidence="eGFR. Bloods taken 25/6/26"))
    assert group["kind"] == "optional"
    assert group["needs_review"] is True


def test_unknown_sections_and_items_are_dropped_from_members():
    rule = _rule(
        name="At least one symptom",
        kind="one_of",
        evidence="Please tick at least one",
        targets=[
            {"section_id": "symptoms", "item_pattern": "Rectal bleeding"},
            {"section_id": "symptoms", "item_pattern": "Made up symptom"},
            {"section_id": "ghost", "item_pattern": ""},
            {"section_id": "symptoms", "item_pattern": "weight loss"},
        ],
    )
    (group,) = _build(rule)
    assert group["kind"] == "one_of"
    assert [(m["section_id"], m["item_pattern"]) for m in group["members"]] == [
        ("symptoms", "Rectal bleeding"),
        ("symptoms", "Weight loss"),
    ]


def test_a_rule_with_no_known_target_is_dropped():
    rule = _rule(targets=[{"section_id": "ghost", "item_pattern": ""}])
    assert _build(rule) == []


def test_an_unknown_kind_is_dropped():
    assert _build(_rule(kind="all_of_them")) == []


def test_if_then_needs_two_targets_and_a_quote():
    if_then = _rule(
        name="If rectal bleeding then bloods",
        kind="if_then",
        evidence="Blood results are mandatory",
        targets=[
            {"section_id": "symptoms", "item_pattern": "Rectal bleeding"},
            {"section_id": "bloods", "item_pattern": ""},
        ],
    )
    (group,) = _build(if_then)
    assert group["if_group"]["item_pattern"] == "Rectal bleeding"
    assert group["then_group"]["section_id"] == "bloods"
    assert _build(dict(if_then, evidence="not on the form")) == []
    assert _build(dict(if_then, targets=if_then["targets"][:1])) == []


def test_n_of_min_count_stays_within_its_members():
    rule = _rule(
        kind="n_of",
        min_count=9,
        evidence="Please tick at least one",
        targets=[
            {"section_id": "symptoms", "item_pattern": "Rectal bleeding"},
            {"section_id": "symptoms", "item_pattern": "Weight loss"},
        ],
    )
    (group,) = _build(rule)
    assert group["min_count"] == 2


def test_rules_are_capped():
    groups = _build(*[_rule(name=f"Rule {i}") for i in range(MAX_RULES + 5)])
    assert len(groups) == MAX_RULES


def test_rules_carry_no_snomed_codes():
    (group,) = _build(_rule())
    assert group["concept_ids"] == []
    assert group["semantic_categories"] == []


def test_rules_follow_borrowed_section_ids():
    borrowed = [dict(SECTIONS[0], section_id="B7"), SECTIONS[1]]
    id_map = section_id_map(SECTIONS, borrowed)
    groups = build_completeness_groups([_rule()], borrowed, LETTER, id_map)
    assert groups[0]["section_id"] == "B7"


def test_parse_rules_keeps_only_well_formed_rules():
    rules = parse_rules([_rule(), "junk", {"name": 3, "targets": "x"}])
    assert len(rules) == 2
    assert rules[0]["targets"][0]["section_id"] == "bloods"
    assert rules[1]["targets"] == []


def test_output_schema_asks_for_completeness_rules():
    assert _OUTPUT_SCHEMA["required"] == ["sections", "completeness_rules"]
    rule = _OUTPUT_SCHEMA["properties"]["completeness_rules"]["items"]
    assert set(rule["required"]) == set(rule["properties"])


def test_prompt_asks_for_quoted_rules_and_forbids_guessing():
    prompt = " ".join(_SYSTEM_PROMPT.split()).lower()
    assert "completeness_rules" in prompt
    assert "quote" in prompt
    assert "do not guess" in prompt


def test_detect_returns_the_model_rules():
    answer = {"sections": SECTIONS, "completeness_rules": [_rule()]}
    response = MagicMock()
    response.text = json.dumps(answer)
    client = MagicMock()
    client.converse.return_value = response
    with patch("libs.llm_client.form_schema_detector.create_llm", return_value=client):
        detection = detect_form_schema(LETTER)
    assert detection.completeness_rules[0]["evidence"] == "Blood results are mandatory"
