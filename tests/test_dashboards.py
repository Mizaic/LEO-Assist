"""Tests for services/analytics_api/app/routers/dashboards.py.

Verifies org filtering uses (Patient)-[:REGISTERED_AT]->(Organization)
graph traversal rather than denormalized tenantId properties.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestEpisodeSummary:

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_returns_aggregation(self, MockPG):
        from services.analytics_api.app.routers.dashboards import episode_summary

        MockPG.return_value.run.return_value = [
            {"cancer_type": "breast", "status": "confirmed", "count": 15},
            {"cancer_type": "lung", "status": "pending", "count": 7},
        ]

        result = episode_summary(org_id=None)
        assert len(result) == 2
        assert result[0]["cancer_type"] == "breast"
        MockPG.return_value.close.assert_called_once()

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_with_org_filter_uses_registered_at(self, MockPG):
        from services.analytics_api.app.routers.dashboards import episode_summary

        MockPG.return_value.run.return_value = [
            {"cancer_type": "skin", "status": "pending", "count": 3},
        ]

        result = episode_summary(org_id="org-123")
        assert len(result) == 1

        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" in query
        assert "Organization" in query
        assert "tenantId" not in query
        assert MockPG.return_value.run.call_args[1]["org"] == "org-123"

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_no_org_filter_queries_all(self, MockPG):
        from services.analytics_api.app.routers.dashboards import episode_summary

        MockPG.return_value.run.return_value = []

        episode_summary(org_id=None)
        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" not in query
        assert "MATCH (ep:CancerEpisode)" in query


class TestEpisodeTimeline:

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_patient_timeline_uses_has_episode(self, MockPG):
        from services.analytics_api.app.routers.dashboards import episode_timeline

        MockPG.return_value.run.return_value = [
            {
                "episode_id": "ep-1",
                "cancer_type": "breast",
                "status": "confirmed",
                "milestones": [
                    {"encounter_id": "e1", "date": "2024-01-15", "milestone": "referral"},
                ],
            },
        ]

        result = episode_timeline(patient_id="P1", org_id=None)
        assert len(result) == 1
        assert result[0]["episode_id"] == "ep-1"

        query = MockPG.return_value.run.call_args[0][0]
        assert "HAS_EPISODE" in query

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_org_timeline_uses_registered_at(self, MockPG):
        from services.analytics_api.app.routers.dashboards import episode_timeline

        MockPG.return_value.run.return_value = [
            {"episode_id": "ep-1", "patient_id": "P1", "cancer_type": "lung", "status": "pending", "referral_date": "2024-03-01"},
        ]

        result = episode_timeline(patient_id=None, org_id="org-1")
        assert len(result) == 1

        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" in query
        assert "Organization" in query
        assert "tenantId" not in query

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_no_filter_timeline(self, MockPG):
        from services.analytics_api.app.routers.dashboards import episode_timeline

        MockPG.return_value.run.return_value = []

        episode_timeline(patient_id=None, org_id=None)
        query = MockPG.return_value.run.call_args[0][0]
        assert "HAS_EPISODE" in query
        assert "REGISTERED_AT" not in query


class TestCSSAlerts:

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_returns_alerts(self, MockPG):
        from services.analytics_api.app.routers.dashboards import css_alerts

        MockPG.return_value.run.return_value = [
            {"episode_id": "ep-1", "type": "missing_safety_netting", "severity": "warning", "description": "No safety-netting found"},
        ]

        result = css_alerts(org_id=None)
        assert len(result) == 1
        assert result[0]["type"] == "missing_safety_netting"
        MockPG.return_value.close.assert_called_once()

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_empty_alerts(self, MockPG):
        from services.analytics_api.app.routers.dashboards import css_alerts

        MockPG.return_value.run.return_value = []
        result = css_alerts(org_id=None)
        assert result == []

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_org_filter_uses_registered_at(self, MockPG):
        from services.analytics_api.app.routers.dashboards import css_alerts

        MockPG.return_value.run.return_value = []

        css_alerts(org_id="org-x")
        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" in query
        assert "Organization" in query
        assert "tenantId" not in query

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_no_org_filter_omits_org_match(self, MockPG):
        from services.analytics_api.app.routers.dashboards import css_alerts

        MockPG.return_value.run.return_value = []

        css_alerts(org_id=None)
        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" not in query
        assert "HAS_CSS_ALERT" in query


class TestActionCSSAlert:

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_marks_alert_actioned(self, MockPG):
        from services.analytics_api.app.routers.dashboards import (
            action_css_alert,
            ActionAlertRequest,
        )

        MockPG.return_value.run.return_value = [{"id": "alert-1"}]

        result = action_css_alert("alert-1", ActionAlertRequest(actioned=True))
        assert result == {"success": True}

        query = MockPG.return_value.run.call_args[0][0]
        assert "SET a.actioned" in query
        assert MockPG.return_value.run.call_args[1]["aid"] == "alert-1"
        assert MockPG.return_value.run.call_args[1]["actioned"] is True
        MockPG.return_value.close.assert_called_once()

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_marks_alert_unactioned(self, MockPG):
        from services.analytics_api.app.routers.dashboards import (
            action_css_alert,
            ActionAlertRequest,
        )

        MockPG.return_value.run.return_value = [{"id": "alert-1"}]

        result = action_css_alert("alert-1", ActionAlertRequest(actioned=False))
        assert result == {"success": True}
        assert MockPG.return_value.run.call_args[1]["actioned"] is False

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_404_when_alert_not_found(self, MockPG):
        from services.analytics_api.app.routers.dashboards import (
            action_css_alert,
            ActionAlertRequest,
        )
        from fastapi import HTTPException

        MockPG.return_value.run.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            action_css_alert("no-such-id", ActionAlertRequest(actioned=True))
        assert exc_info.value.status_code == 404
        MockPG.return_value.close.assert_called_once()

    @patch("services.analytics_api.app.routers.dashboards.PatientGraphClient")
    def test_always_closes_client(self, MockPG):
        from services.analytics_api.app.routers.dashboards import (
            action_css_alert,
            ActionAlertRequest,
        )

        MockPG.return_value.run.return_value = [{"id": "a1"}]

        action_css_alert("a1", ActionAlertRequest(actioned=True))
        MockPG.return_value.close.assert_called_once()
