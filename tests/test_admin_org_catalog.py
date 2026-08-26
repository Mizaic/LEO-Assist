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


def test_shared_service_catalog_matches_either_provides_service_direction() -> None:
    assert "LIST_ORG_SERVICES" in QUERY_SRC
    assert "[:PROVIDES_SERVICE]-" in QUERY_SRC
