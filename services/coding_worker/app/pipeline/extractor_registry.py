"""ExtractorProvider factory with env-driven backend selection and fallback chain.

Environment variables
---------------------
CODING_EXTRACTOR_BACKEND  "llm" | "model" | "auto"
    llm   — always use LLM provider (Bedrock)
    model — always use model provider (spaCy NER service or in-process)
    auto  — prefer model, fallback to llm; respects CODING_EXTRACTOR_STRICT
    Default: "llm"

CODING_EXTRACTOR_STRICT   "true" | "false"
    true  — fail-fast if configured backend unavailable
    false — fallback to next available backend with explicit log event
    Default: "false"

Usage::

    from services.coding_worker.app.pipeline.extractor_registry import build_extractor

    provider = build_extractor(progress_hook=hook)
    items = provider.extract_batch(encounter_text, sentences)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from services.coding_worker.app.pipeline.extractor_contract import (
    ExtractionItem,
    ExtractorProvider,
)

logger = logging.getLogger(__name__)

BACKEND_LLM = "llm"
BACKEND_MODEL = "model"
BACKEND_AUTO = "auto"
_VALID_BACKENDS = frozenset({BACKEND_LLM, BACKEND_MODEL, BACKEND_AUTO})


def _configured_backend() -> str:
    raw = os.getenv("CODING_EXTRACTOR_BACKEND", BACKEND_LLM).lower().strip()
    return raw if raw in _VALID_BACKENDS else BACKEND_LLM


def _is_strict() -> bool:
    return os.getenv("CODING_EXTRACTOR_STRICT", "false").lower() == "true"


def _make_llm_provider() -> "ExtractorProvider":
    from services.coding_worker.app.pipeline.providers.llm_provider import (
        LLMExtractorProvider,
    )
    return LLMExtractorProvider()


def _make_model_provider() -> "ExtractorProvider":
    from services.coding_worker.app.pipeline.providers.model_provider import (
        ModelExtractorProvider,
    )
    return ModelExtractorProvider()


class _FallbackExtractor:
    """Wraps a primary provider with an optional fallback.

    When the primary raises, and strict=False, the fallback is tried and a
    ``fallback_used`` progress event is emitted so operators know a backend
    switch occurred mid-run.
    """

    def __init__(
        self,
        primary: ExtractorProvider,
        fallback: Optional[ExtractorProvider],
        strict: bool = False,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._strict = strict
        self._hook = progress_hook

    @property
    def source(self) -> str:
        return self._primary.source

    @property
    def model_name(self) -> str:
        return self._primary.model_name

    @property
    def model_version(self) -> str:
        return self._primary.model_version

    def is_available(self) -> bool:
        return self._primary.is_available()

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list,
    ) -> list[ExtractionItem]:
        try:
            return self._primary.extract_batch(encounter_text, sentences)
        except Exception as primary_exc:
            if self._strict or self._fallback is None:
                raise
            logger.warning(
                "FallbackExtractor: primary=%s failed (%s) — activating fallback=%s",
                self._primary.source,
                primary_exc,
                self._fallback.source,
            )
            if self._hook:
                self._hook({
                    "type": "fallback_used",
                    "primary_backend": self._primary.source,
                    "fallback_backend": self._fallback.source,
                    "error": str(primary_exc),
                })
            return self._fallback.extract_batch(encounter_text, sentences)


def build_extractor(
    progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
) -> ExtractorProvider:
    """Build the active extractor provider from env config.

    Returns an ExtractorProvider, optionally wrapped in a FallbackExtractor
    when backend=model and strict=false.

    Args:
        progress_hook: Optional callback for progress events.  Receives a dict
            with at minimum ``{"type": "fallback_used", ...}`` when a fallback
            is triggered.

    Raises:
        RuntimeError: When strict=true and the configured backend is unavailable.
    """
    backend = _configured_backend()
    strict = _is_strict()

    if backend == BACKEND_LLM:
        provider = _make_llm_provider()
        if strict and not provider.is_available():
            raise RuntimeError(
                "build_extractor: LLM backend unavailable (CODING_EXTRACTOR_STRICT=true)"
            )
        logger.info("build_extractor: using llm provider (%s)", provider.model_name)
        return provider

    if backend == BACKEND_MODEL:
        model = _make_model_provider()
        if model.is_available():
            if strict:
                logger.info(
                    "build_extractor: using model provider (%s v%s)",
                    model.model_name, model.model_version,
                )
                return model
            llm = _make_llm_provider()
            return _FallbackExtractor(model, llm, strict=False, progress_hook=progress_hook)
        # Model unavailable
        if strict:
            raise RuntimeError(
                "build_extractor: model backend unavailable (CODING_EXTRACTOR_STRICT=true)"
            )
        logger.warning(
            "build_extractor: model backend requested but unavailable — falling back to llm"
        )
        return _make_llm_provider()

    # BACKEND_AUTO: prefer model, fallback to llm
    try:
        model = _make_model_provider()
        if model.is_available():
            llm = _make_llm_provider()
            logger.info(
                "build_extractor: auto selected model provider (%s v%s)",
                model.model_name, model.model_version,
            )
            return _FallbackExtractor(model, llm, strict=False, progress_hook=progress_hook)
    except Exception:
        logger.debug("build_extractor: model provider init failed in auto mode", exc_info=True)

    llm = _make_llm_provider()
    if strict and not llm.is_available():
        raise RuntimeError(
            "build_extractor: no available backend in auto mode (CODING_EXTRACTOR_STRICT=true)"
        )
    logger.info("build_extractor: auto selected llm provider (%s)", llm.model_name)
    return llm
