"""Tests for manual patient document CRUD."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from libs.patient_documents.service import (
    PatientDocumentError,
    create_patient_document,
    delete_patient_document,
    update_patient_document,
)


def _session_mock() -> MagicMock:
    session = MagicMock()
    session.run.return_value.data.return_value = [
        {"document_id": "doc1", "referral_id": "doc1:referral"}
    ]
    return session


def test_create_patient_document_writes_chunks():
    client = MagicMock()
    session = _session_mock()
    client.session.return_value.__enter__.return_value = session

    with patch(
        "libs.patient_documents.service.split_into_chunks",
        return_value=[
            {
                "id": "c1",
                "text": "Hello",
                "sha256": "abc",
                "ordinal": 1,
                "char_start": 0,
                "char_end": 5,
            }
        ],
    ):
        result = create_patient_document(
            client,
            patient_id="p1",
            title="Referral letter",
            markdown_body="Hello",
        )

    assert result.document_id
    assert result.referral_id.endswith(":referral")
    assert result.chunk_ids == ("c1",)


def test_create_patient_document_rejects_empty_body():
    client = MagicMock()
    with pytest.raises(PatientDocumentError, match="required"):
        create_patient_document(
            client,
            patient_id="p1",
            title="Referral letter",
            markdown_body="   ",
        )


def test_update_patient_document_rechunks_when_body_changes():
    client = MagicMock()
    client.run.return_value = [
        {
            "document_id": "doc1",
            "episode_id": "",
            "milestone_type": "",
            "chunk_ids": ["old"],
        }
    ]
    session = MagicMock()
    client.session.return_value.__enter__.return_value = session

    with patch(
        "libs.patient_documents.service.split_into_chunks",
        return_value=[
            {
                "id": "c2",
                "text": "Updated",
                "sha256": "def",
                "ordinal": 1,
                "char_start": 0,
                "char_end": 7,
            }
        ],
    ):
        result = update_patient_document(
            client,
            patient_id="p1",
            document_id="doc1",
            markdown_body="Updated",
        )

    assert result.chunk_ids == ("c2",)


def test_delete_patient_document_requires_manual_source():
    client = MagicMock()
    client.run.side_effect = [
        [],
    ]
    with pytest.raises(PatientDocumentError, match="not found"):
        delete_patient_document(client, patient_id="p1", document_id="doc1")

    client.run.side_effect = [
        [{"document_id": "doc1", "chunk_ids": ["c1"]}],
        [],
    ]
    deleted = delete_patient_document(client, patient_id="p1", document_id="doc1")
    assert deleted == "doc1"
