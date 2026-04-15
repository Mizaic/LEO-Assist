"""Unit tests for one-off few-shot reset/export/import scripts."""

from __future__ import annotations

from scripts.export_verified_gold_for_few_shot_review import (
    build_review_rows,
    build_summary,
)
from scripts.import_curated_few_shot_examples import _validate_payload
from scripts.reset_prompt_few_shot_oneoff import count_few_shot_examples


def test_count_few_shot_examples_handles_common_shapes() -> None:
    assert count_few_shot_examples(None) == 0
    assert count_few_shot_examples("") == 0
    assert count_few_shot_examples("[]") == 0
    assert count_few_shot_examples([{"input": "a"}]) == 1
    assert count_few_shot_examples('[{"input":"a"},{"input":"b"}]') == 2
    assert count_few_shot_examples('{"bad":"shape"}') == 0


def test_build_review_rows_parses_entities_and_skips_empty() -> None:
    rows = build_review_rows(
        [
            {
                "gold_label_id": "g-1",
                "candidate_id": "c-1",
                "source": "reviewer_correction",
                "label_source": "manual",
                "encounter_text": "de-identified text",
                "entities_json": '[{"text":"chest pain","lookup_term":"pain","semantic_tag":"finding","assertion":"present"}]',
                "updated_at": "2026-04-15T10:00:00Z",
                "candidate_lookup_term": "pain",
                "candidate_semantic_tag": "finding",
                "candidate_assertion": "present",
            },
            {
                "gold_label_id": "g-2",
                "candidate_id": "c-2",
                "source": "reviewer_correction",
                "label_source": "manual",
                "encounter_text": "no entities",
                "entities_json": "[]",
                "updated_at": "2026-04-15T10:00:00Z",
                "candidate_lookup_term": "",
                "candidate_semantic_tag": "",
                "candidate_assertion": "",
            },
        ]
    )
    assert len(rows) == 1
    assert rows[0]["gold_label_id"] == "g-1"
    assert rows[0]["entities"][0]["mention_text"] == "chest pain"
    assert rows[0]["entities"][0]["semantic_tag"] == "finding"


def test_build_summary_returns_expected_distributions() -> None:
    summary = build_summary(
        [
            {
                "source": "reviewer_correction",
                "entities": [
                    {
                        "mention_text": "Chest pain",
                        "lookup_term": "pain",
                        "semantic_tag": "finding",
                        "assertion": "present",
                    },
                    {
                        "mention_text": "No fever",
                        "lookup_term": "fever",
                        "semantic_tag": "finding",
                        "assertion": "absent",
                    },
                ],
            }
        ]
    )
    assert summary["row_count"] == 1
    assert summary["entity_count"] == 2
    assert summary["by_source"]["reviewer_correction"] == 1
    assert summary["top_semantic_tags"]["finding"] == 2
    assert summary["assertion_distribution"]["present"] == 1
    assert summary["assertion_distribution"]["absent"] == 1


def test_validate_payload_accepts_and_rejects_expected_shapes() -> None:
    valid = _validate_payload(
        {
            "prompts": [
                {
                    "name": "extraction",
                    "version": 1,
                    "max_few_shot": 20,
                    "few_shot_examples": [{"input": "a", "output": "b"}],
                }
            ]
        }
    )
    assert valid[0]["name"] == "extraction"
    assert valid[0]["version"] == 1
    assert len(valid[0]["few_shot_examples"]) == 1

    try:
        _validate_payload({"prompts": [{"name": "", "version": 1, "max_few_shot": 20}]})
        assert False, "Expected ValueError for missing name"
    except ValueError:
        pass
