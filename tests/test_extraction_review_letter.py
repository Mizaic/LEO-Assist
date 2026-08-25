"""VT for DI-4A012A59 -- letter text from encounter or document chunks."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.pipeline.extraction_review_letter import resolve_review_letter
from libs.pipeline.extraction_review_store import (
    PersistReviewRequest,
    load_extraction_review_detail,
    persist_extraction_review_task,
)
from libs.pipeline.document_quality import score_document_quality


def _quality():
    return score_document_quality(
        "Section A: Gynaecological Cancer type suspected\nCervix [X]",
        few_shot_max_similarity=0.10,
        known_fingerprints={},
    )


def _task(**overrides):
    payload = {
        "run_id": "run-1",
        "patient_id": "p1",
        "plan_definition_id": "pd-referral-assessment",
        "step_id": "act-ref-extract",
        "next_action_id": "act-ref-post-process",
        "quality": _quality(),
        "draft_entities": [{"text": "Cervix"}],
    }
    payload.update(overrides)
    return persist_extraction_review_task(PersistReviewRequest(**payload))


def test_resolve_letter_uses_encounter_text() -> None:
    text = resolve_review_letter(
        client=MagicMock(),
        task={},
        state={"encounter_text": "Encounter letter about cervix."},
    )
    assert text == "Encounter letter about cervix."


def test_resolve_letter_joins_document_chunk_sentences() -> None:
    text = resolve_review_letter(
        client=MagicMock(),
        task={},
        state={
            "text_segmentation_mode": "document_chunks",
            "chunk_ids": ["c1", "c2"],
            "sentences": [
                {"text": "Section A: cervix"},
                {"text": "BMI: 20.2"},
            ],
        },
    )
    assert "Section A: cervix" in text
    assert "BMI: 20.2" in text


def test_resolve_letter_loads_chunks_from_neo4j_when_ids_only() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "chunk_id": "c1",
            "text": "Chunk one letter",
            "ordinal": 0,
            "char_start": 0,
            "char_end": 16,
        },
        {
            "chunk_id": "c2",
            "text": "Chunk two letter",
            "ordinal": 1,
            "char_start": 18,
            "char_end": 34,
        },
    ]
    text = resolve_review_letter(
        client=client,
        task={},
        state={
            "text_segmentation_mode": "document_chunks",
            "chunk_ids": ["c1", "c2"],
        },
    )
    assert "Chunk one letter" in text
    assert "Chunk two letter" in text


def test_resolve_letter_prefers_persisted_task_text() -> None:
    text = resolve_review_letter(
        client=MagicMock(),
        task={"source_text": "Saved letter from the pause"},
        state={"encounter_text": "later overwrite"},
    )
    assert text == "Saved letter from the pause"


def test_review_detail_joins_chunks_when_encounter_text_missing() -> None:
    task = _task()
    client = MagicMock()
    client.run.return_value = [task]
    store = MagicMock()
    store.load_accumulated_state.return_value = {
        "sentences": [{"text": "Doc chunk A"}, {"text": "Doc chunk B"}],
        "text_segmentation_mode": "document_chunks",
    }
    detail = load_extraction_review_detail(client, task["task_id"], store=store)
    assert "Doc chunk A" in detail["source_text"]
    assert "Doc chunk B" in detail["source_text"]


def test_resolve_letter_loads_encounter_from_pipeline_run() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [],
        [{"encounter_id": "enc-1"}],
        [{"text": "Encounter note from the graph"}],
    ]
    text = resolve_review_letter(
        client=client,
        task={"run_id": "run-1", "step_id": "act-ref-extract"},
        state={},
    )
    assert text == "Encounter note from the graph"


def test_persist_keeps_letter_on_the_task() -> None:
    task = persist_extraction_review_task(
        PersistReviewRequest(
            run_id="run-1",
            patient_id="p1",
            plan_definition_id="pd-referral-assessment",
            step_id="act-ref-extract",
            next_action_id="act-next",
            quality=_quality(),
            draft_entities=[{"text": "Cervix"}],
            source_text="Cervix [X] from document chunks",
        )
    )
    assert task["source_text"] == "Cervix [X] from document chunks"
