"""Tests for receiving Service resolution and state wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.clinical_scoping.healthcare_service import (
    HealthcareServiceScope,
    apply_healthcare_service_scope,
    resolve_healthcare_service,
)


def test_resolve_healthcare_service_returns_scope() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "id": "6711368",
            "name": "Fast track cancer referral",
            "specialty": "2WW",
            "guideline_ids_prop": None,
            "guidance_ids": ["NG12", "val-gardena-default"],
            "completeness_domain": None,
            "completeness_subdomain": None,
            "spoa_id": None,
            "organization_id": "M0L1I",
            "organization_name": "Sherwood Forest Hospitals",
        }
    ]
    scope = resolve_healthcare_service(
        client,
        source_node_type="ReferralRequest",
        source_node_id="000049823847",
    )
    assert scope is not None
    assert scope.id == "6711368"
    assert scope.guideline_ids == ["NG12", "val-gardena-default"]
    assert scope.organization_id == "M0L1I"
    assert scope.organization_name == "Sherwood Forest Hospitals"


def test_resolve_healthcare_service_merges_property_and_graph_guidelines() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "id": "6710021",
            "name": "LEO - Agentic Universal Cancer Pathway",
            "specialty": "2WW",
            "guideline_ids_prop": "NG12",
            "guidance_ids": ["NG12", "val-gardena-default"],
            "completeness_domain": None,
            "completeness_subdomain": None,
            "spoa_id": None,
            "organization_id": "M0L1I",
        }
    ]
    scope = resolve_healthcare_service(
        client,
        source_node_type="ReferralRequest",
        source_node_id="000049812191",
    )
    assert scope is not None
    assert scope.guideline_ids == ["NG12", "val-gardena-default"]


def test_resolve_healthcare_service_missing_link_returns_none() -> None:
    client = MagicMock()
    client.run.return_value = []
    scope = resolve_healthcare_service(
        client,
        source_node_type="ReferralRequest",
        source_node_id="missing",
    )
    assert scope is None


def test_apply_healthcare_service_scope_sets_primary_guidelines() -> None:
    state: dict = {}
    service = HealthcareServiceScope(
        id="6711368",
        name="Fast track cancer referral",
        specialty="2WW",
        guideline_ids=["NG12"],
        organization_id="M0L1I",
        organization_name="Sherwood Forest Hospitals",
    )
    apply_healthcare_service_scope(state, service)
    assert state["healthcare_service_id"] == "6711368"
    assert state["healthcare_service_org_id"] == "M0L1I"
    assert state["healthcare_service_org_name"] == "Sherwood Forest Hospitals"
    assert state["primary_guideline_ids"] == ["NG12"]
    assert state["guideline_scope_id"] == "NG12"
    assert state["healthcare_service_missing"] is False


def test_message_guideline_ids_override_service_scope() -> None:
    state: dict = {}
    service = HealthcareServiceScope(
        id="6711368",
        name="Fast track cancer referral",
        specialty="2WW",
        guideline_ids=["NG12"],
    )
    apply_healthcare_service_scope(
        state,
        service,
        message_guideline_ids=["LOCAL-001"],
    )
    assert state["primary_guideline_ids"] == ["LOCAL-001"]
    assert state["guideline_scope_id"] == "LOCAL-001"


def test_missing_service_soft_fails_without_override() -> None:
    state: dict = {}
    apply_healthcare_service_scope(state, None)
    assert state["healthcare_service_missing"] is True
    assert "primary_guideline_ids" not in state
