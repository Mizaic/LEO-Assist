from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("langgraph.graph")

from libs.pipeline_graph.subgraphs.persist import write_gold_training
from libs.pipeline_graph.subgraphs.persist import write_patient_graph


def test_write_gold_training_writes_candidate_only() -> None:
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    client = MagicMock()
    client.session.return_value = session
    with patch(
        "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client",
        return_value=client,
    ):
        out = write_gold_training(
            {
                "encounter_text": "chest pain for 3 days",
                "entities": [
                    {
                        "text": "chest pain",
                        "label": "finding",
                        "start": 0,
                        "end": 10,
                        "_llm_check_source": "llm_added",
                    }
                ],
                "verification_result": {"confidence": 0.95},
                "errors": [],
            }
        )
    assert out["training_labels_written"] == 1
    assert session.run.call_count == 1
    assert session.run.call_args.kwargs["status"] == "pending"
    entities_json = session.run.call_args.kwargs["entities_json"]
    entities = json.loads(entities_json)
    assert entities[0]["text"] == "chest pain"
    assert entities[0]["label"] == "finding"
    assert entities[0]["semantic_tag"] == "finding"


def test_write_gold_training_skips_without_llm_signal() -> None:
    out = write_gold_training(
        {
            "encounter_text": "chest pain for 3 days",
            "entities": [
                {"text": "chest pain", "label": "finding", "start": 0, "end": 10}
            ],
            "verification_result": {"confidence": 0.95},
            "errors": [],
        }
    )
    assert out["training_labels_written"] == 0
    assert out["status"] == "skipped_no_training_signal"


def test_write_gold_training_writes_sentence_level_candidates() -> None:
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    client = MagicMock()
    client.session.return_value = session
    with patch(
        "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client",
        return_value=client,
    ):
        out = write_gold_training(
            {
                "encounter_text": "First sentence. Second sentence.",
                "sentences": [
                    {
                        "sentence_id": "s0",
                        "text": "First sentence.",
                        "start": 0,
                        "end": 15,
                    },
                    {
                        "sentence_id": "s1",
                        "text": "Second sentence.",
                        "start": 16,
                        "end": 32,
                    },
                ],
                "entities": [
                    {
                        "text": "first finding",
                        "label": "finding",
                        "start": 0,
                        "end": 13,
                        "__sentence_id": "s0",
                        "_llm_check_source": "llm_added",
                    },
                    {
                        "text": "second finding",
                        "label": "finding",
                        "start": 17,
                        "end": 31,
                        "__sentence_id": "s1",
                        "_llm_check_source": "llm_added",
                    },
                ],
                "verification_result": {"confidence": 0.95},
                "errors": [],
            }
        )

    assert out["training_labels_written"] == 2

    candidate_texts: list[str] = []
    for call in session.run.call_args_list:
        kwargs = call.kwargs
        if "candidate_id" in kwargs and "text" in kwargs:
            candidate_texts.append(kwargs["text"])

    # Both source sentences are short (<50 chars) so context windowing widens
    # each to include its neighbour.  Assert the target surface appears in
    # each stored text (not exact equality since context is injected).
    assert any("First sentence." in t for t in candidate_texts)
    assert any("Second sentence." in t for t in candidate_texts)


def test_write_gold_training_splits_multiline_lab_sentence_into_line_candidates() -> (
    None
):
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    client = MagicMock()
    client.session.return_value = session
    with patch(
        "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client",
        return_value=client,
    ):
        out = write_gold_training(
            {
                "encounter_text": (
                    "Neutrophil count (42J..) 5.14 10^9/L\n"
                    "Monocyte count - observation (42N..) 0.71 10^9/L"
                ),
                "sentences": [
                    {
                        "sentence_id": "s0",
                        "text": (
                            "Neutrophil count (42J..) 5.14 10^9/L\n"
                            "Monocyte count - observation (42N..) 0.71 10^9/L"
                        ),
                        "start": 0,
                        "end": 90,
                    }
                ],
                "entities": [
                    {
                        "text": "Neutrophil count",
                        "label": "observable_entity",
                        "start": 0,
                        "end": 16,
                        "value": "5.14",
                        "unit": "10^9/L",
                        "__sentence_id": "s0",
                        "_llm_check_source": "llm_added",
                    },
                    {
                        "text": "Monocyte count - observation",
                        "label": "observable_entity",
                        "start": 37,
                        "end": 64,
                        "value": "0.71",
                        "unit": "10^9/L",
                        "__sentence_id": "s0",
                        "_llm_check_source": "llm_added",
                    },
                ],
                "verification_result": {"confidence": 0.95},
                "errors": [],
            }
        )

    assert out["training_labels_written"] == 2

    candidate_texts: list[str] = []
    for call in session.run.call_args_list:
        kwargs = call.kwargs
        if "candidate_id" in kwargs and "text" in kwargs:
            candidate_texts.append(kwargs["text"])

    assert any("Neutrophil count (42J..) 5.14 10^9/L" in t for t in candidate_texts)
    assert any(
        "Monocyte count - observation (42N..) 0.71 10^9/L" in t for t in candidate_texts
    )
    assert not any(
        "Neutrophil count (42J..) 5.14 10^9/L\nMonocyte count - observation" in t
        for t in candidate_texts
    )


