"""Load a golden case keyed by organisation, service and form version.

Atlas trace:
  DI: DI-9A75B3C6
  DO: DO-E9A3C122
  VT: VT-C73DA421
  Risk: R-238CAF49
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REQUIRED = ("organization_id", "service_id", "form_version")


class GoldenCaseError(ValueError):
    """The golden case is missing a required field or file."""


@dataclass(frozen=True)
class ExpectedFact:
    text: str
    assertion: str
    evidence_text: str = ""


@dataclass(frozen=True)
class CompletenessExpect:
    assessable: bool
    complete: bool | None = None


@dataclass(frozen=True)
class SbarExpect:
    headline_must_contain: tuple[str, ...] = ()
    headline_must_not_contain: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoldenCase:
    organization_id: str
    service_id: str
    form_version: str
    letter: str
    form_schema_path: Path
    expected_facts: tuple[ExpectedFact, ...]
    completeness: CompletenessExpect
    fired_rules: tuple[str, ...]
    sbar: SbarExpect
    path: Path


def load_golden_case(path: Path) -> GoldenCase:
    """Load case.json plus the de-identified letter from a case folder."""
    dest = Path(path)
    if dest.is_file():
        dest = dest.parent
    payload = _read_case(dest)
    _require_keys(payload)
    letter = _load_letter(dest, payload)
    return GoldenCase(
        organization_id=str(payload["organization_id"]).strip(),
        service_id=str(payload["service_id"]).strip(),
        form_version=str(payload["form_version"]).strip(),
        letter=letter,
        form_schema_path=_resolve(dest, payload.get("form_schema_path")),
        expected_facts=_facts(payload.get("expected_facts")),
        completeness=_completeness(payload.get("completeness")),
        fired_rules=tuple(str(item) for item in payload.get("fired_rules") or []),
        sbar=_sbar(payload.get("sbar")),
        path=dest,
    )


def _read_case(dest: Path) -> dict[str, Any]:
    case_path = dest / "case.json"
    if not case_path.is_file():
        raise GoldenCaseError(f"missing case.json: {dest}")
    raw = json.loads(case_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise GoldenCaseError("case.json must be an object")
    return raw


def _require_keys(payload: dict[str, Any]) -> None:
    missing = [key for key in _REQUIRED if not str(payload.get(key) or "").strip()]
    if missing:
        raise GoldenCaseError("missing " + ", ".join(missing))


def _load_letter(dest: Path, payload: dict[str, Any]) -> str:
    inline = str(payload.get("letter") or "")
    if inline.strip():
        return inline
    letter_path = dest / str(payload.get("letter_path") or "letter.md")
    if not letter_path.is_file():
        raise GoldenCaseError(f"missing letter: {letter_path}")
    return letter_path.read_text(encoding="utf-8")


def _resolve(dest: Path, raw: Any) -> Path:
    name = str(raw or "form_schema.json")
    path = Path(name)
    if not path.is_absolute():
        path = dest / path
    return path


def _facts(raw: Any) -> tuple[ExpectedFact, ...]:
    rows = raw if isinstance(raw, list) else []
    return tuple(
        ExpectedFact(
            text=str(item.get("text") or "").strip(),
            assertion=str(item.get("assertion") or "").strip(),
            evidence_text=str(item.get("evidence_text") or "").strip(),
        )
        for item in rows
        if isinstance(item, dict)
    )


def _completeness(raw: Any) -> CompletenessExpect:
    data = raw if isinstance(raw, dict) else {}
    complete = data.get("complete")
    return CompletenessExpect(
        assessable=bool(data.get("assessable")),
        complete=None if complete is None else bool(complete),
    )


def _sbar(raw: Any) -> SbarExpect:
    data = raw if isinstance(raw, dict) else {}
    return SbarExpect(
        headline_must_contain=_string_tuple(data.get("headline_must_contain")),
        headline_must_not_contain=_string_tuple(data.get("headline_must_not_contain")),
    )


def _string_tuple(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw if str(item).strip())
