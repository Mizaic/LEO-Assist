"""Auth and contract tests for the form-schema teaching router.

Reviewers teach forms from extraction review. Detect / load / save use
require_role for the operations quality-review set -- not platform admin
only, and not any authenticated session.

Atlas trace: DI-5C9CA57B, DO-D0C19842
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.deps import get_caller_scope_from_request, get_session_data, require_admin
from app.routers.form_schema import (
    FORM_TEACHER_ROLES,
    detect_schema,
    get_schema,
    require_form_teacher,
    save_schema,
)
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection


def _dep_callables(fn):
    deps = []
    for param in inspect.signature(fn).parameters.values():
        default = param.default
        if isinstance(default, type(Depends(lambda: None))):
            deps.append(default.dependency)
    return deps


def _session(role: str, *, platform_admin: bool = False) -> dict:
    return {
        "email": f"{role}@example.com",
        "selected_role": role,
        "allowed_roles": [role],
        "is_platform_admin": platform_admin,
    }


def _client(session: dict) -> TestClient:
    from app.routers.form_schema import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_data] = lambda: session
    return TestClient(app)


def _saved_schema() -> FormSchema:
    return FormSchema(
        schema_id="s1",
        fingerprint="fp-1",
        form_name="Gynae 2WW",
        sections=[
            FormSection(
                section_id="A",
                section_type="checkbox_single",
                label="Cancer type",
                start_pattern="Section A",
                items=[],
            )
        ],
        created_by="validation@example.com",
    )


DETECT_BODY = {"text": "Section A: Cancer type suspected. Ovary [ ] Cervix [X]."}
SAVE_BODY = {
    "form_name": "Gynae 2WW",
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


def test_detect_uses_form_teacher_role_not_open_scope():
    deps = _dep_callables(detect_schema)
    assert require_form_teacher in deps
    assert get_caller_scope_from_request not in deps
    assert require_admin not in deps


def test_get_schema_uses_form_teacher_role_not_open_scope():
    deps = _dep_callables(get_schema)
    assert require_form_teacher in deps
    assert get_caller_scope_from_request not in deps
    assert require_admin not in deps


def test_save_schema_uses_form_teacher_role_not_open_scope():
    deps = _dep_callables(save_schema)
    assert require_form_teacher in deps
    assert get_caller_scope_from_request not in deps
    assert require_admin not in deps


def test_router_source_uses_require_role_not_open_scope():
    src = Path("services/api/app/routers/form_schema.py").read_text()
    assert "require_role" in src
    assert "require_form_teacher" in src
    assert "get_caller_scope_from_request" not in src
    assert "require_admin" not in src


def test_teacher_roles_are_canonical_reviewer_set():
    assert FORM_TEACHER_ROLES == (
        "validation",
        "operations_manager",
        "clinician_admin",
        "administrator",
    )


@patch("app.routers.form_schema.detect_form_sections", return_value=[])
def test_validation_role_can_detect(mock_detect):
    resp = _client(_session("validation")).post(
        "/form-schemas/detect", json=DETECT_BODY
    )
    assert resp.status_code == 200
    assert resp.json() == {"sections": []}
    mock_detect.assert_called_once()


@patch("app.routers.form_schema.save_form_schema", return_value=_saved_schema())
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_operations_manager_can_save(_mock_pg, mock_save):
    resp = _client(_session("operations_manager")).put(
        "/form-schemas/fp-1", json=SAVE_BODY
    )
    assert resp.status_code == 200
    assert resp.json()["saved"] is True
    assert mock_save.call_args.args[1].created_by == "operations_manager@example.com"


@patch("app.routers.form_schema.detect_form_sections", return_value=[])
def test_lms_learner_cannot_detect(_mock_detect):
    resp = _client(_session("lms_learner")).post(
        "/form-schemas/detect", json=DETECT_BODY
    )
    assert resp.status_code == 403


@patch("app.routers.form_schema.save_form_schema", return_value=_saved_schema())
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_lms_learner_cannot_save(_mock_pg, _mock_save):
    resp = _client(_session("lms_learner")).put("/form-schemas/fp-1", json=SAVE_BODY)
    assert resp.status_code == 403


@patch("app.routers.form_schema.detect_form_sections", return_value=[])
def test_platform_admin_can_detect_even_if_selected_role_cannot(_mock_detect):
    resp = _client(_session("lms_learner", platform_admin=True)).post(
        "/form-schemas/detect", json=DETECT_BODY
    )
    assert resp.status_code == 200


@patch("app.routers.form_schema.save_form_schema", return_value=_saved_schema())
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_administrator_role_can_save(_mock_pg, mock_save):
    resp = _client(_session("administrator")).put("/form-schemas/fp-1", json=SAVE_BODY)
    assert resp.status_code == 200
    assert resp.json()["saved"] is True
    mock_save.assert_called_once()


@patch("app.routers.form_schema.save_form_schema", return_value=_saved_schema())
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_save_forwards_organization_service_and_logic_groups(_mock_pg, mock_save):
    body = {
        **SAVE_BODY,
        "organization_id": "org-sfh",
        "service_id": "svc-gynae",
        "completeness_groups": [
            {
                "name": "Section A",
                "kind": "mandatory",
                "concept_ids": [100],
            },
            {
                "name": "Referral criteria",
                "kind": "one_of",
                "members": [
                    {"name": "B1", "concept_ids": [111]},
                    {"name": "B2", "concept_ids": [222]},
                ],
            },
        ],
    }
    resp = _client(_session("validation")).put("/form-schemas/fp-1", json=body)
    assert resp.status_code == 200
    write = mock_save.call_args.args[1]
    assert write.organization_id == "org-sfh"
    assert write.service_id == "svc-gynae"
    assert write.completeness_groups[0]["kind"] == "mandatory"
    assert write.completeness_groups[1]["kind"] == "one_of"


@patch("app.routers.form_schema.save_form_schema", return_value=_saved_schema())
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_save_with_optional_only_completeness_groups(_mock_pg, mock_save):
    body = {
        **SAVE_BODY,
        "organization_id": "org-sfh",
        "service_id": "svc-gynae",
        "completeness_groups": [
            {
                "name": "Optional note",
                "kind": "optional",
                "required": False,
                "semantic_categories": [],
                "concept_ids": [],
            }
        ],
    }
    resp = _client(_session("validation")).put("/form-schemas/fp-1", json=body)
    assert resp.status_code == 200
    mock_save.assert_called_once()


@patch("app.routers.form_schema.save_form_schema", return_value=_saved_schema())
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_save_accepts_extended_section_and_item_fields(_mock_pg, mock_save):
    body = {
        "form_name": "Gynae 2WW",
        "sections": [
            {
                "section_id": "S1",
                "section_type": "ordered_tests",
                "label": "Blood Tests",
                "start_pattern": "Blood Tests",
                "semantic_tags": ["procedure"],
                "items": [
                    {
                        "pattern": "FBC",
                        "entity_text": "Full blood count",
                        "semantic_tag": "procedure",
                        "assertion": "present",
                        "procedure_snomed": "26604007",
                        "procedure_display": "Full blood count",
                        "analytes": [
                            {
                                "label": "Hb",
                                "snomed_code": "1022280009",
                                "display": "Haemoglobin",
                            }
                        ],
                        "value_placeholder": "{{NUMERIC_VALUE}} {{UNIT}}",
                    }
                ],
            }
        ],
    }
    resp = _client(_session("validation")).put("/form-schemas/fp-extended", json=body)
    assert resp.status_code == 200
    write = mock_save.call_args.args[1]
    item = write.sections[0].items[0]
    assert item.procedure_snomed == "26604007"
    assert item.analytes[0]["label"] == "Hb"
    assert item.value_placeholder == "{{NUMERIC_VALUE}} {{UNIT}}"
    assert write.sections[0].semantic_tags == ["procedure"]


@patch("app.routers.form_schema.save_form_schema", return_value=_saved_schema())
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_save_normalizes_empty_start_pattern_from_label(_mock_pg, mock_save):
    body = {
        "form_name": "Gynae 2WW",
        "sections": [
            {
                "section_id": "S1",
                "section_type": "checkbox_single",
                "label": "Section A",
                "start_pattern": "",
                "items": [
                    {"pattern": "Cervix", "entity_text": "Cervical cancer"},
                ],
            }
        ],
    }
    resp = _client(_session("validation")).put("/form-schemas/fp-label", json=body)
    assert resp.status_code == 200
    write = mock_save.call_args.args[1]
    assert write.sections[0].start_pattern == "Section A"


@patch("app.routers.form_schema.save_form_schema", return_value=_saved_schema())
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_save_uses_section_id_when_start_pattern_empty(_mock_pg, mock_save):
    body = {
        "form_name": "Gynae 2WW",
        "sections": [
            {
                "section_id": "S1",
                "section_type": "checkbox_single",
                "label": "",
                "start_pattern": "",
                "items": [
                    {"pattern": "Cervix", "entity_text": "Cervical cancer"},
                ],
            }
        ],
    }
    resp = _client(_session("validation")).put("/form-schemas/fp-section-id", json=body)
    assert resp.status_code == 200
    write = mock_save.call_args.args[1]
    assert write.sections[0].start_pattern == "S1"


def test_save_rejects_when_all_sections_normalize_away():
    from libs.pipeline.form_schema_store import normalize_sections_for_request

    assert normalize_sections_for_request(
        [
            {
                "section_id": "",
                "section_type": "checkbox_single",
                "label": "",
                "start_pattern": "",
                "items": [],
            }
        ]
    ) == []
