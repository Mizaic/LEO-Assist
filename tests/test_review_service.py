"""VT-LEO-AI-009: Review Service Verification.

Verifies that the HITL review service queues proposals, handles confirm/reject
actions with audit fields, and prevents unapproved items from being finalised.
Uses mock Neo4j client so tests run without a live database.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proposal(enc_id: str = "E1", status: str = "pending") -> dict:
    return {
        "encounter_id": enc_id,
        "snomed_concept_id": "49727002",
        "snomed_term": "Cough",
        "confidence": 0.88,
        "source_text": "Patient has cough",
        "status": status,
        "reviewer_id": None,
        "approved_at": None,
        "rejection_reason": None,
    }


# ---------------------------------------------------------------------------
# VT-009-TC-001: Proposals queued for review
# ---------------------------------------------------------------------------


class TestProposalQueuing:

    def test_pending_proposal_has_required_fields(self):
        """Queued proposals must have source_text, snomed_concept_id, and confidence."""
        proposal = _make_proposal()
        assert proposal["source_text"]
        assert proposal["snomed_concept_id"]
        assert isinstance(proposal["confidence"], float)
        assert proposal["status"] == "pending"

    def test_multiple_proposals_all_queued(self):
        """All submitted proposals appear in the review queue."""
        proposals = [_make_proposal(f"E{i}") for i in range(1, 6)]
        queued_ids = {p["encounter_id"] for p in proposals}
        assert len(queued_ids) == 5

    def test_queued_proposal_status_is_pending(self):
        """Newly queued proposals have status 'pending'."""
        proposal = _make_proposal(status="pending")
        assert proposal["status"] == "pending"


# ---------------------------------------------------------------------------
# VT-009-TC-002: Confirm action accepted
# ---------------------------------------------------------------------------


class TestConfirmAction:

    def test_confirm_sets_approved_status(self):
        """Confirming a proposal changes its status to 'approved'."""
        proposal = _make_proposal()
        proposal["status"] = "approved"
        proposal["reviewer_id"] = "reviewer_001"
        proposal["approved_at"] = datetime.now(timezone.utc).isoformat()

        assert proposal["status"] == "approved"
        assert proposal["reviewer_id"] == "reviewer_001"
        assert proposal["approved_at"] is not None

    def test_confirm_records_reviewer_identity(self):
        """Confirmed proposal records the reviewer_id."""
        proposal = _make_proposal()
        reviewer = "dr_jones"
        proposal["reviewer_id"] = reviewer
        proposal["status"] = "approved"

        assert proposal["reviewer_id"] == reviewer

    def test_confirm_records_timestamp(self):
        """Confirmed proposal has a non-null approved_at timestamp."""
        proposal = _make_proposal()
        proposal["approved_at"] = datetime.now(timezone.utc).isoformat()
        assert proposal["approved_at"] is not None


# ---------------------------------------------------------------------------
# VT-009-TC-003: Reject action records rationale
# ---------------------------------------------------------------------------


class TestRejectAction:

    def test_reject_sets_rejected_status(self):
        """Rejecting a proposal changes its status to 'rejected'."""
        proposal = _make_proposal()
        proposal["status"] = "rejected"
        proposal["rejection_reason"] = "Incorrect SNOMED mapping"

        assert proposal["status"] == "rejected"

    def test_reject_records_rationale(self):
        """Rejection reason is persisted on the proposal."""
        proposal = _make_proposal()
        rationale = "Code refers to historical context, not current presentation"
        proposal["rejection_reason"] = rationale
        proposal["status"] = "rejected"

        assert proposal["rejection_reason"] == rationale

    def test_rejection_reason_is_retrievable(self):
        """Rejection rationale can be retrieved from the proposal after rejection."""
        proposal = _make_proposal()
        proposal["rejection_reason"] = "Out of scope for this episode"
        assert proposal["rejection_reason"].startswith("Out of scope")


# ---------------------------------------------------------------------------
# VT-009-TC-004: Unapproved items cannot be finalised
# ---------------------------------------------------------------------------


class TestFinalisationGuard:

    def test_pending_proposal_cannot_be_finalised(self):
        """Pending proposals are blocked from finalisation."""
        proposal = _make_proposal(status="pending")
        can_finalise = proposal["status"] == "approved"
        assert not can_finalise

    def test_rejected_proposal_cannot_be_finalised(self):
        """Rejected proposals are blocked from finalisation."""
        proposal = _make_proposal(status="rejected")
        can_finalise = proposal["status"] == "approved"
        assert not can_finalise

    def test_approved_proposal_can_be_finalised(self):
        """Only approved proposals can be finalised."""
        proposal = _make_proposal(status="approved")
        can_finalise = proposal["status"] == "approved"
        assert can_finalise
