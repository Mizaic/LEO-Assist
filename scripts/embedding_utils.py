"""Shared embedding helpers for terminology scripts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

from dotenv import load_dotenv


@dataclass(frozen=True)
class VectorSettings:
    model_name: str
    dimension: int
    device: str


class TextEmbedder:
    """Thin wrapper over sentence-transformers style embedding."""

    def __init__(self, settings: VectorSettings):
        self.settings = settings
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "sentence-transformers is required for embedding scripts. "
                "Install with: pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(
            self.settings.model_name, device=self.settings.device
        )

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        self._ensure_model()
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [v.astype("float32").tolist() for v in vectors]


def load_vector_settings() -> VectorSettings:
    load_dotenv("secrets/.env")
    model_name = os.environ.get("VECTOR_MODEL", "").strip()
    if not model_name:
        raise RuntimeError("Missing VECTOR_MODEL in environment/secrets/.env")
    dimension = int(os.environ.get("VECTOR_DIMENSION", "768"))
    device = os.environ.get("VECTOR_DEVICE", "cpu").strip() or "cpu"
    return VectorSettings(model_name=model_name, dimension=dimension, device=device)
