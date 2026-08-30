"""List tenant completeness domains from the patient graph.

Atlas trace:
  UN: UN-3B25A20E
  DI: DI-10667413
  DO: DO-9C9CB1D8
  VT: VT-8A590E7A
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers import completeness_domains as mod


def test_list_query_filters_by_organization_id():
    assert "$organization_id" in mod._LIST_DOMAINS
    assert "org.id" in mod._LIST_DOMAINS


def test_list_domains_passes_organization_id_to_patient_graph():
    client = MagicMock()
    client.run.return_value = []
    params = inspect.signature(mod.list_domains).parameters
    assert "organization_id" in params
    with patch.object(mod, "PatientGraphClient", return_value=client):
        result = mod.list_domains(organization_id="RK5", _session={})
    assert result == {"domains": []}
    kwargs = client.run.call_args.kwargs
    assert kwargs.get("organization_id") == "RK5"


def test_list_domains_without_org_still_queries_patient_graph():
    client = MagicMock()
    client.run.return_value = [
        {
            "domain_id": "svc_117038",
            "domain_name": "Breast 2WW dataset",
            "organization_id": "RK5",
            "organization_name": "Sherwood Forest Hospitals",
            "completeness_schema": {"groups": [{"name": "Breast lump"}]},
            "updated_at": "",
        }
    ]
    with patch.object(mod, "PatientGraphClient", return_value=client):
        result = mod.list_domains(organization_id="", _session={})
    domains = result["domains"]
    assert domains[0]["domain_id"] == "svc_117038"
    assert domains[0]["completeness_groups"][0]["name"] == "Breast lump"
