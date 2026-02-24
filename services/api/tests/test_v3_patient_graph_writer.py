"""Tests for V3 patient graph writer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.v3.patient_graph_writer import PatientGraphWriter, SemanticLinkPayload


class TestPatientGraphWriter:
    """Test graph write operations."""

    def test_upsert_skips_empty_concept_id(self) -> None:
        writer = PatientGraphWriter()
        session = MagicMock()
        payload = SemanticLinkPayload(
            encounter_id="enc1",
            semantic_tag="Disease",
            concept_id="",
            term="Hypertension",
            read_code="G20",
            evidence="Patient has hypertension",
            confidence=0.9,
            domain="clinical",
            context={},
            modifiers={},
            source="v3_pipeline",
        )
        writer.upsert_documents_link(payload, session=session)
        session.run.assert_not_called()

    def test_upsert_calls_session_with_correct_params(self) -> None:
        writer = PatientGraphWriter()
        session = MagicMock()
        payload = SemanticLinkPayload(
            encounter_id="enc1",
            semantic_tag="Disease",
            concept_id="38341003",
            term="Hypertension",
            read_code="G20",
            evidence="Patient has hypertension",
            confidence=0.9,
            domain="clinical",
            context={"negated": False},
            modifiers={"severity": None},
            source="v3_pipeline",
        )
        writer.upsert_documents_link(payload, session=session)
        session.run.assert_called_once()
        call_args = session.run.call_args
        assert "enc1" in str(call_args[1].get("encounter_id", ""))
        assert call_args[1]["concept_id"] == "38341003"
        assert call_args[1]["name"] == "Hypertension"
        assert call_args[1]["read_code"] == "G20"
        assert call_args[1]["confidence"] == 0.9

    def test_delete_calls_session_with_params(self) -> None:
        writer = PatientGraphWriter()
        session = MagicMock()
        writer.delete_documents_link(
            encounter_id="enc1",
            concept_id="38341003",
            patient_id="p1",
            session=session,
        )
        session.run.assert_called_once()
        call_args = session.run.call_args
        assert call_args[1]["patient_id"] == "p1"
        assert call_args[1]["encounter_id"] == "enc1"
        assert call_args[1]["concept_id"] == "38341003"

    def test_recode_deletes_old_and_upserts_new(self) -> None:
        writer = PatientGraphWriter()
        session = MagicMock()
        new_payload = SemanticLinkPayload(
            encounter_id="enc1",
            semantic_tag="Disease",
            concept_id="73211009",
            term="Diabetes mellitus",
            read_code="C10",
            evidence="diabetes",
            confidence=0.95,
            domain="clinical",
            context={},
            modifiers={},
            source="manual_recode",
        )
        writer.recode_documents_link(
            patient_id="p1",
            old_concept_id="38341003",
            new_payload=new_payload,
            session=session,
        )
        assert session.run.call_count == 2
        # First call: DELETE (old concept)
        first_call = session.run.call_args_list[0]
        assert first_call[1]["concept_id"] == "38341003"
        # Second call: MERGE (new concept)
        second_call = session.run.call_args_list[1]
        assert second_call[1]["concept_id"] == "73211009"
