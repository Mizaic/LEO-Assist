"""Contract tests for GET /form-schemas/blood-panel-presets.

The form teacher loads the standard NHS blood table from this route
instead of hand-typing every battery and analyte.

Atlas trace: DI-5C9CA57B, DI-26546721
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.deps import get_session_data  # noqa: E402
from app.routers.form_schema import (  # noqa: E402
    blood_panel_presets,
    require_form_teacher,
)

PRESET_PATH = "/form-schemas/blood-panel-presets"


def _dep_callables(fn):
    deps = []
    for param in inspect.signature(fn).parameters.values():
        default = param.default
        if isinstance(default, type(Depends(lambda: None))):
            deps.append(default.dependency)
    return deps


def _session(role: str) -> dict:
    return {
        "email": f"{role}@example.com",
        "selected_role": role,
        "allowed_roles": [role],
        "is_platform_admin": False,
    }


def _client(session: dict) -> TestClient:
    from app.routers.form_schema import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_data] = lambda: session
    return TestClient(app)


def test_route_is_guarded_by_the_form_teacher_role():
    assert require_form_teacher in _dep_callables(blood_panel_presets)


def test_validation_role_gets_the_full_preset():
    resp = _client(_session("validation")).get(PRESET_PATH)
    assert resp.status_code == 200
    body = resp.json()
    assert [item["pattern"] for item in body["batteries"]][:4] == [
        "FBC",
        "UE",
        "LFT",
        "CRP",
    ]
    fbc = body["batteries"][0]
    assert fbc["procedure_snomed"] == "26604007"
    assert [a["label"] for a in fbc["analytes"]] == [
        "Hb",
        "WCC",
        "Plts",
        "MCV",
        "Neut",
    ]


def test_response_flags_rows_needing_clinical_review():
    resp = _client(_session("validation")).get(PRESET_PATH)
    assert resp.status_code == 200
    needs_review = resp.json()["needs_clinical_review"]
    assert "Iron" in needs_review
    assert "Bone / Ca cor" in needs_review


def test_learner_role_cannot_read_the_preset():
    resp = _client(_session("lms_learner")).get(PRESET_PATH)
    assert resp.status_code == 403


def test_preset_path_is_not_swallowed_by_the_fingerprint_route():
    """The literal path must be declared before GET /{fingerprint}."""
    src = Path("services/api/app/routers/form_schema.py").read_text()
    preset_at = src.index('"/blood-panel-presets"')
    fingerprint_at = src.index('@router.get("/{fingerprint}")')
    assert preset_at < fingerprint_at
