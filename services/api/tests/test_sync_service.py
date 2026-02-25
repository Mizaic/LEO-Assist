"""Tests for sync service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.sync_service import sync_gold_to_patient


class TestSyncService:
    """Test sync gold to patient graph (single session for both reads and writes)."""

    def test_sync_creates_links_from_gold(self) -> None:
        patient_session = MagicMock()
        patient_session.run.return_value = [
            {
                "c": {
                    "candidate_id": "c1",
                    "patient_id": "p1",
                    "encounter_id": "enc1",
                    "sentences_json": '[{"sentence_id":"s0","terms":[{"text":"diabetes","coding":{"snomed_concept_id":"73211009","snomed_term":"Diabetes","read_code":"C10","score":0.95},"context":{"negated":false},"semantic_tag":"Disease","modifiers":{}}]}]',
                }
            }
        ]

        result = sync_gold_to_patient(
            "p1",
            patient_session=patient_session,
        )

        assert result["patient_id"] == "p1"
        assert result["encounters_synced"] == 1
        assert result["links_created"] == 1
        assert "error" not in result
        assert patient_session.run.call_count >= 1

    def test_sync_no_approved_gold(self) -> None:
        patient_session = MagicMock()
        patient_session.run.return_value = []

        result = sync_gold_to_patient(
            "p1",
            patient_session=patient_session,
        )

        assert result["patient_id"] == "p1"
        assert result["encounters_synced"] == 0
        assert result["links_created"] == 0
        assert result["error"] == "no_approved_gold"

    def test_sync_skips_terms_without_snomed(self) -> None:
        patient_session = MagicMock()
        patient_session.run.return_value = [
            {
                "c": {
                    "candidate_id": "c1",
                    "patient_id": "p1",
                    "encounter_id": "enc1",
                    "sentences_json": """[
                        {
                            "sentence_id": "s0",
                            "terms": [
                                {
                                    "text": "unknown term",
                                    "coding": {"snomed_concept_id": null, "snomed_term": null},
                                    "context": {},
                                    "semantic_tag": "Other",
                                    "modifiers": {}
                                }
                            ]
                        }
                    ]""",
                }
            }
        ]

        result = sync_gold_to_patient(
            "p1",
            patient_session=patient_session,
        )

        assert result["encounters_synced"] == 1
        assert result["links_created"] == 0
