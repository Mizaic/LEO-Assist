"""Few-shot selector that ranks dynamic examples by semantic similarity."""

from __future__ import annotations

import logging
import os
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)


class _LazySentenceEmbedder:
    """Lazy sentence-transformers wrapper with safe failure mode."""

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
                try:
                    import torch

                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except Exception:
                    device = "cpu"
            elif device == "cuda":
                try:
                    import torch

                    if not torch.cuda.is_available():
                        raise RuntimeError("cuda unavailable")
                except Exception:
                    logger.warning(
                        "VECTOR_DEVICE=cuda but CUDA is not available; falling back to CPU"
                    )
                    device = "cpu"
            offline = os.getenv("HF_HUB_OFFLINE", "0") == "1"
            self._model = SentenceTransformer(
                self.model_name,
                device=device,
                local_files_only=offline,
            )
            logger.info("Few-shot selector embedder loaded: model=%s device=%s", self.model_name, device)
            return True
        except Exception:
            logger.warning("Failed to load few-shot selector embedder", exc_info=True)
            self._load_failed = True
            return False

    def encode(self, texts: Sequence[str]) -> np.ndarray | None:
        if not self._ensure_model():
            return None
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        return arr


class FewShotSelector:
    """Select top-k dynamic examples using cosine similarity."""

    def __init__(self, dynamic_pool: list[dict], embedder: _LazySentenceEmbedder | None = None):
        self._pool = list(dynamic_pool or [])
        self._embedder = embedder or _LazySentenceEmbedder()
        self._pool_embeddings: np.ndarray | None = None

    def warm(self) -> None:
        """Pre-compute and cache embeddings for the dynamic example pool."""
        if not self._pool:
            self._pool_embeddings = None
            return
        texts = [self._example_text(ex) for ex in self._pool]
        vectors = self._embedder.encode(texts)
        if vectors is None or len(vectors) != len(self._pool):
            self._pool_embeddings = None
            return
        self._pool_embeddings = vectors

    def select(self, query_text: str, k: int) -> list[dict]:
        """Return top-k examples by similarity, with deterministic fallback."""
        if k <= 0 or not self._pool:
            return []

        if self._pool_embeddings is None:
            self.warm()

        if self._pool_embeddings is not None:
            qv = self._embedder.encode([query_text or ""])
            if qv is not None and qv.shape[0] == 1 and qv.shape[1] == self._pool_embeddings.shape[1]:
                scores = self._pool_embeddings @ qv[0]
                top_idx = np.argsort(-scores)[: min(k, len(self._pool))]
                return [self._pool[int(i)] for i in top_idx]

        ordered = sorted(
            self._pool,
            key=lambda ex: (self._fallback_priority(str(ex.get("category", ""))), str(ex.get("description", ""))),
        )
        return ordered[: min(k, len(ordered))]

    @staticmethod
    def _example_text(example: dict) -> str:
        return "\n".join(
            [
                f"category={example.get('category', '')}",
                f"description={example.get('description', '')}",
                f"input={example.get('input', '')}",
            ]
        )

    @staticmethod
    def _fallback_priority(category: str) -> int:
        ordered_prefixes = [
            "assertion:absent",
            "negation:compound",
            "assertion:family",
            "assertion:historical",
            "observable",
            "multi-entity",
            "assertion:hypothetical",
            "abbreviation",
        ]
        for i, prefix in enumerate(ordered_prefixes):
            if category.startswith(prefix):
                return i
        return len(ordered_prefixes) + 1
