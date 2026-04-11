from __future__ import annotations

from scripts.seed_plan_definitions import ACTIVITY_DEFINITIONS, PLAN_DEFINITIONS


def _activity(activity_id: str) -> dict:
    for item in ACTIVITY_DEFINITIONS:
        if item["id"] == activity_id:
            return item
    raise AssertionError(f"activity not found: {activity_id}")


def test_gp_plan_includes_extraction_and_coding_checks():
    gp_plan = next(p for p in PLAN_DEFINITIONS if p["id"] == "pd-gp-encounter-coding")
    ids = [a["id"] for a in gp_plan["action"]]
    assert "act-extraction-check" in ids
    assert "act-coding-check" in ids

    by_id = {a["id"]: a for a in gp_plan["action"]}
    assert (
        by_id["act-extract"]["definitionCanonical"]
        == "ActivityDefinition/ad-extraction-ner"
    )
    assert (
        by_id["act-persist"]["definitionCanonical"]
        == "ActivityDefinition/ad-persist-both"
    )

    assert (
        by_id["act-extraction-check"]["_sequence"]
        < by_id["act-terminology"]["_sequence"]
    )
    assert (
        by_id["act-coding-check"]["_sequence"] > by_id["act-terminology"]["_sequence"]
    )
    assert (
        by_id["act-coding-check"]["_sequence"] < by_id["act-tier-classify"]["_sequence"]
    )


def test_new_activities_have_expected_dynamic_values():
    extraction_check = _activity("ad-extraction-check")
    coding_check = _activity("ad-coding-check")
    persist_both = _activity("ad-persist-both")

    assert extraction_check["_subgraphId"] == "extraction_check"
    assert coding_check["_subgraphId"] == "coding_check"

    ex_values = {
        v["path"]: v["expression"]["expression"]
        for v in extraction_check["dynamicValue"]
    }
    code_values = {
        v["path"]: v["expression"]["expression"] for v in coding_check["dynamicValue"]
    }
    persist_values = {
        v["path"]: v["expression"]["expression"] for v in persist_both["dynamicValue"]
    }

    assert ex_values["model_tier"] == "small"
    assert ex_values["prompt_config_name"] == "extraction_check"
    assert code_values["prompt_config_name"] == "coding_check"
    assert persist_values["output_target"] == "both"
