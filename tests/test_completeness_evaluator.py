"""Unit tests for shared completeness schema evaluation."""

from __future__ import annotations

from libs.completeness.evaluator import (
    build_isa_expansion,
    concept_ids_from_entities,
    evaluate_completeness_groups,
    semantic_tags_from_entities,
)


def test_absent_concept_is_not_a_present_completeness_fact() -> None:
    """Denied text must not satisfy a coded completeness member.

    Dry-run 000481827411 coded 'No postmenopausal bleeding' as 76742009
    absent. That code must not complete the gynae 2WW groups.
    """
    ids = concept_ids_from_entities(
        [
            {"concept_id": "76742009", "assertion": "absent"},
            {"concept_id": "68640004", "assertion": "present"},
        ]
    )
    assert 76742009 not in ids
    assert 68640004 in ids


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


def test_optional_group_does_not_block_completeness():
    schema = [
        {
            "name": "Section A",
            "kind": "mandatory",
            "concept_ids": [100],
        },
        {
            "name": "Notes",
            "kind": "optional",
            "concept_ids": [200],
        },
    ]
    result = evaluate_completeness_groups(
        schema,
        present_concept_ids={100},
        present_semantic_tags=set(),
    )
    assert result["complete"] is True


def test_one_of_members_requires_at_least_one():
    schema = [
        {
            "name": "Referral criteria",
            "kind": "one_of",
            "members": [
                {"name": "B1", "concept_ids": [111]},
                {"name": "B2", "concept_ids": [222]},
            ],
        }
    ]
    missing = evaluate_completeness_groups(
        schema,
        present_concept_ids=set(),
        present_semantic_tags=set(),
    )
    assert missing["complete"] is False

    one = evaluate_completeness_groups(
        schema,
        present_concept_ids={222},
        present_semantic_tags=set(),
    )
    assert one["complete"] is True
    assert one["matched_groups"][0]["matched_member_names"] == ["B2"]


def test_n_of_members_requires_minimum_count():
    schema = [
        {
            "name": "Two of three tests",
            "kind": "n_of",
            "min_count": 2,
            "members": [
                {"name": "FIT", "concept_ids": [11]},
                {"name": "Blood", "concept_ids": [22]},
                {"name": "Scan", "concept_ids": [33]},
            ],
        }
    ]
    one = evaluate_completeness_groups(
        schema,
        present_concept_ids={11},
        present_semantic_tags=set(),
    )
    assert one["complete"] is False

    two = evaluate_completeness_groups(
        schema,
        present_concept_ids={11, 33},
        present_semantic_tags=set(),
    )
    assert two["complete"] is True


def test_if_then_requires_then_group_only_when_if_present():
    schema = [
        {
            "name": "If imaging then report",
            "kind": "if_then",
            "if_group": {"name": "Imaging", "concept_ids": [501]},
            "then_group": {"name": "Report", "concept_ids": [502]},
        }
    ]
    vacant = evaluate_completeness_groups(
        schema,
        present_concept_ids=set(),
        present_semantic_tags=set(),
    )
    assert vacant["complete"] is True

    if_only = evaluate_completeness_groups(
        schema,
        present_concept_ids={501},
        present_semantic_tags=set(),
    )
    assert if_only["complete"] is False

    both = evaluate_completeness_groups(
        schema,
        present_concept_ids={501, 502},
        present_semantic_tags=set(),
    )
    assert both["complete"] is True


def test_guideline_kind_aliases_map_to_completeness_logic():
    schema = [
        {
            "name": "Any symptom",
            "kind": "OR",
            "members": [
                {"name": "Cough", "concept_ids": [1]},
                {"name": "Weight loss", "concept_ids": [2]},
            ],
        }
    ]
    result = evaluate_completeness_groups(
        schema,
        present_concept_ids={2},
        present_semantic_tags=set(),
    )
    assert result["complete"] is True


def test_legacy_required_flag_still_means_mandatory():
    schema = [{"name": "Diagnosis", "required": True, "concept_ids": [9]}]
    result = evaluate_completeness_groups(
        schema,
        present_concept_ids=set(),
        present_semantic_tags=set(),
    )
    assert result["complete"] is False
    assert result["missing_groups"][0]["kind"] == "mandatory"
