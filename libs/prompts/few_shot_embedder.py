"""Shared sentence-transformer embedder for few-shot retrieval.

Split out of ``few_shot_selector`` so the selection policy can be read
and tested without the model-loading machinery.

FEW_SHOT_VECTOR_MODEL selects the model, falling back to VECTOR_MODEL.
The override exists because VECTOR_MODEL is shared with terminology
search and pinned to the dimensionality of stored index vectors, so
few-shot retrieval cannot change it globally.

Atlas trace:
  DO: DO-83EBEE2C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-83EBEE2C")
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Sequence

import numpy as np

from libs.utils.device_resolver import resolve_accelerator

logger = logging.getLogger(__name__)

# Import sentence-transformers eagerly at module load time (main thread).
# Deferring this import to a background thread races with spacy-transformers
# loading transformers' lazy modules, which causes an EncoderDecoderConfig
# ImportError due to a mid-initialization read of the lazy module registry.
try:
    from sentence_transformers import SentenceTransformer as _SentenceTransformer

    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except Exception:
    _SentenceTransformer = None  # type: ignore[assignment,misc]
    _SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.debug(
        "sentence-transformers not available; vector few-shot selection disabled"
    )


class _LazySentenceEmbedder:
    """Lazy sentence-transformers wrapper with safe failure mode.

    Designed to be used as a process-wide singleton (see
    ``_get_shared_embedder``). The underlying SentenceTransformer model is
    loaded at most once and cached for the lifetime of the process --
    subsequent calls reuse the already-loaded model.
    """

    def __init__(self) -> None:
        self.model_name = (
            os.getenv("FEW_SHOT_VECTOR_MODEL", "").strip()
            or os.getenv("VECTOR_MODEL", "").strip()
        )
        self.device_requested = os.getenv("VECTOR_DEVICE", "auto").strip()
        self.mps_fail_fast = os.getenv("VECTOR_MPS_FAIL_FAST", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self._resolved_device = "cpu"
        self._model = None
        self._load_failed = False
        self._lock = threading.Lock()

    def _ensure_model(self) -> bool:
        # Fast path -- already loaded or permanently failed
        if self._model is not None:
            return True
        if self._load_failed or not self.model_name:
            return False

        # Only one thread does the actual load; others wait then re-check.
        with self._lock:
            if self._model is not None:
                return True
            if self._load_failed:
                return False
            if not _SENTENCE_TRANSFORMERS_AVAILABLE:
                logger.warning(
                    "A few-shot vector model is set but sentence-transformers "
                    "is unavailable"
                )
                self._load_failed = True
                return False
            return self._load_model()

    def _load_model(self) -> bool:
        """Resolve the accelerator and construct the model. Caller holds the lock."""
        try:
            device = self._resolve_device()
            self._model = _SentenceTransformer(
                self.model_name,
                device=device,
                local_files_only=self._offline(),
            )
            logger.info(
                "Few-shot selector embedder loaded: model=%s device=%s",
                self.model_name,
                device,
            )
            return True
        except Exception:
            logger.warning("Failed to load few-shot selector embedder", exc_info=True)
            self._load_failed = True
            return False

    def _resolve_device(self) -> str:
        decision = resolve_accelerator(
            self.device_requested,
            prefer_mps_on_macos=True,
            min_macos_major_for_mps=int(os.getenv("MPS_MIN_MACOS_MAJOR", "26")),
            enforce_apple_silicon_for_mps=True,
        )
        self._resolved_device = decision.resolved
        if decision.fallback_applied:
            logger.warning(
                "Few-shot embedder accelerator fallback applied: "
                "requested=%s resolved=%s reason=%s",
                decision.requested,
                decision.resolved,
                decision.fallback_reason,
            )
        return decision.resolved

    @staticmethod
    def _offline() -> bool:
        if os.getenv("HF_HUB_ONLINE", "0") == "1":
            return False
        return os.getenv("HF_HUB_OFFLINE", "1") == "1"

    def encode(self, texts: Sequence[str]) -> np.ndarray | None:
        if not self._ensure_model():
            return None
        try:
            vectors = self._model.encode(
                list(texts),
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except Exception:
            if self._resolved_device == "mps" and self.mps_fail_fast:
                raise RuntimeError(
                    "MPS runtime failure in few-shot embedder; fail-fast is enabled"
                )
            logger.warning("Few-shot embedder encode failed", exc_info=True)
            return None
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        return arr


# -- Process-level singleton -------------------------------------------------
# The SentenceTransformer model is heavy (>400 MB on disk, >1 GB in memory on
# CPU). Loading it per-request is the main source of slow test-run cold starts.
# We keep one shared instance for the lifetime of the API process so the model
# is loaded at most once, regardless of how many concurrent pipeline steps run.

_SHARED_EMBEDDER: _LazySentenceEmbedder | None = None
_SHARED_EMBEDDER_LOCK = threading.Lock()


def _get_shared_embedder() -> _LazySentenceEmbedder:
    """Return the process-wide embedder, creating it on first call."""
    global _SHARED_EMBEDDER
    if _SHARED_EMBEDDER is None:
        with _SHARED_EMBEDDER_LOCK:
            if _SHARED_EMBEDDER is None:
                _SHARED_EMBEDDER = _LazySentenceEmbedder()
    return _SHARED_EMBEDDER


def warm_shared_embedder() -> None:
    """Pre-load the sentence-transformer model in the background.

    Call this once at application startup (for example in a FastAPI
    ``lifespan`` handler) so the first real pipeline run does not pay the
    cold-start cost. Safe to call repeatedly -- later calls are instant
    no-ops once the model is loaded.
    """
    embedder = _get_shared_embedder()
    if embedder.model_name:
        logger.info(
            "Pre-warming few-shot embedder in background: model=%s",
            embedder.model_name,
        )
        thread = threading.Thread(
            target=embedder._ensure_model, daemon=True, name="embedder-warmup"
        )
        thread.start()
