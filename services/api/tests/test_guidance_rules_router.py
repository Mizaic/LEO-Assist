"""Tests for guidance_rules FastAPI router -- VT-LEO-AI-064.

Covers:
  - POST /guidance/rules/review/{rule_id}/promote-to-domain (happy path, 409, 404)
  - GET /guidance/rules/review (list endpoint, has_predecessor flag)
  - GET /guidance/rules/review/{rule_id}/diff (version diff endpoint)
  - _compute_diff utility function
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.routers.guidance_rules import router, _compute_diff
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
            "concepts": [
                {"concept_id": "363346000", "term": "Malignant neoplastic disease"}
            ],
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[pending_row]])
            resp = test_client.post(
                "/guidance/rules/review/rule-123/promote-to-domain?reviewer=admin@test.com"
            )

        assert resp.status_code == 409
        assert "active" in resp.json()["detail"].lower()

    def test_returns_404_when_rule_not_found(self, test_client):
        """Promote should fail with 404 if rule_id does not exist."""
        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[]])  # empty result
            resp = test_client.post(
                "/guidance/rules/review/nonexistent-rule/promote-to-domain?reviewer=admin@test.com"
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
                "/guidance/rules/review/rule-123/promote-to-domain?reviewer=admin@test.com"
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
            "concepts": [
                {"concept_id": "363346000", "term": "Malignant neoplastic disease"}
            ],
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_client = _mock_kg_client(
                [
                    [active_row],  # _FETCH_RULE_FOR_PROMOTION
                    [{"added": 1}],  # _PROMOTE_CONCEPT_TO_DOMAIN
                    [{}],  # _WRITE_PROMOTION_AUDIT
                ]
            )
            mock_cls.return_value = mock_client
            resp = test_client.post(
                "/guidance/rules/review/rule-abc/promote-to-domain?reviewer=admin@test.com"
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
                "/guidance/rules/review/rule-empty/promote-to-domain?reviewer=admin@test.com"
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
                {
                    "predicate": "PRESENT",
                    "concept_id": "267051000",
                    "preferred_term": "Rectal bleeding",
                }
            ],
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[raw_row]])
            resp = test_client.get("/guidance/rules/review")

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
            resp = test_client.get("/guidance/rules/review")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_has_predecessor_flag_returned(self, test_client):
        """list_pending_rules includes has_predecessor=True when SUPERSEDES edge exists."""
        raw_row = {
            "rule_id": "r2",
            "name": "Updated cancer referral rule",
            "status": "pending_review",
            "strength": "refer",
            "guideline_id": "NG12",
            "guideline_version": 2,
            "chapter_title": "Referral for suspected cancer",
            "recommendation_text": "Refer immediately for suspected colorectal cancer.",
            "criteria": [
                {
                    "predicate": "PRESENT",
                    "concept_id": "363346000",
                    "preferred_term": "Cancer",
                },
            ],
            "has_predecessor": True,
            "predecessor_id": "rule:NG12:v1:CH000:R000:abc",
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[raw_row]])
            resp = test_client.get("/guidance/rules/review?status=pending_review")

        assert resp.status_code == 200
        rules = resp.json()
        assert rules[0]["has_predecessor"] is True
        assert rules[0]["guideline_version"] == 2
        assert rules[0]["chapter_title"] == "Referral for suspected cancer"

    def test_surfaces_action_priority_and_due_days(self, test_client):
        """list_pending_rules exposes rule-level clinical priority for the editor."""
        raw_row = {
            "rule_id": "r-priority",
            "name": "Rule: 1.2.10",
            "status": "pending_review",
            "strength": "consider",
            "guideline_id": "NG12",
            "recommendation_text": (
                "Consider an urgent, direct access ultrasound scan "
                "(to be done within 2 weeks)."
            ),
            "criteria": [
                {
                    "predicate": "PRESENT",
                    "concept_id": "300344005",
                    "preferred_term": "Gallbladder enlarged",
                }
            ],
            "action_priority": "2ww",
            "action_due_days": 14,
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[raw_row]])
            resp = test_client.get("/guidance/rules/review")

        assert resp.status_code == 200
        rules = resp.json()
        assert rules[0]["action_priority"] == "2ww"
        assert rules[0]["action_due_days"] == 14

    def test_action_priority_null_when_no_action_edges(self, test_client):
        raw_row = {
            "rule_id": "r-no-priority",
            "name": "Stub rule",
            "status": "pending_review",
            "strength": "offer",
            "guideline_id": "NG12",
            "recommendation_text": "Offer review.",
            "criteria": [],
            "action_priority": None,
            "action_due_days": None,
        }

        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[raw_row]])
            resp = test_client.get("/guidance/rules/review")

        assert resp.status_code == 200
        rules = resp.json()
        assert rules[0]["action_priority"] is None
        assert rules[0]["action_due_days"] is None


# ── compute_diff tests ─────────────────────────────────────────────────────


class TestComputeDiff:
    """Unit tests for _compute_diff helper."""

    def test_added_criteria_detected(self):
        """Criteria in new rule but not predecessor are classified as added."""
        new_c = [
            {
                "predicate": "PRESENT",
                "concept_id": "363346000",
                "preferred_term": "Cancer",
            },
            {
                "predicate": "PRESENT",
                "concept_id": "267051000",
                "preferred_term": "Rectal bleeding",
            },
        ]
        pred_c = [
            {
                "predicate": "PRESENT",
                "concept_id": "363346000",
                "preferred_term": "Cancer",
            },
        ]
        diff = _compute_diff(new_c, pred_c)
        assert len(diff["added"]) == 1
        assert diff["added"][0]["concept_id"] == "267051000"
        assert len(diff["removed"]) == 0
        assert len(diff["unchanged"]) == 1

    def test_removed_criteria_detected(self):
        """Criteria in predecessor but not new rule are classified as removed."""
        new_c = [
            {
                "predicate": "PRESENT",
                "concept_id": "363346000",
                "preferred_term": "Cancer",
            },
        ]
        pred_c = [
            {
                "predicate": "PRESENT",
                "concept_id": "363346000",
                "preferred_term": "Cancer",
            },
            {
                "predicate": "ABSENT",
                "concept_id": "394828003",
                "preferred_term": "No weight loss",
            },
        ]
        diff = _compute_diff(new_c, pred_c)
        assert len(diff["removed"]) == 1
        assert diff["removed"][0]["concept_id"] == "394828003"
        assert len(diff["added"]) == 0

    def test_no_changes_all_unchanged(self):
        """Identical criteria return empty added/removed lists."""
        criteria = [
            {
                "predicate": "PRESENT",
                "concept_id": "363346000",
                "preferred_term": "Cancer",
            }
        ]
        diff = _compute_diff(criteria, criteria)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert len(diff["unchanged"]) == 1

    def test_null_concept_ids_excluded(self):
        """Rows with concept_id=None (from OPTIONAL MATCH) are filtered out."""
        new_c = [
            {"predicate": "PRESENT", "concept_id": None, "preferred_term": None},
            {
                "predicate": "PRESENT",
                "concept_id": "363346000",
                "preferred_term": "Cancer",
            },
        ]
        pred_c = [
            {
                "predicate": "PRESENT",
                "concept_id": "363346000",
                "preferred_term": "Cancer",
            },
        ]
        diff = _compute_diff(new_c, pred_c)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert len(diff["unchanged"]) == 1

    def test_predicate_considered_in_key(self):
        """Same concept under different predicates are treated as distinct."""
        new_c = [
            {
                "predicate": "PRESENT",
                "concept_id": "363346000",
                "preferred_term": "Cancer",
            },
        ]
        pred_c = [
            {
                "predicate": "ABSENT",
                "concept_id": "363346000",
                "preferred_term": "Cancer",
            },
        ]
        diff = _compute_diff(new_c, pred_c)
        # PRESENT version is new, ABSENT version was removed
        assert len(diff["added"]) == 1
        assert len(diff["removed"]) == 1


# ── diff endpoint tests ────────────────────────────────────────────────────


class TestRuleDiffEndpoint:
    """GET /guidance/rules/review/{rule_id}/diff"""

    def _rule_row(self, has_predecessor=True):
        return {
            "rule_id": "rule:NG12:v2:CH000:R000:xyz",
            "name": "Updated rule",
            "status": "pending_review",
            "strength": "refer",
            "guideline_id": "NG12",
            "guideline_version": 2,
            "chapter_title": "Referral for suspected cancer",
            "recommendation_text": "Refer immediately.",
            "criteria": [
                {
                    "predicate": "PRESENT",
                    "concept_id": "363346000",
                    "preferred_term": "Cancer",
                },
            ],
            "has_predecessor": has_predecessor,
            "predecessor_id": (
                "rule:NG12:v1:CH000:R000:abc" if has_predecessor else None
            ),
        }

    def _diff_row(self):
        return {
            "predecessor_id": "rule:NG12:v1:CH000:R000:abc",
            "predecessor_name": "Old cancer referral rule",
            "predecessor_status": "superseded",
            "predecessor_recommendation_text": "Refer if rectal bleeding.",
            "predecessor_recommendation_number": "1.1.1",
            "superseded_at": "2026-01-15T12:00:00",
            "predecessor_criteria": [
                {
                    "predicate": "PRESENT",
                    "concept_id": "267051000",
                    "preferred_term": "Rectal bleeding",
                },
            ],
            "predecessor_decisions": [
                {
                    "action": "approve",
                    "reviewer": "dr.jones",
                    "timestamp": "2025-12-01T10:00:00",
                    "reason": "Clinically correct",
                },
            ],
        }

    def test_returns_diff_with_predecessor(self, test_client):
        """Diff endpoint returns has_predecessor=True with full diff data."""
        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client(
                [
                    [self._rule_row(has_predecessor=True)],  # _FETCH_RULE_BY_ID
                    [self._diff_row()],  # _FETCH_RULE_DIFF
                ]
            )
            resp = test_client.get(
                "/guidance/rules/review/rule:NG12:v2:CH000:R000:xyz/diff"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["has_predecessor"] is True
        assert body["predecessor"]["rule_id"] == "rule:NG12:v1:CH000:R000:abc"
        assert len(body["predecessor"]["decisions"]) == 1
        assert body["predecessor"]["decisions"][0]["action"] == "approve"
        # New rule has Cancer, predecessor has Rectal bleeding → both added/removed
        assert body["diff_summary"]["added_count"] == 1  # Cancer is new
        assert body["diff_summary"]["removed_count"] == 1  # Rectal bleeding removed

    def test_returns_has_predecessor_false_when_no_predecessor(self, test_client):
        """Diff endpoint returns has_predecessor=False for first-version rules."""
        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client(
                [
                    [self._rule_row(has_predecessor=False)],
                ]
            )
            resp = test_client.get(
                "/guidance/rules/review/rule:NG12:v1:CH000:R000:xyz/diff"
            )

        assert resp.status_code == 200
        assert resp.json()["has_predecessor"] is False

    def test_returns_404_for_unknown_rule(self, test_client):
        """Diff endpoint returns 404 when the rule_id does not exist."""
        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[]])
            resp = test_client.get("/guidance/rules/review/nonexistent/diff")

        assert resp.status_code == 404


# ── Test extraction dry-run endpoint ─────────────────────────────────────


class TestRuleExtractionTest:
    """POST /guidance/rules/test/{recommendation_id}"""

    _REC_ROW = {
        "id": "NG12:v1:CH000:SEC000:R000",
        "verbatim": "Refer immediately if rectal bleeding with weight loss.",
        "title": "1.1.1",
        "urgency": "urgent_2w",
        "strength": "refer",
        "section_title": "Colorectal cancer",
        "chapter_title": "Symptoms and signs",
        "guideline_id": "NG12",
        "guideline_title": "Suspected cancer: recognition and referral",
        "is_normative": True,
    }

    def test_returns_200_with_extraction_result(self, test_client):
        """Happy path: normative recommendation with verbatim → extraction runs."""
        coded = {
            "present": [
                {
                    "term": "rectal bleeding",
                    "snomed_concept_id": "12345",
                    "preferred_term": "Rectal bleeding",
                    "semantic_tag": "finding",
                }
            ],
            "absent": [],
            "action": {
                "term": "suspected cancer pathway referral",
                "snomed_concept_id": "306206005",
                "preferred_term": "Referral to service",
                "semantic_tag": "procedure",
            },
        }
        raw = {
            "present": ["rectal bleeding"],
            "absent": [],
            "action": "suspected cancer pathway referral",
        }

        with (
            patch("app.routers.guidance_rules._kg_client") as mock_cls,
            patch("app.routers.guidance_rules.get_registry") as mock_reg,
        ):
            mock_cls.return_value = _mock_kg_client([[self._REC_ROW]])
            mock_subgraph = MagicMock()
            mock_subgraph.invoke.return_value = {
                "raw_criteria": raw,
                "coded_criteria": coded,
                "errors": [],
            }
            mock_reg.return_value.build.return_value = mock_subgraph

            resp = test_client.post(
                "/guidance/rules/test/NG12%3Av1%3ACH000%3ASEC000%3AR000"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["raw_criteria"]["present"] == ["rectal bleeding"]
        assert body["coded_criteria"]["present"][0]["snomed_concept_id"] == "12345"
        assert body["recommendation"]["id"] == "NG12:v1:CH000:SEC000:R000"
        assert body["errors"] == []

    def test_returns_404_when_rec_not_found(self, test_client):
        """Returns 404 when the recommendation ID is not in Neo4j."""
        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[]])
            resp = test_client.post("/guidance/rules/test/UNKNOWN%3AREC")

        assert resp.status_code == 404

    def test_returns_422_for_non_normative_rec(self, test_client):
        """Rejects cross-reference table entries (isNormative=false)."""
        cross_ref_row = {**self._REC_ROW, "is_normative": False}
        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[cross_ref_row]])
            resp = test_client.post(
                "/guidance/rules/test/NG12%3Av1%3ACH000%3ASEC000%3AR000"
            )

        assert resp.status_code == 422
        assert "cross-reference" in resp.json()["detail"]

    def test_returns_422_for_rec_with_no_verbatim(self, test_client):
        """Rejects recommendations that have no verbatim text stored."""
        no_text_row = {**self._REC_ROW, "verbatim": None}
        with patch("app.routers.guidance_rules._kg_client") as mock_cls:
            mock_cls.return_value = _mock_kg_client([[no_text_row]])
            resp = test_client.post(
                "/guidance/rules/test/NG12%3Av1%3ACH000%3ASEC000%3AR000"
            )

        assert resp.status_code == 422
        assert "no verbatim text" in resp.json()["detail"]

    def test_surfaces_pipeline_errors_in_response(self, test_client):
        """Pipeline warnings in the errors list are returned in the response body."""
        with (
            patch("app.routers.guidance_rules._kg_client") as mock_cls,
            patch("app.routers.guidance_rules.get_registry") as mock_reg,
        ):
            mock_cls.return_value = _mock_kg_client([[self._REC_ROW]])
            mock_subgraph = MagicMock()
            mock_subgraph.invoke.return_value = {
                "raw_criteria": None,
                "coded_criteria": None,
                "errors": ["prompt_registry_unavailable: connection refused"],
            }
            mock_reg.return_value.build.return_value = mock_subgraph

            resp = test_client.post(
                "/guidance/rules/test/NG12%3Av1%3ACH000%3ASEC000%3AR000"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "prompt_registry_unavailable" in body["errors"][0]
        assert body["coded_criteria"] is None
