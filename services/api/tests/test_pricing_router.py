"""Verification tests for the pricing router.

VT-LEO-AI-068 — Per-Tenant Billing and Pricing Router Verification
DI-LEO-AI-068 — Per-Tenant Billing, Margin Configuration, and Discount Management
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from libs.auth.org_scope import CallerScope

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scope(is_admin: bool = True) -> CallerScope:
    return CallerScope(email="test@example.com", is_admin=is_admin, org_ids=[])


def _patch_scope(is_admin: bool = True):
    scope = _make_scope(is_admin)
    return patch("app.deps.get_caller_scope_from_request", return_value=scope)


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# VT-068-001: GET /pricing/config — 403 for non-admin
# ---------------------------------------------------------------------------


def test_get_pricing_config_403_non_admin(client):
    with _patch_scope(is_admin=False):
        r = client.get("/pricing/config")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# VT-068-002: GET /pricing/config — default when not configured
# ---------------------------------------------------------------------------


def test_get_pricing_config_returns_default(client):
    mock_kg = MagicMock()
    mock_session = MagicMock().__enter__ = MagicMock(return_value=MagicMock())
    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
    ):
        inst = MockKG.return_value
        inst.session.return_value.__enter__ = lambda s: MagicMock(
            run=MagicMock(return_value=MagicMock(single=MagicMock(return_value=None)))
        )
        inst.session.return_value.__exit__ = MagicMock(return_value=False)
        r = client.get("/pricing/config")
    assert r.status_code == 200
    data = r.json()
    assert data["targetMargin"] == pytest.approx(0.75)
    assert data["isDefault"] is True


# ---------------------------------------------------------------------------
# VT-068-003: PUT /pricing/config stores updated margin
# ---------------------------------------------------------------------------


def test_put_pricing_config_updates_margin(client):
    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
    ):
        inst = MockKG.return_value
        inst.session.return_value.__enter__ = lambda s: MagicMock(run=MagicMock())
        inst.session.return_value.__exit__ = MagicMock(return_value=False)
        r = client.put("/pricing/config", json={"targetMargin": 0.65})
    assert r.status_code == 200
    assert r.json()["targetMargin"] == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# VT-068-004: PUT /pricing/config rejects margin >= 1.0
# ---------------------------------------------------------------------------


def test_put_pricing_config_rejects_invalid_margin(client):
    with _patch_scope(is_admin=True):
        r = client.put("/pricing/config", json={"targetMargin": 1.0})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# VT-068-005: GET /pricing/orgs — 403 for non-admin
# ---------------------------------------------------------------------------


def test_get_pricing_orgs_403_non_admin(client):
    with _patch_scope(is_admin=False):
        r = client.get("/pricing/orgs")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# VT-068-006: GET /pricing/orgs — correct list price calculation
# ---------------------------------------------------------------------------


def test_get_pricing_orgs_correct_list_price(client):
    """list_price = raw_cost / (1 - margin) = 10 / 0.25 = 40"""
    org_row = {
        "orgId": "org-1",
        "orgName": "Test GP",
        "runCount": 5,
        "inputTokens": 1000,
        "outputTokens": 200,
        "cachedTokens": 100,
        "rawCostUsd": 10.0,
    }
    discount_row = {"total_discount_rate": 0.0, "active_discounts": []}
    config_row = {
        "target_margin": 0.75,
        "updated_by": "admin",
        "updated_at": "2026-01-01",
    }

    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
        patch("app.routers.pricing.PatientGraphClient") as MockPG,
    ):
        kg = MockKG.return_value
        pg = MockPG.return_value

        def kg_session_run(query, **kwargs):
            result = MagicMock()
            if "PricingConfig" in query:
                result.single.return_value = config_row
            else:
                result.single.return_value = discount_row
            return result

        kg.session.return_value.__enter__ = lambda s: MagicMock(run=kg_session_run)
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        pg_inner = MagicMock()
        pg_inner.run.return_value = MagicMock(data=MagicMock(return_value=[org_row]))
        pg.session.return_value.__enter__ = lambda s: pg_inner
        pg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/pricing/orgs")

    assert r.status_code == 200
    orgs = r.json()["orgs"]
    assert len(orgs) == 1
    assert orgs[0]["listPriceUsd"] == pytest.approx(40.0, rel=1e-3)
    assert orgs[0]["billableUsd"] == pytest.approx(40.0, rel=1e-3)
    assert orgs[0]["grossMargin"] == pytest.approx(0.75, rel=1e-3)


# ---------------------------------------------------------------------------
# VT-068-007: GET /pricing/orgs — discount reduces billable amount
# ---------------------------------------------------------------------------


def test_get_pricing_orgs_applies_discount(client):
    """billable = list_price × (1 - 0.20) = 40 × 0.80 = 32"""
    org_row = {
        "orgId": "org-1",
        "orgName": "Test GP",
        "runCount": 5,
        "inputTokens": 1000,
        "outputTokens": 200,
        "cachedTokens": 100,
        "rawCostUsd": 10.0,
    }
    discount_row = {"total_discount_rate": 0.20, "active_discounts": []}
    config_row = {
        "target_margin": 0.75,
        "updated_by": "admin",
        "updated_at": "2026-01-01",
    }

    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
        patch("app.routers.pricing.PatientGraphClient") as MockPG,
    ):
        kg = MockKG.return_value
        pg = MockPG.return_value

        def kg_session_run(query, **kwargs):
            result = MagicMock()
            if "PricingConfig" in query:
                result.single.return_value = config_row
            else:
                result.single.return_value = discount_row
            return result

        kg.session.return_value.__enter__ = lambda s: MagicMock(run=kg_session_run)
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        pg_inner = MagicMock()
        pg_inner.run.return_value = MagicMock(data=MagicMock(return_value=[org_row]))
        pg.session.return_value.__enter__ = lambda s: pg_inner
        pg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/pricing/orgs")

    assert r.status_code == 200
    org = r.json()["orgs"][0]
    assert org["billableUsd"] == pytest.approx(32.0, rel=1e-3)


# ---------------------------------------------------------------------------
# VT-068-008: GET /pricing/orgs — combined discount capped at 100%
# ---------------------------------------------------------------------------


def test_get_pricing_orgs_caps_discount_at_100_pct(client):
    org_row = {
        "orgId": "org-1",
        "orgName": "Test",
        "runCount": 1,
        "inputTokens": 100,
        "outputTokens": 10,
        "cachedTokens": 0,
        "rawCostUsd": 10.0,
    }
    discount_row = {"total_discount_rate": 1.5, "active_discounts": []}
    config_row = {
        "target_margin": 0.75,
        "updated_by": "admin",
        "updated_at": "2026-01-01",
    }

    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
        patch("app.routers.pricing.PatientGraphClient") as MockPG,
    ):
        kg = MockKG.return_value
        pg = MockPG.return_value

        def kg_session_run(query, **kwargs):
            result = MagicMock()
            if "PricingConfig" in query:
                result.single.return_value = config_row
            else:
                result.single.return_value = discount_row
            return result

        kg.session.return_value.__enter__ = lambda s: MagicMock(run=kg_session_run)
        kg.session.return_value.__exit__ = MagicMock(return_value=False)
        pg_inner = MagicMock()
        pg_inner.run.return_value = MagicMock(data=MagicMock(return_value=[org_row]))
        pg.session.return_value.__enter__ = lambda s: pg_inner
        pg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/pricing/orgs")

    assert r.status_code == 200
    org = r.json()["orgs"][0]
    assert org["billableUsd"] >= 0.0  # never negative


# ---------------------------------------------------------------------------
# VT-068-009: POST /pricing/orgs/{org_id}/discounts — creates and returns 201
# ---------------------------------------------------------------------------


def test_post_org_discount_creates_and_returns_201(client):
    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        kg.session.return_value.__enter__ = lambda s: MagicMock(run=MagicMock())
        kg.session.return_value.__exit__ = MagicMock(return_value=False)
        r = client.post(
            "/pricing/orgs/org-1/discounts",
            json={
                "description": "Year 1 promo",
                "rate": 0.10,
                "type": "promo",
                "validFrom": "2026-01-01T00:00:00Z",
                "validTo": "2026-12-31T23:59:59Z",
            },
        )
    assert r.status_code == 201
    data = r.json()
    assert data["orgId"] == "org-1"
    assert "discountId" in data


# ---------------------------------------------------------------------------
# VT-068-010: POST discount rejects invalid type
# ---------------------------------------------------------------------------


def test_post_org_discount_rejects_invalid_type(client):
    with _patch_scope(is_admin=True):
        r = client.post(
            "/pricing/orgs/org-1/discounts",
            json={"description": "Bad", "rate": 0.1, "type": "invalid"},
        )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# VT-068-011: DELETE with permanent=false deactivates
# ---------------------------------------------------------------------------


def test_delete_discount_deactivate(client):
    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(
            single=MagicMock(return_value={"discount_id": "abc"})
        )
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)
        r = client.delete("/pricing/discounts/abc?permanent=false")
    assert r.status_code == 200
    assert r.json()["status"] == "deactivated"


# ---------------------------------------------------------------------------
# VT-068-012: DELETE with permanent=true hard-deletes
# ---------------------------------------------------------------------------


def test_delete_discount_permanent(client):
    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(
            single=MagicMock(return_value={"deleted": 1})
        )
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)
        r = client.delete("/pricing/discounts/abc?permanent=true")
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"


# ---------------------------------------------------------------------------
# VT-068-013: DELETE returns 404 when not found
# ---------------------------------------------------------------------------


def test_delete_discount_not_found(client):
    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(
            single=MagicMock(return_value={"deleted": 0})
        )
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)
        r = client.delete("/pricing/discounts/nonexistent?permanent=true")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# VT-068-014: GET /pricing/platform-spend — 403 for non-admin
# ---------------------------------------------------------------------------


def test_get_platform_spend_403_non_admin(client):
    with _patch_scope(is_admin=False):
        r = client.get("/pricing/platform-spend")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# VT-068-015: GET /pricing/platform-spend — returns non-patient events
# ---------------------------------------------------------------------------


def test_get_platform_spend_returns_non_patient_events(client):
    event_row = {
        "eventType": "TrainingRun",
        "runCount": 3,
        "inputTokens": 500,
        "outputTokens": 100,
        "cachedTokens": 0,
        "rawCostUsd": 5.0,
    }
    config_row = {
        "target_margin": 0.75,
        "updated_by": "admin",
        "updated_at": "2026-01-01",
    }

    with (
        _patch_scope(is_admin=True),
        patch("app.routers.pricing.PatientGraphClient") as MockPG,
        patch("app.routers.pricing.CodingGraphClient") as MockKG,
    ):
        pg = MockPG.return_value
        pg_inner = MagicMock()
        pg_inner.run.return_value = MagicMock(data=MagicMock(return_value=[event_row]))
        pg.session.return_value.__enter__ = lambda s: pg_inner
        pg.session.return_value.__exit__ = MagicMock(return_value=False)

        kg = MockKG.return_value
        kg_inner = MagicMock()
        kg_inner.run.return_value = MagicMock(single=MagicMock(return_value=config_row))
        kg.session.return_value.__enter__ = lambda s: kg_inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/pricing/platform-spend")

    assert r.status_code == 200
    data = r.json()
    assert any(b["eventType"] == "TrainingRun" for b in data["breakdown"])
    assert "not billed to tenants" in data["totals"]["note"].lower()


# ---------------------------------------------------------------------------
# VT-068-016: Discount date filter in Cypher (code review)
# ---------------------------------------------------------------------------


def test_active_discount_cypher_filters_by_date():
    from libs.cypher.pricing_queries import GET_ACTIVE_DISCOUNT_RATE

    assert "valid_from <= datetime()" in GET_ACTIVE_DISCOUNT_RATE
    assert "valid_to IS NULL OR d.valid_to >= datetime()" in GET_ACTIVE_DISCOUNT_RATE
