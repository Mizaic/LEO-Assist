"""Stage 6 - Pair-linkage classifier training.

Atlas trace:
  DO: DO-9488B454
  DI: DI-D46D83FA
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-9488B454")

Binary head: P(same_pathway | pair_features). Pooled gold + silver positives
and negatives; class-weighted to oversample cancer_excluded positives.

v0 ships with sklearn LogisticRegression; LightGBM is a swap via the
classifier_factory parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

ClassifierFactory = Callable[..., Any]

# Operating points for tier assignment.
TIER_AUTO = 0.95
TIER_SUGGEST = 0.7


@dataclass
class LinkageTrainingResult:
    artifact_path: Path
    metrics: dict[str, float] = field(default_factory=dict)
    n_positive: int = 0
    n_negative: int = 0


def _default_factory():
    from sklearn.linear_model import LogisticRegression

    return LogisticRegression(max_iter=500, class_weight="balanced")


def train_linkage_classifier(
    training_rows: Iterable[dict],
    *,
    artifact_path: Path,
    classifier_factory: ClassifierFactory | None = None,
) -> LinkageTrainingResult:
    """Train binary linkage classifier and persist with joblib.

    Each ``training_rows`` element is expected to carry:
        - features: the dict from extract_pair_features.
        - label: 1 if same pathway, 0 otherwise.
        - weight: per-row weight (float). Cancer_excluded positives should
          arrive pre-oversampled to >=25% of the positive class.
    """
    import joblib
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.pipeline import Pipeline

    rows = list(training_rows)
    if not rows:
        raise ValueError("No linkage training rows provided.")

    features = [r["features"] for r in rows]
    labels = [int(r["label"]) for r in rows]
    weights = [float(r.get("weight", 1.0)) for r in rows]

    factory = classifier_factory or _default_factory
    pipeline = Pipeline(
        [("dictvec", DictVectorizer(sparse=True)), ("clf", factory())]
    )
    pipeline.fit(features, labels, clf__sample_weight=weights)

    metrics = _basic_metrics(pipeline, features, labels)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": pipeline,
            "metadata": {
                "metrics": metrics,
                "n_positive": sum(labels),
                "n_negative": len(labels) - sum(labels),
                "tier_auto": TIER_AUTO,
                "tier_suggest": TIER_SUGGEST,
            },
        },
        artifact_path,
    )
    return LinkageTrainingResult(
        artifact_path=artifact_path,
        metrics=metrics,
        n_positive=sum(labels),
        n_negative=len(labels) - sum(labels),
    )


def _basic_metrics(pipeline, X, y) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, roc_auc_score

    proba = pipeline.predict_proba(X)
    pos_probs = [p[1] for p in proba]
    return {
        "training_accuracy": float(accuracy_score(y, pipeline.predict(X))),
        "training_auc": float(roc_auc_score(y, pos_probs))
        if len(set(y)) > 1
        else 0.0,
    }
