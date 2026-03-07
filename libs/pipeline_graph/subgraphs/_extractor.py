"""Thin adapter that provides an ExtractorProvider for the extraction subgraph.

Replaces the now-deleted ``services.coding_worker.app.pipeline.extractor_registry``.
Delegates to the LLM client using the configurable system prompt.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from libs.ner.extractor_contract import ExtractionItem, ExtractorProvider
from libs.nlp.sentence_splitter import SentenceChunk

logger = logging.getLogger(__name__)


class LLMExtractorAdapter:
    """LLM-backed entity extractor conforming to ExtractorProvider protocol."""

    def __init__(self, system_prompt: str, tier: str = "small") -> None:
        self._system_prompt = system_prompt
        self._tier = tier

    @property
    def source(self) -> str:
        return "llm"

    @property
    def model_name(self) -> str:
        return f"llm-{self._tier}"

    @property
    def model_version(self) -> str:
        return "pipeline-v2"

    def is_available(self) -> bool:
        try:
            from libs.llm_client.factory import create_llm
            llm = create_llm(tier=self._tier)
            return llm is not None
        except Exception:
            return False

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list[SentenceChunk],
    ) -> list[ExtractionItem]:
        from libs.llm_client.factory import create_llm

        llm = create_llm(tier=self._tier)
        sentence_block = "\n".join(
            f"[{s.sentence_id}] {s.text}" for s in sentences
        )
        user_msg = (
            f"Encounter text:\n{encounter_text}\n\n"
            f"Sentences to process:\n{sentence_block}"
        )
        resp = llm.converse(
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=4096,
            temperature=0.0,
        )
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON: %s", raw[:200])
            return []

        terms = data.get("terms", [])
        items: list[ExtractionItem] = []
        for t in terms:
            text_val = t.get("text", "")
            items.append(
                ExtractionItem(
                    sentence_id=t.get("sentence_id", ""),
                    text=text_val,
                    span_start=0,
                    span_end=len(text_val),
                    semantic_tag=t.get("semantic_tag", "finding"),
                    assertion=t.get("assertion", "present"),
                    confidence=1.0,
                    normalized=t.get("lookup_term", text_val),
                    numeric_value=t.get("value") or "",
                    unit=t.get("unit") or "",
                    reference_range=t.get("reference_range") or "",
                    source="llm",
                    model_name=self.model_name,
                    model_version=self.model_version,
                )
            )
        return items


def build_extractor(
    system_prompt: str | None = None,
    tier: str = "small",
) -> LLMExtractorAdapter:
    """Build an LLM extractor with the given system prompt.

    Falls back to the hardcoded extraction prompt if none provided.
    """
    if not system_prompt:
        from libs.prompts.registry import get_prompt
        system_prompt = get_prompt("extraction", version=1)
    return LLMExtractorAdapter(system_prompt=system_prompt, tier=tier)
