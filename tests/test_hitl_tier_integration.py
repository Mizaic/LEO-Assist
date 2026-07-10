"""Tests for HITL tier-reasoning integration.

Covers:
- _build_review_item populates tier fields
- _check_terminology_coding calls classify_tier and returns tier fields
- UPSERT_CODING_REVIEW Cypher includes tier parameter placeholders
- GET_CODING_REVIEW_QUEUE returns tier fields
- GROUP_CODING_REVIEWS_BY_ENTITY returns tier fields
- GET_TIER_OVERRIDE_STATS query structural correctness
- RESOLVE_CODING_REVIEW sets reviewer_tier_override correctly
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _build_review_item
# ---------------------------------------------------------------------------


class TestBuildReviewItem:
    def _import(self):
        from services.api.app.services.label_verifier import _build_review_item

        return _build_review_item

    def test_returns_tier_fields_when_provided(self):
        fn = self._import()
        item = fn(
            "lbl1",
            0,
            "asthma",
            "disorder",
            True,
            {
                "snomed_concept_id": "195967001",
                "snomed_term": "Asthma",
                "semantic_tag": "disorder",
            },
            0.92,
            "present",
            decision_tier=1,
            tier_reason="surface_form_match",
            tier_decision="auto_coded",
        )
        assert item["decision_tier"] == 1
        assert item["tier_reason"] == "surface_form_match"
        assert item["tier_decision"] == "auto_coded"

    def test_tier_fields_default_to_none(self):
        fn = self._import()
        item = fn("lbl1", 0, "asthma", "disorder", False, {}, None, "present")
        assert item["decision_tier"] is None
        assert item["tier_reason"] is None
        assert item["tier_decision"] is None

    def test_review_id_format_unchanged(self):
        fn = self._import()
        item = fn("lbl-abc", 3, "chest pain", "finding", False, {}, None, "present")
        assert item["review_id"] == "coding:lbl-abc:3"


# ---------------------------------------------------------------------------
# _check_terminology_coding calls classify_tier
# ---------------------------------------------------------------------------


class TestCheckTerminologyCodingCallsTier:
    """Verify classify_tier is called and results appear in review items."""

    def _run(self, entities, score=0.55):
        entity_label = entities[0].get("label", "disorder")
        results_map = (
            {
                entities[0]["text"]: [
                    {
                        "snomed_concept_id": "123",
                        "snomed_term": "Test",
                        "score": score,
                        "semantic_tag": entity_label,
                    }
                ]
            }
            if score
            else {}
        )

        with (
            patch(
                "services.api.app.services.label_verifier._resolve_terms_via_api",
                return_value=results_map,
            ),
            patch(
                "services.api.app.services.label_verifier.classify_tier"
            ) as mock_tier,
        ):
            from libs.coding_engine.tier_classifier import TierDecision

            mock_tier.return_value = TierDecision(
                tier=2, decision="code_with_flag", reason="medium_confidence"
            )

            from services.api.app.services.label_verifier import (
                _check_terminology_coding,
            )

            items = _check_terminology_coding("lbl1", entities, frozenset())

        return items, mock_tier

    def test_classify_tier_called_for_each_codeable_entity(self):
        entities = [{"text": "diabetes", "label": "disorder", "assertion": "present"}]
        items, mock_tier = self._run(entities)
        assert mock_tier.called

    def test_tier_fields_in_returned_item(self):
        entities = [{"text": "diabetes", "label": "disorder", "assertion": "present"}]
        items, _ = self._run(entities)
        assert len(items) == 1
        assert items[0]["decision_tier"] == 2
        assert items[0]["tier_reason"] == "medium_confidence"
        assert items[0]["tier_decision"] == "code_with_flag"

    def test_classify_tier_receives_correct_assertion(self):
        # "possible" is filtered out to the assertion queue, not terminology coding.
        # Use "present" -- the assertion that goes through _check_terminology_coding.
        entities = [
            {"text": "hypertension", "label": "disorder", "assertion": "present"}
        ]
        items, mock_tier = self._run(entities)
        assert mock_tier.called
        call_kwargs = mock_tier.call_args.kwargs
        assert call_kwargs["assertion"] == "present"

    def test_classify_tier_receives_score(self):
        entities = [{"text": "asthma", "label": "disorder", "assertion": "present"}]
        _, mock_tier = self._run(entities, score=0.55)
        call_kwargs = mock_tier.call_args.kwargs
        assert call_kwargs["terminology_score"] == pytest.approx(0.55)

    def test_surface_form_status_passed_from_entity(self):
        entities = [
            {
                "text": "T2DM",
                "label": "disorder",
                "assertion": "present",
                "surface_form_status": "approved",
            }
        ]
        _, mock_tier = self._run(entities)
        call_kwargs = mock_tier.call_args.kwargs
        assert call_kwargs["surface_form_status"] == "approved"

    def test_empty_surface_form_status_when_not_in_entity(self):
        entities = [{"text": "pain", "label": "finding", "assertion": "present"}]
        _, mock_tier = self._run(entities)
        call_kwargs = mock_tier.call_args.kwargs
        assert call_kwargs["surface_form_status"] == ""


# ---------------------------------------------------------------------------
# Cypher query structural checks
# ---------------------------------------------------------------------------


class TestUpsertCodingReviewQuery:
    def test_includes_decision_tier_param(self):
        from libs.cypher.coding_review_queries import UPSERT_CODING_REVIEW

        assert "$decision_tier" in UPSERT_CODING_REVIEW

    def test_includes_tier_reason_param(self):
        from libs.cypher.coding_review_queries import UPSERT_CODING_REVIEW

        assert "$tier_reason" in UPSERT_CODING_REVIEW

    def test_includes_tier_decision_param(self):
        from libs.cypher.coding_review_queries import UPSERT_CODING_REVIEW

        assert "$tier_decision" in UPSERT_CODING_REVIEW

    def test_still_has_all_original_params(self):
        from libs.cypher.coding_review_queries import UPSERT_CODING_REVIEW

        for param in (
            "$label_id",
            "$review_id",
            "$entity_text",
            "$coded",
            "$assertion",
        ):
            assert param in UPSERT_CODING_REVIEW, f"Missing {param}"


class TestGetCodingReviewQueueQuery:
    def test_returns_decision_tier(self):
        from libs.cypher.coding_review_queries import GET_CODING_REVIEW_QUEUE

        assert "decision_tier" in GET_CODING_REVIEW_QUEUE

    def test_returns_tier_reason(self):
        from libs.cypher.coding_review_queries import GET_CODING_REVIEW_QUEUE

        assert "tier_reason" in GET_CODING_REVIEW_QUEUE

    def test_returns_tier_decision(self):
        from libs.cypher.coding_review_queries import GET_CODING_REVIEW_QUEUE

        assert "tier_decision" in GET_CODING_REVIEW_QUEUE


class TestGroupCodingReviewsQuery:
    def test_returns_decision_tier(self):
        from libs.cypher.coding_review_queries import GROUP_CODING_REVIEWS_BY_ENTITY

        assert "decision_tier" in GROUP_CODING_REVIEWS_BY_ENTITY

    def test_orders_by_tier(self):
        from libs.cypher.coding_review_queries import GROUP_CODING_REVIEWS_BY_ENTITY

        assert "ORDER BY" in GROUP_CODING_REVIEWS_BY_ENTITY
        order_section = GROUP_CODING_REVIEWS_BY_ENTITY.split("ORDER BY")[1]
        assert "decision_tier" in order_section

    def test_uses_min_tier_aggregation(self):
        from libs.cypher.coding_review_queries import GROUP_CODING_REVIEWS_BY_ENTITY

        assert "min(coalesce(cr.decision_tier" in GROUP_CODING_REVIEWS_BY_ENTITY


class TestResolveCodingReviewQuery:
    def test_sets_reviewer_tier_override(self):
        from libs.cypher.coding_review_queries import RESOLVE_CODING_REVIEW

        assert "reviewer_tier_override" in RESOLVE_CODING_REVIEW

    def test_override_true_for_tier3(self):
        from libs.cypher.coding_review_queries import RESOLVE_CODING_REVIEW

        assert "decision_tier = 3" in RESOLVE_CODING_REVIEW

    def test_override_true_when_tier1_concept_differs(self):
        from libs.cypher.coding_review_queries import RESOLVE_CODING_REVIEW

        assert "decision_tier = 1" in RESOLVE_CODING_REVIEW


class TestGetTierOverrideStatsQuery:
    def test_query_exists(self):
        from libs.cypher.coding_review_queries import GET_TIER_OVERRIDE_STATS

        assert GET_TIER_OVERRIDE_STATS

    def test_groups_by_tier(self):
        from libs.cypher.coding_review_queries import GET_TIER_OVERRIDE_STATS

        assert "cr.decision_tier AS tier" in GET_TIER_OVERRIDE_STATS

    def test_counts_overrides(self):
        from libs.cypher.coding_review_queries import GET_TIER_OVERRIDE_STATS

        assert "reviewer_tier_override" in GET_TIER_OVERRIDE_STATS

    def test_computes_override_pct(self):
        from libs.cypher.coding_review_queries import GET_TIER_OVERRIDE_STATS

        assert "override_pct" in GET_TIER_OVERRIDE_STATS

    def test_orders_by_tier(self):
        from libs.cypher.coding_review_queries import GET_TIER_OVERRIDE_STATS

        assert "ORDER BY tier" in GET_TIER_OVERRIDE_STATS


# ---------------------------------------------------------------------------
# tier_calibration API endpoint
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# not_codeable action in escalate_coding_from_candidates
# ---------------------------------------------------------------------------


class TestNotCodeableAction:
    def _make_result(self, action: str, reason: str = "patient declined"):
        from libs.llm_client.escalation import CandidatesResult

        return CandidatesResult(action=action, reason=reason)

    def test_candidates_result_supports_not_codeable_action(self):
        from libs.llm_client.escalation import CandidatesResult

        r = CandidatesResult(
            action="not_codeable", reason="Patient declined the biopsy."
        )
        assert r.action == "not_codeable"
        assert "declined" in r.reason

    def test_escalate_coding_returns_not_codeable_when_llm_says_so(self):
        from unittest.mock import patch, MagicMock
        from libs.llm_client.escalation import escalate_coding_from_candidates

        mock_resp = MagicMock()
        mock_resp.text = (
            '{"action":"not_codeable","reason":"Patient declined the procedure."}'
        )
        mock_resp.model_id = "claude-haiku"

        mock_client = MagicMock()
        mock_client.converse.return_value = mock_resp

        with patch("libs.llm_client.escalation.create_llm", return_value=mock_client):
            result = escalate_coding_from_candidates(
                entity_text="biopsy",
                encounter_text="patient declined the biopsy",
                candidates=[
                    {"term": "Biopsy (procedure)", "snomed_concept_id": "86273004"}
                ],
            )

        assert result.action == "not_codeable"
        assert "declined" in result.reason.lower()

    def test_candidates_system_prompt_includes_not_codeable_action(self):
        from libs.llm_client.escalation import _CANDIDATES_SYSTEM

        assert "not_codeable" in _CANDIDATES_SYSTEM

    def test_candidates_system_prompt_directs_declined_to_search(self):
        from libs.llm_client.escalation import _CANDIDATES_SYSTEM

        assert "declined" in _CANDIDATES_SYSTEM.lower()
        assert "uk primary care" in _CANDIDATES_SYSTEM.lower()

    def test_candidates_system_prompt_directs_cancelled_to_search(self):
        from libs.llm_client.escalation import _CANDIDATES_SYSTEM

        assert "cancel" in _CANDIDATES_SYSTEM.lower()

    def test_candidates_system_prompt_mentions_awaiting(self):
        from libs.llm_client.escalation import _CANDIDATES_SYSTEM

        assert "awaiting" in _CANDIDATES_SYSTEM.lower()

    def test_ask_leo_smart_router_returns_assertion_warning_for_not_codeable(self):
        import pathlib

        # Ask-LEO Smart routing was extracted into a sibling module to keep
        # the main training router under the file-length limit; that sibling
        # is attached to coding_review.py (not training.py) since the
        # 2026-07 CTO peer-review item 2 core-api router decomposition.
        # Concatenate both modules so the test still proves the contract
        # holds somewhere in the training router surface.
        src = pathlib.Path("services/api/app/routers/coding_review.py").read_text(
            encoding="utf-8"
        ) + pathlib.Path("services/api/app/routers/_training_askleo.py").read_text(
            encoding="utf-8"
        )
        assert "assertion_warning" in src
        assert "not_codeable" in src

    def test_ask_leo_smart_response_includes_assertion_warning_field(self):
        import pathlib

        src = pathlib.Path("services/api/app/routers/coding_review.py").read_text(
            encoding="utf-8"
        ) + pathlib.Path("services/api/app/routers/_training_askleo.py").read_text(
            encoding="utf-8"
        )
        assert '"assertion_warning"' in src or "'assertion_warning'" in src


class TestTierCalibrationEndpointImport:
    """Verify the calibration query is importable and wired in the router source."""

    def test_get_tier_override_stats_importable(self):
        from libs.cypher.coding_review_queries import GET_TIER_OVERRIDE_STATS

        assert GET_TIER_OVERRIDE_STATS

    def test_router_source_references_tier_calibration_route(self):
        import inspect
        import importlib.util
        import pathlib

        # tier-calibration lives in coding_review.py, split out of
        # training.py in the 2026-07 CTO peer-review item 2: core-api
        # router decomposition.
        path = pathlib.Path("services/api/app/routers/coding_review.py")
        src = path.read_text(encoding="utf-8")
        assert "/coding-review/tier-calibration" in src

    def test_router_source_references_get_tier_override_stats(self):
        import pathlib

        path = pathlib.Path("services/api/app/routers/coding_review.py")
        src = path.read_text(encoding="utf-8")
        assert "GET_TIER_OVERRIDE_STATS" in src
