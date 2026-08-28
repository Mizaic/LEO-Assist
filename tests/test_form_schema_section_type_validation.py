"""section_type must never hold a value the normaliser cannot dispatch on.

``_process_section_lines`` dispatches on ``section_type``. A value that is
not in the ``SectionType`` vocabulary falls through to a bare pass-through,
so the deterministic checkbox control silently does nothing and unticked
criteria reach the LLM as plain text. That is the false-positive hazard
R-687E8027 is accepted against, so an unrecognised value must be stopped
at the write boundary rather than stored.

Atlas trace: DI-5C9CA57B, DO-D0C19842
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, get_args
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from app.deps import get_session_data  # noqa: E402
from libs.llm_client.form_schema_detector import _validate_section  # noqa: E402
from libs.pipeline.form_schema_normalizer import SectionType  # noqa: E402
from libs.pipeline.form_schema_request import (  # noqa: E402
    build_sections_from_request,
    dict_to_section,
)
from libs.pipeline.form_schema_section_types import (  # noqa: E402
    SAFE_SECTION_TYPE,
    VALID_SECTION_TYPES,
    coerce_section_type,
    is_valid_section_type,
    validate_section_type,
)
from libs.pipeline.form_schema_store import (  # noqa: E402
    load_form_schema,
    reset_schema_cache,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures/form_schema/sfh_gynae_2ww_template.json"
)


def _section(section_type: str) -> dict[str, Any]:
    return {
        "section_id": "section_a_cancer_type",
        "section_type": section_type,
        "label": "Section A",
        "start_pattern": "Section A",
        "items": [{"pattern": "Cervix", "entity_text": "Suspected cervical cancer"}],
    }


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------


def test_valid_section_types_come_from_the_normaliser_vocabulary() -> None:
    """The list is derived, not copied, so the two can never drift."""
    assert VALID_SECTION_TYPES == frozenset(get_args(SectionType))


def test_checkbox_is_not_a_recognised_section_type() -> None:
    assert not is_valid_section_type("checkbox")
    assert "checkbox" not in VALID_SECTION_TYPES


def test_every_recognised_type_validates() -> None:
    for value in VALID_SECTION_TYPES:
        assert validate_section_type(value) == value


def test_validate_raises_a_plain_english_error_naming_the_bad_value() -> None:
    with pytest.raises(ValueError) as exc:
        validate_section_type("checkbox")
    message = str(exc.value)
    assert "checkbox" in message
    assert "checkbox_multi" in message


# ---------------------------------------------------------------------------
# Write boundary 1 -- request and record conversion
# ---------------------------------------------------------------------------


def test_dict_to_section_rejects_an_unrecognised_section_type() -> None:
    with pytest.raises(ValueError):
        dict_to_section(_section("checkbox"))


def test_dict_to_section_accepts_every_recognised_section_type() -> None:
    for value in VALID_SECTION_TYPES:
        assert dict_to_section(_section(value)).section_type == value


def test_build_sections_from_request_rejects_an_unrecognised_type() -> None:
    with pytest.raises(ValueError):
        build_sections_from_request([_section("checkbox")])


# ---------------------------------------------------------------------------
# Write boundary 2 -- the API
# ---------------------------------------------------------------------------


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


@patch("app.routers.form_schema.save_form_schema")
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_api_rejects_checkbox_and_never_saves(_mock_pg, mock_save) -> None:
    resp = _client().put(
        "/form-schemas/fp-1",
        json={"form_name": "Gynae 2WW", "sections": [_section("checkbox")]},
    )
    assert resp.status_code == 422, resp.text
    assert "checkbox_multi" in resp.text
    mock_save.assert_not_called()


@patch("app.routers.form_schema.save_form_schema")
@patch("app.routers.form_schema.PatientGraphClient", return_value=MagicMock())
def test_api_accepts_a_recognised_type(_mock_pg, mock_save) -> None:
    resp = _client().put(
        "/form-schemas/fp-1",
        json={"form_name": "Gynae 2WW", "sections": [_section("checkbox_multi")]},
    )
    assert resp.status_code == 200, resp.text
    mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# Read boundary -- an unusable schema must not be trusted
# ---------------------------------------------------------------------------


def _stub_client(section_type: str) -> MagicMock:
    client = MagicMock()
    client.run.return_value = [
        {
            "schema_id": "s1",
            "fingerprint": "fp-legacy",
            "form_name": "Gynae 2WW",
            "sections_json": json.dumps([_section(section_type)]),
            "created_by": "seed",
            "status": "active",
        }
    ]
    return client


def test_a_stored_schema_with_an_unrecognised_type_is_not_returned() -> None:
    """Fail closed: the generic checkbox control takes over instead."""
    reset_schema_cache()
    assert load_form_schema(_stub_client("checkbox"), "fp-legacy") is None


def test_a_stored_schema_with_recognised_types_still_loads() -> None:
    reset_schema_cache()
    schema = load_form_schema(_stub_client("checkbox_multi"), "fp-legacy")
    assert schema is not None
    assert schema.sections[0].section_type == "checkbox_multi"


# ---------------------------------------------------------------------------
# Write boundary 3 -- the LLM detector proposes, the clinician reviews
# ---------------------------------------------------------------------------


def test_detector_coerces_checkbox_to_a_recognised_type() -> None:
    out = _validate_section(_section("checkbox"))
    assert out["section_type"] == "checkbox_multi"


def test_detector_coerces_an_unknown_type_to_the_safe_default() -> None:
    out = _validate_section(_section("wingdings"))
    assert out["section_type"] == SAFE_SECTION_TYPE


def test_detector_leaves_a_recognised_type_alone() -> None:
    out = _validate_section(_section("checkbox_yesno"))
    assert out["section_type"] == "checkbox_yesno"


def test_coerce_never_returns_an_unrecognised_value() -> None:
    for value in ("checkbox", "wingdings", "", None, 7):
        assert coerce_section_type(value, source="test") in VALID_SECTION_TYPES


# ---------------------------------------------------------------------------
# Write boundary 4 -- the seeded production template
# ---------------------------------------------------------------------------


def test_seed_fixture_has_only_recognised_section_types() -> None:
    with open(FIXTURE_PATH, encoding="ascii") as fh:
        template = json.load(fh)
    bad = {
        s["section_id"]: s["section_type"]
        for s in template["sections"]
        if not is_valid_section_type(s["section_type"])
    }
    assert not bad, f"fixture holds unrecognised section types: {bad}"


def test_the_ui_vocabulary_matches_the_python_vocabulary() -> None:
    """A fourth write boundary: the teach dialog PUTs sections back."""
    src = (
        Path(__file__).parent.parent
        / "services/ui/src/components/operations/formSchemaDetector.ts"
    ).read_text(encoding="utf-8")
    block = src.split("export const SECTION_TYPES = [", 1)[1].split("]", 1)[0]
    listed = set(re.findall(r'"([a-z_]+)"', block))
    assert listed == set(VALID_SECTION_TYPES)


def test_seed_script_builds_only_recognised_section_types() -> None:
    from seed_sfh_gynae_2ww_template import _built_template

    bad = {
        s["section_id"]: s["section_type"]
        for s in _built_template()["sections"]
        if not is_valid_section_type(s["section_type"])
    }
    assert not bad, f"seed script builds unrecognised section types: {bad}"
