"""VT: start patterns are the form's printed heading, never letter data.

A date the referrer typed must not become part of a taught heading,
because the next letter has a different date and the section is lost.

Atlas trace: VT-25098971, DI-C1744ED5, DO-1C8E7598, R-98702FED
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
from libs.llm_client.form_schema_detector import (  # noqa: E402
    _SYSTEM_PROMPT,
    _validate_section,
)
from libs.pipeline.form_pattern_dates import contains_date  # noqa: E402
from libs.pipeline.form_pattern_match import section_matches  # noqa: E402

_SECTION = {
    "section_id": "bloods",
    "label": "Blood results",
    "section_type": "free_text",
    "items": [],
    "default_semantic_tags": ["finding"],
}


def test_prompt_says_start_pattern_is_the_printed_heading_only():
    prompt = " ".join(_SYSTEM_PROMPT.split()).lower()
    assert "printed heading only" in prompt
    assert "never a date, name, number or result" in prompt


def test_a_dated_sentence_is_dropped_from_a_detected_start_pattern():
    raw = dict(
        _SECTION,
        start_pattern="Blood results: FBC, U&E, eGFR. Bloods taken 25/6/26",
    )
    assert _validate_section(raw)["start_pattern"] == "Blood results: FBC, U&E, eGFR"


def test_a_start_pattern_with_brackets_matches_its_own_heading():
    pattern = "Radiology: (In last 6 months)"
    assert section_matches(pattern, "| Radiology: (In last 6 months) |  |")
    assert not section_matches(pattern, "| Radiology report attached |")


def test_regex_start_patterns_still_match():
    assert section_matches("(?i)section\\s+a", "| SECTION   A: Cancer type |")


@pytest.mark.parametrize(
    "text",
    ["Bloods taken 25/6/26", "Seen 2026-06-25", "on 25 June 2026", "25.06.2026"],
)
def test_dates_are_found(text):
    assert contains_date(text)


@pytest.mark.parametrize(
    "text",
    ["Radiology: (In last 6 months)", "2WW referral", "Section 2.1", "eGFR"],
)
def test_headings_without_dates_are_not_flagged(text):
    assert not contains_date(text)


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


@patch("app.routers.form_schema.check_new_form", return_value=None)
@patch("app.routers.form_schema.save_form_schema")
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_save_refuses_a_dated_start_pattern_and_names_the_section(
    _mock_pg, mock_save, _mock_check
):
    body = {
        "form_name": "Lower GI",
        "sections": [
            {
                "section_id": "bloods",
                "section_type": "free_text",
                "label": "Blood results",
                "start_pattern": "Blood results. Bloods taken 25/6/26",
                "items": [],
            }
        ],
    }
    resp = _client().put("/form-schemas/fp-1", json=body)
    assert resp.status_code == 422
    assert "Blood results" in resp.json()["detail"]
    assert "date" in resp.json()["detail"].lower()
    mock_save.assert_not_called()
