"""Shared embedding helpers for terminology scripts."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Sequence

from dotenv import load_dotenv

log = logging.getLogger(__name__)


def _resolve_device(requested: str) -> str:
    """Return 'cuda' or 'cpu' depending on availability.

    *  ``"auto"`` / ``""`` -> try CUDA, fall back to CPU
    *  ``"cuda"``          -> use CUDA (will fail fast if unavailable)
    *  ``"cpu"``           -> always CPU
    """
    requested = (requested or "auto").strip().lower()
    if requested == "cpu":
        return "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            log.info("CUDA available - using GPU: %s", name)
            return "cuda"
    except Exception:
        pass
    if requested == "cuda":
        log.warning("CUDA was explicitly requested but is not available - falling back to CPU")
    else:
        log.info("CUDA not available - using CPU for embeddings")
    return "cpu"


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
    raw_device = os.environ.get("VECTOR_DEVICE", "auto").strip()
    device = _resolve_device(raw_device)
    return VectorSettings(model_name=model_name, dimension=dimension, device=device)
