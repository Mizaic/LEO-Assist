"""Champion / challenger gating for the v2 site scorers.

Atlas trace:
  DI: DI-8A5FCF4F (12-component, defence-in-depth episode detector)

Wraps a deterministic evaluation step so a candidate ScorerWeights
vector ("challenger") is only promoted to production if it beats the
incumbent ("champion") on the labelled regression cohort by a
configurable margin.

The function is pure on the cohort + a per-set scorer callable so it
can be unit-tested without touching Neo4j.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from libs.episode_learning.scorer_retrain import ScorerWeights


@dataclass(frozen=True)
class CohortCase:
    """Single labelled case from the regression cohort."""

    patient_id: str
    site_key: str
    expected_episode_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationResult:
    """Per-scorer evaluation outcome on the regression cohort."""

    label: str
    site_key: str
    precision: float
    recall: float
    f1: float
    cases_evaluated: int

    def beats(self, other: "EvaluationResult", margin: float) -> bool:
        """Strictly beats the other scorer on both precision and recall."""
        return (
            self.precision >= other.precision + margin
            and self.recall >= other.recall + margin
        )


@dataclass(frozen=True)
class PromotionDecision:
    """Outcome of a champion / challenger evaluation."""

    promote: bool
    rationale: str
    champion: EvaluationResult
    challenger: EvaluationResult


ScorerFn = Callable[[CohortCase, ScorerWeights], set[str]]


def _safe_div(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _evaluate_one(
    label: str,
    site_key: str,
    cases: Iterable[CohortCase],
    scorer: ScorerFn,
    weights: ScorerWeights,
) -> EvaluationResult:
    relevant_cases = [c for c in cases if c.site_key == site_key]
    if not relevant_cases:
        return EvaluationResult(
            label=label,
            site_key=site_key,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            cases_evaluated=0,
        )
    tp = fp = fn = 0
    for case in relevant_cases:
        predicted = scorer(case, weights) or set()
        expected = set(case.expected_episode_ids)
        tp += len(predicted & expected)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return EvaluationResult(
        label=label,
        site_key=site_key,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        cases_evaluated=len(relevant_cases),
    )


def evaluate_challenger(
    cases: Iterable[CohortCase],
    *,
    site_key: str,
    champion_weights: ScorerWeights,
    challenger_weights: ScorerWeights,
    scorer: ScorerFn,
    promotion_margin: float = 0.02,
    min_cases: int = 5,
) -> PromotionDecision:
    """Decide whether the challenger should replace the champion.

    Both scorers are run against the cohort using the supplied
    per-case scorer function. The challenger is promoted only when
    it strictly beats the champion on both precision and recall by
    `promotion_margin` AND the cohort has at least `min_cases`
    relevant cases for the requested site.
    """
    case_list = list(cases)
    champion_eval = _evaluate_one(
        "champion", site_key, case_list, scorer, champion_weights
    )
    challenger_eval = _evaluate_one(
        "challenger", site_key, case_list, scorer, challenger_weights
    )
    if challenger_eval.cases_evaluated < min_cases:
        return PromotionDecision(
            promote=False,
            rationale=(
                f"insufficient cases: have "
                f"{challenger_eval.cases_evaluated}, need {min_cases}"
            ),
            champion=champion_eval,
            challenger=challenger_eval,
        )
    if challenger_eval.beats(champion_eval, promotion_margin):
        return PromotionDecision(
            promote=True,
            rationale=(
                f"challenger beats champion by >= {promotion_margin} on "
                "both precision and recall"
            ),
            champion=champion_eval,
            challenger=challenger_eval,
        )
    return PromotionDecision(
        promote=False,
        rationale="challenger did not beat champion by required margin",
        champion=champion_eval,
        challenger=challenger_eval,
    )


def serialise_decision(
    decision: PromotionDecision,
) -> Mapping[str, object]:
    """Convert a PromotionDecision into a JSON-friendly dict."""
    return {
        "promote": decision.promote,
        "rationale": decision.rationale,
        "champion": {
            "site_key": decision.champion.site_key,
            "precision": decision.champion.precision,
            "recall": decision.champion.recall,
            "f1": decision.champion.f1,
            "cases_evaluated": decision.champion.cases_evaluated,
        },
        "challenger": {
            "site_key": decision.challenger.site_key,
            "precision": decision.challenger.precision,
            "recall": decision.challenger.recall,
            "f1": decision.challenger.f1,
            "cases_evaluated": decision.challenger.cases_evaluated,
        },
    }
