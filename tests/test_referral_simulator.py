"""Happy/unhappy tests for libs.referral_simulator (Slice A)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from libs.cypher.chunk_queries import chunk_sha256, make_chunk_id
from libs.referral_simulator.ids import (
    document_reference_id,
    encounter_id_for_referral,
    referral_id_for_child_run,
    scenario_patient_id,
)
from libs.referral_simulator.message import (
    ReferralSimulatorError,
    build_referral_received_message,
)
from libs.referral_simulator.scaffold import (
    SOURCE_SCENARIO,
    cleanup_referral_scaffold,
    scaffold_referral,
    split_into_chunks,
)


# ---------------------------------------------------------------------------
# split_into_chunks
# ---------------------------------------------------------------------------


def test_split_into_chunks_happy_multi_paragraph():
    text = "First paragraph about jaundice.\n\nSecond paragraph with labs."
    dr_id = "rr-1:leo-referral-bundle"
    chunks = split_into_chunks(text, dr_id)

    assert len(chunks) == 2
    assert chunks[0]["ordinal"] == 1
    assert chunks[1]["ordinal"] == 2
    assert chunks[0]["text"] == "First paragraph about jaundice."
    assert chunks[1]["text"] == "Second paragraph with labs."
    for chunk in chunks:
        expected_sha = chunk_sha256(chunk["text"])
        assert chunk["sha256"] == expected_sha
        assert chunk["id"] == make_chunk_id(dr_id, chunk["ordinal"], expected_sha)


def test_split_into_chunks_unhappy_empty_text_raises():
    with pytest.raises(ReferralSimulatorError, match="empty"):
        split_into_chunks("   \n\n  ", "dr-1")


def test_split_into_chunks_happy_keeps_blood_results_heading_with_table():
    text = (
        "Narrative paragraph about jaundice.\n\n"
        "## Blood Results (Last 2m)\n\n"
        "| Panel | Date | Result |\n"
        "| --- | --- | --- |\n"
        "| LFT | 2026-04-22 | Bili 142.0 umol/L, Alk Phos 486.0 U/L |\n"
    )
    chunks = split_into_chunks(text, "dr-labs")
    assert len(chunks) == 2
    lab_chunk = chunks[1]["text"]
    assert "## Blood Results (Last 2m)" in lab_chunk
    assert "| Panel | Date | Result |" in lab_chunk
    assert "Bili 142.0 umol/L" in lab_chunk


# ---------------------------------------------------------------------------
# ids
# ---------------------------------------------------------------------------


def test_ids_happy_stable_scheme():
    case_id = "upper_gi_jaundice_001"
    child_run = "run-abc:upper_gi_jaundice_001"
    patient = scenario_patient_id(case_id)
    referral = referral_id_for_child_run(child_run)
    dr = document_reference_id(referral)
    enc = encounter_id_for_referral(referral)

    assert patient == "scenario-sbar-upper_gi_jaundice_001"
    assert referral == "run-abc:upper_gi_jaundice_001:referral"
    assert dr == "run-abc:upper_gi_jaundice_001:referral:leo-referral-bundle"
    assert enc == "run-abc:upper_gi_jaundice_001:referral:referral-assessment"


# ---------------------------------------------------------------------------
# build_referral_received_message
# ---------------------------------------------------------------------------


def test_message_happy_includes_production_handoff_keys():
    body = build_referral_received_message(
        patient_id="p-1",
        encounter_id="enc-1",
        referral_id="rr-1",
        document_reference_id="rr-1:leo-referral-bundle",
        chunk_ids=["c1", "c2"],
        run_id="run-1",
        plan_definition_id="pd-referral-assessment",
        guideline_id="NG12",
        completeness_domain="cancer_referrals",
        completeness_subdomain="upper_gi",
        context={"source": SOURCE_SCENARIO, "case_id": "case-1"},
    )

    assert body["event_type"] == "referral-received"
    assert body["referral_id"] == "rr-1"
    assert body["document_reference_id"] == "rr-1:leo-referral-bundle"
    assert body["chunk_ids"] == ["c1", "c2"]
    assert body["text_segmentation_mode"] == "document_chunks"
    assert body["source_node_type"] == "ReferralRequest"
    assert body["source_node_id"] == "rr-1"
    assert body["guideline_id"] == "NG12"
    assert body["completeness_domain"] == "cancer_referrals"
    assert body["completeness_subdomain"] == "upper_gi"
    assert body["context"]["source"] == SOURCE_SCENARIO
    assert body["context"]["case_id"] == "case-1"
    assert body["context"]["referral_id"] == "rr-1"


def test_message_happy_context_does_not_drop_handoff_keys():
    body = build_referral_received_message(
        patient_id="p-1",
        encounter_id="enc-1",
        referral_id="rr-1",
        document_reference_id="dr-1",
        chunk_ids=["c1"],
        run_id="run-1",
        context={"parent_run_id": "parent-1", "case_id": "c1"},
    )
    assert body["referral_id"] == "rr-1"
    assert body["chunk_ids"] == ["c1"]
    assert body["context"]["parent_run_id"] == "parent-1"
    assert body["context"]["referral_id"] == "rr-1"


def test_message_unhappy_empty_chunk_ids_rejected():
    with pytest.raises(ReferralSimulatorError, match="chunk_ids"):
        build_referral_received_message(
            patient_id="p-1",
            encounter_id="enc-1",
            referral_id="rr-1",
            document_reference_id="dr-1",
            chunk_ids=[],
            run_id="run-1",
        )


# ---------------------------------------------------------------------------
# scaffold_referral / cleanup
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls

    def run(self, query: str, **params: Any) -> None:
        self._calls.append((query, params))


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    @contextmanager
    def session(self):
        yield _FakeSession(self.calls)

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        return []

    def close(self) -> None:
        self.closed = True


def test_scaffold_referral_happy_writes_rr_dr_chunks():
    client = _FakeClient()
    text = "Para one.\n\nPara two."
    with patch(
        "libs.referral_simulator.scaffold.PatientGraphClient",
        return_value=client,
    ):
        chunk_ids = scaffold_referral(
            patient_id="p-1",
            referral_id="rr-1",
            dr_id="dr-1",
            text=text,
            encounter_id="rr-1:referral-assessment",
            source=SOURCE_SCENARIO,
            patient_sex="female",
            patient_name="Ada Lovelace",
        )

    assert len(chunk_ids) == 2
    assert client.closed is True
    assert any("ReferralRequest" in q for q, _ in client.calls)
    assert any("DocumentReference" in q for q, _ in client.calls)
    assert any("HAS_ENCOUNTER" in q for q, _ in client.calls)
    enc_params = next(p for q, p in client.calls if "HAS_ENCOUNTER" in q)
    assert enc_params["encounter_id"] == "rr-1:referral-assessment"
    assert enc_params["patient_id"] == "p-1"
    chunk_writes = [p for q, p in client.calls if "Chunk" in q or "chunk_id" in p]
    assert len(chunk_writes) >= 2
    graph_params = next(p for q, p in client.calls if "ReferralRequest" in q)
    assert graph_params["source"] == SOURCE_SCENARIO
    assert graph_params["gender"] == "female"
    assert graph_params["patient_name"] == "Ada Lovelace"


def test_scaffold_referral_happy_skips_encounter_when_id_omitted():
    client = _FakeClient()
    with patch(
        "libs.referral_simulator.scaffold.PatientGraphClient",
        return_value=client,
    ):
        scaffold_referral(
            patient_id="p-1",
            referral_id="rr-1",
            dr_id="dr-1",
            text="Para one.",
        )
    assert not any("HAS_ENCOUNTER" in q for q, _ in client.calls)


def test_scaffold_referral_unhappy_missing_ids_no_writes():
    client = _FakeClient()
    with patch(
        "libs.referral_simulator.scaffold.PatientGraphClient",
        return_value=client,
    ):
        with pytest.raises(ReferralSimulatorError, match="referral_id"):
            scaffold_referral(
                patient_id="p-1",
                referral_id="",
                dr_id="dr-1",
                text="Some clinical text.",
            )
    assert client.calls == []


def test_cleanup_happy_scoped_to_patient_and_source():
    client = _FakeClient()
    with patch(
        "libs.referral_simulator.scaffold.PatientGraphClient",
        return_value=client,
    ):
        cleanup_referral_scaffold("p-1", source=SOURCE_SCENARIO)

    assert len(client.calls) == 1
    query, params = client.calls[0]
    assert "DETACH DELETE" in query
    assert params["patient_id"] == "p-1"
    assert params["source"] == SOURCE_SCENARIO


def test_cleanup_unhappy_wrong_source_still_scoped_not_broad():
    """Cleanup always requires patient_id + source; never a bare MATCH delete."""
    client = _FakeClient()
    with patch(
        "libs.referral_simulator.scaffold.PatientGraphClient",
        return_value=client,
    ):
        cleanup_referral_scaffold("p-1", source="quick-test")

    query, params = client.calls[0]
    assert "$patient_id" in query or "patient_id" in params
    assert params["source"] == "quick-test"
    assert "MATCH (p:Patient)" in query or "Patient {id:" in query
    # Must not be an unscoped delete of all scenario patients.
    assert "scenario-sbar-" not in query or "$patient_id" in query
