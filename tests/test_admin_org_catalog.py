"""Form teachers must be able to read the existing org/service catalog.

Atlas trace: DI-26546721, UN-3B25A20E
"""

from __future__ import annotations

from pathlib import Path

ADMIN_SRC = Path("services/api/app/routers/admin.py").read_text()
AUTH_SRC = Path("services/api/app/org_catalog_auth.py").read_text()
QUERY_SRC = Path("libs/cypher/admin_queries.py").read_text()


def test_list_orgs_allows_form_teachers() -> None:
    assert "require_org_catalog_reader" in AUTH_SRC
    assert "FORM_TEACHER_ROLES" in AUTH_SRC
    assert "require_org_catalog_reader" in ADMIN_SRC
    assert "list_orgs" in ADMIN_SRC


def test_list_org_services_allows_form_teachers() -> None:
    assert ADMIN_SRC.index("def list_org_services") < len(ADMIN_SRC)
    services_block = ADMIN_SRC.split("def list_org_services", 1)[1][:400]
    assert "require_org_catalog_reader" in services_block


def test_shared_org_catalog_includes_service_provider_labels() -> None:
    assert "o:ServiceProvider" in QUERY_SRC
    assert "LIST_ORGS" in QUERY_SRC


def test_shared_service_catalog_follows_provides_service_for() -> None:
    """Live orgs link Service to Organization with PROVIDES_SERVICE_FOR."""
    block = QUERY_SRC.split("LIST_ORG_SERVICES = ", 1)[1].split('"""', 2)[1]
    assert "(s)-[:PROVIDES_SERVICE_FOR]->(o)" in block


def _query_body(name: str) -> str:
    marker = f'{name} = """'
    assert marker in QUERY_SRC, name
    return QUERY_SRC.split(marker, 1)[1].split('"""', 1)[0]


def test_brief_org_catalog_skips_patient_walk() -> None:
    """The form picker must not count patients for every organisation."""
    for name in ("LIST_ORGS_BRIEF", "LIST_ORGS_BRIEF_SCOPED"):
        body = _query_body(name)
        assert ":Patient" not in body
        assert "patient_count" not in body
        assert "o.id AS id" in body
        assert "o.name AS name" in body
        assert "o:ServiceProvider" in body
    assert "$scope_org_ids" in _query_body("LIST_ORGS_BRIEF_SCOPED")


def test_list_orgs_brief_flag_uses_name_only_queries() -> None:
    assert "brief: bool = False" in ADMIN_SRC
    block = ADMIN_SRC.split("def _run_org_list", 1)[1].split("\ndef ", 1)[0]
    assert "aq.LIST_ORGS_BRIEF)" in block
    assert "aq.LIST_ORGS_BRIEF_SCOPED" in block
    assert "aq.LIST_ORGS)" in block
    assert "aq.LIST_ORGS_SCOPED" in block
