"""Few-shot and prompt alignment with annotation_guidelines_v1."""

from __future__ import annotations

import json

from libs.prompts.annotation_guidelines_v1 import ANNOTATION_GUIDELINES_V1
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1


def _example_by_description(fragment: str) -> dict:
    for example in EXTRACTION_EXAMPLES:
        if fragment in str(example.get("description", "")):
            return example
    raise KeyError(fragment)


def test_ex_smoker_few_shot_uses_finding_not_situation() -> None:
    example = _example_by_description("Smoking status as finding")
    terms = json.loads(example["output"])["terms"]
    assert terms[0]["semantic_tag"] == "finding"
    assert terms[0]["text"] == "Ex-smoker"


def test_breast_suspected_pathway_few_shot_is_situation() -> None:
    example = _example_by_description("Breast suspected pathway -- situation present")
    tags = {t["semantic_tag"] for t in json.loads(example["output"])["terms"]}
    assert tags == {"situation"}
    terms = json.loads(example["output"])["terms"]
    assert terms[0]["assertion"] == "present"


def test_extraction_prompt_requires_assertion() -> None:
    assert "ASSERTION" in EXTRACTION_SYSTEM_V1
    assert "assertion is REQUIRED" in EXTRACTION_SYSTEM_V1
    assert "Do not output an assertion field" not in EXTRACTION_SYSTEM_V1


def test_extraction_prompt_treats_womb_in_situ_as_uterus_present() -> None:
    assert "has womb in situ" in EXTRACTION_SYSTEM_V1
    assert "uterus present" in EXTRACTION_SYSTEM_V1
    assert "289619002" in EXTRACTION_SYSTEM_V1


def test_body_structure_organ_list_excepts_in_situ_before_examples() -> None:
    """Organ-present phrases must be excepted in the organ list, not only Examples."""
    after_header = EXTRACTION_SYSTEM_V1.split("BODY STRUCTURE SCOPE", 1)[1]
    organ_list, _, _examples = after_header.partition("Examples:")
    assert "in situ" in organ_list.lower() or "insitu" in organ_list.lower()
    assert "uterus present" in organ_list
    assert "finding" in organ_list.lower()


def test_extraction_prompt_keeps_scanty_vaginal_discharge() -> None:
    assert "scanty vaginal discharge" in EXTRACTION_SYSTEM_V1


def _terms_for_input(needle: str) -> list[dict]:
    example = next(row for row in EXTRACTION_EXAMPLES if needle in row["input"])
    return json.loads(example["output"])["terms"]


def test_womb_insitu_few_shot_is_uterus_present_finding() -> None:
    terms = _terms_for_input("has womb insitu")
    womb = next(term for term in terms if "womb" in term["text"].lower())
    assert womb["semantic_tag"] == "finding"
    assert womb["lookup_term"] == "uterus present"


def test_scanty_discharge_few_shot_keeps_qualifier() -> None:
    terms = _terms_for_input("scanty vaginal discharge")
    discharge = next(
        term for term in terms if "discharge" in term["lookup_term"].lower()
    )
    assert discharge["lookup_term"] == "scanty vaginal discharge"


def test_extraction_prompt_has_blood_results_table_section() -> None:
    assert "Blood Tests" in EXTRACTION_SYSTEM_V1
    assert "one observable entity per parameter" in EXTRACTION_SYSTEM_V1


def test_blood_panel_examples_exist() -> None:
    categories = {ex.get("category") for ex in EXTRACTION_EXAMPLES}
    assert "observable:blood_panel" in categories


def test_guidelines_rule_10_ex_smoker_is_finding() -> None:
    assert "Ex-smoker | finding | present" in ANNOTATION_GUIDELINES_V1


def test_guidelines_fh_situation_is_present() -> None:
    assert "FH of breast cancer | situation | present" in ANNOTATION_GUIDELINES_V1


def test_llm_extractor_parses_assertion_from_json() -> None:
    src = open(
        "services/coding_worker/app/pipeline/llm_extractor.py", encoding="utf-8"
    ).read()
    assert "def _parse_assertion" in src
    assert "_parse_assertion(term.get" in src
