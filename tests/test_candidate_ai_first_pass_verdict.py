"""VT-LEO-AI-200 -- AI first-pass verdict ladder.

Cases:
  TC-006: all rejected + no rail -> verdict='delete'.
  TC-007: at least one accepted -> verdict='pre_done' (regardless of rejected).
  TC-008: zero entities -> verdict='review' (zero_entities_safety_rail).
  TC-009: blocked assertion -> verdict='review' (blocked_assertion_safety_rail).
  TC-010: manual_gold_seed source -> verdict='review' (manual_seed_safety_rail).
"""

from __future__ import annotations

from services.api.app.services.candidate_ai_first_pass._types import (
    CodingOutcome,
    ExtractedEntity,
    ExtractionResult,
)
from services.api.app.services.candidate_ai_first_pass._verdict import (
    SAFETY_RAIL_LIVE_COMPLETED,
    classify_candidate,
)
from services.api.app.services.candidate_prune import (
    SAFETY_RAIL_BLOCKED_ASSERTION,
    SAFETY_RAIL_MANUAL_SEED,
    SAFETY_RAIL_ZERO_ENTITIES,
)


def _coding(text: str, label: str, *, accepted: bool, reason: str = "") -> CodingOutcome:
    return CodingOutcome(
        text=text,
        label=label,
        accepted=accepted,
        rejection_reason="" if accepted else (reason or "rejected"),
    )


def _candidate(*, status: str = "pending", source: str = "llm_extract") -> dict:
    return {
        "candidate_id": "c1",
        "status": status,
        "source": source,
        "text": "Some sentence.",
    }


def test_VT_194_TC_006_all_rejected_no_rail_routes_to_delete():
    extraction = ExtractionResult(
        entities=[
            ExtractedEntity(text="x", label="finding"),
            ExtractedEntity(text="y", label="procedure"),
        ]
    )
    codings = [
        _coding("x", "finding", accepted=False, reason="tag_mismatch"),
        _coding("y", "procedure", accepted=False, reason="surface_short"),
    ]
    out = classify_candidate(_candidate(), extraction, codings)
    assert out.verdict == "delete"
    assert out.accepted_count == 0
    assert out.rejected_count == 2
    assert "tag_mismatch" in out.rejection_reasons


def test_VT_194_TC_007_at_least_one_accepted_routes_to_pre_done():
    extraction = ExtractionResult(
        entities=[
            ExtractedEntity(text="diabetes", label="disorder"),
            ExtractedEntity(text="weight", label="finding"),
        ]
    )
    codings = [
        _coding("diabetes", "disorder", accepted=True),
        _coding("weight", "finding", accepted=False, reason="surface_short"),
    ]
    out = classify_candidate(_candidate(), extraction, codings)
    assert out.verdict == "pre_done"


def test_VT_194_TC_007b_all_accepted_also_pre_done():
    extraction = ExtractionResult(
        entities=[
            ExtractedEntity(text="diabetes", label="disorder"),
            ExtractedEntity(text="biopsy", label="procedure"),
        ]
    )
    codings = [
        _coding("diabetes", "disorder", accepted=True),
        _coding("biopsy", "procedure", accepted=True),
    ]
    out = classify_candidate(_candidate(), extraction, codings)
    assert out.verdict == "pre_done"


def test_VT_194_TC_008_zero_entities_routes_to_review():
    out = classify_candidate(
        _candidate(),
        ExtractionResult(entities=[]),
        codings=[],
    )
    assert out.verdict == "review"
    assert SAFETY_RAIL_ZERO_ENTITIES in out.rejection_reasons


def test_VT_194_TC_009_blocked_assertion_overrides_accepted_count():
    extraction = ExtractionResult(
        entities=[
            ExtractedEntity(text="chest pain", label="finding", assertion="absent"),
            ExtractedEntity(text="diabetes", label="disorder"),
        ]
    )
    codings = [
        _coding("chest pain", "finding", accepted=True),
        _coding("diabetes", "disorder", accepted=True),
    ]
    out = classify_candidate(_candidate(), extraction, codings)
    assert out.verdict == "review"
    assert SAFETY_RAIL_BLOCKED_ASSERTION in out.rejection_reasons


def test_VT_194_TC_010_manual_gold_seed_source_routes_to_review():
    extraction = ExtractionResult(
        entities=[ExtractedEntity(text="diabetes", label="disorder")]
    )
    codings = [_coding("diabetes", "disorder", accepted=True)]
    out = classify_candidate(
        _candidate(source="manual_gold_seed_2026_04_17"),
        extraction,
        codings,
    )
    assert out.verdict == "review"
    assert SAFETY_RAIL_MANUAL_SEED in out.rejection_reasons


def test_live_completed_status_routes_to_review():
    extraction = ExtractionResult(
        entities=[ExtractedEntity(text="x", label="finding")]
    )
    codings = [_coding("x", "finding", accepted=True)]
    out = classify_candidate(
        _candidate(status="completed"),
        extraction,
        codings,
    )
    assert out.verdict == "review"
    assert SAFETY_RAIL_LIVE_COMPLETED in out.rejection_reasons
