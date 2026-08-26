"""Service completeness domain upsert used when teaching a form.

Atlas trace:
  UN: UN-3B25A20E
"""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.completeness.service_domain import (
    domain_id_for_service,
    ensure_service_completeness_domain,
)


def test_domain_id_uses_existing_service_id():
    assert domain_id_for_service("svc-gynae") == "svc_svc-gynae"


def test_ensure_domain_writes_schema_and_service_pointers():
    client = MagicMock()
    client.run.return_value = []
    groups = [
        {"name": "Section A", "kind": "mandatory", "required": True, "concept_ids": [1]}
    ]
    result = ensure_service_completeness_domain(
        client,
        organization_id="org-sfh",
        service_id="svc-gynae",
        form_name="SFH Gynae",
        groups=groups,
    )
    assert result["domain_id"]
    assert result["subdomain"] == "minimum_dataset"
    written = " ".join(str(call.args[0]) for call in client.run.call_args_list)
    assert "MERGE (d:AuditDomain" in written
    assert "HAS_SUBDOMAIN" in written
    assert "completeness_domain" in written
    kwargs = client.run.call_args_list[-1].kwargs
    assert kwargs["service_id"] == "svc-gynae"
    assert kwargs["organization_id"] == "org-sfh"
