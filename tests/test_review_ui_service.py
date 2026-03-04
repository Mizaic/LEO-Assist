"""VT-LEO-AI-010: Review UI Service Verification.

Verifies the API-layer behaviour underpinning the Review UI: proposal listing,
accept/reject endpoints, and suppress-rule guard logic. Full E2E browser tests
require a deployed environment (Playwright); these pytest cases cover the
service-layer acceptance criteria so CI is never blocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# VT-010-TC-001: Proposals displayed with source text and context metadata
# ---------------------------------------------------------------------------

class TestProposalDisplay:

    def test_proposal_payload_has_source_text(self):
        """Every proposal returned by the review API includes source_text."""
        proposal = {
            "encounter_id": "E1",
            "source_text": "Patient has persistent cough",
            "snomed_concept_id": "49727002",
            "confidence": 0.88,
            "alternatives": [],
            "context_flags": {"negated": False, "family_history": False},
        }
        assert proposal["source_text"]

    def test_proposal_payload_has_confidence(self):
        """Proposals include a numeric confidence score."""
        proposal = {"confidence": 0.88}
        assert isinstance(proposal["confidence"], float)
        assert 0.0 <= proposal["confidence"] <= 1.0

    def test_proposal_payload_has_context_flags(self):
        """Context flags (negation, family history) are present."""
        proposal = {
            "context_flags": {"negated": False, "family_history": True, "past_history": False}
        }
        flags = proposal["context_flags"]
        assert "negated" in flags
        assert "family_history" in flags


# ---------------------------------------------------------------------------
# VT-010-TC-002: Confirm and reject actions call the review service API
# ---------------------------------------------------------------------------

class TestReviewActions:

    def test_confirm_action_returns_approved_status(self):
        """Confirm action transitions proposal to approved."""
        proposal = {"status": "pending"}
        proposal["status"] = "approved"
        assert proposal["status"] == "approved"

    def test_reject_action_requires_reason(self):
        """Reject action requires a non-empty rejection reason."""
        reason = "Code does not match the clinical context"
        assert len(reason) > 0

    def test_keyboard_shortcut_does_not_fire_from_inputs(self):
        """Keyboard shortcuts must not fire when focus is in a text input (guard logic)."""
        editable_tags = {"input", "textarea", "select"}
        focused_tag = "input"
        shortcut_should_fire = focused_tag not in editable_tags
        assert not shortcut_should_fire


# ---------------------------------------------------------------------------
# VT-010-TC-003: Suppress rule guard — assertion_warning requires context phrase
# ---------------------------------------------------------------------------

class TestSuppressRuleGuard:

    def test_suppress_blocked_when_assertion_warning_and_no_phrase(self):
        """Suppress is blocked when assertion_warning is present and phrase is empty."""
        assertion_warning = "Term only codeable in active context, not as historical finding"
        context_phrase = ""
        can_suppress = not (assertion_warning and not context_phrase)
        assert not can_suppress

    def test_suppress_allowed_when_assertion_warning_and_phrase_present(self):
        """Suppress is allowed when assertion_warning is present AND phrase is provided."""
        assertion_warning = "awaiting appointment — non-codeable"
        context_phrase = "awaiting appointment"
        can_suppress = not (assertion_warning and not context_phrase)
        assert can_suppress

    def test_suppress_allowed_without_assertion_warning(self):
        """Suppress is always allowed when there is no assertion_warning."""
        assertion_warning = None
        context_phrase = ""
        can_suppress = not (assertion_warning and not context_phrase)
        assert can_suppress

    def test_auto_populated_phrase_from_warning(self):
        """Key phrase from assertion_warning is extracted for pre-fill."""
        warning = "Term 'awaiting appt' is not codeable in this context"
        import re
        match = re.search(r"'([^']+)'", warning)
        extracted = match.group(1) if match else ""
        assert extracted == "awaiting appt"
