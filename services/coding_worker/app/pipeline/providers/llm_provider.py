"""LLMExtractorProvider: wraps LLMExtractor to produce canonical ExtractionItem.

This provider preserves all existing Bedrock LLM extraction behaviour while
conforming to the ExtractorProvider protocol.  It is the reference
implementation and the fallback target in non-strict mode.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from services.coding_worker.app.pipeline.extractor_contract import (
    CONTRACT_VERSION,
    ExtractionItem,
)
from services.coding_worker.app.pipeline.llm_extractor import (
    ExtractionError,  # re-exported so callers can catch it  # noqa: F401
    ExtractedTerm,
    LLMExtractor,
)

logger = logging.getLogger(__name__)

_SOURCE = "llm"


class LLMExtractorProvider:
    """ExtractorProvider backed by AWS Bedrock LLM (existing behaviour)."""

    source = _SOURCE

    def __init__(self) -> None:
        model_id = os.getenv("AWS_BEDROCK_MODEL", "")
        region = os.getenv("AWS_DEFAULT_REGION", "eu-west-2")
        self._extractor = LLMExtractor(model_id=model_id, region=region)

    @property
    def model_name(self) -> str:
        return self._extractor.model_id or "llm-unconfigured"

    @property
    def model_version(self) -> str:
        return "bedrock-1.0"

    def is_available(self) -> bool:
        return self._extractor.enabled

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list,
    ) -> list[ExtractionItem]:
        terms: list[ExtractedTerm] = self._extractor.extract_batch(
            encounter_text, sentences
        )
        sent_map = {s.sentence_id: s for s in sentences}
        return [self._term_to_item(t, sent_map) for t in terms]

    def _term_to_item(self, term: ExtractedTerm, sent_map: dict) -> ExtractionItem:
        sent = sent_map.get(term.sentence_id)
        return ExtractionItem(
            sentence_id=term.sentence_id,
            text=term.text,
            span_start=sent.start if sent else 0,
            span_end=sent.end if sent else 0,
            semantic_tag=term.semantic_tag,
            assertion=term.assertion,
            confidence=1.0,
            normalized=term.lookup_term,
            source_meta={
                "context": term.context,
                "modifiers": term.modifiers,
            },
            relations=[],
            numeric_value=term.numeric_value,
            unit=term.unit,
            reference_range=term.reference_range,
            source=_SOURCE,
            model_name=self.model_name,
            model_version=self.model_version,
            contract_version=CONTRACT_VERSION,
        )
