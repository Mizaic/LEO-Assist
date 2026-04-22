"""Unit tests for libs/episode_learning/champion_challenger.py."""

from __future__ import annotations

from libs.episode_learning.champion_challenger import (
    CohortCase,
    PromotionDecision,
    evaluate_challenger,
    serialise_decision,
)
from libs.episode_learning.scorer_retrain import (
    DEFAULT_WEIGHTS,
    ScorerWeights,
)


def _weights(site_key: str = "breast", code: float = 1.0) -> ScorerWeights:
    weights = dict(DEFAULT_WEIGHTS)
    weights["code"] = code
    return ScorerWeights(
        site_key=site_key,
        weights=weights,
        sample_count=10,
        learning_rate=0.1,
        iteration=1,
    )


def _cases(n: int) -> list[CohortCase]:
    return [
        CohortCase(
            patient_id=f"p-{i}",
            site_key="breast",
            expected_episode_ids=(f"ep-{i}",),
        )
        for i in range(n)
    ]


def test_promotion_when_challenger_strictly_better():
    cases = _cases(8)
    champion = _weights(code=0.5)
    challenger = _weights(code=1.0)

    def scorer(case, weights):
        if weights.weights["code"] > 0.7:
            return {f"ep-{int(case.patient_id.split('-')[1])}"}
        return set()

    decision = evaluate_challenger(
        cases,
        site_key="breast",
        champion_weights=champion,
        challenger_weights=challenger,
        scorer=scorer,
        promotion_margin=0.01,
        min_cases=5,
    )
    assert isinstance(decision, PromotionDecision)
    assert decision.promote is True
    assert decision.challenger.recall == 1.0
    assert decision.champion.recall == 0.0


def test_no_promotion_when_below_min_cases():
    cases = _cases(2)
    decision = evaluate_challenger(
        cases,
        site_key="breast",
        champion_weights=_weights(),
        challenger_weights=_weights(),
        scorer=lambda c, w: set(c.expected_episode_ids),
        min_cases=5,
    )
    assert decision.promote is False
    assert "insufficient cases" in decision.rationale


def test_no_promotion_when_challenger_only_marginally_better():
    cases = _cases(10)

    def scorer(case, weights):
        # Champion gets 9 of 10 right, challenger gets all 10 right.
        if weights.weights["code"] > 0.9 or int(
            case.patient_id.split("-")[1]
        ) < 9:
            return {f"ep-{int(case.patient_id.split('-')[1])}"}
        return set()

    decision = evaluate_challenger(
        cases,
        site_key="breast",
        champion_weights=_weights(code=0.5),
        challenger_weights=_weights(code=1.0),
        scorer=scorer,
        promotion_margin=0.5,  # require huge margin
        min_cases=5,
    )
    assert decision.promote is False
    assert "did not beat" in decision.rationale


def test_irrelevant_site_cases_are_filtered_out():
    cases = _cases(6) + [
        CohortCase(
            patient_id="p-x",
            site_key="lung",
            expected_episode_ids=("ep-x",),
        )
    ]
    decision = evaluate_challenger(
        cases,
        site_key="breast",
        champion_weights=_weights(),
        challenger_weights=_weights(),
        scorer=lambda c, w: set(c.expected_episode_ids),
        min_cases=5,
    )
    assert decision.champion.cases_evaluated == 6
    assert decision.challenger.cases_evaluated == 6


def test_serialise_decision_round_trips_to_jsonable_dict():
    cases = _cases(6)
    decision = evaluate_challenger(
        cases,
        site_key="breast",
        champion_weights=_weights(),
        challenger_weights=_weights(code=1.5),
        scorer=lambda c, w: set(c.expected_episode_ids),
        min_cases=5,
    )
    payload = serialise_decision(decision)
    assert payload["promote"] is False  # equal scores -> no promotion
    assert payload["champion"]["site_key"] == "breast"
    assert payload["challenger"]["cases_evaluated"] == 6
