"""The label to chunk-id map must survive the loader into pipeline state.

The document-chunks loader builds it, and the persist step needs it to turn
an ``s0`` label back into the :Chunk id a ``MATCH (src:Chunk {id: ...})``
can find. The extraction subgraph nodes return an explicit dictionary rather
than merging the whole loader result, so a key the loader adds is dropped
unless it is named here. Drop it and every fact goes back to being written
against an id that matches nothing.

Atlas trace:
  DI: DI-16CE412B, DI-B7A69F26  (fail-closed boundary)
  DO: DO-728930A1
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from libs.pipeline_graph.subgraphs.extraction import (
    load_communication_thread,
    load_document_chunks,
)

_CHUNK = "b689f4e037be32adc8f70163067c0063"
_ATTACHMENT = "4a8d9afbdb1e46b4caedb0aadcdbece1"


def _chunk_rows() -> list[dict[str, Any]]:
    text = "Reason for referral: post-menopausal bleeding."
    return [
        {
            "chunk_id": _CHUNK,
            "text": text,
            "ordinal": 0,
            "char_start": 0,
            "char_end": len(text),
        }
    ]


def test_document_chunks_loader_publishes_the_reverse_map() -> None:
    client = MagicMock()
    client.run.return_value = _chunk_rows()
    with (
        patch(
            "libs.neo4j_client.client.PatientGraphClient",
            return_value=client,
        ),
        patch(
            "libs.pipeline.document_chunk_loader._recognise_chunks",
            return_value=[],
        ),
    ):
        out = load_document_chunks({"chunk_ids": [_CHUNK]})

    assert out["sentences"][0]["sentence_id"] == "s0"
    assert out.get("chunk_id_by_sentence_id") == {"s0": _CHUNK}


def test_communication_thread_loader_publishes_the_reverse_map() -> None:
    thread_rows = [
        {
            "communication_id": "c1",
            "note": "Please advise.",
            "category": "REQUESTER",
            "sent_datetime": "2026-01-01T09:00:00",
            "attachment_chunks": [
                {
                    "chunk_id": _ATTACHMENT,
                    "text": "Haemoglobin 118 g/L.",
                    "ordinal": 0,
                }
            ],
        }
    ]
    loaded = {
        "sentences": [
            {
                "sentence_id": "c1",
                "text": "[REQUESTER] Please advise.",
                "persist_source_label": "Communication",
            },
            {
                "sentence_id": "s0",
                "text": "[ATTACHMENT] Haemoglobin 118 g/L.",
                "persist_source_label": "Chunk",
            },
        ],
        "chunk_id_by_sentence_id": {"s0": _ATTACHMENT},
        "encounter_text": "[REQUESTER] Please advise.",
        "text_segmentation_mode": "communication_thread",
    }
    del thread_rows

    with (
        patch(
            "libs.neo4j_client.client.PatientGraphClient",
            return_value=MagicMock(),
        ),
        patch(
            "libs.pipeline.communication_thread_loader."
            "load_communication_thread_from_neo4j",
            return_value=loaded,
        ),
    ):
        out = load_communication_thread({"communication_request_id": "cr-1"})

    assert out.get("chunk_id_by_sentence_id") == {"s0": _ATTACHMENT}


def test_preloaded_sentences_keep_the_reverse_map_already_in_state() -> None:
    """Durable steps load chunks once and replay the state on later steps."""
    state = {
        "sentences": [{"sentence_id": "s0", "text": "x", "start": 0, "end": 1}],
        "encounter_text": "x",
        "chunk_id_by_sentence_id": {"s0": _CHUNK},
    }
    out = load_document_chunks(state)
    assert out.get("chunk_id_by_sentence_id") == {"s0": _CHUNK}


def test_every_state_that_carries_the_map_declares_it_as_a_channel() -> None:
    """LangGraph drops an undeclared key without a word of complaint.

    A silent drop here is the whole bug again, so the channel must be
    declared everywhere the map has to travel.
    """
    from libs.pipeline_graph import state as shared_state
    from libs.pipeline_graph.subgraphs import extraction, persist

    carriers = (
        extraction.ExtractionState,
        persist.PersistState,
        shared_state.ExtractionState,
        shared_state.PersistState,
        shared_state.PipelineState,
    )
    missing = [
        carrier.__name__
        for carrier in carriers
        if "chunk_id_by_sentence_id" not in carrier.__annotations__
    ]
    assert missing == [], f"states that would silently drop the map: {missing}"


def test_the_states_that_report_a_lost_fact_declare_a_warnings_channel() -> None:
    from libs.pipeline_graph import state as shared_state
    from libs.pipeline_graph.subgraphs import persist

    for carrier in (persist.PersistState, shared_state.PipelineState):
        assert "warnings" in carrier.__annotations__, carrier.__name__
