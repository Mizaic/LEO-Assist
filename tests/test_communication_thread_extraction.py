"""Tests for communication_thread extraction subgraph behaviour."""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline.communication_thread_loader import COMMUNICATION_THREAD_MODE
from libs.pipeline_graph.subgraphs.extraction import (
    _SOURCE_NODE_CONFIG,
    load_communication_thread,
    resolve_text_units,
)


def test_source_node_config_includes_communication() -> None:
    assert "Communication" in _SOURCE_NODE_CONFIG
    assert _SOURCE_NODE_CONFIG["Communication"]["text_properties"] == ("note",)


def test_resolve_text_units_communication_thread_skips_splitter() -> None:
    state = {
        "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
        "sentences": [
            {
                "sentence_id": "c1",
                "text": "[REQUESTER] Question",
                "persist_source_label": "Communication",
            }
        ],
    }
    loaded = resolve_text_units(state)
    assert loaded["sentences"][0]["text"] == "[REQUESTER] Question"
    assert loaded["text_segmentation_mode"] == COMMUNICATION_THREAD_MODE


def test_load_communication_thread_empty_thread_errors() -> None:
    state = {
        "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
        "communication_request_id": "cr-missing",
    }
    with patch(
        "libs.pipeline.communication_thread_loader.load_communication_thread_from_neo4j",
        return_value={
            "sentences": [],
            "encounter_text": "",
            "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
            "errors": [
                "communication_thread mode requires thread, attachment, or AGR text"
            ],
        },
    ):
        loaded = load_communication_thread(state)
    assert loaded["errors"]
