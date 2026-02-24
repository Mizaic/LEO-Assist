"""Tests for reset service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.reset_service import reset_patient


class TestResetService:
    """Test reset patient DOCUMENTS."""

    def test_reset_returns_links_deleted(self) -> None:
        session = MagicMock()
        session.run.side_effect = [
            [{"patient_id": "p1", "encounter_count": 2}],
            MagicMock(single=MagicMock(return_value={"links_deleted": 5})),
            MagicMock(single=MagicMock(return_value={"direct_deleted": 2})),
        ]
        result = reset_patient("p1", session)
        assert result["patient_id"] == "p1"
        assert result["links_deleted"] == 7
        assert "error" not in result

    def test_reset_patient_not_found(self) -> None:
        session = MagicMock()
        session.run.return_value = []
        result = reset_patient("nonexistent", session)
        assert result["patient_id"] == "nonexistent"
        assert result["links_deleted"] == 0
        assert result["error"] == "patient_not_found"

    def test_reset_no_documents_returns_zero(self) -> None:
        session = MagicMock()
        session.run.side_effect = [
            [{"patient_id": "p1", "encounter_count": 2}],
            MagicMock(single=MagicMock(return_value=None)),
            MagicMock(single=MagicMock(return_value={"direct_deleted": 0})),
        ]
        result = reset_patient("p1", session)
        assert result["patient_id"] == "p1"
        assert result["links_deleted"] == 0
