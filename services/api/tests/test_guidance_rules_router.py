"""Tests for guidance_rules FastAPI router -- VT-LEO-AI-064.

Covers:
  - POST /guidance/rules/review/{rule_id}/promote-to-domain (happy path, 409, 404)
  - GET /guidance/rules/review (list endpoint)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.routers.guidance_rules import router
from fastapi import FastAPI

# ── Test app setup ───────────────────────────────────────────────────────


def _make_app():
    """Wrap the router in a minimal FastAPI app, bypassing auth."""
    app = FastAPI()

    # Override require_admin to a no-op for unit tests
    from app import deps

    app.dependency_overrides[deps.require_admin] = lambda: None
    app.include_router(router)
    return app


@pytest.fixture()
def test_client():
    return TestClient(_make_app())


# ── Helpers ──────────────────────────────────────────────────────────────


def _mock_kg_client(run_results: list):
    """Return a context-manager-compatible mock KnowledgeGraphClient."""
    mock_client = MagicMock()
    mock_client.run.side_effect = run_results
    mock_client.close = MagicMock()
    return mock_client


# ── promote-to-domain tests ───────────────────────────────────────────────


class TestPromoteToDomain:
    """POST /guidance/rules/review/{rule_id}/promote-to-domain"""

    def test_returns_409_when_rule_not_active(self, test_client):
        """Promote should fail with 409 if rule status is not active."""
        pending_row = {
            "status": "pending_review",
            "guideline_id": "NG151",
            "domain_id": "nice:conditions-and-diseases:cancer",
            "domain_name": "Cancer",
            "concepts": [{"concept_id": "363346000", "term": "Malignant neoplastic disease"}],
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[pending_row]])
            resp = test_client.post(
                "/rules/review/rule-123/promote-to-domain?reviewer=admin@test.com"
            )

        assert resp.status_code == 409
        assert "active" in resp.json()["detail"].lower()

    def test_returns_404_when_rule_not_found(self, test_client):
        """Promote should fail with 404 if rule_id does not exist."""
        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[]])  # empty result
            resp = test_client.post(
                "/rules/review/nonexistent-rule/promote-to-domain?reviewer=admin@test.com"
            )

        assert resp.status_code == 404

    def test_returns_404_when_no_nice_domain(self, test_client):
        """Promote should fail with 404 if no NICE domain is linked to the guideline."""
        row_no_domain = {
            "status": "active",
            "guideline_id": "NG151",
            "domain_id": None,
            "domain_name": None,
            "concepts": [],
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[row_no_domain]])
            resp = test_client.post(
                "/rules/review/rule-123/promote-to-domain?reviewer=admin@test.com"
            )

        assert resp.status_code == 404
        assert "domain" in resp.json()["detail"].lower()

    def test_happy_path_promotes_concepts_and_writes_audit(self, test_client):
        """Promote returns 200 and runs MERGE + audit Cypher for an active rule."""
        active_row = {
            "status": "active",
            "guideline_id": "NG151",
            "domain_id": "nice:conditions-and-diseases:cancer",
            "domain_name": "Cancer",
            "concepts": [{"concept_id": "363346000", "term": "Malignant neoplastic disease"}],
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_client = _mock_kg_client([
                [active_row],   # _FETCH_RULE_FOR_PROMOTION
                [{"added": 1}],  # _PROMOTE_CONCEPT_TO_DOMAIN
                [{}],            # _WRITE_PROMOTION_AUDIT
            ])
            mock_cls.return_value = mock_client
            resp = test_client.post(
                "/rules/review/rule-abc/promote-to-domain?reviewer=admin@test.com"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["domain_id"] == "nice:conditions-and-diseases:cancer"
        assert body["domain_name"] == "Cancer"
        assert body["concepts_added"] == 1

        # Verify both MERGE and audit Cypher ran
        assert mock_client.run.call_count == 3

    def test_returns_200_with_zero_concepts(self, test_client):
        """Promote returns 200 with a message if rule has no SNOMED criteria."""
        active_no_concepts = {
            "status": "active",
            "guideline_id": "NG151",
            "domain_id": "nice:conditions-and-diseases:cancer",
            "domain_name": "Cancer",
            "concepts": [],
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[active_no_concepts]])
            resp = test_client.post(
                "/rules/review/rule-empty/promote-to-domain?reviewer=admin@test.com"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["concepts_added"] == 0
        assert "message" in body


# ── list rules tests ──────────────────────────────────────────────────────


class TestListPendingRules:
    """GET /guidance/rules/review"""

    def test_returns_formatted_rules(self, test_client):
        """list_pending_rules returns plain-English formatted rule dicts."""
        raw_row = {
            "rule_id": "r1",
            "name": "Test rule",
            "status": "pending_review",
            "strength": "refer",
            "guideline_id": "NG151",
            "guideline_title": "Bowel cancer",
            "recommendation_text": "Refer all patients with rectal bleeding.",
            "criteria": [
                {"predicate": "PRESENT", "concept_id": "267051000", "preferred_term": "Rectal bleeding"}
            ],
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[raw_row]])
            resp = test_client.get("/rules/review")

        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) == 1
        assert rules[0]["rule_id"] == "r1"
        assert "Rectal bleeding" in rules[0]["plain_english"]
        assert "HAS" in rules[0]["plain_english"]

    def test_returns_empty_list_when_no_rules(self, test_client):
        """list_pending_rules returns empty list when no rules exist."""
        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[]])
            resp = test_client.get("/rules/review")

        assert resp.status_code == 200
        assert resp.json() == []
