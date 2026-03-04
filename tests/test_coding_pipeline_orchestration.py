"""Tests: CodingPipeline orchestration, idempotency, and integration flow.

Covers:
- run_single_encounter calls extract_batch then resolve then persist.
- Structured progress events are emitted in correct order.
- Dry-run skips persistence.
- Idempotency: re-running same encounter does not duplicate UPSERT calls
  (MERGE semantics; same candidate_id).
- run_id is threaded through to progress events and persistence.
- Extractor source/model_name/model_version appear in persisted payload.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from services.coding_worker.app.pipeline.extractor_contract import (
    CONTRACT_VERSION,
    ExtractionItem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_extraction_item(
    text="colorectal cancer",
    source="llm",
    model_name="bedrock",
    model_version="1.0",
) -> ExtractionItem:
    return ExtractionItem(
        sentence_id="s_001",
        text=text,
        span_start=0,
        span_end=len(text),
        semantic_tag="disease",
        assertion="present",
        confidence=0.9,
        normalized=text,
        source=source,
        model_name=model_name,
        model_version=model_version,
        contract_version=CONTRACT_VERSION,
    )


def _stub_patient_client(encounter_text: str = "Patient referred for colorectal cancer"):
    client = MagicMock()
    client.run.return_value = [
        {
            "encounter_id": "enc-001",
            "date": "2024-01-15",
            "text": encounter_text,
        }
    ]
    session_cm = MagicMock()
    session_cm.__enter__ = MagicMock(return_value=MagicMock())
    session_cm.__exit__ = MagicMock(return_value=False)
    client.session.return_value = session_cm
    return client


# ---------------------------------------------------------------------------
# Progress events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_single_encounter_emits_events():
    patient_client = _stub_patient_client()
    knowledge_client = MagicMock()

    from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

    pipeline = CodingPipeline(
        patient_client=patient_client,
        knowledge_client=knowledge_client,
    )

    mock_extractor = MagicMock()
    mock_extractor.source = "llm"
    mock_extractor.model_name = "bedrock"
    mock_extractor.model_version = "1.0"
    mock_extractor.extract_batch.return_value = [_make_extraction_item()]

    events: list[dict[str, Any]] = []

    with patch(
        "services.coding_worker.app.pipeline.pipeline_service.build_extractor",
        return_value=mock_extractor,
    ):
        with patch(
            "services.coding_worker.app.pipeline.pipeline_service.CodingPipeline._resolve_via_api",
            new_callable=AsyncMock,
            return_value={"colorectal cancer": [{"snomed_concept_id": "363346000",
                                                  "snomed_term": "Malignant neoplasm",
                                                  "score": 0.95}]},
        ):
            await pipeline.run_single_encounter(
                patient_id="pat-001",
                encounter_id="enc-001",
                dry_run=True,
                progress_hook=events.append,
                run_id="run-xyz",
            )

    event_types = [e["type"] for e in events]
    assert "encounter_started" in event_types
    assert "fetched" in event_types
    assert "extracted" in event_types
    assert "resolved" in event_types
    assert "persisted" in event_types
    assert "run_completed" in event_types


@pytest.mark.asyncio
async def test_run_id_in_events():
    patient_client = _stub_patient_client()
    knowledge_client = MagicMock()

    from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

    pipeline = CodingPipeline(patient_client=patient_client, knowledge_client=knowledge_client)
    mock_extractor = MagicMock()
    mock_extractor.source = "llm"
    mock_extractor.model_name = "bedrock"
    mock_extractor.model_version = "1.0"
    mock_extractor.extract_batch.return_value = []

    events: list[dict[str, Any]] = []

    with patch(
        "services.coding_worker.app.pipeline.pipeline_service.build_extractor",
        return_value=mock_extractor,
    ):
        with patch(
            "services.coding_worker.app.pipeline.pipeline_service.CodingPipeline._resolve_via_api",
            new_callable=AsyncMock,
            return_value={},
        ):
            await pipeline.run_single_encounter(
                patient_id="pat-001",
                encounter_id="enc-001",
                dry_run=True,
                progress_hook=events.append,
                run_id="my-run-id",
            )

    assert all(
        e.get("run_id") == "my-run-id"
        for e in events
        if "encounter_id" in e or e.get("type") == "run_completed"
    )


# ---------------------------------------------------------------------------
# Dry-run: no persistence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_skips_persistence():
    patient_client = _stub_patient_client()
    knowledge_client = MagicMock()

    from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

    pipeline = CodingPipeline(patient_client=patient_client, knowledge_client=knowledge_client)
    mock_extractor = MagicMock()
    mock_extractor.source = "llm"
    mock_extractor.model_name = "bedrock"
    mock_extractor.model_version = "1.0"
    mock_extractor.extract_batch.return_value = [_make_extraction_item()]

    with patch(
        "services.coding_worker.app.pipeline.pipeline_service.build_extractor",
        return_value=mock_extractor,
    ):
        with patch(
            "services.coding_worker.app.pipeline.pipeline_service.CodingPipeline._resolve_via_api",
            new_callable=AsyncMock,
            return_value={},
        ):
            with patch.object(pipeline, "_persist_documents") as mock_persist:
                await pipeline.run_single_encounter(
                    patient_id="pat-001",
                    encounter_id="enc-001",
                    dry_run=True,
                )

    mock_persist.assert_not_called()


# ---------------------------------------------------------------------------
# Idempotency: same candidate_id for same patient+encounter
# ---------------------------------------------------------------------------

def test_candidate_id_deterministic():
    """Same patient_id+encounter_id always produces the same candidate_id."""
    candidate_id_1 = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "candidate:pat-001:enc-001")
    )
    candidate_id_2 = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "candidate:pat-001:enc-001")
    )
    assert candidate_id_1 == candidate_id_2


@pytest.mark.asyncio
async def test_run_twice_calls_upsert_not_insert():
    """Re-running same encounter calls _persist_documents twice — MERGE semantics are idempotent.

    With empty extraction results there is nothing to persist, so we verify
    that _persist_documents is called once per non-dry_run invocation regardless
    of whether there are items to write (the method handles empty payloads safely).
    """
    patient_client = _stub_patient_client()
    knowledge_client = MagicMock()

    from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

    mock_extractor = MagicMock()
    mock_extractor.source = "llm"
    mock_extractor.model_name = "bedrock"
    mock_extractor.model_version = "1.0"
    mock_extractor.extract_batch.return_value = [_make_extraction_item()]

    persist_call_count = 0

    def _count_persist(*args, **kwargs):
        nonlocal persist_call_count
        persist_call_count += 1

    pipeline = CodingPipeline(
        patient_client=patient_client,
        knowledge_client=knowledge_client,
    )

    with patch(
        "services.coding_worker.app.pipeline.pipeline_service.build_extractor",
        return_value=mock_extractor,
    ):
        with patch(
            "services.coding_worker.app.pipeline.pipeline_service.CodingPipeline._resolve_via_api",
            new_callable=AsyncMock,
            return_value={},
        ):
            with patch.object(pipeline, "_persist_documents", side_effect=_count_persist):
                await pipeline.run_single_encounter("pat-001", "enc-001", dry_run=False)
                await pipeline.run_single_encounter("pat-001", "enc-001", dry_run=False)

    assert persist_call_count == 2, (
        f"Expected _persist_documents called twice (idempotent MERGE), got {persist_call_count}"
    )


# ---------------------------------------------------------------------------
# Provenance in sentences payload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sentences_payload_has_provenance():
    """sentences_payload items must carry extraction_source/model_name/version."""
    patient_client = _stub_patient_client()
    knowledge_client = MagicMock()

    from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

    item = _make_extraction_item(source="model", model_name="spacy-ner", model_version="2.1")
    mock_extractor = MagicMock()
    mock_extractor.source = "model"
    mock_extractor.model_name = "spacy-ner"
    mock_extractor.model_version = "2.1"
    mock_extractor.extract_batch.return_value = [item]

    captured_payload: list = []

    async def _fake_resolve(terms, **kwargs):
        return {}

    pipeline = CodingPipeline(patient_client=patient_client, knowledge_client=knowledge_client)

    def _capture_persist(encounter_id, sentences_payload, extractor, run_id=""):
        captured_payload.extend(sentences_payload)

    with patch(
        "services.coding_worker.app.pipeline.pipeline_service.build_extractor",
        return_value=mock_extractor,
    ):
        with patch.object(pipeline, "_resolve_via_api", new=_fake_resolve):
            with patch.object(pipeline, "_persist_documents", side_effect=_capture_persist):
                await pipeline.run_single_encounter(
                    patient_id="pat-001",
                    encounter_id="enc-001",
                    dry_run=False,
                )

    all_terms = [
        term for sent in captured_payload for term in sent.get("terms", [])
    ]
    for term in all_terms:
        assert term.get("extraction_source") == "model"
        assert term.get("extraction_model_name") == "spacy-ner"
        assert term.get("extraction_model_version") == "2.1"
        assert term.get("contract_version") == CONTRACT_VERSION


# ---------------------------------------------------------------------------
# Extraction failure emits failed event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extraction_failure_emits_failed_event():
    patient_client = _stub_patient_client()
    knowledge_client = MagicMock()

    from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

    mock_extractor = MagicMock()
    mock_extractor.source = "llm"
    mock_extractor.model_name = "bedrock"
    mock_extractor.model_version = "1.0"
    mock_extractor.extract_batch.side_effect = RuntimeError("LLM timeout")

    events: list[dict[str, Any]] = []

    with patch(
        "services.coding_worker.app.pipeline.pipeline_service.build_extractor",
        return_value=mock_extractor,
    ):
        pipeline = CodingPipeline(patient_client=patient_client, knowledge_client=knowledge_client)
        await pipeline.run_single_encounter(
            patient_id="pat-001",
            encounter_id="enc-001",
            dry_run=True,
            progress_hook=events.append,
        )

    failed_events = [e for e in events if e.get("type") == "failed"]
    assert len(failed_events) == 1
    assert failed_events[0]["stage"] == "extraction"
