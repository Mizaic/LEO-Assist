"""Lazy sentence-transformers embedder for terminology resolver."""

from __future__ import annotations

import logging
import os
from typing import Sequence

import numpy as np
from libs.utils.device_resolver import resolve_accelerator

logger = logging.getLogger(__name__)


class TerminologyTextEmbedder:
    """Small wrapper that lazily loads a sentence-transformers model.

    Loads once on first use.  If loading fails the failure is cached so
    subsequent calls return ``None`` immediately without retrying or
    spamming the logs.
    """

    def __init__(self) -> None:
        self.model_name = os.getenv("VECTOR_MODEL", "").strip()
        self.device_requested = os.getenv("VECTOR_DEVICE", "auto").strip()
        self.mps_fail_fast = os.getenv("VECTOR_MPS_FAIL_FAST", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self._resolved_device = "cpu"
        self._model = None
        self._load_failed = False

    @property
    def resolved_device(self) -> str:
        return self._resolved_device

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
            decision = resolve_accelerator(
                self.device_requested,
                prefer_mps_on_macos=True,
                min_macos_major_for_mps=int(os.getenv("MPS_MIN_MACOS_MAJOR", "26")),
                enforce_apple_silicon_for_mps=True,
            )
            device = decision.resolved
            self._resolved_device = device
            if decision.fallback_applied:
                logger.warning(
                    "Terminology embedder accelerator fallback applied: requested=%s resolved=%s reason=%s",
                    decision.requested,
                    decision.resolved,
                    decision.fallback_reason,
                )
            # Default to local-only; set HF_HUB_ONLINE=1 only if you
            # intentionally want the library to reach out to huggingface.co.
            online = os.getenv("HF_HUB_ONLINE", "0") == "1"
            self._model = SentenceTransformer(
                self.model_name,
                device=device,
                local_files_only=not online,
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
                    "MPS runtime failure in terminology embedder; fail-fast is enabled"
                )
            logger.warning("Terminology embedder encode failed", exc_info=True)
            return None
        return [np.asarray(v, dtype=np.float32, copy=True).tolist() for v in vectors]
