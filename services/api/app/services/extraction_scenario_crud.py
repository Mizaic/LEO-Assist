"""Create, update, and delete extraction validation scenarios.

Atlas trace:
  DI: DI-1B3B5375
  DO: DO-416BA91D
  Risk: R-80E8BD96
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

_CASE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
_VALID_SEMANTIC_TAGS = frozenset(
    {
        "finding",
        "disorder",
        "observable_entity",
        "procedure",
        "situation",
        "pharmaceutical",
        "body_structure",
        "social_context",
    }
)


class ScenarioValidationError(ValueError):
    """Raised when scenario payload fails validation."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_case_id(case_id: str) -> None:
    """Validate a scenario case_id slug."""
    if not _CASE_ID_RE.match(case_id.strip()):
        raise ScenarioValidationError(
            "case_id must start with a letter, use lowercase letters, "
            "digits, or underscores only, and be 3-80 characters long."
        )


def _require_text(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ScenarioValidationError(f"{field} is required.")
    return cleaned


def _normalise_phrase_list(raw: list[Any]) -> list[dict[str, str]]:
    if not raw:
        raise ScenarioValidationError("At least one expected phrase is required.")
    normalised: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            tag = "finding"
        elif isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            tag = str(item.get("semantic_tag", "finding")).strip() or "finding"
        else:
            raise ScenarioValidationError("Each expected phrase must be text or an object.")
        if not text:
            raise ScenarioValidationError("Expected phrases cannot be blank.")
        if tag not in _VALID_SEMANTIC_TAGS:
            raise ScenarioValidationError(
                f"Unsupported semantic tag {tag!r}. "
                f"Use one of: {', '.join(sorted(_VALID_SEMANTIC_TAGS))}."
            )
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalised.append({"text": text, "semantic_tag": tag})
    if not normalised:
        raise ScenarioValidationError("At least one expected phrase is required.")
    return normalised


def _normalise_string_list(raw: list[Any] | None) -> list[str]:
    if not raw:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else [])


def validate_write_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise a create/update payload."""
    site = _require_text(str(body.get("site", "")), "site")
    fmt = _require_text(str(body.get("format", "")), "format")
    markdown_body = _require_text(str(body.get("markdown_body", "")), "markdown_body")
    expected_strings = _normalise_phrase_list(list(body.get("expected_strings") or []))
    must_not_extract = _normalise_string_list(body.get("must_not_extract"))
    phrase_classes = _normalise_string_list(body.get("phrase_classes"))
    difficulty = _normalise_string_list(body.get("difficulty"))
    notes = body.get("notes_for_clinician_review")
    notes_text = str(notes).strip() if notes is not None else ""
    return {
        "site": site,
        "format": fmt,
        "markdown_body": markdown_body,
        "expected_strings": expected_strings,
        "must_not_extract": must_not_extract,
        "phrase_classes": phrase_classes,
        "difficulty": difficulty,
        "notes_for_clinician_review": notes_text or None,
        "expected_observables": body.get("expected_observables") or [],
        "synthetic_patient": body.get("synthetic_patient") or {},
        "blood_results": body.get("blood_results") or [],
        "source_template_markdown": body.get("source_template_markdown") or "",
    }


def scenario_exists(client: Any, case_id: str) -> bool:
    from libs.cypher.extraction_scenario_queries import GET_EXTRACTION_SCENARIO_EXISTS

    rows = client.run(GET_EXTRACTION_SCENARIO_EXISTS, case_id=case_id)
    return bool(rows)


def create_scenario(client: Any, case_id: str, body: dict[str, Any]) -> dict[str, str]:
    """Create a new ExtractionScenario node."""
    from libs.cypher.extraction_scenario_queries import CREATE_EXTRACTION_SCENARIO

    validate_case_id(case_id)
    if scenario_exists(client, case_id):
        raise ScenarioValidationError(f"Scenario {case_id!r} already exists.")
    payload = validate_write_payload(body)
    now = _now_iso()
    params = {
        "case_id": case_id,
        **payload,
        "expected_strings": _json_dump(payload["expected_strings"]),
        "expected_observables": _json_dump(payload["expected_observables"]),
        "must_not_extract": _json_dump(payload["must_not_extract"]),
        "phrase_classes": _json_dump(payload["phrase_classes"]),
        "difficulty": _json_dump(payload["difficulty"]),
        "synthetic_patient": _json_dump(payload["synthetic_patient"]),
        "blood_results": _json_dump(payload["blood_results"]),
        "review_status": "draft_for_clinician_approval",
        "schema_version": int(body.get("schema_version") or 1),
        "source": "ui",
        "created_at": now,
    }
    rows = client.run(CREATE_EXTRACTION_SCENARIO, **params)
    if not rows:
        raise ScenarioValidationError("Could not create scenario.")
    return {"case_id": case_id, "review_status": "draft_for_clinician_approval"}


def update_scenario(client: Any, case_id: str, body: dict[str, Any]) -> dict[str, str]:
    """Replace editable fields on an existing scenario."""
    from libs.cypher.extraction_scenario_queries import UPDATE_EXTRACTION_SCENARIO

    validate_case_id(case_id)
    if not scenario_exists(client, case_id):
        raise ScenarioValidationError(f"Scenario {case_id!r} not found.")
    payload = validate_write_payload(body)
    params = {
        "case_id": case_id,
        **payload,
        "expected_strings": _json_dump(payload["expected_strings"]),
        "expected_observables": _json_dump(payload["expected_observables"]),
        "must_not_extract": _json_dump(payload["must_not_extract"]),
        "phrase_classes": _json_dump(payload["phrase_classes"]),
        "difficulty": _json_dump(payload["difficulty"]),
        "synthetic_patient": _json_dump(payload["synthetic_patient"]),
        "blood_results": _json_dump(payload["blood_results"]),
        "updated_at": _now_iso(),
    }
    rows = client.run(UPDATE_EXTRACTION_SCENARIO, **params)
    if not rows:
        raise ScenarioValidationError(f"Scenario {case_id!r} not found.")
    return {
        "case_id": case_id,
        "review_status": "draft_for_clinician_approval",
    }


def delete_scenario(client: Any, case_id: str) -> dict[str, str]:
    """Delete one ExtractionScenario node."""
    from libs.cypher.extraction_scenario_queries import DELETE_EXTRACTION_SCENARIO

    validate_case_id(case_id)
    rows = client.run(DELETE_EXTRACTION_SCENARIO, case_id=case_id)
    if not rows:
        raise ScenarioValidationError(f"Scenario {case_id!r} not found.")
    return {"case_id": case_id, "deleted": True}
