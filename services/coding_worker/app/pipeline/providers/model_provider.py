from __future__ import annotations

import os

import httpx


class ModelExtractorProvider:
    source = "model"

    def __init__(self) -> None:
        self.model_name = "model-inference"
        self.model_version = "1.0"
        self._health_url = os.getenv("MODEL_INFERENCE_HEALTH_URL", "http://localhost:8010/health")

    def is_available(self) -> bool:
        try:
            httpx.get(self._health_url, timeout=2.0)
            return True
        except Exception:
            return False

    def extract_batch(self, encounter_text: str, sentences: list) -> list:
        return []
