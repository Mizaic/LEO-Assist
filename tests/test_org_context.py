"""Tests for the org context endpoint (analytics_api/auth/org-context).

Verifies Practitioner lookup, platform-admin all-org access,
and standard user WORKS_AT scoping.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock, call

import pytest


class TestGetOrgContext:

    @patch("services.analytics_api.app.routers.org_context.PatientGraphClient")
    def test_platform_admin_sees_all_orgs(self, MockPG):
        from services.analytics_api.app.routers.org_context import get_org_context

        instance = MockPG.return_value
        instance.run.side_effect = [
            [{"id": "pr-1", "name": "Rob Smith", "email": "rob@test.ai", "is_platform_admin": True}],
            [
                {"id": "org-1", "name": "Practice A", "odsCode": "A001", "short_name": None, "type": "GP"},
                {"id": "org-2", "name": "Practice B", "odsCode": "B002", "short_name": None, "type": "GP"},
            ],
        ]

        result = get_org_context(email="rob@test.ai")

        assert result["user"]["is_platform_admin"] is True
        assert len(result["organizations"]) == 2
        assert result["organizations"][0]["id"] == "org-1"
        assert result["organizations"][1]["name"] == "Practice B"

        all_org_query = instance.run.call_args_list[1][0][0]
        assert "GPPractice" in all_org_query or "Organization" in all_org_query
        assert "labels(o)" in all_org_query
        assert "WORKS_AT" not in all_org_query

    @patch("services.analytics_api.app.routers.org_context.PatientGraphClient")
    def test_standard_user_sees_only_linked_orgs(self, MockPG):
        from services.analytics_api.app.routers.org_context import get_org_context

        instance = MockPG.return_value
        instance.run.side_effect = [
            [{"id": "pr-2", "name": "Ben Noble", "email": "ben@nhs.net", "is_platform_admin": False}],
            [
                {"id": "org-3", "name": "WOODBROOK MEDICAL CENTRE", "odsCode": "C82070", "short_name": None, "type": "GP"},
            ],
        ]

        result = get_org_context(email="ben@nhs.net")

        assert result["user"]["is_platform_admin"] is False
        assert len(result["organizations"]) == 1
        assert result["organizations"][0]["name"] == "WOODBROOK MEDICAL CENTRE"

        linked_query = instance.run.call_args_list[1][0][0]
        assert "WORKS_AT" in linked_query

    @patch("services.analytics_api.app.routers.org_context.PatientGraphClient")
    def test_unknown_email_returns_404(self, MockPG):
        from fastapi import HTTPException
        from services.analytics_api.app.routers.org_context import get_org_context

        instance = MockPG.return_value
        instance.run.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            get_org_context(email="nobody@unknown.com")

        assert exc_info.value.status_code == 404

    @patch("services.analytics_api.app.routers.org_context.PatientGraphClient")
    def test_email_is_lowered_and_stripped(self, MockPG):
        from services.analytics_api.app.routers.org_context import get_org_context

        instance = MockPG.return_value
        instance.run.side_effect = [
            [{"id": "pr-1", "name": "Test", "email": "test@example.com", "is_platform_admin": False}],
            [],
        ]

        get_org_context(email="  Test@Example.COM  ")

        first_call_kwargs = instance.run.call_args_list[0][1]
        assert first_call_kwargs["email"] == "test@example.com"

    @patch("services.analytics_api.app.routers.org_context.PatientGraphClient")
    def test_client_is_always_closed(self, MockPG):
        from services.analytics_api.app.routers.org_context import get_org_context

        instance = MockPG.return_value
        instance.run.side_effect = [
            [{"id": "pr-1", "name": "Test", "email": "t@t.com", "is_platform_admin": True}],
            [],
        ]

        get_org_context(email="t@t.com")
        instance.close.assert_called_once()

    @patch("services.analytics_api.app.routers.org_context.PatientGraphClient")
    def test_client_closed_on_error(self, MockPG):
        from fastapi import HTTPException
        from services.analytics_api.app.routers.org_context import get_org_context

        instance = MockPG.return_value
        instance.run.return_value = []

        with pytest.raises(HTTPException):
            get_org_context(email="fail@test.com")

        instance.close.assert_called_once()

    @patch("services.analytics_api.app.routers.org_context.PatientGraphClient")
    def test_response_shape(self, MockPG):
        from services.analytics_api.app.routers.org_context import get_org_context

        instance = MockPG.return_value
        instance.run.side_effect = [
            [{"id": "pr-1", "name": "Test", "email": "t@t.com", "is_platform_admin": False}],
            [{"id": "o1", "name": "Org One", "odsCode": "X1", "short_name": "O1", "type": "GP"}],
        ]

        result = get_org_context(email="t@t.com")

        assert "user" in result
        assert "organizations" in result
        user = result["user"]
        assert set(user.keys()) == {"id", "name", "email", "is_platform_admin"}

        org = result["organizations"][0]
        assert set(org.keys()) == {"id", "name", "odsCode", "shortName", "type", "scopeType"}
