"""Unit tests for scripts/episode_v2/release_scorer.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from libs.episode_learning.champion_challenger import (
    EvaluationResult,
    PromotionDecision,
)
from libs.episode_learning.scorer_retrain import (
    DEFAULT_WEIGHTS,
    ScorerWeights,
)
from scripts.episode_v2.release_scorer import (
    ReleaseRecord,
    release_scorer,
)


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, cypher: str, **params: Any) -> Any:
        self.calls.append((cypher, params))
        return [{"version_id": params.get("version_id")}]


def _decision(promote: bool = True) -> PromotionDecision:
    base = EvaluationResult(
        label="champion",
        site_key="breast",
        precision=0.8,
        recall=0.8,
        f1=0.8,
        cases_evaluated=10,
    )
    new = EvaluationResult(
        label="challenger",
        site_key="breast",
        precision=0.9,
        recall=0.9,
        f1=0.9,
        cases_evaluated=10,
    )
    return PromotionDecision(
        promote=promote,
        rationale="ok" if promote else "no",
        champion=base,
        challenger=new,
    )


def _weights() -> ScorerWeights:
    return ScorerWeights(
        site_key="breast",
        weights=dict(DEFAULT_WEIGHTS),
        sample_count=15,
        learning_rate=0.2,
        iteration=2,
    )


def test_release_writes_one_node_with_versioned_id():
    runner = _FakeRunner()
    when = datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc)
    record = release_scorer(
        runner,
        weights=_weights(),
        decision=_decision(promote=True),
        released_by="agent",
        notes="phase 5 verification",
        released_at=when,
    )
    assert isinstance(record, ReleaseRecord)
    assert record.site_key == "breast"
    assert record.promoted is True
    assert record.released_at == when
    assert record.version_id.startswith("breast-2026-04-22-")
    assert len(runner.calls) == 1
    cypher, params = runner.calls[0]
    assert "MERGE (v:EpisodeScorerVersion" in cypher
    assert params["site_key"] == "breast"
    assert params["sample_count"] == 15
    assert params["promoted"] is True
    weights_payload = json.loads(params["weights_json"])
    assert weights_payload["code"] == DEFAULT_WEIGHTS["code"]
    eval_payload = json.loads(params["evaluation_json"])
    assert eval_payload["promote"] is True
    assert eval_payload["challenger"]["precision"] == 0.9


def test_release_records_non_promotion_decisions_too():
    runner = _FakeRunner()
    record = release_scorer(
        runner,
        weights=_weights(),
        decision=_decision(promote=False),
        released_by="agent",
    )
    assert record.promoted is False
    assert runner.calls[0][1]["promoted"] is False


def test_release_uses_now_when_released_at_omitted():
    runner = _FakeRunner()
    record = release_scorer(
        runner,
        weights=_weights(),
        decision=_decision(promote=True),
        released_by="agent",
    )
    assert record.released_at.tzinfo is not None
