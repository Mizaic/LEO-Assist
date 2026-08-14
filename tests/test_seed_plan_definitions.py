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
    assert "act-relation-link" in ids
    assert "act-extraction-check" in ids
    assert "act-extraction-route" in ids
    assert "act-hitl-ner-queue" in ids
    assert "act-snomed-enrich" in ids
    assert "act-snomed-relation-judge" in ids
    assert "act-coding-route" in ids
    assert "act-hitl-coding-queue" in ids

    by_id = {a["id"]: a for a in gp_plan["action"]}
    assert (
        by_id["act-extract"]["definitionCanonical"]
        == "ActivityDefinition/ad-extraction-ner"
    )
    assert (
        by_id["act-persist"]["definitionCanonical"]
        == "ActivityDefinition/ad-persist-both"
    )

    assert by_id["act-relation-link"]["_sequence"] < by_id["act-extraction-check"][
        "_sequence"
    ]
    assert by_id["act-extraction-route"]["_nodeType"] == "condition"
    assert by_id["act-coding-route"]["_nodeType"] == "condition"
    assert by_id["act-snomed-enrich"]["_sequence"] < by_id["act-snomed-relation-judge"][
        "_sequence"
    ]
    assert by_id["act-snomed-relation-judge"]["_sequence"] < by_id["act-coding-route"][
        "_sequence"
    ]
    assert by_id["act-coding-route"]["relatedAction"][0]["actionId"] == (
        "act-snomed-relation-judge"
    )
    assert by_id["act-terminology"]["relatedActionEdges"][0]["sourceHandle"] == (
        "pass_through"
    )
    assert by_id["act-hitl-ner-queue"]["relatedActionEdges"][0]["sourceHandle"] == (
        "changed"
    )
    assert by_id["act-hitl-coding-queue"]["relatedActionEdges"][0]["sourceHandle"] == (
        "issues"
    )


def test_new_activities_have_expected_dynamic_values():
    extraction_check = _activity("ad-extraction-check")
    relation_linking = _activity("ad-relation-linking")
    snomed_enrichment = _activity("ad-snomed-enrichment")
    extraction_route = _activity("ad-condition-extraction-route")
    coding_check = _activity("ad-coding-check")
    coding_route = _activity("ad-condition-coding-route")
    persist_both = _activity("ad-persist-both")

    assert extraction_check["_subgraphId"] == "extraction_check"
    assert relation_linking["_subgraphId"] == "relation_linking"
    assert snomed_enrichment["_subgraphId"] == "snomed_enrichment"
    assert extraction_route["_subgraphId"] == "condition"
    assert coding_check["_subgraphId"] == "coding_check"
    assert coding_route["_subgraphId"] == "condition"

    ex_values = {
        v["path"]: v["expression"]["expression"]
        for v in extraction_check["dynamicValue"]
    }
    relation_values = {
        v["path"]: v["expression"]["expression"]
        for v in relation_linking["dynamicValue"]
    }
    extraction_route_values = {
        v["path"]: v["expression"]["expression"]
        for v in extraction_route["dynamicValue"]
    }
    code_values = {
        v["path"]: v["expression"]["expression"] for v in coding_check["dynamicValue"]
    }
    coding_route_values = {
        v["path"]: v["expression"]["expression"] for v in coding_route["dynamicValue"]
    }
    persist_values = {
        v["path"]: v["expression"]["expression"] for v in persist_both["dynamicValue"]
    }

    assert ex_values["model_tier"] == "small"
    assert ex_values["prompt_config_name"] == "extraction_check"
    assert ex_values["prompt_config_version"] == "2"
    assert relation_values["prompt_config_name"] == "relation_linking"
    assert relation_values["prompt_config_version"] == "1"
    assert extraction_route_values["defaultPort"] == "pass_through"
    assert coding_route_values["defaultPort"] == "clean"
    assert code_values["prompt_config_name"] == "coding_check"
    assert persist_values["output_target"] == "both"
