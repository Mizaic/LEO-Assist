"""Per-site logistic-regression weight update for the v2 scorer.

Atlas trace:
  DI: DI-8A5FCF4F (12-component, defence-in-depth episode detector)

The v2 detector's evidence aggregator combines five signal channels
into a single score per (candidate, encounter). v1 uses fixed
weights; this module retrains those weights from labelled
CorrectionEvent rows using a single-step batch gradient update on a
logistic-regression model.

The output is a ScorerWeights dataclass that downstream code can
load via libs.feature_flags / config so the live detector picks up
the new weights without a redeploy.

Pure module: no Neo4j calls. correction_capture.py reads the audit
trail; release_scorer.py writes the new ScorerWeights to the graph.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from libs.episode_learning.correction_capture import CorrectionEvent

CHANNELS = ("code", "text", "pathway", "result", "treatment")

DEFAULT_WEIGHTS: dict[str, float] = {
    "code": 1.0,
    "text": 0.4,
    "pathway": 0.8,
    "result": 0.9,
    "treatment": 0.6,
    "bias": -0.2,
}


@dataclass(frozen=True)
class ScorerWeights:
    """Per-site weight vector for the v2 evidence aggregator."""

    site_key: str
    weights: dict[str, float]
    sample_count: int
    learning_rate: float
    iteration: int = 1
    notes: str = ""

    @classmethod
    def default_for(cls, site_key: str) -> "ScorerWeights":
        return cls(
            site_key=site_key,
            weights=dict(DEFAULT_WEIGHTS),
            sample_count=0,
            learning_rate=0.0,
            iteration=0,
            notes="default",
        )


@dataclass
class _FeatureVector:
    """Per-event feature row passed to the gradient step."""

    label: int
    features: dict[str, float] = field(default_factory=dict)


def _features_from_event(event: CorrectionEvent) -> _FeatureVector:
    """Map a CorrectionEvent to a feature vector keyed by channel name.

    The feature value for a channel is 1.0 if the correction's
    correction_target maps onto that channel, 0.0 otherwise. The
    bias feature is always 1.0.
    """
    target_to_channels = {
        "detector_boundary": {"pathway", "code", "result"},
        "coding_decision": {"code", "result"},
        "canonical_code": {"code"},
        "sbar_text": {"text"},
        "other": set(),
    }
    active_channels = target_to_channels.get(event.correction_target, set())
    feats: dict[str, float] = {ch: 1.0 if ch in active_channels else 0.0
                               for ch in CHANNELS}
    feats["bias"] = 1.0
    return _FeatureVector(label=int(event.label), features=feats)


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _gradient_step(
    weights: dict[str, float],
    rows: list[_FeatureVector],
    learning_rate: float,
) -> dict[str, float]:
    """One full-batch gradient update on a logistic-regression model.

    Updates are clamped to +/- 0.5 per step to keep weights stable
    when a site has very few correction events. The bias term is
    updated alongside the channels.
    """
    if not rows:
        return dict(weights)
    grads: dict[str, float] = {key: 0.0 for key in weights}
    for row in rows:
        z = sum(weights.get(k, 0.0) * v for k, v in row.features.items())
        prediction = _sigmoid(z)
        error = prediction - row.label
        for key, value in row.features.items():
            grads[key] = grads.get(key, 0.0) + error * value
    n = float(len(rows))
    new_weights: dict[str, float] = {}
    for key, value in weights.items():
        delta = learning_rate * grads.get(key, 0.0) / n
        delta = max(-0.5, min(0.5, delta))
        new_weights[key] = value - delta
    return new_weights


def retrain_site_scorer(
    events: Iterable[CorrectionEvent],
    *,
    site_key: str,
    base_weights: Mapping[str, float] | None = None,
    learning_rate: float = 0.2,
    iteration: int = 1,
) -> ScorerWeights:
    """Retrain the per-site scorer from a list of CorrectionEvent rows.

    Drops events that are not for the requested site. Returns the
    base weights unchanged if there are no usable events. The result
    keeps the feature-channel order constant so downstream callers
    can persist a stable weight vector.
    """
    site_events = [e for e in events if e.site_key == site_key]
    base = dict(base_weights or DEFAULT_WEIGHTS)
    if not site_events:
        return ScorerWeights(
            site_key=site_key,
            weights=base,
            sample_count=0,
            learning_rate=learning_rate,
            iteration=iteration,
            notes="no events for site; weights unchanged",
        )
    rows = [_features_from_event(e) for e in site_events]
    new_weights = _gradient_step(base, rows, learning_rate)
    return ScorerWeights(
        site_key=site_key,
        weights=new_weights,
        sample_count=len(site_events),
        learning_rate=learning_rate,
        iteration=iteration,
    )
