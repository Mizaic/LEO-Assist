from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


class ModelExtractorProvider:
    source = "model"

    def __init__(self) -> None:
        self.model_name = "model-inference"
        self.model_version = "1.0"
        self._health_url = os.getenv("MODEL_INFERENCE_HEALTH_URL", "http://localhost:8010/health")
        self._enabled = os.getenv("CODING_MODEL_PROVIDER_ENABLED", "false").lower() in {
            "true",
            "1",
            "yes",
            "on",
        }

    def is_available(self) -> bool:
        if not self._enabled:
            return False
        try:
            httpx.get(self._health_url, timeout=2.0)
            return True
        except Exception:
            return False

    def extract_batch(self, encounter_text: str, sentences: list) -> list:
        _ = (encounter_text, sentences)
        if not self._enabled:
            raise RuntimeError(
                "model extractor backend is deprecated by default; "
                "set CODING_MODEL_PROVIDER_ENABLED=true only for validated rollout"
            )
        logger.warning("Model extractor called but implementation is not wired")
        return []
