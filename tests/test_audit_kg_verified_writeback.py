"""Tests for audit-verified KG writeback (DE-ID gate)."""

from unittest.mock import MagicMock, patch

import pytest

from libs.audit.kg_verified_writeback import write_audit_verified_to_kg


@pytest.fixture
def mock_kg_session():
    with patch("libs.audit.kg_verified_writeback.KnowledgeGraphClient") as cls:
        inst = MagicMock()
        cls.return_value = inst
        session = MagicMock()
        inst.session.return_value.__enter__ = MagicMock(return_value=session)
        inst.session.return_value.__exit__ = MagicMock(return_value=False)
        yield inst, session


def test_writeback_blocked_when_validator_finds_issues(mock_kg_session):
    inst, session = mock_kg_session
    with patch("libs.audit.kg_verified_writeback.DeIdValidator") as vcls:
        vcls.return_value.check_record.return_value = [
            MagicMock(issue_type="nhs_number"),
        ]
        out = write_audit_verified_to_kg(
            raw_encounter_text="NHS 123 456 7890 cough",
            coded_rows=[],
            quality_score=0.95,
            verified_by="audit_agent",
            assessment="no_clinical_content",
        )
    assert out["written"] is False
    assert out["deid_failed"] is True
    assert session.run.call_count >= 1
    inst.close.assert_called()


def test_writeback_stores_deidentified_text_not_raw_nhs(mock_kg_session):
    inst, session = mock_kg_session
    with patch("libs.audit.kg_verified_writeback.DeIdValidator") as vcls:
        vcls.return_value.check_record.return_value = []
        raw = "Reviewed patient 123 456 7890 -- cough settled."
        out = write_audit_verified_to_kg(
            raw_encounter_text=raw,
            coded_rows=[],
            quality_score=0.9,
            verified_by="audit_agent",
            assessment="no_issues",
        )
    assert out["written"] is True
    assert out["deid_failed"] is False
    texts = []
    for c in session.run.call_args_list:
        kw = getattr(c, "kwargs", {}) or {}
        if "text" in kw:
            texts.append(kw["text"])
    assert any("[NHS_NUMBER]" in t for t in texts)
    assert all("123 456 7890" not in t for t in texts)
    inst.close.assert_called()
