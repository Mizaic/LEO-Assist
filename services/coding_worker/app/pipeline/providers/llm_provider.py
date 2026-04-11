from __future__ import annotations

from libs.ner.extractor_contract import ExtractionItem
from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor


class LLMExtractorProvider:
    source = "llm"

    def __init__(self, model_id: str = "llm-default") -> None:
        self._extractor = LLMExtractor(model_id=model_id)
        self.model_name = self._extractor.model_name or "llm-unconfigured"
        self.model_version = self._extractor.model_version or "1.0"

    def is_available(self) -> bool:
        return bool(self._extractor.is_available())

    def extract_batch(
        self, encounter_text: str, sentences: list
    ) -> list[ExtractionItem]:
        return self._extractor.extract_batch(encounter_text, sentences)
