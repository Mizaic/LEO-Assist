from __future__ import annotations

from libs.pipeline.label_filter import repair_entity_spans


def test_repair_entity_spans_updates_cleaned_lab_text_to_source_span() -> None:
    text = "Urine creatinine level (XE2qO) 5.5 mmol/L Clinical Information"
    entities = [
        {
            "text": "Urine creatinine level 5.5 mmol/L",
            "label": "observable_entity",
            "start": 0,
            "end": 35,
        }
    ]

    report = repair_entity_spans(text, entities)

    assert len(report["repaired"]) == 1
    repaired = report["entities"][0]
    assert repaired["text"] == "Urine creatinine level (XE2qO) 5.5 mmol/L"
    assert text[repaired["start"] : repaired["end"]] == repaired["text"]


def test_repair_entity_spans_keeps_unrepairable_entities_for_review() -> None:
    entities = [{"text": "Missing lab 1 mmol/L", "label": "observable_entity"}]

    report = repair_entity_spans("No matching text here", entities)

    assert len(report["unrepairable"]) == 1
    assert report["entities"] == entities


def test_repair_entity_spans_can_drop_unrepairable_when_explicit() -> None:
    entities = [{"text": "Missing lab 1 mmol/L", "label": "observable_entity"}]

    report = repair_entity_spans(
        "No matching text here",
        entities,
        drop_unrepairable=True,
    )

    assert len(report["unrepairable"]) == 1
    assert report["entities"] == []


def test_repair_entity_spans_reports_ambiguous_repeated_lab_surface() -> None:
    text = (
        "Serum sodium level (XE2q0) 140 mmol/L. "
        "Serum sodium level (XE2q0) 140 mmol/L."
    )
    entities = [
        {
            "text": "Serum sodium level 140 mmol/L",
            "label": "observable_entity",
            "start": 0,
            "end": 10,
        }
    ]

    report = repair_entity_spans(text, entities)

    assert len(report["ambiguous"]) == 1
    assert report["ambiguous"][0]["candidate_count"] == 2
    assert report["entities"] == entities
