"""Stage 6 - Linkage classifier inference module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class LinkageScore:
    """One pair's same-pathway probability + tier assignment."""

    probability: float
    tier: Literal["auto", "suggest", "review"]


class LinkageClassifier:
    """Wraps the linkage joblib artifact for the assignment stage."""

    def __init__(self, artifact_path: Path):
        import joblib

        self._artifact = joblib.load(artifact_path)
        self._pipeline = self._artifact["pipeline"]
        self._tier_auto = self._artifact["metadata"]["tier_auto"]
        self._tier_suggest = self._artifact["metadata"]["tier_suggest"]

    def score_one(self, features: dict[str, float]) -> LinkageScore:
        proba = self._pipeline.predict_proba([features])[0]
        classes = list(self._pipeline.classes_)
        # Robust to either label encoding (1/0 or 'pos'/'neg').
        positive_idx = self._positive_class_index(classes)
        p = float(proba[positive_idx])
        return LinkageScore(probability=p, tier=self._tier_for(p))

    def score_many(self, feature_rows: list[dict[str, float]]) -> list[LinkageScore]:
        return [self.score_one(f) for f in feature_rows]

    def _positive_class_index(self, classes: list) -> int:
        for i, c in enumerate(classes):
            if c == 1 or str(c).lower() in {"1", "true", "pos", "positive"}:
                return i
        return len(classes) - 1

    def _tier_for(self, probability: float) -> Literal["auto", "suggest", "review"]:
        if probability >= self._tier_auto:
            return "auto"
        if probability >= self._tier_suggest:
            return "suggest"
        return "review"
