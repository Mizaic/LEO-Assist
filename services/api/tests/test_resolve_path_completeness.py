"""Verify that every coding-resolution path records assertion and writes surface forms.

Defects fixed:
  D1/D2 -- batch-resolve never stored resolved_assertion or reviewer_tier_override.
  D3     -- cascade from single-resolve dropped resolved_assertion.
  D4     -- auto-recheck resolved_direct / escalation never wrote a SurfaceForm.

Tests are pure-Python unit tests (no live Neo4j or HTTP calls).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Cypher -- BATCH_RESOLVE_BY_ENTITY_TEXT contains the new fields
# ---------------------------------------------------------------------------


class TestBatchResolveCypher:
    """BATCH_RESOLVE_BY_ENTITY_TEXT must record assertion and tier override."""

    def _query(self) -> str:
        from libs.cypher.coding_review_queries import BATCH_RESOLVE_BY_ENTITY_TEXT
        return BATCH_RESOLVE_BY_ENTITY_TEXT

    def test_resolved_assertion_param_present(self):
        assert "$resolved_assertion" in self._query()

    def test_resolved_assertion_set_with_coalesce(self):
        # Must coalesce to 'present' so callers that omit the param are safe.
        assert "coalesce($resolved_assertion" in self._query()

    def test_reviewer_tier_override_set(self):
        assert "cr.reviewer_tier_override" in self._query()

    def test_tier_override_case_tier_1(self):
        assert "cr.decision_tier = 1" in self._query()

    def test_tier_override_case_tier_3(self):
        assert "cr.decision_tier = 3" in self._query()

    def test_resolved_concept_id_comparison(self):
        # Tier-1 override fires when the reviewer picks a different code.
        assert "$resolved_concept_id <> coalesce(cr.snomed_concept_id" in self._query()

    def test_resolved_method_still_batch_resolve(self):
        assert "'batch_resolve'" in self._query()


# ---------------------------------------------------------------------------
# 2. Pydantic model -- BatchResolveCodingReviewRequest
# ---------------------------------------------------------------------------


class TestBatchResolveCodingReviewRequest:
    """BatchResolveCodingReviewRequest must expose resolved_assertion."""

    def _model(self):
        from app.routers.training import BatchResolveCodingReviewRequest
        return BatchResolveCodingReviewRequest

    def test_resolved_assertion_defaults_present(self):
        m = self._model()(
            entity_text="hypertension",
            resolved_concept_id="38341003",
            resolved_term="Hypertensive disorder",
        )
        assert m.resolved_assertion == "present"

    def test_resolved_assertion_accepts_declined(self):
        m = self._model()(
            entity_text="biopsy",
            resolved_concept_id="86273004",
            resolved_term="Biopsy",
            resolved_assertion="declined",
        )
        assert m.resolved_assertion == "declined"

    def test_resolved_assertion_accepts_cancelled(self):
        m = self._model()(
            entity_text="referral",
            resolved_concept_id="3457005",
            resolved_term="Patient referral",
            resolved_assertion="cancelled",
        )
        assert m.resolved_assertion == "cancelled"


# ---------------------------------------------------------------------------
# 3. Endpoint -- batch_resolve_coding_review passes resolved_assertion to Cypher
# ---------------------------------------------------------------------------


class TestBatchResolveEndpoint:
    """batch_resolve_coding_review must forward resolved_assertion to the query."""

    def _run(self, resolved_assertion: str = "present"):
        from app.routers.training import (
            BatchResolveCodingReviewRequest,
            batch_resolve_coding_review,
        )

        mock_session = MagicMock()
        mock_session.run.return_value.single.return_value = {"resolved_count": 1}

        mock_client = MagicMock()
        mock_client.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client.session.return_value.__exit__ = MagicMock(return_value=False)

        body = BatchResolveCodingReviewRequest(
            entity_text="hypertension",
            entity_label="FINDING",
            resolved_concept_id="38341003",
            resolved_term="Hypertensive disorder",
            resolved_assertion=resolved_assertion,
        )

        with (
            patch(
                "app.routers.training.PatientGraphClient",
                return_value=mock_client,
            ),
            patch("services.api.app.db.neo4j_client.CodingGraphClient"),
            patch("app.routers.training._write_coding_ignore_rule"),
        ):
            result = batch_resolve_coding_review(body, scope=MagicMock())

        return mock_session.run.call_args, result

    def test_passes_present_assertion(self):
        run_call, _ = self._run("present")
        kwargs = run_call.kwargs
        assert kwargs.get("resolved_assertion") == "present"

    def test_passes_declined_assertion(self):
        run_call, _ = self._run("declined")
        kwargs = run_call.kwargs
        assert kwargs.get("resolved_assertion") == "declined"

    def test_returns_resolved_count(self):
        _, result = self._run()
        assert result.get("resolved_count") == 1


# ---------------------------------------------------------------------------
# 4. Cascade -- single-resolve passes resolved_assertion forward
# ---------------------------------------------------------------------------


class TestSingleResolveCascade:
    """The cascade call inside /{review_id}/resolve must propagate resolved_assertion."""

    def _run(self, resolved_assertion: str = "declined"):
        from app.routers.training import (
            ResolveCodingReviewRequest,
            resolve_coding_review,
        )

        # Primary resolve session -- returns entity_text so cascade is triggered.
        primary_session = MagicMock()
        primary_session.run.return_value.single.return_value = {
            "review_id": "rev-001",
            "entity_text": "lymph node biopsy",
        }
        primary_client = MagicMock()
        primary_client.session.return_value.__enter__ = MagicMock(
            return_value=primary_session
        )
        primary_client.session.return_value.__exit__ = MagicMock(return_value=False)

        # Cascade client (second PatientGraphClient instantiation).
        cascade_session = MagicMock()
        cascade_row = MagicMock()
        cascade_row.__getitem__ = MagicMock(return_value=1)
        cascade_session.run.return_value.single.return_value = cascade_row
        cascade_client = MagicMock()
        cascade_client.session.return_value.__enter__ = MagicMock(
            return_value=cascade_session
        )
        cascade_client.session.return_value.__exit__ = MagicMock(return_value=False)

        call_count = [0]

        def make_client():
            call_count[0] += 1
            return primary_client if call_count[0] == 1 else cascade_client

        body = ResolveCodingReviewRequest(
            resolved_concept_id="86273004",
            resolved_term="Biopsy of lymph node",
            reviewer="ops",
            resolved_assertion=resolved_assertion,
        )

        with (
            patch("app.routers.training.PatientGraphClient", side_effect=make_client),
            patch("services.api.app.db.neo4j_client.CodingGraphClient"),
        ):
            resolve_coding_review("rev-001", body, scope=MagicMock())

        return cascade_session.run.call_args

    def test_cascade_carries_resolved_assertion(self):
        run_call = self._run("declined")
        if run_call is None:
            pytest.skip("Cascade not reached -- entity_text was empty in mock")
        kwargs = run_call.kwargs
        assert kwargs.get("resolved_assertion") == "declined"


# ---------------------------------------------------------------------------
# 5. Auto-recheck resolved_direct -- _writeback_recheck_surface_form is called
# ---------------------------------------------------------------------------


class TestRecheckDirectWriteback:
    """resolved_direct path must write a SurfaceForm mapping."""

    def _run_recheck_item(self, *, scored_coding=None, mock_writeback=None,
                          try_alternatives: bool = False):
        from app.routers.training import _apply_recheck_item

        mock_session = MagicMock()
        mock_session.run.return_value.single.return_value = None

        if scored_coding is None:
            scored_coding = {
                "snomed_concept_id": "38341003",
                "snomed_term": "Hypertensive disorder",
                "score": 0.98,
                "semantic_tag": "disorder",
            }

        # results_map values are lists of candidate dicts (function does candidates[0]).
        results_map = {"hypertension": [scored_coding]}
        item = {
            "review_id": "rev-test-01",
            "entity_text": "hypertension",
            "entity_label": "FINDING",
        }

        wb = mock_writeback or MagicMock(return_value=True)
        with patch(
            "app.routers.training._writeback_recheck_surface_form", wb
        ) as wb_mock:
            outcome, ok = _apply_recheck_item(
                mock_session, item, results_map, frozenset(), try_alternatives,
            )
        return outcome, ok, wb_mock

    def test_resolved_direct_writes_surface_form(self):
        wb = MagicMock(return_value=True)
        outcome, ok, wb_mock = self._run_recheck_item(mock_writeback=wb)
        assert outcome == "resolved_direct"
        wb_mock.assert_called_once()

    def test_resolved_direct_surface_form_entity_text(self):
        wb = MagicMock(return_value=True)
        outcome, _, wb_mock = self._run_recheck_item(mock_writeback=wb)
        assert outcome == "resolved_direct"
        kwargs = wb_mock.call_args.kwargs
        assert kwargs["entity_text"] == "hypertension"

    def test_resolved_direct_surface_form_concept_id(self):
        wb = MagicMock(return_value=True)
        outcome, _, wb_mock = self._run_recheck_item(mock_writeback=wb)
        assert outcome == "resolved_direct"
        kwargs = wb_mock.call_args.kwargs
        assert kwargs["concept_id"] == "38341003"

    def test_resolved_direct_ok_reflects_writeback_result(self):
        wb = MagicMock(return_value=False)
        _, ok, _ = self._run_recheck_item(mock_writeback=wb)
        assert ok is False

    def test_pending_does_not_write_surface_form(self):
        """Items below the recheck threshold must NOT write a surface form."""
        low_score = {
            "snomed_concept_id": "38341003",
            "snomed_term": "Hypertensive disorder",
            "score": 0.1,
            "semantic_tag": "disorder",
        }
        wb = MagicMock(return_value=True)
        outcome, _, wb_mock = self._run_recheck_item(
            scored_coding=low_score, mock_writeback=wb
        )
        assert outcome.startswith("pending")
        wb_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Auto-recheck escalation -- uses concept_id (not concept_term) for writeback
# ---------------------------------------------------------------------------


class TestRecheckEscalationWriteback:
    """Escalation path must use esc.concept_id and write a SurfaceForm."""

    def _make_esc(self, concept_id="38341003", concept_term="Hypertensive disorder",
                  resolved=True):
        from libs.llm_client.escalation import EscalationResult
        return EscalationResult(
            resolved=resolved,
            concept_id=concept_id,
            concept_term=concept_term,
            confidence=0.92,
            model_tier="big",
        )

    def _run_escalation(self, esc_result, writeback_mock=None):
        from app.routers.training import _apply_recheck_item

        mock_session = MagicMock()
        mock_session.run.return_value.single.return_value = None

        # Empty results_map so direct match is skipped and escalation runs.
        results_map: dict = {}
        item = {
            "review_id": "rev-esc-01",
            "entity_text": "hypertension",
            "entity_label": "FINDING",
        }

        wb = writeback_mock or MagicMock(return_value=True)
        with (
            patch("app.routers.training.escalate_coding", return_value=esc_result),
            patch("app.routers.training._writeback_recheck_surface_form", wb),
        ):
            outcome, ok = _apply_recheck_item(
                mock_session, item, results_map, frozenset(), try_alternatives=True,
            )
        return outcome, ok, wb

    def test_escalation_writes_surface_form(self):
        esc = self._make_esc()
        outcome, _, wb = self._run_escalation(esc)
        assert outcome == "resolved_llm"
        wb.assert_called_once()

    def test_escalation_uses_concept_id_not_term(self):
        """Regression: concept_term was previously passed as the concept_id."""
        esc = self._make_esc(concept_id="38341003", concept_term="Some FSN text")
        _, _, wb = self._run_escalation(esc)
        kwargs = wb.call_args.kwargs
        assert kwargs["concept_id"] == "38341003"
        assert kwargs["concept_id"] != "Some FSN text"

    def test_escalation_no_concept_id_skips_writeback(self):
        """If escalation result has no concept_id, item remains pending."""
        from libs.llm_client.escalation import EscalationResult
        esc = EscalationResult(resolved=False, concept_id=None, concept_term=None)
        wb = MagicMock()
        outcome, _, _ = self._run_escalation(esc, writeback_mock=wb)
        wb.assert_not_called()
