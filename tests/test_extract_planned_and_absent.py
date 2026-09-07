"""Extract planned named tests and reported-absent findings.

Atlas: DI-6EDCD972 / DO-6953211C / VT-35BB209B
"""

from __future__ import annotations

import json

from libs.prompts.extraction_check_v1 import EXTRACTION_CHECK_EXAMPLES_V1
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1
from libs.prompts.referral_extraction_v1 import REFERRAL_EXTRACTION_SYSTEM_V1
from scripts.seed_prompt_configs import SEED_PROMPTS


def test_extract_prompt_treats_named_request_as_planned_procedure() -> None:
    assert "please-arranged named tests" in EXTRACTION_SYSTEM_V1
    assert "please arrange" in EXTRACTION_SYSTEM_V1
    assert "blood test requested" not in EXTRACTION_SYSTEM_V1


def test_extract_prompt_extracts_no_x_reported_as_absent() -> None:
    assert "no X reported" in EXTRACTION_SYSTEM_V1


def test_extract_prompt_does_not_skip_named_requested_tests() -> None:
    assert "requests/orders not yet performed" not in EXTRACTION_SYSTEM_V1
    assert "investigations requested" in EXTRACTION_SYSTEM_V1


def test_few_shots_cover_please_arrange_and_reported_absent() -> None:
    planned = _example("Please arrange urgent imaging")
    absent = _example("No recent alcohol excess reported")
    planned_terms = json.loads(planned["output"])["terms"]
    absent_terms = json.loads(absent["output"])["terms"]
    assert {term["text"] for term in planned_terms} == {
        "CT abdomen/pelvis",
        "liver function tests",
    }
    assert all(term["assertion"] == "planned" for term in planned_terms)
    assert all(term["semantic_tag"] == "procedure" for term in planned_terms)
    assert absent_terms[0]["text"] == "recent alcohol excess"
    assert absent_terms[0]["assertion"] == "absent"


def test_referral_prompt_has_the_same_two_rules() -> None:
    assert "please arrange" in REFERRAL_EXTRACTION_SYSTEM_V1
    assert "no X reported" in REFERRAL_EXTRACTION_SYSTEM_V1


def test_extract_check_adds_missed_planned_and_absent() -> None:
    planned = _check("ec-k")
    absent = _check("ec-l")
    planned_add = json.loads(planned["output"])["add"]
    absent_add = json.loads(absent["output"])["add"]
    assert [row["text"] for row in planned_add] == [
        "CT abdomen/pelvis",
        "liver function tests",
    ]
    assert absent_add[0]["assertion"] == "absent"


def test_seed_includes_new_extract_examples() -> None:
    extraction = next(row for row in SEED_PROMPTS if row["name"] == "extraction")
    referral = next(row for row in SEED_PROMPTS if row["name"] == "referral_extraction")
    texts = [row["input"] for row in extraction["few_shot_examples"]]
    referral_texts = [row["input"] for row in referral["few_shot_examples"]]
    assert any("Please arrange urgent imaging" in text for text in texts)
    assert any("No recent alcohol excess reported" in text for text in texts)
    assert any("Please arrange urgent imaging" in text for text in referral_texts)
    assert any("No recent alcohol excess reported" in text for text in referral_texts)


def test_seed_extraction_prompt_contains_womb_and_scanty() -> None:
    extraction = next(row for row in SEED_PROMPTS if row["name"] == "extraction")
    text = extraction["system_prompt"]
    assert "uterus present" in text
    assert "289619002" in text
    assert "scanty vaginal discharge" in text
    inputs = [row["input"] for row in extraction["few_shot_examples"]]
    assert any("has womb insitu" in text for text in inputs)
    assert any("scanty vaginal discharge" in text for text in inputs)


def _example(needle: str) -> dict:
    return next(row for row in EXTRACTION_EXAMPLES if needle in row["input"])


def _check(example_id: str) -> dict:
    return next(row for row in EXTRACTION_CHECK_EXAMPLES_V1 if row["id"] == example_id)
