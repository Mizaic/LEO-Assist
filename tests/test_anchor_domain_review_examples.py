"""Tests for `libs/prompts/anchor_domain_review_examples.py`.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7

Few-shot examples drive the anchor-domain-review LLM step. The schema
contract is enforced here so that a typo in input/output JSON fails
loud at import time, not at runtime against a real LLM call.

Each example MUST:
  - have category, model_scope, description, input, output
  - have input/output that parse as JSON arrays
  - have a single-line input/output to keep token costs predictable
  - have category prefixed `anchor:`
  - have `core` set after the module-level _apply_core_by_first_category
"""

from __future__ import annotations

import json

import pytest

from libs.prompts.anchor_domain_review_examples import (
    ANCHOR_DOMAIN_REVIEW_EXAMPLES,
)

REQUIRED_FIELDS = {"category", "model_scope", "description", "input", "output"}
VALID_SCOPES = {"any", "aws", "azure"}
VALID_DOMAINS = {
    "2WW_REFERRAL",
    "2WW_CLINIC_SEEN",
    "CANCER_DIAGNOSIS",
    "CANCER_DIAGNOSIS_EXCLUDED",
    "CANCER_EXCLUDED",
    "CANCER_TREATMENT",
    "CANCER_TREATMENT_HIST",
    "CANCER_TREATMENT_HISTORICAL",
    "INVESTIGATION",
    "METASTATIC_DISEASE",
    "NON_CANCER",
    "AMBIGUOUS",
    "FAMILY_HISTORY",
    "NEGATED",
    "DISAGREEMENT",
}


class TestRegistryShape:
    def test_at_least_one_example_per_core_category(self):
        cores = {
            "anchor:2ww-referral",
            "anchor:2ww-clinic-seen",
            "anchor:cancer-diagnosis",
            "anchor:cancer-excluded",
            "anchor:cancer-treatment",
            "anchor:metastatic",
            "anchor:non-cancer",
            "anchor:ambiguous",
        }
        present = {ex["category"] for ex in ANCHOR_DOMAIN_REVIEW_EXAMPLES}
        missing = cores - present
        assert not missing, f"Missing core anchor categories: {missing}"

    def test_examples_list_is_non_empty(self):
        assert len(ANCHOR_DOMAIN_REVIEW_EXAMPLES) > 0


@pytest.mark.parametrize("ex", ANCHOR_DOMAIN_REVIEW_EXAMPLES)
class TestPerExampleContract:
    def test_required_fields_present(self, ex):
        missing = REQUIRED_FIELDS - set(ex.keys())
        assert not missing, f"Example missing fields {missing}: {ex.get('description')}"

    def test_category_uses_anchor_prefix(self, ex):
        assert ex["category"].startswith("anchor:"), ex["category"]

    def test_model_scope_in_allowed_set(self, ex):
        assert ex["model_scope"] in VALID_SCOPES

    def test_input_parses_as_json_array(self, ex):
        parsed = json.loads(ex["input"])
        assert isinstance(parsed, list)
        assert len(parsed) >= 1

    def test_output_parses_as_json_array(self, ex):
        parsed = json.loads(ex["output"])
        assert isinstance(parsed, list)
        assert len(parsed) >= 1

    def test_input_and_output_align_by_line_number(self, ex):
        ins = json.loads(ex["input"])
        outs = json.loads(ex["output"])
        assert len(ins) == len(outs), ex["description"]
        in_lines = [r.get("line_number") for r in ins]
        out_lines = [r.get("line_number") for r in outs]
        assert in_lines == out_lines

    def test_output_domain_in_taxonomy(self, ex):
        for o in json.loads(ex["output"]):
            assert o["domain"] in VALID_DOMAINS, (ex["description"], o["domain"])

    def test_inputs_and_outputs_are_single_line_strings(self, ex):
        assert "\n" not in ex["input"]
        assert "\n" not in ex["output"]


class TestCoreFlagAssignment:
    def test_first_example_per_core_category_marked_core(self):
        cores = {
            "anchor:2ww-referral",
            "anchor:cancer-diagnosis",
            "anchor:non-cancer",
        }
        seen: set[str] = set()
        for ex in ANCHOR_DOMAIN_REVIEW_EXAMPLES:
            cat = ex["category"]
            if cat in cores and cat not in seen:
                assert ex.get("core") is True, cat
                seen.add(cat)
            elif cat in cores:
                assert ex.get("core") is False, (cat, ex.get("description"))
