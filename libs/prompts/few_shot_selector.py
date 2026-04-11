"""Few-shot selector that ranks dynamic examples by semantic similarity."""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Sequence

import numpy as np
from libs.utils.device_resolver import resolve_accelerator

logger = logging.getLogger(__name__)


class _LazySentenceEmbedder:
    """Lazy sentence-transformers wrapper with safe failure mode.

    Designed to be used as a process-wide singleton (see ``_get_shared_embedder``).
    The underlying SentenceTransformer model is loaded at most once and cached for
    the lifetime of the process — subsequent calls reuse the already-loaded model.
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
        self._lock = threading.Lock()

    def _ensure_model(self) -> bool:
        # Fast path — already loaded or permanently failed
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
                        "Few-shot embedder accelerator fallback applied: requested=%s resolved=%s reason=%s",
                        decision.requested,
                        decision.resolved,
                        decision.fallback_reason,
                    )
                offline = os.getenv("HF_HUB_OFFLINE", "0") == "1"
                self._model = SentenceTransformer(
                    self.model_name,
                    device=device,
                    local_files_only=offline,
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


# ── Process-level singleton ───────────────────────────────────────────────────
# The SentenceTransformer model is heavy (>400 MB on disk, >1 GB in memory on CPU).
# Loading it per-request is the main source of slow test-run cold starts.
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

    Call this once at application startup (e.g. in a FastAPI ``lifespan`` handler
    or ``startup`` event) so the first real pipeline run doesn't pay the cold-start
    cost.  Safe to call multiple times — subsequent calls are instant no-ops once
    the model is loaded.
    """
    embedder = _get_shared_embedder()
    if embedder.model_name:
        logger.info(
            "Pre-warming few-shot embedder in background: model=%s", embedder.model_name
        )
        t = threading.Thread(target=embedder._ensure_model, daemon=True, name="embedder-warmup")
        t.start()


class FewShotSelector:
    """Select top-k dynamic examples using cosine similarity."""

    def __init__(self, dynamic_pool: list[dict], embedder: _LazySentenceEmbedder | None = None):
        self._pool = list(dynamic_pool or [])
        # Always use the shared singleton unless a custom embedder is explicitly provided.
        self._embedder = embedder if embedder is not None else _get_shared_embedder()
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
        query = query_text or ""
        routed_pool = self._route_pool_for_query(query)
        if not routed_pool:
            routed_pool = self._pool

        pool_embeddings = self._pool_embeddings
        if pool_embeddings is None:
            self.warm()
            pool_embeddings = self._pool_embeddings

        if (
            pool_embeddings is not None
            and len(routed_pool) == len(self._pool)
        ):
            qv = self._embedder.encode([query])
            if qv is not None and qv.shape[0] == 1 and qv.shape[1] == pool_embeddings.shape[1]:
                scores = pool_embeddings @ qv[0]
                top_idx = np.argsort(-scores)[: min(k, len(self._pool))]
                return [self._pool[int(i)] for i in top_idx]

        # Routed subset path: embed only the filtered pool for precision.
        routed_texts = [self._example_text(ex) for ex in routed_pool]
        routed_vectors = self._embedder.encode(routed_texts)
        if routed_vectors is not None:
            qv = self._embedder.encode([query])
            if qv is not None and qv.shape[0] == 1 and qv.shape[1] == routed_vectors.shape[1]:
                scores = routed_vectors @ qv[0]
                top_idx = np.argsort(-scores)[: min(k, len(routed_pool))]
                return [routed_pool[int(i)] for i in top_idx]

        ordered = sorted(
            routed_pool,
            key=lambda ex: (self._fallback_priority(str(ex.get("category", ""))), str(ex.get("description", ""))),
        )
        return ordered[: min(k, len(ordered))]

    def _route_pool_for_query(self, query_text: str) -> list[dict]:
        """Route retrieval by domain so lab-heavy notes prefer lab slices."""
        bucket = self._query_bucket(query_text)
        if bucket == "generic":
            return list(self._pool)
        mapped = [ex for ex in self._pool if self._example_bucket(ex) == bucket]
        if len(mapped) >= 3:
            return mapped
        # Keep strict route preference while allowing broad recall when sparse.
        return mapped + [ex for ex in self._pool if ex not in mapped]

    @staticmethod
    def _query_bucket(query_text: str) -> str:
        text = (query_text or "").lower()
        if re.search(r"\b(hba1c|egfr|creatinine|haemoglobin|hemoglobin|platelet|lymphocyte|neutrophil|monocyte|eosinophil|basophil|mmol\/l|10\^9\/l|g\/l|fbc|full blood count)\b", text):
            return "labs"
        if re.search(r"\b(stage|staging|tnm|metastatic|oncology|carcinoma|tumour|tumor|cancer)\b", text):
            return "oncology"
        if re.search(r"\b(referral|urgent|two week wait|2ww|booked|appointment|admin|letter)\b", text):
            return "referral_admin"
        if re.search(r"\b(medication|dose|tablet|capsule|mg|drug|prescribed)\b", text):
            return "medication"
        return "generic"

    @staticmethod
    def _example_bucket(example: dict) -> str:
        category = str(example.get("category", "")).lower()
        if any(t in category for t in ("lab", "observable", "value-unit", "haematology")):
            return "labs"
        if any(t in category for t in ("oncology", "staging", "cancer")):
            return "oncology"
        if any(t in category for t in ("referral", "admin", "pathway")):
            return "referral_admin"
        if any(t in category for t in ("medication", "drug", "substance")):
            return "medication"
        return "generic"

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
