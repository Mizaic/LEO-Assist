"""Stage 4 - Role classifier inference module.

Loads the joblib artifact produced by services.training_worker.app
.ncda_role_trainer.train_role_classifier and exposes a predict() that
returns per-encounter role probabilities + outcome attribute.

Inference inputs are strict: text + flags + encounter_date + optional vector.
No SNOMED codes, no v2 milestones.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from services.analysis_worker.app.ncda_detector.role_features import (
    NCDA_ROLES,
    extract_features,
)


@dataclass(frozen=True)
class RolePrediction:
    """One encounter's predicted role distribution + outcome (when role=dx)."""

    encounter_id: str
    role: str
    role_probabilities: dict[str, float]
    outcome: str | None
    outcome_probability: float | None


class RoleClassifier:
    """Wraps the persisted joblib artifact with a tidy predict() API."""

    def __init__(self, artifact_path: Path):
        import joblib

        self._artifact = joblib.load(artifact_path)
        self._role_pipeline = self._artifact["role_pipeline"]
        self._outcome_pipeline = self._artifact.get("dx_outcome_pipeline")
        self._archetypes = self._artifact.get("archetypes") or {}
        self._labels = self._artifact["metadata"]["labels"]

    def predict_one(
        self,
        *,
        encounter_id: str,
        text: str,
        flags: str | None,
        encounter_date: str | None,
        vector: Sequence[float] | None = None,
    ) -> RolePrediction:
        row = {
            "__text__": text or "",
            "__features__": extract_features(
                text=text or "",
                flags=flags,
                encounter_date=encounter_date,
                vector=vector,
                archetypes=self._archetypes,
            ),
        }
        proba = self._role_pipeline.predict_proba([row])[0]
        classes = list(self._role_pipeline.classes_)
        role_probs = {label: float(p) for label, p in zip(classes, proba)}
        for label in NCDA_ROLES:
            role_probs.setdefault(label, 0.0)
        top_role = max(role_probs, key=role_probs.get)

        outcome = None
        outcome_proba: float | None = None
        if top_role == "dx" and self._outcome_pipeline is not None:
            o_proba = self._outcome_pipeline.predict_proba([row])[0]
            o_classes = list(self._outcome_pipeline.classes_)
            o_dict = {c: float(p) for c, p in zip(o_classes, o_proba)}
            outcome = max(o_dict, key=o_dict.get)
            outcome_proba = o_dict[outcome]

        return RolePrediction(
            encounter_id=encounter_id,
            role=top_role,
            role_probabilities=role_probs,
            outcome=outcome,
            outcome_probability=outcome_proba,
        )

    def predict_many(self, rows: list[dict]) -> list[RolePrediction]:
        """Batch convenience wrapper. rows must carry encounter_id+text+date."""
        return [
            self.predict_one(
                encounter_id=r["encounter_id"],
                text=r.get("text") or "",
                flags=r.get("flags"),
                encounter_date=r.get("encounter_date"),
                vector=r.get("vector"),
            )
            for r in rows
        ]
