"""Unit tests for shared completeness schema evaluation."""

from __future__ import annotations

from libs.completeness.evaluator import (
    build_isa_expansion,
    evaluate_completeness_groups,
    semantic_tags_from_entities,
)


def test_semantic_tags_normalise_observable_entity_alias():
    tags = semantic_tags_from_entities([{"semantic_tag": "observable entity"}])
    assert tags == {"observable_entity"}


def test_category_match_uses_normalised_tags():
    schema = [
        {
            "name": "Lab result",
            "required": True,
            "semantic_categories": ["observable_entity"],
            "concept_ids": [],
        }
    ]
    result = evaluate_completeness_groups(
        schema,
        present_concept_ids=set(),
        present_semantic_tags={"observable_entity"},
    )
    assert result["complete"] is True
    assert result["matched_groups"][0]["matched_semantic_category"] is True


def test_concept_ids_use_or_semantics():
    schema = [
        {
            "name": "FIT result",
            "required": True,
            "semantic_categories": [],
            "concept_ids": [111, 222],
        }
    ]
    matched = evaluate_completeness_groups(
        schema,
        present_concept_ids={111},
        present_semantic_tags=set(),
    )
    assert matched["complete"] is True
    assert matched["matched_groups"][0]["matched_concept_ids"] == [111]
    assert matched["matched_groups"][0]["missing_concept_ids"] == []


def test_missing_required_concept_lists_all_alternatives():
    schema = [
        {
            "name": "FIT result",
            "required": True,
            "semantic_categories": [],
            "concept_ids": [111, 222],
        }
    ]
    result = evaluate_completeness_groups(
        schema,
        present_concept_ids={999},
        present_semantic_tags=set(),
    )
    assert result["complete"] is False
    group = result["missing_groups"][0]
    assert group["missing_concept_ids"] == [111, 222]


def test_isa_expansion_matches_descendant_concepts():
    schema = [
        {
            "name": "Malignant disorder",
            "required": True,
            "semantic_categories": [],
            "concept_ids": [100],
        }
    ]
    expansion = build_isa_expansion({100}, lambda *_args, **_kwargs: [])
    expansion[100] = {100, 200}
    result = evaluate_completeness_groups(
        schema,
        present_concept_ids={200},
        present_semantic_tags=set(),
        isa_expansion=expansion,
    )
    assert result["complete"] is True
    assert result["matched_groups"][0]["matched_concept_ids"] == [100]


def test_group_requires_both_concepts_and_semantic_category():
    schema = [
        {
            "name": "Symptom plus code",
            "required": True,
            "semantic_categories": ["finding"],
            "concept_ids": [123],
        }
    ]
    only_tag = evaluate_completeness_groups(
        schema,
        present_concept_ids=set(),
        present_semantic_tags={"finding"},
    )
    assert only_tag["complete"] is False

    only_code = evaluate_completeness_groups(
        schema,
        present_concept_ids={123},
        present_semantic_tags=set(),
    )
    assert only_code["complete"] is False

    both = evaluate_completeness_groups(
        schema,
        present_concept_ids={123},
        present_semantic_tags={"finding"},
    )
    assert both["complete"] is True
