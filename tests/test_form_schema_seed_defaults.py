"""Tests for POST /form-schemas/seed-defaults.

Confirms that the endpoint seeds the SFH Gynae 2WW schema when it is absent
and skips it when it already exists, without hitting Neo4j.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import json
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
            "app.routers.form_schema.rebind_form_schema_ids",
            return_value="seeded",
        ) as mock_rebind,
    ):
        client = _client(mock_client)
        resp = client.post("/form-schemas/seed-defaults")

    assert resp.status_code == 200
    body = resp.json()
    assert body["seeded"] == ["sfh-gynae-2ww-v1"]
    assert body["skipped"] == []
    assert body["updated"] == []
    mock_rebind.assert_called_once()


def test_seed_defaults_skips_when_live_ids_already_bound() -> None:
    """Skip when the existing node already matches the fixture bind ids."""
    bound = _mock_schema()
    bound.organization_id = "RK5"
    bound.service_id = "7980224"
    mock_client = MagicMock()

    with (
        patch(
            "app.routers.form_schema.PatientGraphClient",
            return_value=mock_client,
        ),
        patch(
            "app.routers.form_schema.rebind_form_schema_ids",
            return_value="skipped",
        ) as mock_rebind,
    ):
        client = _client(mock_client)
        resp = client.post("/form-schemas/seed-defaults")

    assert resp.status_code == 200
    body = resp.json()
    assert body["seeded"] == []
    assert body["skipped"] == ["sfh-gynae-2ww-v1"]
    assert body["updated"] == []
    mock_rebind.assert_called_once()


def test_seed_defaults_rebinds_slug_ids_to_live_nodes() -> None:
    """Rebind an existing alias-slug schema to Organization.id / Service.id."""
    mock_client = MagicMock()

    with (
        patch(
            "app.routers.form_schema.PatientGraphClient",
            return_value=mock_client,
        ),
        patch(
            "app.routers.form_schema.rebind_form_schema_ids",
            return_value="updated",
        ) as mock_rebind,
    ):
        client = _client(mock_client)
        resp = client.post("/form-schemas/seed-defaults")

    assert resp.status_code == 200
    body = resp.json()
    assert body["seeded"] == []
    assert body["skipped"] == []
    assert body["updated"] == ["sfh-gynae-2ww-v1"]
    write = mock_rebind.call_args.args[1]
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/form_schema/sfh_gynae_2ww_template.json"
        ).read_text(encoding="ascii")
    )
    assert write.organization_id == fixture["organization_id"]
    assert write.service_id == fixture["service_id"]


def test_rebind_keeps_sections_and_writes_live_ids() -> None:
    from unittest.mock import MagicMock

    from libs.pipeline.form_schema_normalizer import FormSection
    from libs.pipeline.form_schema_store import (
        FormSchemaWrite,
        rebind_form_schema_ids,
        reset_schema_cache,
    )

    reset_schema_cache()
    existing = _mock_schema()
    existing.organization_id = "sfh-nhs-trust"
    existing.service_id = "sfh-gynae-2ww"
    existing.sections = [
        FormSection(
            section_id="A",
            section_type="checkbox",
            label="Cancer type",
            start_pattern="Section A",
            items=[],
        )
    ]
    client = MagicMock()
    write = FormSchemaWrite(
        fingerprint="sfh-gynae-2ww-v1",
        form_name="Test",
        sections=[],
        created_by="seed-defaults",
        organization_id="RK5",
        service_id="7980224",
        organization_name="Sherwood Forest Hospitals NHS Foundation Trust",
        service_name="Sherwood - Gynaecology Urgent Suspected Cancer Pathway",
    )
    with patch(
        "libs.pipeline.form_schema_store.load_form_schema",
        return_value=existing,
    ):
        with patch(
            "libs.pipeline.form_schema_store.save_form_schema",
        ) as mock_save:
            action = rebind_form_schema_ids(client, write)
    assert action == "updated"
    saved = mock_save.call_args.args[1]
    assert saved.organization_id == "RK5"
    assert saved.service_id == "7980224"
    assert saved.sections == existing.sections
