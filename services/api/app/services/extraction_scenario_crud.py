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
            phrase: dict[str, str] = {"text": text, "semantic_tag": tag}
        elif isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            tag = str(item.get("semantic_tag", "finding")).strip() or "finding"
            phrase = {"text": text, "semantic_tag": tag}
            concept_id = str(item.get("concept_id") or "").strip()
            preferred_term = str(item.get("preferred_term") or "").strip()
            if concept_id:
                phrase["concept_id"] = concept_id
            if preferred_term:
                phrase["preferred_term"] = preferred_term
        else:
            raise ScenarioValidationError(
                "Each expected phrase must be text or an object."
            )
        if not phrase["text"]:
            raise ScenarioValidationError("Expected phrases cannot be blank.")
        if phrase["semantic_tag"] not in _VALID_SEMANTIC_TAGS:
            raise ScenarioValidationError(
                f"Unsupported semantic tag {phrase['semantic_tag']!r}. "
                f"Use one of: {', '.join(sorted(_VALID_SEMANTIC_TAGS))}."
            )
        key = phrase["text"].casefold()
        if key in seen:
            continue
        seen.add(key)
        normalised.append(phrase)
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


def _clean_string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _normalise_expected_analysis(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    matched_rule_ids = _clean_string_list(raw.get("matched_rule_ids"))
    expect_no_rules = bool(raw.get("expect_no_rules_fired"))
    priority_raw = raw.get("expected_action_priority")
    priority = str(priority_raw).strip() if priority_raw is not None else ""
    reviewer_notes = str(raw.get("reviewer_notes") or "").strip()
    if not matched_rule_ids and not expect_no_rules and not priority and not reviewer_notes:
        return None
    payload: dict[str, Any] = {
        "matched_rule_ids": matched_rule_ids,
        "expect_no_rules_fired": expect_no_rules,
        "expected_action_priority": priority or None,
        "reviewer_notes": reviewer_notes,
    }
    return payload


def _normalise_expected_sbar(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    payload = {
        "situation_md": str(raw.get("situation_md") or "").strip(),
        "background_md": str(raw.get("background_md") or "").strip(),
        "recommendation_md": str(raw.get("recommendation_md") or "").strip(),
        "matched_rule_ids": _clean_string_list(raw.get("matched_rule_ids")),
        "required_phrases": _clean_string_list(raw.get("required_phrases")),
        "banned_phrases": _clean_string_list(raw.get("banned_phrases")),
        "expected_action_priority": (
            str(raw.get("expected_action_priority") or "").strip() or None
        ),
        "reviewer_focus": str(raw.get("reviewer_focus") or "").strip(),
    }
    if not any(
        [
            payload["situation_md"],
            payload["background_md"],
            payload["recommendation_md"],
            payload["matched_rule_ids"],
            payload["required_phrases"],
            payload["banned_phrases"],
            payload["expected_action_priority"],
            payload["reviewer_focus"],
        ]
    ):
        return None
    return payload


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
        "expected_analysis": _normalise_expected_analysis(body.get("expected_analysis")),
        "expected_sbar": _normalise_expected_sbar(body.get("expected_sbar")),
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
        "expected_analysis": json.dumps(payload["expected_analysis"] or {}),
        "expected_sbar": json.dumps(payload["expected_sbar"] or {}),
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
        "expected_analysis": json.dumps(payload["expected_analysis"] or {}),
        "expected_sbar": json.dumps(payload["expected_sbar"] or {}),
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


def delete_scenario(client: Any, case_id: str) -> dict[str, Any]:
    """Delete one ExtractionScenario node."""
    from libs.cypher.extraction_scenario_queries import DELETE_EXTRACTION_SCENARIO

    validate_case_id(case_id)
    rows = client.run(DELETE_EXTRACTION_SCENARIO, case_id=case_id)
    if not rows:
        raise ScenarioValidationError(f"Scenario {case_id!r} not found.")
    return {"case_id": case_id, "deleted": True}
