"""Tenant startup seed must write a valid Organization node.

Atlas trace:
  VT: VT-91B5C8D7
  DI: DI-96D95459
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-91B5C8D7")

The patient graph requires Organization.organization_id. The Mizaic
platform org MERGE must set that property on create and heal it on match.
"""

from __future__ import annotations

from services.api.app.services.tenant_seed import (
    MIZAIC_ORG_ID,
    _seed_mizaic_org_and_group,
)


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **params: object) -> list:
        self.calls.append((query, params))
        return []


def test_mizaic_org_seed_sets_organization_id_on_create_and_match() -> None:
    """Mizaic Organization MERGE sets organization_id so the existence
    constraint does not reject the node.
    """
    client = _FakeClient()
    _seed_mizaic_org_and_group(client)

    org_calls = [(query, params) for query, params in client.calls if ":Organization" in query]
    assert org_calls, "expected an Organization MERGE"
    query, params = org_calls[0]
    assert params.get("id") == MIZAIC_ORG_ID
    assert "o.organization_id" in query
    assert "ON CREATE SET" in query
    assert "ON MATCH SET" in query
