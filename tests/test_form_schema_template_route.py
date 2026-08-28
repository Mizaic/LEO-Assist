"""POST /form-schemas/{fingerprint}/template must bind Cypher parameters.

``PatientGraphClient.run`` is declared as ``run(self, query, **params)``.
Passing the parameter map as a positional dict raises ``TypeError``, the
route turns that into a 500, and the normalised template is never saved.
This is the same defect already fixed in ``delete_form_schema``.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.deps import get_session_data  # noqa: E402
from libs.cypher.form_schema_queries import SAVE_NORMALISED_TEMPLATE  # noqa: E402
from libs.pipeline.form_schema_normalizer import (  # noqa: E402
    FormSchema,
    FormSection,
)

LETTER = (
    "Section A: Gynaecological Cancer type suspected\n"
    "Ovary [ ] Cervix [X] Endometrium [ ]\n"
    "\n"
    "Section C: Further Clinical details\n"
    "Thank you for seeing this lady with vaginal discharge.\n"
)


class _RecordingClient:
    """Mimics ``PatientGraphClient.run(self, query, **params)`` exactly."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append({"query": query, "params": params})
        return [{"schema_id": "s1"}]

    def close(self) -> None:
        return None


def _schema() -> FormSchema:
    return FormSchema(
        schema_id="s1",
        fingerprint="fp-template",
        form_name="Gynae 2WW",
        sections=[
            FormSection(
                section_id="section_a_cancer_type",
                section_type="checkbox_multi",
                label="Section A",
                start_pattern="Section A",
                items=[],
            ),
            FormSection(
                section_id="section_c_clinical_details",
                section_type="free_text",
                label="Section C",
                start_pattern="Section C",
                items=[],
            ),
        ],
        created_by="test",
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


def _post_template(recorder: _RecordingClient) -> Any:
    with (
        patch("app.routers.form_schema.PatientGraphClient", return_value=recorder),
        patch("app.routers.form_schema.load_form_schema", return_value=_schema()),
    ):
        return _client().post(
            "/form-schemas/fp-template/template", json={"text": LETTER}
        )


def test_template_save_binds_parameters_as_keyword_arguments() -> None:
    recorder = _RecordingClient()
    _post_template(recorder)

    saves = [c for c in recorder.calls if c["query"] == SAVE_NORMALISED_TEMPLATE]
    assert len(saves) == 1, "the normalised template save must run exactly once"
    params = saves[0]["params"]
    assert params["fingerprint"] == "fp-template"
    assert set(params) == {
        "fingerprint",
        "normalised_template",
        "chunk_section_map",
    }


def test_template_route_persists_and_returns_the_template() -> None:
    recorder = _RecordingClient()
    resp = _post_template(recorder)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["normalised_template"].strip()
    assert isinstance(body["chunk_section_map"], list)
