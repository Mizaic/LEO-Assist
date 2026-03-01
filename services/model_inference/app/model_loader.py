"""ModelLoader — thread-safe spaCy model manager for the inference service.

Downloads model artifacts from Azure Blob Storage (via ModelStore), unpacks
them to a local cache directory, and loads them into memory.

Hot-reload protocol
-------------------
1. ``load_version(version)`` downloads + unpacks into cache/
2. Loads the new model into a *staging* variable
3. Acquires the swap lock and assigns staging to active
4. The old nlp object is dereferenced (GC handles cleanup)

This means the old model serves requests right up until the moment the
in-memory pointer is swapped — zero dropped requests.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ModelLoader:
    """Thread-safe model holder for the inference service."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._nlp: Any = None
        self._active_version: Optional[str] = None
        self._model_name = os.getenv("CODING_MODEL_NAME", "medspacy_clinical_ner")

    @property
    def nlp(self) -> Any:
        with self._lock:
            return self._nlp

    @property
    def active_version(self) -> Optional[str]:
        with self._lock:
            return self._active_version

    @property
    def model_name(self) -> str:
        return self._model_name

    def load_version(self, version: str) -> None:
        """Download from blob and hot-swap to the requested version.

        Thread-safe — safe to call concurrently.  Only one caller will win
        the swap; others will see the new version immediately after.

        Args:
            version: Version string matching a blob path in the model store.

        Raises:
            RuntimeError: If download or spaCy load fails.
        """
        from libs.model_store import ModelStore
        import spacy

        store = ModelStore()

        logger.info("ModelLoader: downloading v%s from blob store...", version)
        local_model_dir = store.download(version)
        logger.info("ModelLoader: loading spaCy model from %s...", local_model_dir)

        # Load in staging — outside the lock so requests keep flowing
        try:
            new_nlp = spacy.load(str(local_model_dir))
        except Exception as exc:
            raise RuntimeError(
                f"ModelLoader: spaCy failed to load model from {local_model_dir}: {exc}"
            ) from exc

        # Atomic swap
        with self._lock:
            old_version = self._active_version
            self._nlp = new_nlp
            self._active_version = version

        logger.info(
            "ModelLoader: hot-swapped v%s → v%s (pipes: %s)",
            old_version or "none",
            version,
            ", ".join(new_nlp.pipe_names),
        )
