"""Tests for GET /form-schemas/letter-text endpoint.

The endpoint fetches :Chunk nodes by UBRN from Neo4j, joins them, and
returns the encounter text with a fingerprint.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from libs.cypher.chunk_queries import GET_CHUNKS_BY_UBRN

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.deps import get_session_data
from app.routers.form_schema import router


def _session(role: str = "validation") -> dict:
    return {
        "email": "tester@example.com",
        "selected_role": role,
        "allowed_roles": [role],
        "is_platform_admin": False,
    }


def _client(session: dict | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_data] = lambda: session or _session()
    return TestClient(app)


_SAMPLE_CHUNKS = [
    {
        "chunk_id": "c1",
        "text": "Patient presents with chest pain.",
        "ordinal": 0,
        "char_start": 0,
        "char_end": 32,
    },
    {
        "chunk_id": "c2",
        "text": "Referred urgently to cardiology.",
        "ordinal": 1,
        "char_start": 34,
        "char_end": 66,
    },
]


@patch("app.routers.form_schema.PatientGraphClient")
def test_letter_text_returns_joined_chunks(mock_neo: MagicMock) -> None:
    """Happy path: UBRN resolves to chunks; text and fingerprint are returned."""
    mock_client = MagicMock()
    mock_client.run.return_value = _SAMPLE_CHUNKS
    mock_neo.return_value = mock_client

    tc = _client()
    resp = tc.get(
        "/form-schemas/letter-text",
        params={"ubrn": "0001234567", "organization_id": "org-1"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "Patient presents with chest pain." in body["text"]
    assert "Referred urgently to cardiology." in body["text"]
    assert body["fingerprint"]
    assert body["chunk_count"] == 2


@patch("app.routers.form_schema.PatientGraphClient")
def test_letter_text_404_when_no_chunks(mock_neo: MagicMock) -> None:
    """Returns 404 when Neo4j finds no chunks for the UBRN."""
    mock_client = MagicMock()
    mock_client.run.return_value = []
    mock_neo.return_value = mock_client

    tc = _client()
    resp = tc.get(
        "/form-schemas/letter-text",
        params={"ubrn": "9999999999", "organization_id": "org-1"},
    )

    assert resp.status_code == 404
    assert "9999999999" in resp.json()["detail"]


@patch("app.routers.form_schema.PatientGraphClient")
def test_letter_text_404_when_chunks_have_no_text(mock_neo: MagicMock) -> None:
    """Returns 404 when chunks exist but all have empty text."""
    mock_client = MagicMock()
    mock_client.run.return_value = [
        {"chunk_id": "c1", "text": "", "ordinal": 0, "char_start": 0, "char_end": 0}
    ]
    mock_neo.return_value = mock_client

    tc = _client()
    resp = tc.get(
        "/form-schemas/letter-text",
        params={"ubrn": "0001234567", "organization_id": "org-1"},
    )

    assert resp.status_code == 404


@patch("app.routers.form_schema.PatientGraphClient")
def test_letter_text_400_when_ubrn_missing(mock_neo: MagicMock) -> None:
    """Returns 422 when ubrn query param is absent (FastAPI validation)."""
    tc = _client()
    resp = tc.get(
        "/form-schemas/letter-text",
        params={"organization_id": "org-1"},
    )
    assert resp.status_code == 422


def test_letter_query_finds_the_organisation_through_the_referral_service() -> None:
    """Referrals carry no organization_id; the tenant is on their Service.

    In the live graph every ReferralRequest links FOR_SERVICE to a Service,
    and the Service PROVIDES_SERVICE_FOR an Organization. A query that only
    reads rr.organization_id finds no letter for any referral.
    """
    query = " ".join(GET_CHUNKS_BY_UBRN.split())
    assert (
        "(rr)-[:FOR_SERVICE]->(:Service)-[:PROVIDES_SERVICE_FOR]->(org:Organization)"
        in query
    )
    assert "org.id = $organization_id" in query


def test_letter_text_requires_auth() -> None:
    """Returns 403 when the caller has no form-teacher role."""
    tc = _client(_session(role="lms_learner"))
    resp = tc.get(
        "/form-schemas/letter-text",
        params={"ubrn": "0001234567", "organization_id": "org-1"},
    )
    assert resp.status_code == 403
