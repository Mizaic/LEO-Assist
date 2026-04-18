"""VT-LEO-AI-230 -- patient_finder router contracts (PatientGraphClient stubbed).

Verifies DI-LEO-AI-230 acceptance criteria for the four endpoints
backing the PatientFinder primitive:
  - GET /patient-finder/search trims input and forwards a digits-only
    derivative for NHS number / id matching.
  - GET /patient-finder/by-filter parses CohortFilter and applies the
    caller's org scope clause.
  - GET /patient-finder/{id}/encounters returns 404 when the patient is
    out of scope (R-LEO-AI-211 mitigation -- no leakage).
  - GET /document-references/{id}/chunks paginates and previews text.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from libs.auth.org_scope import CallerScope, get_caller_scope
from services.analytics_api.app.routers.patient_finder import (
    router as patient_finder_router,
)


def _make_app(scope: CallerScope) -> FastAPI:
    app = FastAPI()
    app.include_router(patient_finder_router)
    app.dependency_overrides[get_caller_scope] = lambda: scope
    return app


@contextmanager
def _patched_client(rows_by_query: List[List[Dict[str, Any]]]):
    """Stub PatientGraphClient so each .run() returns the next row list."""
    client = MagicMock()
    client.run.side_effect = list(rows_by_query)
    client.close = MagicMock()
    with patch(
        "services.analytics_api.app.routers.patient_finder.PatientGraphClient",
        return_value=client,
    ):
        yield client


GP_SCOPE = CallerScope(
    email="gp@example.test",
    is_admin=False,
    org_ids=["GP-1"],
)
ADMIN_SCOPE = CallerScope(email="admin@example.test", is_admin=True)


# -- /patient-finder/search --------------------------------------------------


def test_search_returns_results_with_nhs_number_and_dob() -> None:
    rows = [
        {
            "id": "pat-1",
            "display_name": "Alice Smith",
            "nhs_number": "9991112222",
            "dob": "1970-01-01",
            "gender": "female",
            "gp_id": "GP-1",
        }
    ]
    with _patched_client([rows]) as client:
        app = _make_app(GP_SCOPE)
        r = TestClient(app).get("/patient-finder/search", params={"q": "smith"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    row0 = body["results"][0]
    assert row0["nhs_number"] == "9991112222"
    assert row0["dob"] == "1970-01-01"
    cypher, params = client.run.call_args.args[0], client.run.call_args.kwargs
    assert "MATCH (p:Patient)" in cypher
    assert params["needle"] == "smith"
    assert params["digits"] == ""
    assert params["scope_org_ids"] == ["GP-1"]


def test_search_extracts_digits_for_nhs_number_or_id_match() -> None:
    with _patched_client([[]]) as client:
        TestClient(_make_app(ADMIN_SCOPE)).get(
            "/patient-finder/search", params={"q": "999 111 2222"}
        )
    params = client.run.call_args.kwargs
    assert params["digits"] == "9991112222"
    # Admin scope -> no scope_org_ids param injected.
    assert "scope_org_ids" not in params


def test_search_rejects_blank_q() -> None:
    app = _make_app(GP_SCOPE)
    r = TestClient(app).get("/patient-finder/search", params={"q": ""})
    assert r.status_code == 422


# -- /patient-finder/by-filter ----------------------------------------------


def test_by_filter_parses_cohort_filter_json_and_applies_scope() -> None:
    rows_count = [{"cnt": 7}]
    rows_page = [
        {
            "id": "pat-1",
            "display_name": "B",
            "nhs_number": "1",
            "dob": "1990-01-01",
            "gender": "male",
            "gp_id": "GP-1",
        }
    ]
    with _patched_client([rows_count, rows_page]) as client:
        r = TestClient(_make_app(GP_SCOPE)).get(
            "/patient-finder/by-filter",
            params={
                "filters": '{"age_min": 40, "imd_decile_min": 1}',
                "limit": 10,
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 7
    assert len(body["results"]) == 1
    page_call = client.run.call_args_list[1]
    assert "p.age >= $age_min" in page_call.args[0]
    assert "$imd_decile_min" in page_call.args[0]
    assert page_call.kwargs["age_min"] == 40
    assert page_call.kwargs["scope_org_ids"] == ["GP-1"]


def test_by_filter_returns_422_on_bad_json() -> None:
    r = TestClient(_make_app(ADMIN_SCOPE)).get(
        "/patient-finder/by-filter", params={"filters": "{not json"}
    )
    assert r.status_code == 422


# -- /patient-finder/{id}/encounters ----------------------------------------


def test_encounters_returns_404_for_out_of_scope_patient() -> None:
    """R-LEO-AI-211 mitigation -- mismatched patients are 404 not 403."""
    with _patched_client([[], []]):
        r = TestClient(_make_app(GP_SCOPE)).get(
            "/patient-finder/pat-out-of-scope/encounters"
        )
    assert r.status_code == 404


def test_encounters_returns_summaries_when_in_scope() -> None:
    scope_check = [{"id": "pat-1"}]
    encounter_rows = [
        {
            "id": "enc-1",
            "date": "2026-01-01",
            "encounter_type": "GP",
            "top_concept": "Cough",
            "coded_count": 3,
        }
    ]
    with _patched_client([scope_check, encounter_rows]):
        r = TestClient(_make_app(GP_SCOPE)).get(
            "/patient-finder/pat-1/encounters"
        )
    assert r.status_code == 200
    rows = r.json()
    assert rows[0]["id"] == "enc-1"
    assert rows[0]["coded_count"] == 3
    assert rows[0]["top_concept"] == "Cough"


# -- /document-references/{id}/chunks ---------------------------------------


def test_chunks_endpoint_truncates_text_to_80_char_preview() -> None:
    long_text = "a" * 200
    chunk_rows = [{"id": "c-1", "ordinal": 0, "text": long_text}]
    with _patched_client([chunk_rows]):
        r = TestClient(_make_app(GP_SCOPE)).get(
            "/document-references/dr-1/chunks"
        )
    assert r.status_code == 200
    rows = r.json()
    assert rows[0]["id"] == "c-1"
    assert rows[0]["preview"].endswith("...")
    assert len(rows[0]["preview"]) == 83  # 80 chars + "..."
