"""VT-1215D85D / DI-B00BD595: platform-admin emergency override."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from libs.auth.break_glass import require_second_person

GATE = "phrase_publish"
RESOURCE = "psa"
AUTHOR = "engineer@example.com"
OTHER = "reviewer@example.com"
REASON = "No second reviewer on duty tonight"


def _call(**overrides: object) -> None:
    kwargs = {
        "author": AUTHOR,
        "actor": AUTHOR,
        "is_platform_admin": False,
        "reason": "",
        "gate": GATE,
        "resource_id": RESOURCE,
    }
    kwargs.update(overrides)
    require_second_person(**kwargs)  # type: ignore[arg-type]


def test_same_person_without_reason_is_refused() -> None:
    with pytest.raises(HTTPException) as exc:
        _call()
    assert exc.value.status_code == 403


def test_different_person_needs_no_reason() -> None:
    _call(actor=OTHER, reason="")


def test_admin_same_person_with_reason_writes_audit() -> None:
    with patch("libs.auth.break_glass.emit_break_glass") as audit:
        _call(is_platform_admin=True, reason=REASON)
    audit.assert_called_once()
    payload = audit.call_args.kwargs
    assert payload["email"] == AUTHOR
    assert payload["gate"] == GATE
    assert payload["reason"] == REASON
    assert payload["resource_id"] == RESOURCE
    assert payload["outcome"] == "allowed"


def test_non_admin_same_person_with_reason_is_refused() -> None:
    with pytest.raises(HTTPException) as exc:
        _call(reason=REASON)
    assert exc.value.status_code == 403


def test_admin_short_reason_is_refused() -> None:
    with pytest.raises(HTTPException) as exc:
        _call(is_platform_admin=True, reason="too short")
    assert exc.value.status_code == 403


def test_admin_blank_reason_is_refused() -> None:
    with pytest.raises(HTTPException) as exc:
        _call(is_platform_admin=True, reason="   ")
    assert exc.value.status_code == 403
