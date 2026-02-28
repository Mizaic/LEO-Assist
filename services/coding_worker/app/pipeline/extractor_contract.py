"""Canonical extraction DTO and ExtractorProvider protocol.

CONTRACT_VERSION must be bumped whenever ExtractionItem fields change, so that
persisted outputs can always be traced back to the schema under which they were
produced.  The version is stamped on every :DOCUMENTS relationship and on every
EncounterCandidate node at write time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

CONTRACT_VERSION = "1.0"


@dataclass(frozen=True)
class ExtractionItem:
    """Canonical extraction DTO produced by any ExtractorProvider.

    All extractors — LLM-backed or model-backed — must produce instances of
    this type.  Downstream code must not assume any provider-specific shape.
    """

    sentence_id: str
    text: str
    span_start: int
    span_end: int
    semantic_tag: str
    assertion: str          # present | absent | possible | historical | hypothetical | family
    confidence: float
    normalized: str         # lookup term or normalised surface form
    source_meta: dict[str, Any] = field(default_factory=dict)
    relations: list[dict[str, Any]] = field(default_factory=list)

    # Provenance — stamped at write time from the provider that produced this item
    source: str = "unknown"           # "llm" | "model"
    model_name: str = ""
    model_version: str = ""
    contract_version: str = CONTRACT_VERSION

    def with_provenance(
        self,
        source: str,
        model_name: str,
        model_version: str,
    ) -> "ExtractionItem":
        """Return a new ExtractionItem with provenance fields set."""
        return ExtractionItem(
            sentence_id=self.sentence_id,
            text=self.text,
            span_start=self.span_start,
            span_end=self.span_end,
            semantic_tag=self.semantic_tag,
            assertion=self.assertion,
            confidence=self.confidence,
            normalized=self.normalized,
            source_meta=self.source_meta,
            relations=self.relations,
            source=source,
            model_name=model_name,
            model_version=model_version,
            contract_version=self.contract_version,
        )


@runtime_checkable
class ExtractorProvider(Protocol):
    """Protocol for coding extraction backends.

    Implementations must be stateless with respect to extraction state.
    All context (text, sentences) is passed per call.  Any provider that
    satisfies this protocol can be used by CodingPipeline.
    """

    @property
    def source(self) -> str:
        """Short identifier: ``"llm"`` | ``"model"``."""
        ...

    @property
    def model_name(self) -> str:
        """Human-readable model or provider name stamped on outputs."""
        ...

    @property
    def model_version(self) -> str:
        """Model version string stamped on outputs."""
        ...

    def is_available(self) -> bool:
        """Return True when the backend is ready to accept requests.

        For LLM providers this checks boto3/azure client init.
        For service-hosted models this performs a lightweight health-check.
        """
        ...

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list,
    ) -> list[ExtractionItem]:
        """Extract entities from a batch of sentences.

        Args:
            encounter_text: Full de-identified encounter text (context).
            sentences: List of SentenceChunk from the sentence splitter.

        Returns:
            List of ExtractionItem, each stamped with provenance by the
            provider implementation.

        Raises:
            ExtractionError (or RuntimeError): on unrecoverable backend failure.
        """
        ...
