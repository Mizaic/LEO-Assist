"""VT-LEO-AI-182 -- candidate_prune verdict ladder + safety rails.

Pins the verdict ladder defined by DI-LEO-AI-196:

  * zero entities                         -> verdict='review'
  * any _AUTO_CODE_BLOCKED assertion       -> verdict='review'
  * source startswith 'manual_gold_seed'   -> verdict='review'
  * every entity validator-rejected        -> verdict='delete'
  * every entity validator-accepted        -> verdict='keep'
  * mixed accept+reject                    -> verdict='review'

Plus the execute_prune TOCTOU re-check (status='completed' is skipped).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from services.api.app.services import candidate_prune as cp
from scripts.lib.gold_label_snomed_check import ValidationResult


# ---------- helpers ----------------------------------------------------------


def _entity(text: str, label: str, **extra) -> dict:
    base = {"text": text, "label": label, "semantic_tag": label}
    base.update(extra)
    return base


def _candidate(
    *,
    candidate_id: str,
    entities: list[dict],
    status: str = "pending",
    source: str = "pipeline_gold",
    text: str = "Example sentence for prune verdict.",
) -> dict:
    return {
        "candidate_id": candidate_id,
        "status": status,
        "source": source,
        "text": text,
        "entities_json": json.dumps(entities),
    }


def _accept(text: str, label: str) -> ValidationResult:
    return ValidationResult(
        accepted=True,
        reason="accepted_exact",
        surface_text=text,
        proposed_label=label,
        concept_id="123",
        snomed_term="Example",
    )


def _reject(text: str, label: str, reason: str = "tag_mismatch_all") -> ValidationResult:
    return ValidationResult(
        accepted=False,
        reason=reason,
        surface_text=text,
        proposed_label=label,
    )


@contextmanager
def _patch_validator(verdict_for):
    """Patch validate_proposal to return ``verdict_for(text, label)``."""

    def _side_effect(text, label, _client, **_kwargs):
        return verdict_for(text, label)

    with patch.object(cp, "validate_proposal", side_effect=_side_effect) as p:
        yield p


# ---------- assess_candidates: safety rails ---------------------------------


def test_zero_entities_routes_to_review_safety_rail():
    cand = _candidate(candidate_id="c-zero", entities=[])
    with _patch_validator(lambda t, l: _accept(t, l)) as v:
        out = cp.assess_candidates(
            client=MagicMock(),
            terminology=MagicMock(),
            params=cp.PruneParams(),
            candidates=[cand],
        )
    assert len(out) == 1
    a = out[0]
    assert a.verdict == "review"
    assert cp.SAFETY_RAIL_ZERO_ENTITIES in a.rejection_reasons
    assert v.call_count == 0


def test_blocked_assertion_routes_to_review_safety_rail():
    cand = _candidate(
        candidate_id="c-blocked",
        entities=[
            _entity("hydrocephalus", "finding", assertion="absent"),
            _entity("rash", "finding"),
        ],
    )
    with _patch_validator(lambda t, l: _reject(t, l)) as v:
        out = cp.assess_candidates(
            client=MagicMock(),
            terminology=MagicMock(),
            params=cp.PruneParams(),
            candidates=[cand],
        )
    a = out[0]
    assert a.verdict == "review"
    assert cp.SAFETY_RAIL_BLOCKED_ASSERTION in a.rejection_reasons
    assert v.call_count == 0  # fast-path, no resolver burn


def test_manual_gold_seed_source_routes_to_review_safety_rail():
    cand = _candidate(
        candidate_id="c-seed",
        source="manual_gold_seed_2026_04_17",
        entities=[_entity("eschar", "finding")],
    )
    with _patch_validator(lambda t, l: _reject(t, l)):
        out = cp.assess_candidates(
            client=MagicMock(),
            terminology=MagicMock(),
            params=cp.PruneParams(),
            candidates=[cand],
        )
    a = out[0]
    assert a.verdict == "review"
    assert cp.SAFETY_RAIL_MANUAL_SEED in a.rejection_reasons


# ---------- assess_candidates: validator-driven verdicts --------------------


def test_all_rejected_routes_to_delete():
    cand = _candidate(
        candidate_id="c-del",
        entities=[
            _entity("blah blah blah", "finding"),
            _entity("nonsense token", "procedure"),
        ],
    )
    with _patch_validator(lambda t, l: _reject(t, l)):
        out = cp.assess_candidates(
            client=MagicMock(),
            terminology=MagicMock(),
            params=cp.PruneParams(),
            candidates=[cand],
        )
    a = out[0]
    assert a.verdict == "delete"
    assert a.accepted_count == 0
    assert a.rejected_count == 2
    assert "tag_mismatch_all" in a.rejection_reasons


def test_all_accepted_routes_to_keep():
    cand = _candidate(
        candidate_id="c-keep",
        entities=[
            _entity("eschar", "finding"),
            _entity("biopsy", "procedure"),
        ],
    )
    with _patch_validator(lambda t, l: _accept(t, l)):
        out = cp.assess_candidates(
            client=MagicMock(),
            terminology=MagicMock(),
            params=cp.PruneParams(),
            candidates=[cand],
        )
    a = out[0]
    assert a.verdict == "keep"
    assert a.accepted_count == 2
    assert a.rejected_count == 0


def test_mixed_routes_to_review():
    cand = _candidate(
        candidate_id="c-mixed",
        entities=[
            _entity("eschar", "finding"),
            _entity("nonsense token", "procedure"),
        ],
    )

    def verdict(t, l):
        return _accept(t, l) if t == "eschar" else _reject(t, l)

    with _patch_validator(verdict):
        out = cp.assess_candidates(
            client=MagicMock(),
            terminology=MagicMock(),
            params=cp.PruneParams(),
            candidates=[cand],
        )
    a = out[0]
    assert a.verdict == "review"
    assert a.accepted_count == 1
    assert a.rejected_count == 1


def test_entity_with_empty_text_is_treated_as_rejected():
    cand = _candidate(
        candidate_id="c-empty",
        entities=[_entity("", "finding")],
    )
    with _patch_validator(lambda t, l: _accept(t, l)):
        out = cp.assess_candidates(
            client=MagicMock(),
            terminology=MagicMock(),
            params=cp.PruneParams(),
            candidates=[cand],
        )
    a = out[0]
    assert a.verdict == "delete"
    assert a.rejected_count == 1
    assert "empty_input" in a.rejection_reasons


def test_resolver_exception_is_caught_and_treated_as_rejected():
    cand = _candidate(
        candidate_id="c-err",
        entities=[_entity("eschar", "finding")],
    )

    def _boom(text, label, _client, **_kwargs):
        raise RuntimeError("terminology offline")

    with patch.object(cp, "validate_proposal", side_effect=_boom):
        out = cp.assess_candidates(
            client=MagicMock(),
            terminology=MagicMock(),
            params=cp.PruneParams(),
            candidates=[cand],
        )
    a = out[0]
    assert a.verdict == "delete"
    assert "resolver_error" in a.rejection_reasons


# ---------- summarise --------------------------------------------------------


def test_summarise_counts_by_verdict_and_reason():
    a1 = cp.CandidateAssessment(
        candidate_id="a",
        status="pending",
        source="pipeline_gold",
        text="t1",
        entity_count=2,
        accepted_count=0,
        rejected_count=2,
        blocked_assertion_count=0,
        verdict="delete",
        rejection_reasons=["tag_mismatch_all"],
    )
    a2 = cp.CandidateAssessment(
        candidate_id="b",
        status="pending",
        source="pipeline_gold",
        text="t2",
        entity_count=2,
        accepted_count=2,
        rejected_count=0,
        blocked_assertion_count=0,
        verdict="keep",
        rejection_reasons=[],
    )
    a3 = cp.CandidateAssessment(
        candidate_id="c",
        status="pending",
        source="pipeline_gold",
        text="t3",
        entity_count=1,
        accepted_count=0,
        rejected_count=0,
        blocked_assertion_count=0,
        verdict="review",
        rejection_reasons=[cp.SAFETY_RAIL_ZERO_ENTITIES],
    )
    summary = cp.summarise([a1, a2, a3])
    assert summary["candidate_count"] == 3
    assert summary["by_verdict"]["delete"] == 1
    assert summary["by_verdict"]["keep"] == 1
    assert summary["by_verdict"]["review"] == 1
    assert summary["by_rejection_reason"]["tag_mismatch_all"] == 1
    assert summary["by_rejection_reason"][cp.SAFETY_RAIL_ZERO_ENTITIES] == 1
    assert summary["entity_total"] == 5
    assert summary["entity_accepted"] == 2
    assert summary["entity_rejected"] == 2


# ---------- execute_prune ---------------------------------------------------


def _kg_with_session(run_side_effect):
    inner = MagicMock()
    inner.run.side_effect = run_side_effect
    kg = MagicMock()
    kg.session.return_value.__enter__ = lambda s: inner
    kg.session.return_value.__exit__ = MagicMock(return_value=False)
    return kg, inner


def test_execute_prune_skips_completed_candidates():
    """TOCTOU re-check: candidate flipped to 'completed' between preview and execute."""

    def run_side_effect(query, **kwargs):
        if "MATCH (c:TrainingCandidate {candidate_id" in query and "DETACH DELETE" not in query:
            return MagicMock(
                single=MagicMock(
                    return_value={"candidate_id": "c-1", "status": "completed"}
                )
            )
        # DETACH DELETE branch -- should never be hit
        return MagicMock(single=MagicMock(return_value={"candidate_id": "c-1"}))

    kg, inner = _kg_with_session(run_side_effect)
    outcome = cp.execute_prune(kg, ["c-1"])
    assert outcome.skipped_completed == ["c-1"]
    assert outcome.deleted == []
    # Only the GET was invoked, never the DELETE.
    assert inner.run.call_count == 1


def test_execute_prune_reports_not_found_when_candidate_missing():
    def run_side_effect(query, **kwargs):
        return MagicMock(single=MagicMock(return_value=None))

    kg, _ = _kg_with_session(run_side_effect)
    outcome = cp.execute_prune(kg, ["c-missing"])
    assert outcome.not_found == ["c-missing"]
    assert outcome.deleted == []
    assert outcome.skipped_completed == []


def test_execute_prune_deletes_pending_candidate_and_records_cascade_counts():
    state = {"step": 0}

    def run_side_effect(query, **kwargs):
        state["step"] += 1
        if state["step"] == 1:
            return MagicMock(
                single=MagicMock(
                    return_value={"candidate_id": "c-1", "status": "pending"}
                )
            )
        # Second call is the DETACH DELETE.
        return MagicMock(
            single=MagicMock(
                return_value={
                    "candidate_id": "c-1",
                    "gold_labels_deleted": 1,
                    "surface_form_tasks_deleted": 0,
                }
            )
        )

    kg, _ = _kg_with_session(run_side_effect)
    outcome = cp.execute_prune(kg, ["c-1"])
    assert outcome.deleted == ["c-1"]
    assert outcome.cascade_counts["c-1"]["gold_labels_deleted"] == 1
    assert outcome.cascade_counts["c-1"]["surface_form_tasks_deleted"] == 0


def test_execute_prune_handles_empty_request():
    kg = MagicMock()
    outcome = cp.execute_prune(kg, [])
    assert outcome.requested == []
    assert outcome.deleted == []
    kg.session.assert_not_called()


# ---------- fetch scope guard -----------------------------------------------


def test_fetch_non_completed_candidates_strips_completed_status():
    """Caller cannot inject 'completed' into the status filter."""
    captured: list[dict] = []

    def run_side_effect(query, **kwargs):
        captured.append(kwargs)
        return iter([])

    kg, _ = _kg_with_session(run_side_effect)
    cp.fetch_non_completed_candidates(
        kg, statuses=["pending", "completed"], limit=10
    )
    statuses_used = [c.get("status") for c in captured]
    assert "completed" not in statuses_used
    assert all(c.get("exclude_completed") is True for c in captured)
