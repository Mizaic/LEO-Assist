from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.cypher.documents_queries import write_documents_from_sentences_payload


def test_sentence_evidence_maps_to_correct_documents_relationship() -> None:
    session = MagicMock()
    payload = [
        {
            "text": "Sentence one has Haematocrit mention.",
            "terms": [
                {
                    "text": "Haematocrit",
                    "semantic_tag": "observable_entity",
                    "assertion": "present",
                    "coding": {
                        "snomed_concept_id": "1022291000000105",
                        "snomed_term": "Haematocrit (observable entity)",
                        "score": 0.99,
                    },
                }
            ],
        },
        {
            "text": "Sentence two has Neutrophil count mention.",
            "terms": [
                {
                    "text": "Neutrophil count",
                    "semantic_tag": "observable_entity",
                    "assertion": "present",
                    "coding": {
                        "snomed_concept_id": "1022551000000104",
                        "snomed_term": "Neutrophil count (observable entity)",
                        "score": 0.88,
                    },
                }
            ],
        },
    ]

    with patch(
        "libs.cypher.documents_queries.deidentify_with_span",
        side_effect=[
            ("DEID sentence one", 18, 29),
            ("DEID sentence two", 22, 37),
        ],
    ) as deid_mock:
        written = write_documents_from_sentences_payload(
            encounter_id="enc-1",
            sentences_payload=payload,
            session=session,
            source="pipeline_runtime",
            run_id="run-123",
        )

    assert written == 2

    deid_mock.assert_any_call("Sentence one has Haematocrit mention.", "Haematocrit")
    deid_mock.assert_any_call(
        "Sentence two has Neutrophil count mention.",
        "Neutrophil count",
    )

    docs_calls = [
        c
        for c in session.run.call_args_list
        if c.kwargs.get("encounter_id") == "enc-1" and "evidence_sentence" in c.kwargs
    ]
    assert len(docs_calls) == 2

    first = docs_calls[0].kwargs
    assert first["concept_id"] == "1022291000000105"
    assert first["evidence_sentence"] == "DEID sentence one"
    assert first["sentence_index"] == 0
    assert first["evidence_start"] == 18
    assert first["evidence_end"] == 29

    second = docs_calls[1].kwargs
    assert second["concept_id"] == "1022551000000104"
    assert second["evidence_sentence"] == "DEID sentence two"
    assert second["sentence_index"] == 1
    assert second["evidence_start"] == 22
    assert second["evidence_end"] == 37


def test_multiline_sentence_payload_is_narrowed_to_matching_line() -> None:
    session = MagicMock()
    block = (
        "09:25 - Surgery: Auto-filed\n"
        "Monocyte count - observation (42N..) 0.16 10^9/L [0.2 - 0.8]\n"
        "Haematocrit (X76tb) 0.357 [0.37 - 0.47] - Outside reference range\n"
        "Neutrophil count (42J..) 2.8 10^9/L [1.5 - 7.5]"
    )
    payload = [
        {
            "text": block,
            "terms": [
                {
                    "text": "Haematocrit",
                    "semantic_tag": "observable_entity",
                    "assertion": "present",
                    "coding": {
                        "snomed_concept_id": "1022291000000105",
                        "snomed_term": "Haematocrit (observable entity)",
                        "score": 0.99,
                    },
                }
            ],
        }
    ]

    with patch(
        "libs.cypher.documents_queries.deidentify_with_span",
        return_value=("DEID haematocrit line", 0, 11),
    ) as deid_mock:
        written = write_documents_from_sentences_payload(
            encounter_id="enc-2",
            sentences_payload=payload,
            session=session,
            source="pipeline_runtime",
            run_id="run-456",
        )

    assert written == 1
    deid_mock.assert_called_once()
    deid_sentence_arg = deid_mock.call_args.args[0]
    assert deid_sentence_arg == "Haematocrit (X76tb) 0.357 [0.37 - 0.47] - Outside reference range"
    assert deid_mock.call_args.args[1] == "Haematocrit"

    docs_calls = [
        c
        for c in session.run.call_args_list
        if c.kwargs.get("encounter_id") == "enc-2" and "evidence_sentence" in c.kwargs
    ]
    assert len(docs_calls) == 1
    call = docs_calls[0].kwargs
    assert call["concept_id"] == "1022291000000105"
    assert call["evidence_sentence"] == "DEID haematocrit line"
