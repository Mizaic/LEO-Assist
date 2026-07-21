"""Additional tests for mixed Communication/Chunk persist behaviour."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.cypher.documents_queries import (
    _VALID_SOURCE_LABELS,
    _build_upsert_query,
    write_documents_from_sentences_payload,
)


def test_valid_source_labels_includes_communication() -> None:
    assert "Communication" in _VALID_SOURCE_LABELS


def test_build_upsert_query_communication_reaches_patient() -> None:
    query = _build_upsert_query(
        "SnomedConcept", "HAS_CONCEPT", source_label="Communication"
    )
    assert "Communication {id: $source_id}" in query
    assert "HAS_CONVERSATION" in query
    assert "FOR_PATIENT" in query


def test_write_documents_uses_per_sentence_persist_source_label() -> None:
    session = MagicMock()
    payload = [
        {
            "sentence_id": "c1",
            "text": "[REQUESTER] Pain in chest",
            "persist_source_label": "Communication",
            "terms": [
                {
                    "text": "Pain in chest",
                    "semantic_tag": "finding",
                    "assertion": "present",
                    "coding": {
                        "snomed_concept_id": "29857009",
                        "snomed_term": "Chest pain",
                        "score": 0.9,
                    },
                }
            ],
        },
        {
            "sentence_id": "chunk-1",
            "text": "[ATTACHMENT] Hb 120",
            "persist_source_label": "Chunk",
            "terms": [
                {
                    "text": "Hb",
                    "semantic_tag": "observable_entity",
                    "assertion": "present",
                    "coding": {
                        "snomed_concept_id": "104091002",
                        "snomed_term": "Haemoglobin",
                        "score": 0.9,
                    },
                }
            ],
        },
    ]
    with patch(
        "libs.cypher.documents_queries.deidentify_with_span",
        side_effect=[("DEID comm", 0, 5), ("DEID chunk", 0, 2)],
    ):
        written = write_documents_from_sentences_payload(
            encounter_id="enc-1",
            sentences_payload=payload,
            session=session,
            source="pipeline",
            run_id="run-1",
            source_label="Encounter",
        )
    assert written == 2
    source_ids = [
        call.kwargs.get("source_id")
        for call in session.run.call_args_list
        if "source_id" in call.kwargs
    ]
    assert "c1" in source_ids
    assert "chunk-1" in source_ids


def test_write_documents_communication_vs_chunk_in_same_payload() -> None:
    session = MagicMock()
    payload = [
        {
            "sentence_id": "comm-1",
            "persist_source_label": "Communication",
            "text": "note",
            "terms": [
                {
                    "text": "fever",
                    "semantic_tag": "finding",
                    "coding": {
                        "snomed_concept_id": "386661006",
                        "snomed_term": "Fever",
                        "score": 0.8,
                    },
                }
            ],
        },
        {
            "sentence_id": "chunk-9",
            "persist_source_label": "Chunk",
            "text": "attachment",
            "terms": [
                {
                    "text": "WBC",
                    "semantic_tag": "observable_entity",
                    "coding": {
                        "snomed_concept_id": "767002",
                        "snomed_term": "White blood cell count",
                        "score": 0.8,
                    },
                }
            ],
        },
    ]
    with patch(
        "libs.cypher.documents_queries.deidentify_with_span",
        return_value=("DEID", 0, 1),
    ):
        write_documents_from_sentences_payload(
            encounter_id="enc-2",
            sentences_payload=payload,
            session=session,
            source_label="Communication",
        )
    queries = [str(call.args[0]) for call in session.run.call_args_list]
    assert any("Communication" in q for q in queries)
    assert any("Chunk" in q for q in queries)
