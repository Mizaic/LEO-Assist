"""Tests for login-time practitioner org context (Patient Graph)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.auth.practitioner_org_context import fetch_practitioner_org_context


@patch("libs.auth.practitioner_org_context.PatientGraphClient")
def test_platform_admin_returns_flag_and_orgs(MockClient: MagicMock) -> None:
    instance = MockClient.return_value
    instance.run.side_effect = [
        [
            {
                "id": "pr-1",
                "name": "Rob",
                "email": "rob@test.ai",
                "is_platform_admin": True,
            }
        ],
        [
            {
                "id": "org-1",
                "name": "Practice A",
                "odsCode": "A001",
                "short_name": None,
                "type": "GP",
                "nodeLabels": ["GPPractice"],
            }
        ],
    ]

    is_admin, orgs = fetch_practitioner_org_context("Rob@Test.AI ")

    assert is_admin is True
    assert len(orgs) == 1
    assert orgs[0]["id"] == "org-1"
    assert orgs[0]["scopeType"] == "gp"
    instance.close.assert_called_once()


@patch("libs.auth.practitioner_org_context.PatientGraphClient")
def test_missing_practitioner_returns_empty(MockClient: MagicMock) -> None:
    instance = MockClient.return_value
    instance.run.return_value = []

    is_admin, orgs = fetch_practitioner_org_context("nobody@x.com")

    assert is_admin is False
    assert orgs == []
    instance.close.assert_called_once()
