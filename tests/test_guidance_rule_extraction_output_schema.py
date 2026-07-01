"""Validate the guidance-rule extraction few-shot examples against their
own JSON schema (Phase 6: actions array with per-action strength)."""

from __future__ import annotations

import json

import jsonschema
import pytest

from libs.prompts.guidance_rule_extraction_output_schema import (
    GUIDANCE_RULE_EXTRACTION_EXAMPLES,
    GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA,
)

_STRENGTH_ENUM = {
    "offer",
    "consider",
    "refer",
    "discuss",
    "safety_net",
    "do_not_offer",
    "unspecified",
}


@pytest.mark.parametrize(
    "example",
    GUIDANCE_RULE_EXTRACTION_EXAMPLES,
    ids=[ex["id"] for ex in GUIDANCE_RULE_EXTRACTION_EXAMPLES],
)
def test_example_output_conforms_to_schema(example):
    payload = json.loads(example["output"])
    jsonschema.validate(payload, GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA)


@pytest.mark.parametrize(
    "example",
    GUIDANCE_RULE_EXTRACTION_EXAMPLES,
    ids=[ex["id"] for ex in GUIDANCE_RULE_EXTRACTION_EXAMPLES],
)
def test_example_actions_is_a_nonempty_list_with_valid_strength(example):
    payload = json.loads(example["output"])
    actions = payload["actions"]
    assert isinstance(actions, list) and len(actions) >= 1
    for action in actions:
        assert action["text"]
        assert action["strength"] in _STRENGTH_ENUM


def test_at_least_one_example_demonstrates_two_actions_with_different_strengths():
    multi_action_examples = [
        json.loads(ex["output"])
        for ex in GUIDANCE_RULE_EXTRACTION_EXAMPLES
        if len(json.loads(ex["output"])["actions"]) >= 2
    ]
    assert multi_action_examples, "expected at least one 2+ action example"
    payload = multi_action_examples[0]
    strengths = {action["strength"] for action in payload["actions"]}
    assert len(strengths) >= 2


def test_schema_no_longer_has_singular_action_field():
    assert "action" not in GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA["properties"]
    assert "actions" in GUIDANCE_RULE_EXTRACTION_OUTPUT_SCHEMA["required"]
