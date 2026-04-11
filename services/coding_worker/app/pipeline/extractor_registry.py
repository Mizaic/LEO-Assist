from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Callable

from libs.ner.extractor_contract import ExtractionItem
from services.coding_worker.app.pipeline.providers.llm_provider import (
    LLMExtractorProvider,
)
from services.coding_worker.app.pipeline.providers.model_provider import (
    ModelExtractorProvider,
)

logger = logging.getLogger(__name__)

_AGENT_ENABLED = os.getenv("CODING_AGENT_ENABLED", "true").lower() not in {
    "false",
    "0",
    "no",
    "off",
}
_AGENT_TIER = os.getenv("CODING_AGENT_TIER", "small")


def _verdict_to_extraction_items(verdict: dict) -> list[ExtractionItem]:
    """Map a code-mode agent verdict to ExtractionItem list for the pipeline."""
    items: list[ExtractionItem] = []
    for ent in verdict.get("entities", []):
        text = str(ent.get("text") or "").strip()
        if not text:
            continue
        items.append(
            ExtractionItem(
                sentence_id=str(uuid.uuid4()),
                text=text,
                span_start=int(ent.get("char_start") or 0),
                span_end=int(ent.get("char_end") or len(text)),
                semantic_tag=str(ent.get("semantic_tag") or "disorder"),
                assertion=str(ent.get("assertion") or "present"),
                confidence=float(ent.get("confidence") or 0.75),
                normalized=str(ent.get("preferred_term") or text),
                source="agent",
                source_meta={
                    "concept_id": ent.get("snomed_concept_id"),
                    "reason": ent.get("reason"),
                    "sentence": ent.get("sentence"),
                },
            )
        )
    return items


class AgentExtractorProvider:
    """Coding agent backed by the encounter_coding_agent LangGraph subgraph.

    Always invoked with apply=False -- the existing pipeline persistence layer
    controls all write-back, preserving the HITL review gate (CSO-001 fix).
    """

    source = "agent"
    model_name = "coding_agent"
    model_version = "1.0"

    def __init__(self) -> None:
        self._subgraph = None

    def _get_subgraph(self):
        if self._subgraph is None:
            from libs.pipeline_graph.registry import get_registry

            self._subgraph = get_registry().build("encounter_coding_agent")
        return self._subgraph

    def is_available(self) -> bool:
        if not _AGENT_ENABLED:
            return False
        try:
            self._get_subgraph()
            return True
        except Exception as exc:
            logger.warning("AgentExtractorProvider unavailable: %s", exc)
            return False

    def extract_batch(
        self, encounter_text: str, sentences: list
    ) -> list[ExtractionItem]:
        subgraph = self._get_subgraph()
        output = subgraph.invoke(
            {
                "encounter_text": encounter_text,
                "coded_entities": [],  # code mode
                "tier": _AGENT_TIER,
                "apply": False,  # pipeline handles persistence, not the agent
            }
        )
        verdict = output.get("verdict") or {}
        return _verdict_to_extraction_items(verdict)


def _make_llm_provider():
    return LLMExtractorProvider()


def _make_model_provider():
    return ModelExtractorProvider()


def _make_agent_provider():
    return AgentExtractorProvider()


class FallbackExtractor:
    def __init__(
        self,
        primary,
        fallback,
        *,
        strict: bool,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._strict = strict
        self._progress_hook = progress_hook
        self.source = getattr(primary, "source", "")
        self.model_name = getattr(primary, "model_name", "")
        self.model_version = getattr(primary, "model_version", "")

    def is_available(self) -> bool:
        return bool(self._primary.is_available())

    def extract_batch(self, encounter_text: str, sentences: list):
        try:
            return self._primary.extract_batch(encounter_text, sentences)
        except Exception:
            if self._strict:
                raise
            if self._progress_hook:
                self._progress_hook(
                    {
                        "type": "fallback_used",
                        "primary_backend": getattr(self._primary, "source", ""),
                        "fallback_backend": getattr(self._fallback, "source", ""),
                    }
                )
            return self._fallback.extract_batch(encounter_text, sentences)


def build_extractor(progress_hook: Callable[[dict[str, Any]], None] | None = None):
    backend = os.getenv("CODING_EXTRACTOR_BACKEND", "auto").lower()
    strict = os.getenv("CODING_EXTRACTOR_STRICT", "false").lower() == "true"
    llm = _make_llm_provider()
    model = _make_model_provider()

    if backend == "llm":
        return llm
    if backend == "agent":
        agent = _make_agent_provider()
        if not agent.is_available():
            if strict:
                raise RuntimeError("agent backend unavailable")
            return llm
        return FallbackExtractor(agent, llm, strict=strict, progress_hook=progress_hook)
    if backend == "model":
        if not model.is_available():
            logger.warning(
                "CODING_EXTRACTOR_BACKEND=model requested but model backend is unavailable or deprecated"
            )
            if strict:
                raise RuntimeError("model backend unavailable")
            if progress_hook:
                progress_hook(
                    {
                        "type": "backend_unavailable",
                        "backend": "model",
                        "fallback": "llm",
                    }
                )
            return llm
        return FallbackExtractor(model, llm, strict=strict, progress_hook=progress_hook)
    if backend == "auto":
        if model.is_available():
            primary = model
        elif _AGENT_ENABLED:
            agent = _make_agent_provider()
            if agent.is_available():
                return FallbackExtractor(
                    agent, llm, strict=strict, progress_hook=progress_hook
                )
            return llm
        else:
            return llm
        return FallbackExtractor(
            primary, llm, strict=strict, progress_hook=progress_hook
        )
    return llm
