"""Tests for `services/api/app/routers/audit_quality.py`.

Atlas trace:
  DO: DO-720CD183
  DI: DI-1126FFD1

Covers the Loop 1 quality dashboard endpoints:
  POST   /operations/quality/runs               -- trigger
  GET    /operations/quality/runs               -- list
  GET    /operations/quality/runs/latest        -- latest
  GET    /operations/quality/runs/{run_id}      -- by id
  GET    /operations/quality/drift              -- drift series
  GET    /operations/quality/alerts             -- safety alerts
  GET    /operations/quality/alerts/count       -- unack count
  PATCH  /operations/quality/alerts/{id}/acknowledge
  GET    /operations/quality/config             -- LoopConfig
  PATCH  /operations/quality/config/{loop_id}   -- toggle
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from libs.auth.org_scope import CallerScope


def _scope(is_admin: bool = True) -> CallerScope:
    return CallerScope(
        email="auditor@example.com",
        is_admin=is_admin,
        org_ids=[],
    )


@contextmanager
def _override_scope(is_admin: bool = True):
    """Override the request-scope dependency for both reader and admin paths."""
    from app.deps import get_caller_scope_from_request, require_admin

    sc = _scope(is_admin)
    app.dependency_overrides[get_caller_scope_from_request] = lambda: sc
    if is_admin:
        app.dependency_overrides[require_admin] = lambda: sc
    try:
        yield sc
    finally:
        app.dependency_overrides.pop(get_caller_scope_from_request, None)
        app.dependency_overrides.pop(require_admin, None)


def _stub_neo(rows_by_query: dict[str, list[dict]]):
    """Patch PatientGraphClient so its session().run() returns rows
    keyed by a substring of the executed Cypher query."""
    inst = MagicMock()

    def _run(query, **params):
        for needle, rows in rows_by_query.items():
            if needle in query:
                result = MagicMock()
                result.__iter__ = lambda s: iter(rows)
                result.single = MagicMock(
                    return_value=(rows[0] if rows else None)
                )
                return result
        result = MagicMock()
        result.__iter__ = lambda s: iter([])
        result.single = MagicMock(return_value=None)
        return result

    sess = MagicMock()
    sess.run = _run
    inst.session.return_value.__enter__ = MagicMock(return_value=sess)
    inst.session.return_value.__exit__ = MagicMock(return_value=False)
    inst.close = MagicMock()
    return patch(
        "app.routers.audit_quality.PatientGraphClient",
        return_value=inst,
    ), inst


@pytest.fixture
def client():
    """TestClient that sends `X-Requested-With: XMLHttpRequest` on every
    request, satisfying the CSRF middleware in `app.main`."""
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield c


class TestTriggerAuditRun:
    def test_returns_run_id_and_accepted_status(self, client):
        with _override_scope():
            r = client.post(
                "/operations/quality/runs",
                json={"since_days": 14, "triggered_by": "manual"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "accepted"
        assert body["since_days"] == 14
        assert body["triggered_by"] == "manual"
        assert body["run_id"].startswith("audit-manual-")

    def test_default_since_days_is_seven(self, client):
        with _override_scope():
            r = client.post("/operations/quality/runs", json={})
        assert r.status_code == 200
        assert r.json()["since_days"] == 7


class TestListAuditRuns:
    def test_returns_paginated_runs(self, client):
        rows = [
            {"run_id": "audit-1", "status": "complete", "pct_clean": 0.97},
            {"run_id": "audit-2", "status": "complete", "pct_clean": 0.95},
        ]
        patch_, _ = _stub_neo({
            "ORDER BY a.started_at DESC": rows,
            "RETURN count(a) AS total": [{"total": 42}],
        })
        with patch_, _override_scope():
            r = client.get("/operations/quality/runs?page=2&page_size=10")
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 2
        assert body["page_size"] == 10
        assert body["total"] == 42
        assert len(body["items"]) == 2
        assert body["items"][0]["run_id"] == "audit-1"


class TestGetLatestAuditRun:
    def test_returns_none_when_no_runs(self, client):
        patch_, _ = _stub_neo({"AuditRun {status: 'complete'}": []})
        with patch_, _override_scope():
            r = client.get("/operations/quality/runs/latest")
        assert r.status_code == 200
        assert r.json() == {"run": None, "drift_metric": None}

    def test_separates_run_keys_from_drift_keys(self, client):
        row = {
            "run_id": "audit-99",
            "status": "complete",
            "pct_clean": 0.96,
            "metric_id": "drift-1",
            "week_start": "2026-04-13",
            "high_count": 4,
        }
        patch_, _ = _stub_neo({"AuditRun {status: 'complete'}": [row]})
        with patch_, _override_scope():
            r = client.get("/operations/quality/runs/latest")
        body = r.json()
        assert body["run"]["run_id"] == "audit-99"
        assert body["run"]["pct_clean"] == 0.96
        assert "metric_id" not in body["run"]
        assert body["drift_metric"]["metric_id"] == "drift-1"
        assert body["drift_metric"]["high_count"] == 4


class TestGetAuditRun:
    def test_404_when_missing(self, client):
        patch_, _ = _stub_neo({"AuditRun {run_id": []})
        with patch_, _override_scope():
            r = client.get("/operations/quality/runs/audit-missing")
        assert r.status_code == 404

    def test_returns_row_when_found(self, client):
        patch_, _ = _stub_neo({"AuditRun {run_id": [
            {"run_id": "audit-7", "status": "complete"}
        ]})
        with patch_, _override_scope():
            r = client.get("/operations/quality/runs/audit-7")
        assert r.status_code == 200
        assert r.json()["run_id"] == "audit-7"


class TestDriftMetrics:
    def test_returns_series_with_metadata(self, client):
        rows = [
            {"metric_id": "m1", "week_start": "2026-03-30", "pct_clean": 0.94},
            {"metric_id": "m2", "week_start": "2026-04-06", "pct_clean": 0.96},
        ]
        patch_, _ = _stub_neo({"DriftMetric {metric_type:": rows})
        with patch_, _override_scope():
            r = client.get("/operations/quality/drift?weeks=4")
        body = r.json()
        assert body["metric_type"] == "audit"
        assert body["weeks"] == 4
        assert len(body["series"]) == 2


class TestAlerts:
    def test_list_returns_alerts(self, client):
        rows = [
            {"alert_id": "alert-1", "severity": "high",
             "alert_type": "coding_overcoded"},
        ]
        patch_, _ = _stub_neo({"MATCH (a:SafetyNetAlert)\nWHERE a.alert_type": rows})
        with patch_, _override_scope():
            r = client.get("/operations/quality/alerts?unacknowledged_only=true")
        body = r.json()
        assert body["unacknowledged_only"] is True
        assert body["items"][0]["alert_id"] == "alert-1"

    def test_count_returns_total(self, client):
        patch_, _ = _stub_neo({
            "RETURN count(a) AS total": [{"total": 7}],
        })
        with patch_, _override_scope():
            r = client.get("/operations/quality/alerts/count")
        assert r.json() == {"unacknowledged": 7}

    def test_count_zero_when_no_row(self, client):
        patch_, _ = _stub_neo({"RETURN count(a) AS total": []})
        with patch_, _override_scope():
            r = client.get("/operations/quality/alerts/count")
        assert r.json() == {"unacknowledged": 0}

    def test_acknowledge_returns_404_when_missing(self, client):
        patch_, _ = _stub_neo({"MATCH (a:SafetyNetAlert {alert_id": []})
        with patch_, _override_scope():
            r = client.patch(
                "/operations/quality/alerts/missing-id/acknowledge",
                json={"acknowledged_by": "ops@example.com"},
            )
        assert r.status_code == 404

    def test_acknowledge_returns_acknowledged(self, client):
        patch_, _ = _stub_neo({"MATCH (a:SafetyNetAlert {alert_id": [
            {"alert_id": "alert-x", "acknowledged_by": "ops@example.com"},
        ]})
        with patch_, _override_scope():
            r = client.patch(
                "/operations/quality/alerts/alert-x/acknowledge",
                json={"acknowledged_by": "ops@example.com"},
            )
        body = r.json()
        assert body["status"] == "acknowledged"
        assert body["alert_id"] == "alert-x"


class TestLoopConfig:
    def test_get_returns_defaults_when_no_configs(self, client):
        patch_, _ = _stub_neo({"MATCH (c:LoopConfig)": []})
        with patch_, _override_scope():
            r = client.get("/operations/quality/config")
        body = r.json()
        loop_ids = {c["loop_id"] for c in body["configs"]}
        assert loop_ids == {
            "loop1_audit", "loop2_surface_form", "loop3_evidence",
        }
        for c in body["configs"]:
            assert c["enabled"] is True
            assert c["updated_by"] is None

    def test_get_returns_neo_configs_when_present(self, client):
        rows = [
            {"loop_id": "loop1_audit", "enabled": False,
             "updated_by": "admin@x", "updated_at": "2026-04-19T10:00Z"},
        ]
        patch_, _ = _stub_neo({"MATCH (c:LoopConfig)": rows})
        with patch_, _override_scope():
            r = client.get("/operations/quality/config")
        body = r.json()
        assert len(body["configs"]) == 1
        assert body["configs"][0]["loop_id"] == "loop1_audit"
        assert body["configs"][0]["enabled"] is False

    def test_update_rejects_unknown_loop_id(self, client):
        with _override_scope():
            r = client.patch(
                "/operations/quality/config/loop99_bogus",
                json={"enabled": False},
            )
        assert r.status_code == 400
        assert "Unknown loop_id" in r.json()["detail"]

    def test_update_404_when_loop_config_missing(self, client):
        patch_, _ = _stub_neo({"MATCH (c:LoopConfig {loop_id": []})
        with patch_, _override_scope():
            r = client.patch(
                "/operations/quality/config/loop1_audit",
                json={"enabled": False},
            )
        assert r.status_code == 404

    def test_update_returns_new_state(self, client):
        patch_, _ = _stub_neo({"MATCH (c:LoopConfig {loop_id": [
            {"loop_id": "loop1_audit", "enabled": False,
             "updated_by": "auditor@example.com"},
        ]})
        with patch_, _override_scope():
            r = client.patch(
                "/operations/quality/config/loop1_audit",
                json={"enabled": False},
            )
        body = r.json()
        assert body["loop_id"] == "loop1_audit"
        assert body["enabled"] is False
        assert body["updated_by"] == "auditor@example.com"
