"""Referral bundles in document_chunks mode must carry receiving-service scope.

Atlas trace: DI-26546721 (organisation and service bind)

A referral bundle is loaded as :Chunk rows, so ``default_source_fields``
returns source_node_type "Chunk". ``_apply_healthcare_service_scope`` only
runs for "ReferralRequest" or "CommunicationRequest", so the receiving trust
and service are never written onto pipeline state. ``_schema_scope`` then
falls back to ``org_id`` (the patient's GP practice) and a blank service, and
the organisation-plus-service lookup for a taught :FormSchema can never match.

These tests are RED against the current code and describe the behaviour the
fix must deliver. Do not weaken them to make them pass.
"""

from __future__ import annotations

from typing import Any

import pytest

from libs.pipeline.document_chunk_loader import DOCUMENT_CHUNKS_MODE
from libs.pipeline_graph.subgraphs.extraction import _schema_scope
from libs.workflow.durable_steps import StepRequest
from libs.workflow.step_state_loader import load_step_state

RECEIVING_ORG_ID = "RK5"
RECEIVING_SERVICE_ID = "7980224"
GP_PRACTICE_ORG_ID = "Y05690"
REFERRAL_ID = "000481914514"
DOCUMENT_REFERENCE_ID = f"{REFERRAL_ID}:leo-referral-bundle"
CHUNK_ID = "chunk-section-c"
CHUNK_TEXT = "| Section C: Further Clinical details |\n| --- |\n| BMI: 20.2 |"


class _FakeGraphClient:
    """Stands in for PatientGraphClient over the referral graph shape.

    Mirrors production: the patient is registered with a GP practice, the
    referral points at the receiving Service, and the Service points at the
    receiving Organization.
    """

    def __init__(self) -> None:
        self.queries: list[str] = []

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        if "HAS_GENERAL_PRACTITIONER" in query:
            return [{"org_id": GP_PRACTICE_ORG_ID}]
        if "p:Patient" in query and "birthDate" in query:
            return [{"birth_date": "1962-04-01", "gender": "female", "source": ""}]
        if "FOR_SERVICE" in query:
            return [
                {
                    "id": RECEIVING_SERVICE_ID,
                    "name": "Sherwood - Gynaecology Urgent Suspected Cancer Pathway",
                    "ers_service_id": RECEIVING_SERVICE_ID,
                    "specialty": "Gynaecology",
                    "guideline_ids_prop": None,
                    "guidance_ids": [],
                    "completeness_domain": None,
                    "completeness_subdomain": None,
                    "spoa_id": None,
                    "organization_id": RECEIVING_ORG_ID,
                    "organization_name": "Sherwood Forest Hospitals NHS FT",
                }
            ]
        if "c:Chunk" in query:
            return [
                {
                    "chunk_id": CHUNK_ID,
                    "text": CHUNK_TEXT,
                    "ordinal": 0,
                    "char_start": 0,
                    "char_end": len(CHUNK_TEXT),
                }
            ]
        return []


class _FakeStageStore:
    """Accumulated state for a referral run before the extract step."""

    def load_accumulated_state(self, run_id: str) -> dict[str, Any]:
        return {
            "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
            "chunk_ids": [CHUNK_ID],
            "document_reference_id": DOCUMENT_REFERENCE_ID,
            "referral_id": REFERRAL_ID,
            "ubrn": REFERRAL_ID,
        }


def _request() -> StepRequest:
    return StepRequest(
        event_type="durable_step",
        run_id="run-referral-1",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="7185630207",
        encounter_id=f"{REFERRAL_ID}:referral-assessment",
        plan_definition_id="pd-referral-assessment",
        guideline_ids=[],
        context={"source": "patient-viewer"},
    )


@pytest.fixture
def referral_state(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Load durable step state exactly as the referral extract step does."""
    monkeypatch.setattr(
        "libs.workflow.step_state_loader._validate_trigger_chunk_scope",
        lambda client, state, chunk_ids: [],
    )
    monkeypatch.setattr(
        "libs.workflow.step_state_loader._load_execution_manifest",
        lambda client, run_id, state: None,
    )
    monkeypatch.setattr(
        "libs.pipeline.document_chunk_loader._resolve_chunk_schema",
        lambda *args, **kwargs: (
            None,
            {
                "form_schema_fingerprint": "none",
                "form_schema_match": "none",
                "form_schema_label": "",
            },
        ),
    )
    return load_step_state(_FakeGraphClient(), _FakeStageStore(), _request())


def test_referral_chunk_state_carries_receiving_organisation(
    referral_state: dict[str, Any],
) -> None:
    """The receiving trust must reach state, not just the patient's GP."""
    assert referral_state.get("healthcare_service_org_id") == RECEIVING_ORG_ID


def test_referral_chunk_state_carries_receiving_service(
    referral_state: dict[str, Any],
) -> None:
    """The receiving Service.id must reach state for the schema lookup."""
    assert referral_state.get("healthcare_service_id") == RECEIVING_SERVICE_ID


def test_schema_scope_resolves_receiving_org_and_service(
    referral_state: dict[str, Any],
) -> None:
    """_schema_scope must not fall back to the GP practice or a blank service."""
    org_id, service_id, _ers_id = _schema_scope(referral_state)
    assert (org_id, service_id) == (RECEIVING_ORG_ID, RECEIVING_SERVICE_ID)
    assert org_id != GP_PRACTICE_ORG_ID


def test_schema_scope_service_is_never_blank(
    referral_state: dict[str, Any],
) -> None:
    """A blank service id makes _load_schema_by_org_service return None."""
    _org_id, service_id, _ers_id = _schema_scope(referral_state)
    assert service_id.strip() != ""