def test_write_patient_graph_holds_when_coding_check_flags_issue() -> None:
    out = write_patient_graph(
        {
            "encounter_id": "enc-1",
            "patient_id": "pat-1",
            "entities": [{"text": "test", "concept_id": "123"}],
            "llm_check_changes": [{"type": "force_review", "index": 0}],
            "errors": [],
        }
    )
    assert out["documents_written"] == 0
    assert out["status"] == "held_pending_review"


def test_write_gold_training_sets_hitl_fields() -> None:
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    client = MagicMock()
    client.session.return_value = session
    with patch(
        "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client",
        return_value=client,
    ):
        out = write_gold_training(
            {
                "encounter_text": "abdominal pain",
                "entities": [
                    {
                        "text": "abdominal pain",
                        "label": "finding",
                        "start": 0,
                        "end": 14,
                        "_llm_check_source": "relation_corrected",
                    }
                ],
                "relation_changes": [{"type": "relation_corrected", "index": 0}],
                "verification_result": {"confidence": 0.9},
                "errors": [],
            }
        )
    assert out["training_labels_written"] == 1
    assert session.run.call_args.kwargs["hitl_reason"] == "pipeline_feedback"


def test_write_gold_training_widens_short_sentence_with_context() -> None:
    """Candidates shorter than NER_SHORT_CONTEXT_THRESHOLD should include
    neighbouring sentence text so the model trains on the same richer context
    it sees at inference time."""
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    client = MagicMock()
    client.session.return_value = session

    sentences = [
        {"sentence_id": "s0", "text": "No cough.", "start": 0, "end": 9},
        {"sentence_id": "s1", "text": "SOB", "start": 10, "end": 13},
        {"sentence_id": "s2", "text": "O2 sats 96%.", "start": 14, "end": 26},
    ]

    with patch(
        "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client",
        return_value=client,
    ), patch.dict("os.environ", {"NER_SHORT_CONTEXT_THRESHOLD": "50"}):
        out = write_gold_training(
            {
                "encounter_text": "No cough. SOB O2 sats 96%.",
                "sentences": sentences,
                "entities": [
                    {
                        "text": "SOB",
                        "label": "finding",
                        "__sentence_id": "s1",
                        "start": 10,
                        "end": 13,
                        "_llm_check_source": "llm_added",
                    }
                ],
                "verification_result": {"confidence": 0.9},
                "errors": [],
            }
        )

    assert out["training_labels_written"] == 1
    # The text stored in Neo4j should include the neighbouring sentences
    stored_text: str = session.run.call_args.kwargs["text"]
    assert "No cough." in stored_text
    assert "SOB" in stored_text
    assert "O2 sats 96%." in stored_text
    stored_entities = json.loads(session.run.call_args.kwargs["entities_json"])
    assert stored_entities[0]["text"] == "SOB"
    assert stored_text[
        stored_entities[0]["start"] : stored_entities[0]["end"]
    ] == "SOB"


def test_write_gold_training_leaves_long_sentence_unchanged() -> None:
    """Candidates at or above the threshold must not have context injected."""
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    client = MagicMock()
    client.session.return_value = session

    long_text = "Patient presents with severe shortness of breath for three days."

    sentences = [
        {"sentence_id": "s0", "text": "Prev.", "start": 0, "end": 5},
        {"sentence_id": "s1", "text": long_text, "start": 6, "end": 6 + len(long_text)},
    ]

    with patch(
        "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client",
        return_value=client,
    ), patch.dict("os.environ", {"NER_SHORT_CONTEXT_THRESHOLD": "50"}):
        out = write_gold_training(
            {
                "encounter_text": f"Prev. {long_text}",
                "sentences": sentences,
                "entities": [
                    {
                        "text": "shortness of breath",
                        "label": "finding",
                        "__sentence_id": "s1",
                        "start": 6 + long_text.index("shortness"),
                        "end": 6 + long_text.index("shortness") + len("shortness of breath"),
                        "_llm_check_source": "llm_added",
                    }
                ],
                "verification_result": {"confidence": 0.9},
                "errors": [],
            }
        )

    assert out["training_labels_written"] == 1
    stored_text: str = session.run.call_args.kwargs["text"]
    # Neighbouring "Prev." must NOT have been injected
    assert "Prev." not in stored_text
