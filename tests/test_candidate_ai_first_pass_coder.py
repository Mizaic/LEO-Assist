"""VT-LEO-AI-200 -- AI first-pass per-entity smart coder.

Cases:
  TC-003: ai_code_entity accepts on first try when validator passes.
  TC-004: ai_code_entity retries with Haiku alt-query when validator rejects.
  TC-005: ai_code_entity gives up after the configured retry cap.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.training.gold_label_snomed_check import ValidationResult
from services.api.app.services.candidate_ai_first_pass import _coder
from services.api.app.services.candidate_ai_first_pass._coder import ai_code_entity
from services.api.app.services.candidate_ai_first_pass._types import ExtractedEntity


def _accept(text: str, label: str) -> ValidationResult:
    return ValidationResult(
        accepted=True,
        reason="accepted_exact",
        surface_text=text,
        proposed_label=label,
        concept_id="123",
        snomed_term="Acute kidney injury",
        resolver_score=0.95,
        surface_match=0.9,
    )


def _reject(text: str, label: str, reason: str = "tag_mismatch") -> ValidationResult:
    return ValidationResult(
        accepted=False, reason=reason, surface_text=text, proposed_label=label
    )


def _terminology_with_rows(rows):
    t = MagicMock()
    t.search.return_value = rows
    return t


def test_VT_194_TC_003_accept_on_first_try_no_haiku_call():
    ent = ExtractedEntity(text="acute kidney injury", label="disorder")
    terminology = _terminology_with_rows([])

    haiku_calls = {"n": 0}

    def _haiku_should_not_be_called(**_kw):
        haiku_calls["n"] += 1
        return ("not_codeable", "")

    with patch.object(_coder, "validate_proposal", return_value=_accept(ent.text, ent.label)):
        outcome = ai_code_entity(
            ent,
            terminology,
            ask_haiku=_haiku_should_not_be_called,
        )

    assert outcome.accepted is True
    assert outcome.retries_used == 0
    assert outcome.snomed_concept_id == "123"
    assert outcome.snomed_term == "Acute kidney injury"
    assert haiku_calls["n"] == 0


def test_VT_194_TC_004_retry_with_alt_query_then_accept():
    ent = ExtractedEntity(text="ARF", label="disorder")
    terminology = _terminology_with_rows(
        [{"term": "Acute kidney injury", "snomed_concept_id": "14669001"}]
    )

    haiku_calls: list[dict] = []

    def _haiku(**kw):
        haiku_calls.append(kw)
        return ("search", "acute renal failure")

    seq = [_reject(ent.text, ent.label), _accept("acute renal failure", ent.label)]

    def _validate(text, label, _client, **_kw):
        return seq.pop(0)

    with patch.object(_coder, "validate_proposal", side_effect=_validate):
        outcome = ai_code_entity(
            ent,
            terminology,
            ask_haiku=_haiku,
        )

    assert outcome.accepted is True
    assert outcome.retries_used == 1
    assert outcome.alt_query_used == "acute renal failure"
    assert len(haiku_calls) == 1
    # Resolver search was called once for the alt-query (the first
    # validator pass uses the resolver internally; we check our own
    # search wrapper was invoked exactly once before the retry).
    assert terminology.search.call_count == 1


def test_VT_194_TC_005_retry_cap_exhausted():
    ent = ExtractedEntity(text="ckd", label="disorder")
    terminology = _terminology_with_rows(
        [{"term": "Chronic kidney disease", "snomed_concept_id": "709044004"}]
    )

    haiku_alt_queries = iter(["chronic renal disease", "renal failure chronic", "ckd stage 3"])

    def _haiku(**_kw):
        try:
            return ("search", next(haiku_alt_queries))
        except StopIteration:
            return ("search", "")

    def _always_reject(text, label, _client, **_kw):
        return _reject(text, label)

    with patch.object(_coder, "validate_proposal", side_effect=_always_reject):
        outcome = ai_code_entity(
            ent,
            terminology,
            ask_haiku=_haiku,
            max_retries=2,
        )

    assert outcome.accepted is False
    assert outcome.retries_used == 2
    assert outcome.rejection_reason.startswith("retry_cap_exhausted")


def test_haiku_not_codeable_short_circuits_no_more_retries():
    ent = ExtractedEntity(text="banana", label="disorder")
    terminology = _terminology_with_rows(
        [{"term": "Banana fruit", "snomed_concept_id": "9999"}]
    )

    haiku_calls = {"n": 0}

    def _haiku(**_kw):
        haiku_calls["n"] += 1
        return ("not_codeable", "")

    with patch.object(_coder, "validate_proposal", side_effect=lambda t, l, c, **k: _reject(t, l)):
        outcome = ai_code_entity(
            ent,
            terminology,
            ask_haiku=_haiku,
            max_retries=2,
        )

    assert outcome.accepted is False
    assert outcome.rejection_reason == "haiku_not_codeable"
    assert haiku_calls["n"] == 1


def test_no_resolver_candidates_short_circuits():
    ent = ExtractedEntity(text="zzqqww", label="disorder")
    terminology = _terminology_with_rows([])

    def _never_called(**_kw):
        raise AssertionError("Haiku must not be called when resolver returns nothing")

    with patch.object(_coder, "validate_proposal", side_effect=lambda t, l, c, **k: _reject(t, l)):
        outcome = ai_code_entity(
            ent,
            terminology,
            ask_haiku=_never_called,
            max_retries=2,
        )

    assert outcome.accepted is False
    assert outcome.rejection_reason.startswith("no_resolver_candidates")
