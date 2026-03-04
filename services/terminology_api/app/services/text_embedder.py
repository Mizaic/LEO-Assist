"""Lazy sentence-transformers embedder for terminology resolver."""

from __future__ import annotations

import logging
import os
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)


class TerminologyTextEmbedder:
    """Small wrapper that lazily loads a sentence-transformers model.

    Loads once on first use.  If loading fails the failure is cached so
    subsequent calls return ``None`` immediately without retrying or
    spamming the logs.
    """

    def __init__(self) -> None:
        self.model_name = os.getenv("VECTOR_MODEL", "").strip()
        self.device = os.getenv("VECTOR_DEVICE", "auto").strip()
        self._model = None
        self._load_failed = False

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        if self._load_failed or not self.model_name:
            return False
        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            logger.warning(
                "VECTOR_MODEL is set but sentence-transformers is unavailable",
                exc_info=True,
            )
            self._load_failed = True
            return False
        try:
            device = self.device
            if device == "auto":
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            offline = os.getenv("HF_HUB_OFFLINE", "0") == "1"
            self._model = SentenceTransformer(
                self.model_name,
                device=device,
                local_files_only=offline,
            )
            logger.info(
                "Terminology embedder loaded: model=%s device=%s",
                self.model_name,
                device,
            )
            return True
        except Exception:
            logger.warning(
                "Failed to load terminology embedder (will not retry)",
                exc_info=True,
            )
            self._load_failed = True
            return False

    def encode(self, texts: Sequence[str]) -> list[list[float]] | None:
        if not self._ensure_model():
            return None
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [np.asarray(v, dtype=np.float32, copy=True).tolist() for v in vectors]
