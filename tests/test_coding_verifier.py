"""Tests for the LLM coding verifier gate.

Atlas trace:
  VT: VT-C265FD93
  DI: DI-0EC8620E

Tests cover the six acceptance criteria defined in VT-C265FD93.
"""

from __future__ import annotations

import json
from unittest.mock import patch

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
    coding_candidates: list | None = None,
) -> dict:
    entity = {
        "text": text,
        "concept_id": concept_id,
        "term": term,
        "semantic_tag": semantic_tag,
        "score": score,
        "had_exact_match": had_exact_match,
        "terminology_unresolved": terminology_unresolved,
        "read_code": "XE0WT",
    }
    if coding_candidates is not None:
        entity["coding_candidates"] = coding_candidates
    return entity


def _candidate(concept_id: str, term: str, tag: str = "finding", score: float = 0.80):
    return {
        "concept_id": concept_id,
        "term": term,
        "semantic_tag": tag,
        "score": score,
    }


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


def test_apply_retry_is_retired_and_leaves_uncoded():
    ent = _make_entity()
    result = _apply_retry(ent, "vascularity", min_score=0.55)
    assert result["terminology_unresolved"] is True
    assert result["concept_id"] is None
    assert result["coding_verifier_verdict"] == "retry_retired"


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
        {
            "index": 0,
            "verdict": "not_codeable",
            "better_term": None,
            "reason": "descriptor",
        }
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
        {
            "index": 0,
            "verdict": "accept",
            "better_term": None,
            "reason": "clinically correct",
        }
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
        {
            "index": 0,
            "verdict": "gate_failed",
            "better_term": None,
            "reason": "parse error",
        }
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
        _make_entity(text="pleural effusion", concept_id=f"c{i}") for i in range(5)
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


def test_verify_entities_accepts_selected_shortlist_index():
    candidates = [
        _candidate("247348008", "Tenderness", score=0.90),
        _candidate("30473006", "Pelvic pain", score=0.84),
        _candidate("247404004", "Pain in pelvis", score=0.80),
    ]
    ent = _make_entity(
        text="pelvic pain",
        concept_id="247348008",
        term="Tenderness",
        coding_candidates=candidates,
    )
    state = {
        "entities": [ent],
        "encounter_text": "Patient reports pelvic pain.",
        "errors": [],
    }
    mock_verdicts = [
        {
            "index": 0,
            "verdict": "accept",
            "selected_index": 1,
            "reason": "second candidate matches pelvic pain",
        }
    ]

    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch",
        return_value=mock_verdicts,
    ):
        result = _verify_entities(state)

    chosen = result["entities"][0]
    assert chosen["concept_id"] == "30473006"
    assert chosen["term"] == "Pelvic pain"
    assert chosen["coding_verifier_verdict"] == "accept"
    assert chosen["terminology_unresolved"] is False


def test_verify_entities_reject_all_leaves_uncoded():
    candidates = [
        _candidate("227420009", "Gelatin", tag="substance", score=0.88),
        _candidate("412457006", "Jelly", tag="substance", score=0.80),
    ]
    ent = _make_entity(
        text="Vaseline",
        concept_id="227420009",
        term="Gelatin",
        semantic_tag="substance",
        coding_candidates=candidates,
    )
    state = {
        "entities": [ent],
        "encounter_text": "Uses Vaseline (petroleum jelly).",
        "errors": [],
    }
    mock_verdicts = [
        {
            "index": 0,
            "verdict": "reject_all",
            "selected_index": None,
            "reason": "none match petroleum jelly",
        }
    ]

    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch",
        return_value=mock_verdicts,
    ):
        result = _verify_entities(state)

    chosen = result["entities"][0]
    assert chosen["terminology_unresolved"] is True
    assert chosen["concept_id"] is None
    assert chosen["coding_verifier_verdict"] == "reject_all"


def test_verify_entities_empty_shortlist_skips_llm():
    ent = _make_entity(
        text="Vaseline",
        concept_id="227420009",
        term="Gelatin",
        coding_candidates=[],
    )
    state = {
        "entities": [ent],
        "encounter_text": "Uses Vaseline.",
        "errors": [],
    }

    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch"
    ) as mock_batch:
        result = _verify_entities(state)

    mock_batch.assert_not_called()
    assert result["entities"][0]["terminology_unresolved"] is True
    assert result["entities"][0]["concept_id"] is None


def test_user_message_includes_coding_candidates():
    from libs.llm_client.coding_verifier import _build_user_message

    payload = json.loads(
        _build_user_message(
            [
                {
                    "text": "pelvic pain",
                    "term": "Pelvic pain",
                    "concept_id": "30473006",
                    "semantic_tag": "finding",
                    "coding_candidates": [
                        _candidate("30473006", "Pelvic pain"),
                        _candidate("247348008", "Tenderness"),
                    ],
                }
            ],
            "Patient reports pelvic pain.",
        )
    )
    item = payload["proposed_codes"][0]
    assert len(item["candidates"]) == 2
    assert item["candidates"][1]["term"] == "Tenderness"
