"""Site 3 callers: the form-schema API must not report a blip as "not taught".

Both routes used to turn a failed lookup into an answer about the form
itself: the GET route replied ``match: none`` and the template route
replied "Save the form schema first". A form teacher would then re-teach
a form that is already taught, or believe normalisation is off when it is
not.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DI: DI-5C9CA57B (form checkbox normalisation)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.deps import get_session_data  # noqa: E402
from libs.pipeline.form_schema_store import FormSchemaLookupError  # noqa: E402

LETTER = (
    "Section A: Gynaecological Cancer type suspected\n"
    "Ovary [ ] Cervix [X] Endometrium [ ]\n"
)
_LOOKUP_FAILED = FormSchemaLookupError(
    "We could not check whether form fp-1 has a taught form."
)


def _client() -> TestClient:
    from app.routers.form_schema import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_data] = lambda: {
        "email": "validation@example.com",
        "selected_role": "validation",
        "allowed_roles": ["validation"],
        "is_platform_admin": False,
    }
    return TestClient(app)


def _stub_pg() -> Any:
    client = MagicMock()
    client.run.return_value = []
    client.close.return_value = None
    return client


# ---------------------------------------------------------------------------
# Happy path -- a genuine miss still answers "not taught"
# ---------------------------------------------------------------------------


def test_get_schema_reports_none_for_a_form_never_taught() -> None:
    with (
        patch("app.routers.form_schema.PatientGraphClient", return_value=_stub_pg()),
        patch("app.routers.form_schema.load_form_schema", return_value=None),
    ):
        resp = _client().get("/form-schemas/fp-1")

    assert resp.status_code == 200
    assert resp.json() == {"schema": None, "match": "none"}


def test_template_route_still_says_save_the_form_first_on_a_real_miss() -> None:
    with (
        patch("app.routers.form_schema.PatientGraphClient", return_value=_stub_pg()),
        patch("app.routers.form_schema.load_form_schema", return_value=None),
    ):
        resp = _client().post("/form-schemas/fp-1/template", json={"text": LETTER})

    assert resp.status_code == 404
    assert "Save the form schema first" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Site 3 callers -- a failed lookup is not an answer about the form
# ---------------------------------------------------------------------------


def test_get_schema_returns_503_when_the_lookup_fails() -> None:
    with (
        patch("app.routers.form_schema.PatientGraphClient", return_value=_stub_pg()),
        patch(
            "app.routers.form_schema.load_form_schema",
            side_effect=_LOOKUP_FAILED,
        ),
    ):
        resp = _client().get("/form-schemas/fp-1")

    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "could not reach the form database" in detail
    assert "Nothing was changed" in detail
    assert detail.isascii()


def test_template_route_returns_503_when_the_lookup_fails() -> None:
    with (
        patch("app.routers.form_schema.PatientGraphClient", return_value=_stub_pg()),
        patch(
            "app.routers.form_schema.load_form_schema",
            side_effect=_LOOKUP_FAILED,
        ),
    ):
        resp = _client().post("/form-schemas/fp-1/template", json={"text": LETTER})

    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "Save the form schema first" not in detail
    assert "could not reach the form database" in detail
