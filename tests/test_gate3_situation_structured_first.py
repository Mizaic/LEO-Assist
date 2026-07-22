"""Gate 3 D3.1-D3.2 -- structured-first Situation."""

from __future__ import annotations

from libs.sbar.situation_source import (
    ReferralReasonEvidence,
    build_structured_situation,
    reason_evidence_to_dict,
)


def test_prefers_referral_request_reason() -> None:
    result = build_structured_situation(
        referral_request={
            "id": "rr-1",
            "reason": "Suspected gall bladder malignancy.",
            "priority": "urgent",
        },
        referral_reason=None,
        trigger_scoped_letter="Unrelated attachment prose.",
        run_id="run-1",
    )
    assert "gall bladder" in result.headline.lower()
    assert result.source_precedence == ["referral_request.reason"]
    assert result.referral_reason is not None
    assert result.letter_extract is None


def test_persists_referral_reason_evidence_with_provenance() -> None:
    evidence = ReferralReasonEvidence(
        reason_text="Progressive dysphagia.",
        source_type="Chunk",
        source_id="chunk-1",
        chunk_id="chunk-1",
        evidence_text="Reason for referral: progressive dysphagia.",
        run_id="run-1",
    )
    payload = reason_evidence_to_dict(evidence)
    assert payload["chunk_id"] == "chunk-1"
    assert payload["run_id"] == "run-1"
    assert payload["result_version"] == "1.0"
