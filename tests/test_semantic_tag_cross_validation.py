"""Tests for semantic tag cross-validation in the coding pipeline.

Covers:
- _cross_check_semantic_tag returns (None, None) when tags agree
- _cross_check_semantic_tag detects mismatches and returns suggested_label + delta
- _cross_check_semantic_tag ignores small deltas below _TAG_XVAL_MIN_DELTA
- _cross_check_semantic_tag handles empty / insufficient candidates
- _check_terminology_coding auto-reclassifies high-confidence mismatches
- _check_terminology_coding queues medium-confidence mismatches for HITL
- _check_terminology_coding uses unbiased resolve (no expected_tags)
- _build_review_item passes through suggested_label and tag_mismatch_delta
- Cypher queries include suggested_label and tag_mismatch_delta params
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _cross_check_semantic_tag
# ---------------------------------------------------------------------------


class TestCrossCheckSemanticTag:
    def _import(self):
        from services.api.app.services.label_verifier import _cross_check_semantic_tag

        return _cross_check_semantic_tag

    def test_agreement_returns_none(self):
        fn = self._import()
        candidates = [
            {"semantic_tag": "disorder", "score": 0.95},
            {"semantic_tag": "finding", "score": 0.60},
        ]
        suggested, delta = fn("disorder", candidates)
        assert suggested is None
        assert delta is None

    def test_mismatch_detected(self):
        fn = self._import()
        candidates = [
            {"semantic_tag": "observable entity", "score": 0.95},
            {"semantic_tag": "finding", "score": 0.60},
            {"semantic_tag": "disorder", "score": 0.40},
        ]
        suggested, delta = fn("finding", candidates)
        assert suggested == "observable_entity"
        assert delta == pytest.approx(0.35)

    def test_small_delta_ignored(self):
        fn = self._import()
        candidates = [
            {"semantic_tag": "disorder", "score": 0.85},
            {"semantic_tag": "finding", "score": 0.80},
        ]
        suggested, delta = fn("finding", candidates)
        assert suggested is None
        assert delta is None

    def test_empty_candidates(self):
        fn = self._import()
        suggested, delta = fn("finding", [])
        assert suggested is None
        assert delta is None

    def test_single_candidate_matching(self):
        fn = self._import()
        candidates = [{"semantic_tag": "finding", "score": 0.90}]
        suggested, delta = fn("finding", candidates)
        assert suggested is None
        assert delta is None

    def test_single_candidate_mismatching(self):
        fn = self._import()
        candidates = [{"semantic_tag": "observable entity", "score": 0.90}]
        suggested, delta = fn("finding", candidates)
        assert suggested == "observable_entity"
        assert delta == pytest.approx(0.90)

    def test_unknown_semantic_tag_skipped(self):
        fn = self._import()
        candidates = [
            {"semantic_tag": "totally_unknown_tag_xyz", "score": 0.95},
            {"semantic_tag": "disorder", "score": 0.50},
        ]
        suggested, delta = fn("disorder", candidates)
        assert suggested is None

    def test_none_semantic_tag_handled(self):
        fn = self._import()
        candidates = [
            {"semantic_tag": None, "score": 0.95},
            {"semantic_tag": "finding", "score": 0.50},
        ]
        suggested, delta = fn("finding", candidates)
        assert suggested is None
        assert delta is None

    def test_only_considers_top_3(self):
        """Candidates beyond index 2 should be ignored."""
        fn = self._import()
        candidates = [
            {"semantic_tag": "finding", "score": 0.80},
            {"semantic_tag": "finding", "score": 0.70},
            {"semantic_tag": "finding", "score": 0.60},
            {"semantic_tag": "observable entity", "score": 0.99},
        ]
        suggested, delta = fn("finding", candidates)
        assert suggested is None


# ---------------------------------------------------------------------------
# _check_terminology_coding — unbiased resolve + cross-validation
# ---------------------------------------------------------------------------


class TestCheckTerminologyCodingCrossValidation:
    def _run(
        self,
        entities,
        candidates_map,
        *,
        auto_reclassify_score=0.90,
        same_tag_ceiling=0.50,
    ):
        env_patches = {
            "TAG_XVAL_AUTO_RECLASSIFY_SCORE": str(auto_reclassify_score),
            "TAG_XVAL_SAME_TAG_CEILING": str(same_tag_ceiling),
        }
        with (
            patch(
                "services.api.app.services.label_verifier._resolve_terms_via_api",
                return_value=candidates_map,
            ) as mock_resolve,
            patch(
                "services.api.app.services.label_verifier.classify_tier"
            ) as mock_tier,
            patch.dict("os.environ", env_patches),
        ):
            from libs.coding_engine.tier_classifier import TierDecision

            mock_tier.return_value = TierDecision(
                tier=2, decision="code_with_flag", reason="medium_confidence"
            )

            from services.api.app.services.label_verifier import (
                _check_terminology_coding,
            )

            items = _check_terminology_coding("lbl1", entities, frozenset())

        return items, mock_resolve, mock_tier

    def test_unbiased_resolve_no_expected_tags(self):
        """The resolve call should NOT pass expected_tags."""
        entities = [
            {"text": "neutrophil count", "label": "finding", "assertion": "present"}
        ]
        candidates_map = {
            "neutrophil count": [
                {
                    "snomed_concept_id": "1000",
                    "snomed_term": "Neutrophil count",
                    "score": 0.95,
                    "semantic_tag": "observable entity",
                },
            ]
        }
        _, mock_resolve, _ = self._run(entities, candidates_map)
        mock_resolve.assert_called_once()
        call_kwargs = mock_resolve.call_args
        assert "expected_tags" not in (
            call_kwargs.kwargs or {}
        ), "expected_tags should not be passed"

    def test_tag_mismatch_queued_for_review(self):
        entities = [
            {"text": "neutrophil count", "label": "finding", "assertion": "present"}
        ]
        candidates_map = {
            "neutrophil count": [
                {
                    "snomed_concept_id": "1000",
                    "snomed_term": "Neutrophil count",
                    "score": 0.75,
                    "semantic_tag": "observable entity",
                },
                {
                    "snomed_concept_id": "1001",
                    "snomed_term": "Something",
                    "score": 0.40,
                    "semantic_tag": "finding",
                },
            ]
        }
        items, _, _ = self._run(entities, candidates_map)
        assert len(items) == 1
        assert items[0]["suggested_label"] == "observable_entity"
        assert items[0]["tag_mismatch_delta"] is not None
        assert items[0]["decision_tier"] == 2
        assert "semantic_tag_mismatch" in items[0]["tier_reason"]

    def test_auto_reclassification_high_confidence(self):
        """When top score >= 0.90 and delta >= threshold, entity label is auto-corrected."""
        entities = [
            {"text": "neutrophil count", "label": "finding", "assertion": "present"}
        ]
        candidates_map = {
            "neutrophil count": [
                {
                    "snomed_concept_id": "1000",
                    "snomed_term": "Neutrophil count",
                    "score": 0.95,
                    "semantic_tag": "observable entity",
                },
                {
                    "snomed_concept_id": "1001",
                    "snomed_term": "Something",
                    "score": 0.30,
                    "semantic_tag": "finding",
                },
            ]
        }
        items, _, _ = self._run(entities, candidates_map)
        # Auto-reclassified → entity passes the score threshold → no review item.
        assert len(items) == 0
        # Verify the entity itself was mutated.
        assert entities[0]["label"] == "observable_entity"

    def test_no_mismatch_passes_through(self):
        entities = [{"text": "asthma", "label": "disorder", "assertion": "present"}]
        candidates_map = {
            "asthma": [
                {
                    "snomed_concept_id": "195967001",
                    "snomed_term": "Asthma",
                    "score": 0.95,
                    "semantic_tag": "disorder",
                },
            ]
        }
        items, _, _ = self._run(entities, candidates_map)
        assert len(items) == 0


# ---------------------------------------------------------------------------
# _build_review_item — suggested_label and tag_mismatch_delta fields
# ---------------------------------------------------------------------------


class TestBuildReviewItemTagMismatch:
    def _import(self):
        from services.api.app.services.label_verifier import _build_review_item

        return _build_review_item

    def test_includes_suggested_label_when_provided(self):
        fn = self._import()
        item = fn(
            "lbl1",
            0,
            "neutrophil count",
            "finding",
            True,
            {
                "snomed_concept_id": "1000",
                "snomed_term": "Neutrophil count",
                "semantic_tag": "observable entity",
            },
            0.75,
            "present",
            decision_tier=2,
            tier_reason="semantic_tag_mismatch",
            suggested_label="observable_entity",
            tag_mismatch_delta=0.35,
        )
        assert item["suggested_label"] == "observable_entity"
        assert item["tag_mismatch_delta"] == pytest.approx(0.35)

    def test_omits_suggested_label_when_none(self):
        fn = self._import()
        item = fn("lbl1", 0, "asthma", "disorder", True, {}, 0.5, "present")
        assert "suggested_label" not in item
        assert "tag_mismatch_delta" not in item


# ---------------------------------------------------------------------------
# Cypher query structural checks
# ---------------------------------------------------------------------------


class TestCypherQueriesTagMismatchFields:
    def test_upsert_includes_suggested_label(self):
        from libs.cypher.coding_review_queries import UPSERT_CODING_REVIEW

        assert "$suggested_label" in UPSERT_CODING_REVIEW

    def test_upsert_includes_tag_mismatch_delta(self):
        from libs.cypher.coding_review_queries import UPSERT_CODING_REVIEW

        assert "$tag_mismatch_delta" in UPSERT_CODING_REVIEW

    def test_group_query_returns_suggested_label(self):
        from libs.cypher.coding_review_queries import GROUP_CODING_REVIEWS_BY_ENTITY

        assert "suggested_label" in GROUP_CODING_REVIEWS_BY_ENTITY

    def test_group_query_returns_tag_mismatch_delta(self):
        from libs.cypher.coding_review_queries import GROUP_CODING_REVIEWS_BY_ENTITY

        assert "tag_mismatch_delta" in GROUP_CODING_REVIEWS_BY_ENTITY

    def test_queue_query_returns_suggested_label(self):
        from libs.cypher.coding_review_queries import GET_CODING_REVIEW_QUEUE

        assert "suggested_label" in GET_CODING_REVIEW_QUEUE

    def test_queue_query_returns_tag_mismatch_delta(self):
        from libs.cypher.coding_review_queries import GET_CODING_REVIEW_QUEUE

        assert "tag_mismatch_delta" in GET_CODING_REVIEW_QUEUE

    def test_entity_query_returns_suggested_label(self):
        from libs.cypher.coding_review_queries import GET_CODING_REVIEW_FOR_ENTITY

        assert "suggested_label" in GET_CODING_REVIEW_FOR_ENTITY

    def test_entity_query_returns_tag_mismatch_delta(self):
        from libs.cypher.coding_review_queries import GET_CODING_REVIEW_FOR_ENTITY

        assert "tag_mismatch_delta" in GET_CODING_REVIEW_FOR_ENTITY
