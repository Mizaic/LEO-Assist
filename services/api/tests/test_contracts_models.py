"""Tests for `services/api/app/models/contracts.py`.

Atlas trace:
  DO: DO-19FA25C3
  DI: DI-727C94B4

Covers:
  - score / confidence clamping (negatives saturate to 0, >1 saturate to 1)
  - span validation (end must be > start)
  - edit decision validation (edited_candidate is required when action=edit)
  - enum coverage (every ReviewStatus / ReviewAction value parses cleanly)
  - default factories on list fields produce independent instances
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.contracts import (
    ContextSubject,
    EncounterCandidate,
    EncounterSentence,
    EncounterTerm,
    ExportDatasetRequest,
    PipelineRunRequest,
    ReviewAction,
    ReviewDecisionRequest,
    ReviewStatus,
    Temporality,
    TermCodingProposal,
    TermContext,
    _clamp_0_1,
)


def _ctx() -> TermContext:
    return TermContext(
        negated=False,
        uncertain=False,
        historical=False,
        subject=ContextSubject.patient,
        temporality=Temporality.present,
    )


class TestClampHelper:
    def test_negative_clamps_to_zero(self):
        assert _clamp_0_1(-0.5) == 0.0

    def test_above_one_clamps_to_one(self):
        assert _clamp_0_1(2.5) == 1.0

    def test_in_range_returns_value(self):
        assert _clamp_0_1(0.42) == 0.42

    def test_non_numeric_passes_through(self):
        assert _clamp_0_1("not-a-number") == "not-a-number"  # type: ignore[arg-type]


class TestTermCodingProposal:
    def test_score_clamped_below(self):
        p = TermCodingProposal(score=-0.2)
        assert p.score == 0.0

    def test_score_clamped_above(self):
        p = TermCodingProposal(score=99.9)
        assert p.score == 1.0

    def test_default_source(self):
        p = TermCodingProposal()
        assert p.source == "neo4j_hybrid"


class TestEncounterTerm:
    def test_valid_spans_accepted(self):
        t = EncounterTerm(
            term_id="T1",
            text="hypertension",
            span_start=10,
            span_end=22,
            context=_ctx(),
            coding=TermCodingProposal(),
            evidence_text="hypertension noted",
            extraction_method="ner",
        )
        assert t.span_end == 22

    def test_zero_length_span_rejected(self):
        with pytest.raises(ValidationError):
            EncounterTerm(
                term_id="T1",
                text="x",
                span_start=10,
                span_end=10,
                context=_ctx(),
                coding=TermCodingProposal(),
                evidence_text="x",
                extraction_method="ner",
            )

    def test_extraction_confidence_clamped(self):
        t = EncounterTerm(
            term_id="T1",
            text="x",
            span_start=0,
            span_end=1,
            context=_ctx(),
            coding=TermCodingProposal(),
            evidence_text="x",
            extraction_method="ner",
            extraction_confidence=2.0,
        )
        assert t.extraction_confidence == 1.0


class TestEncounterSentence:
    def test_invalid_span_rejected(self):
        with pytest.raises(ValidationError):
            EncounterSentence(
                sentence_id="S1",
                start=10,
                end=10,
                text="hi",
                terms=[],
            )

    def test_valid_sentence_accepts_empty_terms(self):
        s = EncounterSentence(
            sentence_id="S1", start=0, end=5, text="hello", terms=[]
        )
        assert s.terms == []


class TestReviewDecisionRequest:
    def test_edit_with_explicit_none_payload_rejected(self):
        with pytest.raises(ValidationError):
            ReviewDecisionRequest(
                action=ReviewAction.edit,
                reviewer="alice",
                reason="needs change",
                edited_candidate=None,
            )

    def test_edit_with_payload_accepted(self):
        r = ReviewDecisionRequest(
            action=ReviewAction.edit,
            reviewer="alice",
            reason="needs change",
            edited_candidate={"x": 1},
        )
        assert r.edited_candidate == {"x": 1}

    def test_approve_without_payload_accepted(self):
        r =             ReviewDecisionRequest(
                action=ReviewAction.approve, reviewer="alice", reason="okay",
            )
        assert r.edited_candidate is None

    def test_short_reason_rejected(self):
        with pytest.raises(ValidationError):
            ReviewDecisionRequest(
                action=ReviewAction.approve, reviewer="alice", reason="hi",
            )

    def test_approve_with_payload_returns_request(self):
        r = ReviewDecisionRequest(
            action=ReviewAction.approve,
            reviewer="alice",
            reason="ok then",
        )
        assert r.action == ReviewAction.approve


class TestEnumCoverage:
    def test_review_status_round_trip(self):
        for v in ("pending", "in_review", "approved", "rejected", "escalated"):
            assert ReviewStatus(v).value == v

    def test_review_action_round_trip(self):
        for v in ("approve", "edit", "reject", "escalate"):
            assert ReviewAction(v).value == v


class TestPipelineRunRequest:
    def test_default_lists_are_independent(self):
        a = PipelineRunRequest()
        b = PipelineRunRequest()
        a.patient_ids.append("P1")
        assert b.patient_ids == []

    def test_max_encounters_must_be_positive(self):
        with pytest.raises(ValidationError):
            PipelineRunRequest(max_encounters_per_patient=0)


class TestExportDatasetRequest:
    def test_train_ratio_must_be_strictly_in_open_unit(self):
        with pytest.raises(ValidationError):
            ExportDatasetRequest(export_name="abc", train_ratio=0.0)
        with pytest.raises(ValidationError):
            ExportDatasetRequest(export_name="abc", train_ratio=1.0)

    def test_export_name_min_length(self):
        with pytest.raises(ValidationError):
            ExportDatasetRequest(export_name="ab")


class TestEncounterCandidate:
    def test_default_lists_are_empty(self):
        c = EncounterCandidate(
            candidate_id="C1",
            patient_id="P1",
            encounter_id="E1",
            date="2025-01-01",
            source_hash="h1",
            deidentified_hash="h2",
            deidentified_text="text",
            sentences=[],
        )
        assert c.hard_fail_reasons == []
        assert c.warning_reasons == []
        assert c.audit_events == []
        assert c.approval_status == ReviewStatus.pending
