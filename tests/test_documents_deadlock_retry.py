"""DOCUMENTS write retries Neo4j deadlocks (DI-79D15317 / DO-728930A1)."""

from __future__ import annotations

import logging
import threading
from unittest.mock import MagicMock, patch

import pytest
from neo4j.exceptions import TransientError

from libs.cypher.documents_queries import (
    _DOC_WRITE_MAX_RETRIES,
    _collect_pending_document_writes,
    _session_run_with_deadlock_retry,
    write_documents_from_sentences_payload,
)


def _deadlock() -> TransientError:
    return TransientError("Neo.TransientError.Transaction.DeadlockDetected")


def _sample_payload(*, reverse_terms: bool = False) -> list[dict]:
    terms = [
        {
            "text": "hypertension",
            "semantic_tag": "finding",
            "assertion": "present",
            "coding": {
                "snomed_concept_id": "38341003",
                "snomed_term": "Hypertension",
                "score": 0.9,
            },
        },
        {
            "text": "dysphagia",
            "semantic_tag": "finding",
            "assertion": "present",
            "coding": {
                "snomed_concept_id": "40739000",
                "snomed_term": "Dysphagia",
                "score": 0.9,
            },
        },
    ]
    if reverse_terms:
        terms = list(reversed(terms))
    return [
        {
            "text": "Patient has hypertension and dysphagia.",
            "sentence_id": "s-1",
            "terms": terms,
        }
    ]


def test_session_run_retries_deadlock_then_succeeds() -> None:
    session = MagicMock()
    session.run.side_effect = [_deadlock(), _deadlock(), None]
    with patch("libs.cypher.documents_queries.time.sleep") as sleep_mock:
        _session_run_with_deadlock_retry(session, "RETURN 1", concept_id="1")
    assert session.run.call_count == 3
    assert sleep_mock.call_count == 2


def test_session_run_raises_after_retries_exhausted() -> None:
    session = MagicMock()
    session.run.side_effect = _deadlock()
    with patch("libs.cypher.documents_queries.time.sleep"):
        with pytest.raises(TransientError):
            _session_run_with_deadlock_retry(session, "RETURN 1", concept_id="1")
    assert session.run.call_count == _DOC_WRITE_MAX_RETRIES


def test_deadlock_retry_logs_debug_not_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = MagicMock()
    session.run.side_effect = [_deadlock(), None]
    with (
        caplog.at_level(logging.DEBUG),
        patch("libs.cypher.documents_queries.time.sleep"),
    ):
        _session_run_with_deadlock_retry(session, "RETURN 1", concept_id="40739000")
    messages = [record.message for record in caplog.records]
    assert any("retry in" in msg for msg in messages)
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


def test_deadlock_final_failure_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    session = MagicMock()
    session.run.side_effect = _deadlock()
    with (
        caplog.at_level(logging.DEBUG),
        patch("libs.cypher.documents_queries.time.sleep"),
    ):
        with pytest.raises(TransientError):
            _session_run_with_deadlock_retry(session, "RETURN 1", concept_id="40739000")
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert "failed after" in warnings[0].message


def test_collect_pending_writes_sorts_by_concept_id() -> None:
    pending = _collect_pending_document_writes(
        "enc-1",
        _sample_payload(reverse_terms=True),
        source="pipeline_runtime",
        model_name="",
        model_version="",
        contract_version="",
        run_id="run-1",
        source_label="Encounter",
        active_terms=set(),
    )
    concept_ids = [item.params["concept_id"] for item in pending]
    assert concept_ids == ["38341003", "40739000"]


def test_write_payload_retries_deadlock_and_counts_write() -> None:
    session = MagicMock()
    session.run.side_effect = [_deadlock(), None]
    payload = [
        {
            "text": "Patient has dysphagia.",
            "terms": [
                {
                    "text": "dysphagia",
                    "semantic_tag": "finding",
                    "assertion": "present",
                    "coding": {
                        "snomed_concept_id": "40739000",
                        "snomed_term": "Dysphagia",
                        "score": 0.9,
                    },
                }
            ],
        }
    ]
    with (
        patch(
            "libs.cypher.documents_queries.deidentify_with_span",
            return_value=("Patient has dysphagia.", 12, 21),
        ),
        patch("libs.cypher.documents_queries.time.sleep"),
    ):
        written = write_documents_from_sentences_payload(
            encounter_id="enc-1",
            sentences_payload=payload,
            session=session,
            source="pipeline_runtime",
            run_id="run-1",
        )
    assert written == 1
    assert session.run.call_count == 2


def test_concurrent_payload_writes_use_same_concept_order() -> None:
    """Two threads with reversed term order should MERGE concepts in same order."""
    lock = threading.Lock()
    observed_order: list[str] = []

    def _recording_run(_query: str, **params: object) -> None:
        with lock:
            observed_order.append(str(params.get("concept_id")))

    session = MagicMock()
    session.run.side_effect = _recording_run

    def _write(reverse: bool) -> None:
        with (
            patch(
                "libs.cypher.documents_queries.deidentify_with_span",
                return_value=("Patient has hypertension and dysphagia.", 0, 5),
            ),
            patch("libs.cypher.documents_queries.time.sleep"),
        ):
            write_documents_from_sentences_payload(
                encounter_id="enc-1",
                sentences_payload=_sample_payload(reverse_terms=reverse),
                session=session,
                source="pipeline_runtime",
                run_id="run-1",
            )

    threads = [
        threading.Thread(target=_write, args=(False,)),
        threading.Thread(target=_write, args=(True,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    expected = ["38341003", "40739000"]
    first_pair = observed_order[0:2]
    second_pair = observed_order[2:4]
    assert first_pair == expected
    assert second_pair == expected
