"""VT: OAuth callback must not issue a session for users with no LEO roles."""

from __future__ import annotations

from libs.auth.session_access import may_issue_session


def test_platform_admin_may_receive_session_without_roles() -> None:
    assert may_issue_session(True, []) is True


def test_non_admin_with_roles_may_receive_session() -> None:
    assert may_issue_session(False, ["triage_clinician"]) is True


def test_non_admin_without_roles_must_not_receive_session() -> None:
    assert may_issue_session(False, []) is False
