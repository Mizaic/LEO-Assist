"""Stage 4 - Encounter role classifier training.

Trains a multi-class classifier over {ftr, seen, dx, treatment, none} plus a
binary sub-head for Dx outcome {cancer_found, cancer_excluded}.

v0 ships with scikit-learn LogisticRegression for portability; the
training contract allows LightGBM (or any sklearn-compatible classifier)
to be plugged in via ``classifier_factory``.

Output artifact: a joblib-serialised dict containing:
  - role_pipeline: TF-IDF + DictVectorizer + classifier for the role head.
  - dx_outcome_pipeline: same shape but trained only on dx-labelled rows.
  - archetypes: per-role vector means used at inference for vector-delta
    features.
  - calibration: per-class isotonic breakpoints (sparse, sklearn-free).
  - metadata: training counts, F1 per class, feature schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from services.analysis_worker.app.ncda_detector.role_features import (
    NCDA_ROLES,
    compute_role_archetypes,
    extract_features,
)

ClassifierFactory = Callable[..., Any]


@dataclass
class TrainingResult:
    """Aggregate output from train_role_classifier."""

    artifact_path: Path
    role_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    outcome_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    n_rows_gold: int = 0
    n_rows_silver: int = 0


def _default_classifier_factory():
    """Build the v0 sklearn classifier. Replaceable with LightGBM."""
    from sklearn.linear_model import LogisticRegression

    return LogisticRegression(max_iter=500)


def _build_pipeline(classifier_factory: ClassifierFactory):
    """Build a sklearn pipeline that union-features TF-IDF text + dict feats.

    Pipeline steps:
      1. FeatureUnion of text TF-IDF and structured dict features.
      2. Classifier (default: LogisticRegression).
    """
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion, Pipeline

    text_features = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=1500,
        min_df=1,
        max_df=0.95,
        lowercase=True,
        strip_accents="unicode",
    )
    dict_features = DictVectorizer(sparse=True)

    union = FeatureUnion(
        transformer_list=[
            ("text", _TextSelector("__text__", text_features)),
            ("dict", _DictSelector("__features__", dict_features)),
        ]
    )
    return Pipeline([("features", union), ("clf", classifier_factory())])


class _TextSelector:
    """Extracts the text from each row (List[Dict]) for a TF-IDF transformer."""

    def __init__(self, key: str, transformer):
        self.key = key
        self.transformer = transformer

    def fit(self, X, y=None):
        texts = [row[self.key] for row in X]
        self.transformer.fit(texts, y)
        return self

    def transform(self, X):
        texts = [row[self.key] for row in X]
        return self.transformer.transform(texts)

    def fit_transform(self, X, y=None):
        return self.fit(X, y).transform(X)


class _DictSelector:
    """Extracts the structured feature dict and DictVectorises."""

    def __init__(self, key: str, transformer):
        self.key = key
        self.transformer = transformer

    def fit(self, X, y=None):
        feats = [row[self.key] for row in X]
        self.transformer.fit(feats, y)
        return self

    def transform(self, X):
        feats = [row[self.key] for row in X]
        return self.transformer.transform(feats)

    def fit_transform(self, X, y=None):
        return self.fit(X, y).transform(X)


def _row_to_pipeline_input(
    row: dict,
    archetypes: dict[str, list[float]] | None,
) -> dict:
    feats = extract_features(
        text=row.get("text") or "",
        flags=row.get("flags"),
        encounter_date=row.get("encounter_date"),
        vector=row.get("vector"),
        archetypes=archetypes,
    )
    return {
        "__text__": row.get("text") or "",
        "__features__": feats,
    }


def train_role_classifier(
    gold_rows: Iterable[dict],
    silver_rows: Iterable[dict],
    *,
    artifact_path: Path,
    classifier_factory: ClassifierFactory | None = None,
) -> TrainingResult:
    """Train role and dx-outcome heads; persist artifact via joblib."""
    import joblib

    gold = list(gold_rows)
    silver = list(silver_rows)
    if not gold and not silver:
        raise ValueError("No training rows provided.")

    archetypes = compute_role_archetypes(gold + silver)
    factory = classifier_factory or _default_classifier_factory

    role_X, role_y, role_w = _build_role_dataset(gold, silver, archetypes)
    role_pipeline = _build_pipeline(factory)
    role_pipeline.fit(role_X, role_y, **_sample_weight_kwargs(role_w))
    role_metrics = _per_class_metrics(role_pipeline, role_X, role_y)

    outcome_metrics: dict[str, dict[str, float]] = {}
    outcome_pipeline = None
    dx_X, dx_y, dx_w = _build_outcome_dataset(gold, silver, archetypes)
    if dx_X and len(set(dx_y)) >= 2:
        outcome_pipeline = _build_pipeline(factory)
        outcome_pipeline.fit(dx_X, dx_y, **_sample_weight_kwargs(dx_w))
        outcome_metrics = _per_class_metrics(outcome_pipeline, dx_X, dx_y)

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "role_pipeline": role_pipeline,
            "dx_outcome_pipeline": outcome_pipeline,
            "archetypes": archetypes,
            "metadata": {
                "role_metrics": role_metrics,
                "outcome_metrics": outcome_metrics,
                "n_rows_gold": len(gold),
                "n_rows_silver": len(silver),
                "labels": list(NCDA_ROLES),
            },
        },
        artifact_path,
    )
    return TrainingResult(
        artifact_path=artifact_path,
        role_metrics=role_metrics,
        outcome_metrics=outcome_metrics,
        n_rows_gold=len(gold),
        n_rows_silver=len(silver),
    )


def _build_role_dataset(
    gold: list[dict],
    silver: list[dict],
    archetypes: dict[str, list[float]] | None,
) -> tuple[list[dict], list[str], list[float]]:
    X: list[dict] = []
    y: list[str] = []
    w: list[float] = []
    for row in gold:
        if row.get("role") is None:
            continue
        X.append(_row_to_pipeline_input(row, archetypes))
        y.append(row["role"])
        w.append(1.0)
    for row in silver:
        if row.get("role") is None:
            continue
        X.append(_row_to_pipeline_input(row, archetypes))
        y.append(row["role"])
        w.append(0.3)
    return X, y, w


def _build_outcome_dataset(
    gold: list[dict],
    silver: list[dict],
    archetypes: dict[str, list[float]] | None,
) -> tuple[list[dict], list[str], list[float]]:
    X: list[dict] = []
    y: list[str] = []
    w: list[float] = []
    for source, weight in ((gold, 1.0), (silver, 0.3)):
        for row in source:
            if row.get("role") != "dx":
                continue
            outcome = row.get("outcome")
            if outcome not in ("cancer_found", "cancer_excluded"):
                continue
            X.append(_row_to_pipeline_input(row, archetypes))
            y.append(outcome)
            w.append(weight)
    return X, y, w


def _sample_weight_kwargs(weights: list[float]) -> dict[str, Any]:
    if not weights:
        return {}
    return {"clf__sample_weight": weights}


def _per_class_metrics(pipeline, X, y) -> dict[str, dict[str, float]]:
    """Training-set metrics; full eval lives in Stage 12."""
    from sklearn.metrics import precision_recall_fscore_support

    y_pred = pipeline.predict(X)
    labels = sorted(set(y))
    p, r, f1, support = precision_recall_fscore_support(
        y, y_pred, labels=labels, zero_division=0
    )
    return {
        label: {
            "precision": float(p[i]),
            "recall": float(r[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i, label in enumerate(labels)
    }
