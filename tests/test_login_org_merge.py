"""VT-DC9757B4 -- login merges Organization on azureTenantId.

Atlas trace:
  VT: VT-DC9757B4
  DI: DI-E6963408, DI-A482F83F
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-DC9757B4")
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

from libs.auth.login_org import ensure_organization_for_tenant
from libs.cypher import admin_queries as aq


def test_merge_cypher_keys_on_azure_tenant_id() -> None:
    query = aq.MERGE_ORG_BY_AZURE_TENANT
    assert "MERGE (o:Organization {azureTenantId: $azureTenantId})" in query
    assert "o.organization_id = $id" in query
    assert "entra_tenant_id" not in query


def test_org_list_and_create_use_azure_tenant_id() -> None:
    assert "o.azureTenantId AS azureTenantId" in aq.LIST_ORGS
    assert "o.azureTenantId AS azureTenantId" in aq.LIST_ORGS_SCOPED
    assert "o.azureTenantId = $azureTenantId" in aq.CREATE_ORG_GP
    assert "entra_tenant_id" not in aq.LIST_ORGS
    assert "entra_tenant_id" not in aq.CREATE_ORG_GP


def test_valid_tid_merges_org_with_id_and_organization_id() -> None:
    tid = "2a5d13c4-6c54-4c7f-b17b-e00a0eab6285"
    client = MagicMock()
    client.run.return_value = [{"id": tid, "name": "mizaic.com"}]

    with patch("libs.auth.login_org.PatientGraphClient", return_value=client):
        result = ensure_organization_for_tenant(tid, "mizaic.com")

    assert result.ok is True
    assert result.org_id == tid
    kwargs = client.run.call_args.kwargs
    assert kwargs["azureTenantId"] == tid
    assert kwargs["id"] == tid
    assert kwargs["name"] == "mizaic.com"
    query = client.run.call_args.args[0]
    assert "azureTenantId" in query
    assert "organization_id" in query


def test_same_tid_reuses_merge_key() -> None:
    query = aq.MERGE_ORG_BY_AZURE_TENANT
    assert query.count("MERGE (o:Organization {azureTenantId: $azureTenantId})") == 1
    assert "CREATE (o:Organization" not in query


def test_empty_tid_does_not_merge() -> None:
    client = MagicMock()
    with patch("libs.auth.login_org.PatientGraphClient", return_value=client):
        result = ensure_organization_for_tenant("", "mizaic.com")

    assert result.ok is False
    assert result.reason == "empty_tid"
    client.run.assert_not_called()


def test_merge_exception_does_not_succeed() -> None:
    client = MagicMock()
    client.run.side_effect = RuntimeError("graph down")
    with patch("libs.auth.login_org.PatientGraphClient", return_value=client):
        result = ensure_organization_for_tenant(
            "2a5d13c4-6c54-4c7f-b17b-e00a0eab6285",
            "mizaic.com",
        )

    assert result.ok is False
    assert result.reason == "merge_failed"


def test_existing_hccp_tid_is_matched_not_recreated() -> None:
    tid = "fbe0dd99-aa0d-45db-8dd8-9c0c465c7ce1"
    client = MagicMock()
    client.run.return_value = [{"id": "HCCP", "name": "Healthcare Copilot"}]

    with patch("libs.auth.login_org.PatientGraphClient", return_value=client):
        result = ensure_organization_for_tenant(tid, "immj.cloud")

    assert result.ok is True
    assert result.org_id == "HCCP"
    assert client.run.call_args.kwargs["id"] == tid
    assert client.run.call_args.kwargs["azureTenantId"] == tid


def test_identity_lookups_use_user_not_practitioner() -> None:
    from libs.auth import org_scope, practitioner_org_context
    from libs.cypher import density_queries
    from services.analytics_api.app.routers import org_context as analytics_org

    scope_src = inspect.getsource(org_scope.resolve_caller_scope)
    login_src = inspect.getsource(practitioner_org_context.fetch_practitioner_org_context)
    analytics_src = inspect.getsource(analytics_org.get_org_context)
    assert "MATCH (pr:User {email:" in scope_src
    assert ":Practitioner" not in scope_src
    assert "MATCH (pr:User {email:" in login_src
    assert ":Practitioner" not in login_src
    assert ":Practitioner" not in analytics_src
    assert ":User" in density_queries.GET_PRACTITIONER_DENSITY
    assert ":Practitioner" not in density_queries.GET_PRACTITIONER_DENSITY
    assert ":Practitioner" not in aq.CREATE_PRACTITIONER
    assert "MERGE (pr:User {email: $email})" in aq.CREATE_PRACTITIONER
