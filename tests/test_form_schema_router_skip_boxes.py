"""Detect and save fill skipped sections with their printed tick boxes.

Detect fills them so the teacher sees them in the editor. Save fills
them again, before the teach check, so edits, borrowed sections and the
offline detect fallback are covered too.

Atlas trace: UN-AF530E8E -> DI-455C4EF1 -> DO-B7A3AF41 -> VT-8E71E0F1.
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
from libs.llm_client.form_detection import FormDetection  # noqa: E402
from libs.pipeline.form_schema_normalizer import FormSchema  # noqa: E402

_ROUTER = "app.routers.form_schema"
_LETTER = (
    Path(__file__).parent / "fixtures" / "form_schema" / "sfh_lower_gi_2ww_deid.md"
).read_text(encoding="utf-8")
_HOSPITAL_BOXES = ["Pt Contacted", "Interpreter Booked", "Transport Booked", "Accepted"]


def _section(sid: str, stype: str, label: str, items: list[str] = ()) -> dict:
    return {
        "section_id": sid,
        "section_type": stype,
        "label": label,
        "start_pattern": label,
        "items": [{"pattern": p, "entity_text": p} for p in items],
    }


def _detected() -> list[dict]:
    return [
        _section("S1", "admin", "SECTION 1 - PATIENT DEMOGRAPHIC DETAILS"),
        _section(
            "S2",
            "checkbox_multi",
            "SECTION 2: Symptoms suggesting colorectal cancer",
            [
                "Change in bowel habit",
                "New onset of abdominal pain",
                "Definite palpable abdominal mass",
                "Unexplained iron deficiency anaemia",
                "New onset of constipation",
                "New onset of Diarrhoea",
                "Significant unexplained weight loss",
                "Rectal mass",
                "Unexplained rectal bleeding",
            ],
        ),
        _section(
            "S3",
            "scale",
            "Performance Status - Clinical Frailty Scale",
            [
                "Very Fit",
                "Managing well",
                "Very Mild",
                "Mild",
                "Moderate",
                "Severe",
                "Very severe",
                "Terminally ill",
            ],
        ),
        _section("S4", "free_text", "SECTION 3 - PAST MEDICAL HISTORY"),
        _section("S5", "admin", "Hospital Use Only"),
    ]


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


def _hospital_items(sections: list) -> list[str]:
    (section,) = [s for s in sections if _sid(s) == "S5"]
    items = section["items"] if isinstance(section, dict) else section.items
    return [i["pattern"] if isinstance(i, dict) else i.pattern for i in items]


def _sid(section: object) -> str:
    if isinstance(section, dict):
        return section["section_id"]
    return section.section_id


def test_detect_returns_admin_sections_with_their_tick_boxes() -> None:
    graph = MagicMock()
    graph.run.return_value = []
    with (
        patch(f"{_ROUTER}.PatientGraphClient", return_value=graph),
        patch(
            f"{_ROUTER}.detect_form_schema",
            return_value=FormDetection(sections=_detected()),
        ),
    ):
        resp = _client().post("/form-schemas/detect", json={"text": _LETTER})
    assert resp.status_code == 200, resp.text
    assert _hospital_items(resp.json()["sections"]) == _HOSPITAL_BOXES


def test_a_heading_only_form_saves_and_carries_the_tick_boxes() -> None:
    graph = MagicMock()
    graph.run.return_value = []
    saved = FormSchema(
        schema_id="s1",
        fingerprint="fp-lgi",
        form_name="Sherwood Lower GI",
        sections=[],
        created_by="validation@example.com",
    )
    body = {
        "form_name": "Sherwood Lower GI",
        "organization_id": "RK5",
        "source_text": _LETTER,
        "sections": _detected(),
    }
    with (
        patch(f"{_ROUTER}.PatientGraphClient", return_value=graph),
        patch(f"{_ROUTER}.save_form_schema", return_value=saved) as save,
    ):
        resp = _client().put("/form-schemas/fp-lgi", json=body)
    assert resp.status_code == 200, resp.text
    write = save.call_args.args[1]
    assert _hospital_items(write.sections) == _HOSPITAL_BOXES
