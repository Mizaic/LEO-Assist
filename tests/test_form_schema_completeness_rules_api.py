"""VT: the form-schema API keeps and returns completeness rules.

Opening a saved form must return its rules, and a save must keep the
fields that tie a rule to the taught form and to its evidence.

Atlas trace: VT-BFDEDB18, DI-9BF69EC9, DO-F120628C, R-A3BD3AC7
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.deps import get_session_data  # noqa: E402
from app.routers.form_schema import router  # noqa: E402
from libs.llm_client.form_detection import FormDetection  # noqa: E402
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection  # noqa: E402

BLOOD_RULE = {
    "name": "Blood results",
    "kind": "mandatory",
    "required": True,
    "semantic_categories": [],
    "concept_ids": [],
    "section_id": "bloods",
    "item_pattern": "",
    "evidence": "Blood results are mandatory",
    "needs_review": False,
}

SYMPTOM_RULE = {
    "name": "At least one symptom",
    "kind": "one_of",
    "required": True,
    "semantic_categories": [],
    "concept_ids": [],
    "evidence": "tick at least one",
    "needs_review": True,
    "members": [
        {
            "name": "Rectal bleeding",
            "kind": "optional",
            "section_id": "symptoms",
            "item_pattern": "Rectal bleeding",
        }
    ],
}


@pytest.fixture(autouse=True)
def _pass_teach_check():
    with patch("app.routers.form_schema.check_new_form", return_value=None):
        yield


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


def _schema(groups: list[dict]) -> FormSchema:
    return FormSchema(
        schema_id="s1",
        fingerprint="fp-1",
        form_name="Lower GI",
        sections=[
            FormSection(
                section_id="bloods",
                section_type="free_text",
                label="Blood results",
                start_pattern="Blood results",
                items=[],
            )
        ],
        created_by="validation@example.com",
        completeness_groups=groups,
    )


_DETECT_LETTER = "| Blood results |\n| Blood results are mandatory |\n"


@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
@patch("app.routers.form_schema.detect_form_schema")
def test_detect_response_carries_proposed_rules(mock_detect, mock_pg):
    mock_pg.return_value.run.return_value = []
    mock_detect.return_value = FormDetection(
        sections=[
            {
                "section_id": "bloods",
                "label": "Blood results",
                "section_type": "free_text",
                "start_pattern": "Blood results",
                "items": [],
                "default_semantic_tags": ["finding"],
            }
        ],
        completeness_rules=[
            {
                "name": "Blood results",
                "kind": "mandatory",
                "targets": [{"section_id": "bloods", "item_pattern": ""}],
                "min_count": 1,
                "evidence": "Blood results are mandatory",
            }
        ],
    )
    resp = _client().post("/form-schemas/detect", json={"text": _DETECT_LETTER})
    assert resp.status_code == 200
    (group,) = resp.json()["completeness_groups"]
    assert group["kind"] == "mandatory"
    assert group["section_id"] == "bloods"
    assert group["needs_review"] is False


@patch("app.routers.form_schema.load_form_schema")
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_opening_a_saved_form_returns_its_rules(_mock_pg, mock_load):
    mock_load.return_value = _schema([BLOOD_RULE])
    resp = _client().get("/form-schemas/fp-1")
    assert resp.status_code == 200
    assert resp.json()["schema"]["completeness_groups"] == [BLOOD_RULE]


@patch("app.routers.form_schema.save_form_schema")
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_save_keeps_section_item_evidence_and_review_mark(_mock_pg, mock_save):
    mock_save.return_value = _schema([])
    body = {
        "form_name": "Lower GI",
        "sections": [
            {
                "section_id": "bloods",
                "section_type": "free_text",
                "label": "Blood results",
                "start_pattern": "Blood results",
                "items": [],
            }
        ],
        "completeness_groups": [BLOOD_RULE, SYMPTOM_RULE],
    }
    resp = _client().put("/form-schemas/fp-1", json=body)
    assert resp.status_code == 200
    blood, symptom = mock_save.call_args.args[1].completeness_groups
    assert blood["section_id"] == "bloods"
    assert blood["evidence"] == "Blood results are mandatory"
    assert blood["needs_review"] is False
    assert symptom["needs_review"] is True
    assert symptom["members"][0]["section_id"] == "symptoms"
    assert symptom["members"][0]["item_pattern"] == "Rectal bleeding"
