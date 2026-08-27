"""Tests for POST /form-schemas/seed-defaults.

Confirms that the endpoint seeds the SFH Gynae 2WW schema when it is absent
and skips it when it already exists, without hitting Neo4j.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.deps import get_session_data
from app.routers.form_schema import router
from libs.pipeline.form_schema_normalizer import FormSchema


def _session() -> dict:
    return {
        "email": "teacher@example.com",
        "selected_role": "validation",
        "allowed_roles": ["validation"],
        "is_platform_admin": False,
    }


def _client(neo4j_mock: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_data] = _session
    return TestClient(app)


def _mock_schema() -> FormSchema:
    return FormSchema(
        schema_id="test-id",
        fingerprint="sfh-gynae-2ww-v1",
        form_name="Test",
        sections=[],
        created_by="seed",
        version=1,
        status="active",
        created_at="",
        organization_id="",
        service_id="",
    )


def test_seed_defaults_seeds_when_absent() -> None:
    """Returns seeded list when the schema does not exist yet."""
    mock_client = MagicMock()
    mock_client.run.return_value = []

    with (
        patch(
            "app.routers.form_schema.PatientGraphClient",
            return_value=mock_client,
        ),
        patch(
            "app.routers.form_schema.load_form_schema",
            return_value=None,
        ),
        patch(
            "app.routers.form_schema.save_form_schema",
            return_value=_mock_schema(),
        ) as mock_save,
    ):
        client = _client(mock_client)
        resp = client.post("/form-schemas/seed-defaults")

    assert resp.status_code == 200
    body = resp.json()
    assert body["seeded"] == ["sfh-gynae-2ww-v1"]
    assert body["skipped"] == []
    mock_save.assert_called_once()


def test_seed_defaults_skips_when_present() -> None:
    """Returns skipped list when the schema already exists."""
    mock_client = MagicMock()

    with (
        patch(
            "app.routers.form_schema.PatientGraphClient",
            return_value=mock_client,
        ),
        patch(
            "app.routers.form_schema.load_form_schema",
            return_value=_mock_schema(),
        ),
        patch(
            "app.routers.form_schema.save_form_schema",
        ) as mock_save,
    ):
        client = _client(mock_client)
        resp = client.post("/form-schemas/seed-defaults")

    assert resp.status_code == 200
    body = resp.json()
    assert body["seeded"] == []
    assert body["skipped"] == ["sfh-gynae-2ww-v1"]
    mock_save.assert_not_called()
