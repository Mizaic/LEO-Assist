"""Tests for the LLM coding verifier gate.

Atlas trace:
  VT: VT-C265FD93
  DI: DI-0EC8620E

Tests cover the six acceptance criteria defined in VT-C265FD93.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from libs.pipeline_graph.subgraphs.coding_verifier import (
    _apply_gate_failed,
    _apply_not_codeable,
    _apply_retry,
    _is_exact_match,
    _verify_entities,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_entity(
    text: str = "moderate left pleural effusion",
    concept_id: str = "12345678",
    term: str = "Pleural effusion",
    semantic_tag: str = "finding",
    score: float = 0.92,
    had_exact_match: bool = False,
    terminology_unresolved: bool = False,
) -> dict:
    return {
        "text": text,
        "concept_id": concept_id,
        "term": term,
        "semantic_tag": semantic_tag,
        "score": score,
        "had_exact_match": had_exact_match,
        "terminology_unresolved": terminology_unresolved,
        "read_code": "XE0WT",
    }


def _resolved_term_mock(concept_id: str, term: str, score: float = 0.80):
    rt = MagicMock()
    rt.concept_id = concept_id
    rt.term = term
    rt.semantic_tag = "finding"
    rt.score = score
    rt.read_code = None
    return rt


# ---------------------------------------------------------------------------
# _is_exact_match
# ---------------------------------------------------------------------------


def test_is_exact_match_with_flag():
    ent = _make_entity(had_exact_match=True)
    assert _is_exact_match(ent) is True


def test_is_exact_match_without_flag():
    ent = _make_entity(had_exact_match=False)
    assert _is_exact_match(ent) is False


# ---------------------------------------------------------------------------
# _apply_not_codeable
# ---------------------------------------------------------------------------


def test_apply_not_codeable_clears_code():
    ent = _make_entity()
    result = _apply_not_codeable(ent)
    assert result["terminology_unresolved"] is True
    assert result["concept_id"] is None
    assert result["term"] is None
    assert result["score"] == 0.0
    assert result["coding_verifier_verdict"] == "not_codeable"


# ---------------------------------------------------------------------------
# _apply_gate_failed
# ---------------------------------------------------------------------------


def test_apply_gate_failed_keeps_code_and_sets_tier_override():
    ent = _make_entity()
    result = _apply_gate_failed(ent)
    assert result["concept_id"] == ent["concept_id"]
    assert result["term"] == ent["term"]
    assert result["verifier_tier_override"] == 1
    assert result["coding_verifier_verdict"] == "gate_failed"


# ---------------------------------------------------------------------------
# _apply_retry
# ---------------------------------------------------------------------------


def test_apply_retry_succeeds_with_good_match():
    ent = _make_entity(
        text="marked internal vascularity",
        concept_id="999999",
        term="Finding of scleral vascularity",
    )
    mock_candidate = _resolved_term_mock("11111111", "Internal vascularity", 0.82)
    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.TerminologyClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.resolve.return_value = {
            "vascularity": [mock_candidate]
        }
        result = _apply_retry(ent, "vascularity", min_score=0.55)

    assert result["coding_verifier_verdict"] == "retry_accepted"
    assert result["concept_id"] == "11111111"
    assert result["term"] == "Internal vascularity"
    assert result["terminology_unresolved"] is False


def test_apply_retry_below_threshold_marks_unresolved():
    ent = _make_entity()
    mock_candidate = _resolved_term_mock("11111111", "Something", 0.40)
    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.TerminologyClient"
    ) as mock_client_cls:
        mock_client_cls.return_value.resolve.return_value = {
            "vascularity": [mock_candidate]
        }
        result = _apply_retry(ent, "vascularity", min_score=0.55)

    assert result["terminology_unresolved"] is True
    assert result["concept_id"] is None
    assert result["coding_verifier_verdict"] == "retry_no_match"


def test_apply_retry_no_term_marks_unresolved():
    ent = _make_entity()
    result = _apply_retry(ent, None, min_score=0.55)
    assert result["terminology_unresolved"] is True
    assert result["coding_verifier_verdict"] == "retry_no_term"


# ---------------------------------------------------------------------------
# _verify_entities - wrong domain entity is rejected
# ---------------------------------------------------------------------------


def test_verify_entities_wrong_domain_rejected():
    """Entity with wrong-domain code gets not_codeable verdict and loses concept_id."""
    wrong_domain_entity = _make_entity(
        text="marked internal vascularity",
        concept_id="370047000",
        term="Finding of scleral vascularity (finding)",
        had_exact_match=False,
    )
    state = {
        "entities": [wrong_domain_entity],
        "encounter_text": "Ultrasound ovary: marked internal vascularity noted.",
        "errors": [],
    }

    mock_verdicts = [
        {"index": 0, "verdict": "not_codeable", "better_term": None, "reason": "descriptor"}
    ]

    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch",
        return_value=mock_verdicts,
    ):
        result = _verify_entities(state)

    entities = result["entities"]
    assert entities[0]["terminology_unresolved"] is True
    assert entities[0]["concept_id"] is None
    assert entities[0]["coding_verifier_verdict"] == "not_codeable"
    warnings = result.get("warnings") or []
    assert any("not_codeable" in w for w in warnings)
    assert not (result.get("errors") or [])


# ---------------------------------------------------------------------------
# _verify_entities - correct code is preserved
# ---------------------------------------------------------------------------


def test_verify_entities_correct_code_preserved():
    """Entity with correct code gets accept verdict and keeps concept_id."""
    ent = _make_entity(
        text="pleural effusion",
        concept_id="60046008",
        term="Pleural effusion",
    )
    state = {
        "entities": [ent],
        "encounter_text": "Chest radiograph shows pleural effusion.",
        "errors": [],
    }

    mock_verdicts = [
        {"index": 0, "verdict": "accept", "better_term": None, "reason": "clinically correct"}
    ]

    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch",
        return_value=mock_verdicts,
    ):
        result = _verify_entities(state)

    entities = result["entities"]
    assert entities[0]["concept_id"] == "60046008"
    assert entities[0]["coding_verifier_verdict"] == "accept"


# ---------------------------------------------------------------------------
# _verify_entities - surface form exact matches bypass verifier
# ---------------------------------------------------------------------------


def test_verify_entities_exact_match_bypasses_verifier():
    """Surface-form exact matches are not passed to verify_coding_batch."""
    ent = _make_entity(had_exact_match=True)
    state = {
        "entities": [ent],
        "encounter_text": "Some text.",
        "errors": [],
    }

    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch"
    ) as mock_batch:
        result = _verify_entities(state)

    mock_batch.assert_not_called()
    assert result["entities"][0]["concept_id"] == ent["concept_id"]


# ---------------------------------------------------------------------------
# _verify_entities - gate_failed forces tier override
# ---------------------------------------------------------------------------


def test_verify_entities_gate_failed_sets_tier_override():
    ent = _make_entity()
    state = {
        "entities": [ent],
        "encounter_text": "Some text.",
        "errors": [],
    }

    mock_verdicts = [
        {"index": 0, "verdict": "gate_failed", "better_term": None, "reason": "parse error"}
    ]

    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch",
        return_value=mock_verdicts,
    ):
        result = _verify_entities(state)

    entities = result["entities"]
    assert entities[0]["concept_id"] == ent["concept_id"]
    assert entities[0]["verifier_tier_override"] == 1
    assert entities[0]["coding_verifier_verdict"] == "gate_failed"


# ---------------------------------------------------------------------------
# _verify_entities - single batch call for N entities
# ---------------------------------------------------------------------------


def test_verify_entities_single_batch_call_for_multiple():
    """Subgraph calls verify_coding_batch once; sub-batching is internal."""
    entities = [
        _make_entity(text="pleural effusion", concept_id=f"c{i}")
        for i in range(5)
    ]
    state = {
        "entities": entities,
        "encounter_text": "Clinical text.",
        "errors": [],
    }
    mock_verdicts = [
        {"index": i, "verdict": "accept", "better_term": None, "reason": "ok"}
        for i in range(5)
    ]

    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch",
        return_value=mock_verdicts,
    ) as mock_batch:
        _verify_entities(state)

    mock_batch.assert_called_once()
    call_entities = mock_batch.call_args[0][0]
    assert len(call_entities) == 5


# ---------------------------------------------------------------------------
# libs.llm_client.coding_verifier -- batch size / response caps
# ---------------------------------------------------------------------------


def test_coding_verifier_response_cap_scales_with_batch():
    from libs.llm_client.coding_verifier import _response_cap, _token_budget

    assert _response_cap(5) < _response_cap(40)
    assert _response_cap(40) >= 8_000
    assert _token_budget(40) > 2_000
    assert _token_budget(40) <= 8_000


def test_coding_verifier_splits_large_batches():
    """Large entity lists are verified in sub-batches under the response cap."""
    from libs.llm_client.coding_verifier import (
        _SUB_BATCH_SIZE,
        verify_coding_batch,
    )

    entities = [
        {
            "text": f"finding {i}",
            "term": f"Finding {i}",
            "concept_id": str(1000 + i),
            "semantic_tag": "finding",
        }
        for i in range(_SUB_BATCH_SIZE + 5)
    ]
    call_sizes: list[int] = []

    class _FakeResult:
        def __init__(self, count: int):
            self.verdict = [
                {
                    "index": i,
                    "verdict": "accept",
                    "better_term": None,
                    "reason": "ok",
                }
                for i in range(count)
            ]

    def _fake_consensus(**kwargs):
        payload = json.loads(kwargs["user_msg"])
        count = len(payload["proposed_codes"])
        call_sizes.append(count)
        return _FakeResult(count)

    with patch(
        "libs.llm_client.coding_verifier.run_consensus",
        side_effect=_fake_consensus,
    ):
        verdicts = verify_coding_batch(entities, "clinical text")

    assert call_sizes == [_SUB_BATCH_SIZE, 5]
    assert len(verdicts) == len(entities)
    assert [v["index"] for v in verdicts] == list(range(len(entities)))
