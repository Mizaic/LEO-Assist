"""Tests for reset review queue service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.reset_review_queue_service import reset_review_queue


class TestResetReviewQueueService:
    """Test reset review queue for a patient."""

    def test_reset_returns_deleted(self) -> None:
        session = MagicMock()
        session.run.return_value = MagicMock(single=MagicMock(return_value={"deleted": 12}))
        result = reset_review_queue("p1", session)
        assert result["patient_id"] == "p1"
        assert result["deleted"] == 12

    def test_reset_no_tasks_returns_zero(self) -> None:
        session = MagicMock()
        session.run.return_value = MagicMock(single=MagicMock(return_value={"deleted": 0}))
        result = reset_review_queue("p1", session)
        assert result["patient_id"] == "p1"
        assert result["deleted"] == 0
