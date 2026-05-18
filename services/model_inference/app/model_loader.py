"""ModelLoader — thread-safe spaCy model manager for the inference service.

Atlas trace:
  DO: DO-A00CD165
  DI: DI-3FDBB57B
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A00CD165")

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

Concurrency safeguards
----------------------
- ``_load_lock`` serialises all ``load_version`` calls so only one download
  runs at a time.  A concurrent call for the same version that arrives while
  a load is in progress will return immediately once the lock is released
  (the version will already be active).  A call for a *different* version
  waits and then proceeds normally.
- The idempotency check inside ``_load_lock`` means that startup +
  a concurrent registry ``_signal_reload`` for the same version never
  trigger two redundant 400 MB blob downloads.
"""

from __future__ import annotations

import logging
import os
import threading
import importlib
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _ensure_leo_transformer_listener_registered() -> None:
    """Register custom training-time TransformerListener architecture if needed."""
    try:
        importlib.import_module("services.training_worker.app.spacy_listener_width")
        return
    except Exception:
        # Fallback to local registration in runtime environments where the
        # training worker package path may not be importable.
        pass

    try:
        from spacy.tokens import Doc
        from spacy_transformers.layers import TransformerListener, trfs2arrays
        from spacy_transformers.util import registry
        from thinc.api import Model, chain
        from thinc.types import Floats2d, Ragged
    except Exception:
        return

    try:
        @registry.architectures.register("leo_training.TransformerListener.v1")
        def _leo_transformer_listener_v1(
            pooling: Model[Ragged, Floats2d],
            grad_factor: float = 1.0,
            upstream: str = "*",
            width: int = 768,
        ) -> Model[list[Doc], list[Floats2d]]:
            listener = TransformerListener(upstream_name=upstream)
            listener.set_dim("nO", int(width))
            model: Model = chain(listener, trfs2arrays(pooling, grad_factor))
            model.set_ref("listener", listener)
            return model
    except ValueError:
        # Already registered in this process.
        return


class ModelLoader:
    """Thread-safe model holder for the inference service."""

    def __init__(self, *, accelerator: str = "cpu", mps_fail_fast: bool = True) -> None:
        # Guards in-memory swap of _nlp / _active_version.
        self._lock = threading.RLock()
        # Serialises concurrent load_version calls — prevents duplicate
        # blob downloads when startup and _signal_reload race each other.
        self._load_lock = threading.Lock()
        self._nlp: Any = None
        self._active_version: Optional[str] = None
        self._calibration: Any = None
        self._model_name = os.getenv("CODING_MODEL_NAME", "medspacy_clinical_ner")
        self._accelerator = accelerator
        self._mps_fail_fast = mps_fail_fast

    @property
    def nlp(self) -> Any:
        with self._lock:
            return self._nlp

    @property
    def active_version(self) -> Optional[str]:
        with self._lock:
            return self._active_version

    @property
    def calibration(self) -> Any:
        with self._lock:
            return self._calibration

    @property
    def model_name(self) -> str:
        return self._model_name

    def load_version(self, version: str) -> None:
        """Download from blob and hot-swap to the requested version.

        Idempotent: if this version is already active when the load lock is
        acquired (e.g. a concurrent call finished first), returns immediately
        without a redundant download.

        Args:
            version: Version string matching a blob path in the model store.

        Raises:
            RuntimeError: If download or spaCy load fails.
        """
        with self._load_lock:
            # Re-check inside the lock: another thread may have loaded this
            # version while we were waiting (startup vs. _signal_reload race).
            with self._lock:
                if self._active_version == version:
                    logger.info(
                        "ModelLoader: v%s already active — skipping redundant load",
                        version,
                    )
                    return

            from libs.model_store import ModelStore
            import spacy

            store = ModelStore()

            logger.info("ModelLoader: downloading v%s from blob store...", version)
            local_model_dir = store.download(version)
            logger.info("ModelLoader: loading spaCy model from %s...", local_model_dir)

            # Load in staging — outside the swap lock so requests keep flowing.
            try:
                if self._accelerator in {"cuda", "mps"}:
                    gpu_ok = spacy.prefer_gpu()
                    if not gpu_ok:
                        msg = (
                            "ModelLoader: spaCy GPU activation failed for "
                            f"accelerator={self._accelerator}"
                        )
                        if self._accelerator == "mps" and self._mps_fail_fast:
                            raise RuntimeError(msg)
                        logger.warning("%s; continuing on CPU", msg)
                _ensure_leo_transformer_listener_registered()
                new_nlp = spacy.load(str(local_model_dir))
            except Exception as exc:
                raise RuntimeError(
                    f"ModelLoader: spaCy failed to load model from {local_model_dir}: {exc}"
                ) from exc

            new_calibration = None
            try:
                from libs.training_ext.inference_calibration import load_calibration

                new_calibration = load_calibration(Path(str(local_model_dir)))
            except Exception as exc:
                logger.warning(
                    "ModelLoader: could not load calibration sidecar (%s) — "
                    "falling back to raw probabilities",
                    exc,
                )

            # Atomic swap.
            with self._lock:
                old_version = self._active_version
                self._nlp = new_nlp
                self._active_version = version
                self._calibration = new_calibration

            logger.info(
                "ModelLoader: hot-swapped v%s → v%s (pipes: %s)",
                old_version or "none",
                version,
                ", ".join(new_nlp.pipe_names),
            )
