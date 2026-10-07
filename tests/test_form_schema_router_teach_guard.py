"""PUT /form-schemas/{fingerprint} runs the teach-time clash check.

An active form is only saved once it has passed the check. A refusal,
an unavailable check and a failed lookup all leave nothing saved. A
draft save skips the check, because a draft is never used to recognise
a letter.

Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
Risk R-B88CCFD6.
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

from app.deps import get_session_data  # noqa: E402
from app.routers.form_schema import router  # noqa: E402
from libs.pipeline.form_schema_normalizer import FormSchema  # noqa: E402
from libs.pipeline.form_schema_store import FormSchemaLookupError  # noqa: E402
from libs.pipeline.form_teach_guard import (  # noqa: E402
    TeachCheckRequest,
    TeachCheckUnavailable,
    TeachRefused,
)

_ROUTER = "app.routers.form_schema"
_LETTER = "Section A: Cancer type suspected. Ovary [ ] Cervix [X]."
_BODY = {
    "form_name": "Gynae 2WW",
    "organization_id": "RK5",
    "source_text": _LETTER,
    "sections": [
        {
            "section_id": "A",
            "section_type": "checkbox_single",
            "label": "Cancer type",
            "start_pattern": "Section A",
            "items": [{"pattern": "Cervix", "entity_text": "Cervical cancer"}],
        }
    ],
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_data] = lambda: {
        "email": "validation@example.com",
        "selected_role": "validation",
        "allowed_roles": ["validation"],
        "is_platform_admin": False,
    }
    return TestClient(app)


def _saved() -> FormSchema:
    return FormSchema(
        schema_id="s1",
        fingerprint="fp-1",
        form_name="Gynae 2WW",
        sections=[],
        created_by="validation@example.com",
    )


def _put(guard: MagicMock, body: dict | None = None):
    with (
        patch(f"{_ROUTER}.PatientGraphClient", return_value=MagicMock()),
        patch(f"{_ROUTER}.check_new_form", guard),
        patch(f"{_ROUTER}.save_form_schema", return_value=_saved()) as save,
    ):
        resp = _client().put("/form-schemas/fp-1", json=body or _BODY)
    return resp, save


def test_an_active_save_runs_the_check_with_the_letter_and_org() -> None:
    guard = MagicMock(return_value=None)
    resp, save = _put(guard)
    assert resp.status_code == 200, resp.text
    (req,) = [c.args[1] for c in guard.call_args_list]
    assert isinstance(req, TeachCheckRequest)
    assert req.source_text == _LETTER
    assert req.organization_id == "RK5"
    assert req.schema.fingerprint == "fp-1"
    assert [s.section_id for s in req.schema.sections] == ["A"]
    save.assert_called_once()


def test_a_refused_form_is_not_saved_and_says_why() -> None:
    guard = MagicMock(side_effect=TeachRefused("Too like X. Nothing was saved."))
    resp, save = _put(guard)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Too like X. Nothing was saved."
    save.assert_not_called()


def test_an_unavailable_check_is_not_a_pass() -> None:
    guard = MagicMock(side_effect=TeachCheckUnavailable("We could not run it."))
    resp, save = _put(guard)
    assert resp.status_code == 503
    assert "nothing was saved" in resp.json()["detail"].lower()
    save.assert_not_called()


def test_a_failed_candidate_lookup_is_not_a_pass() -> None:
    guard = MagicMock(side_effect=FormSchemaLookupError("neo4j down"))
    resp, save = _put(guard)
    assert resp.status_code == 503
    assert "form database" in resp.json()["detail"]
    assert "neo4j" not in resp.json()["detail"]
    save.assert_not_called()


def test_a_draft_save_skips_the_check() -> None:
    guard = MagicMock(side_effect=AssertionError("should not run"))
    resp, save = _put(guard, {**_BODY, "status": "draft"})
    assert resp.status_code == 200, resp.text
    guard.assert_not_called()
    save.assert_called_once()


def test_an_active_save_without_the_letter_is_refused() -> None:
    body = {k: v for k, v in _BODY.items() if k != "source_text"}
    with (
        patch(f"{_ROUTER}.PatientGraphClient", return_value=MagicMock()),
        patch(f"{_ROUTER}.save_form_schema", return_value=_saved()) as save,
    ):
        resp = _client().put("/form-schemas/fp-1", json=body)
    assert resp.status_code == 422
    assert "letter" in resp.json()["detail"]
    save.assert_not_called()
