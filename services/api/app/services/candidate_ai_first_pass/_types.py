"""Data types for the AI first-pass workflow.

Atlas trace:
  DO: DO-D7005C41
  DI: DI-0FFA05BB
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D7005C41")

DI-LEO-AI-208 / DO-LEO-AI-205.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Verdict surface for a candidate after the AI first-pass.
#  - pre_done: AI extracted + coded at least one entity; entities_json is
#    overwritten with the AI pass; status stays 'pending'.
#  - delete:   AI extracted entities but NONE could be coded (and no safety
#    rail fired); the candidate is cascade-deleted.
#  - review:   safety rail fired or the verdict is mixed; no writes happen.
AIFirstPassVerdict = Literal["pre_done", "delete", "review"]

# Action actually taken on disk for a candidate after the verdict ran.
#  - upserted_pre_done: entities_json overwritten + audit copy stashed.
#  - deleted:           DETACH DELETE applied.
#  - skipped_completed: TOCTOU re-check found status='completed'; no-op.
#  - skipped_review:    verdict=review; no-op by design.
#  - error:             unhandled exception; recorded; no-op.
AIFirstPassAction = Literal[
    "upserted_pre_done",
    "deleted",
    "skipped_completed",
    "skipped_review",
    "error",
]

_DEFAULT_STATUSES: tuple[str, ...] = ("pending", "processing", "failed")


@dataclass(frozen=True)
class AIFirstPassParams:
    """Caller-supplied tunables for the AI first-pass."""

    min_surface_match: float = 0.7
    semantic_vector_floor: float = 0.92
    semantic_min_surface: float = 0.66
    statuses: tuple[str, ...] = _DEFAULT_STATUSES
    limit: int = 200
    max_workers: int = 4
    few_shot_k: int = 5
    few_shot_pool_limit: int = 1500
    coder_max_retries: int = 2
    haiku_tier: str = "small"
    dry_run: bool = False  # When True, never writes or deletes; pure preview.

    def validator_kwargs(self) -> dict[str, float]:
        return {
            "min_surface_match": float(self.min_surface_match),
            "semantic_vector_floor": float(self.semantic_vector_floor),
            "semantic_min_surface": float(self.semantic_min_surface),
        }


@dataclass
class CodingOutcome:
    """Result of coding ONE entity through the AI smart loop."""

    text: str
    label: str
    accepted: bool
    snomed_concept_id: str | None = None
    snomed_term: str | None = None
    score: float = 0.0
    surface_match: float = 0.0
    rejection_reason: str = ""
    alt_query_used: str | None = None
    retries_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "label": self.label,
            "accepted": self.accepted,
            "snomed_concept_id": self.snomed_concept_id,
            "snomed_term": self.snomed_term,
            "score": round(float(self.score or 0.0), 3),
            "surface_match": round(float(self.surface_match or 0.0), 3),
            "rejection_reason": self.rejection_reason,
            "alt_query_used": self.alt_query_used,
            "retries_used": int(self.retries_used or 0),
        }


@dataclass
class ExtractedEntity:
    """One entity emitted by the Haiku extractor (or copied from the
    original entities_json when the extractor falls back)."""

    text: str
    label: str
    assertion: str = "present"
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self.extras)
        out["text"] = self.text
        out["label"] = self.label
        if self.assertion and self.assertion != "present":
            out["assertion"] = self.assertion
        out["ai_first_pass"] = True
        return out


@dataclass
class ExtractionResult:
    """Outcome of the AI extraction step for one candidate."""

    entities: list[ExtractedEntity]
    fallback_used: bool = False
    extractor_error: str | None = None

    @property
    def entity_count(self) -> int:
        return len(self.entities)


@dataclass
class CandidateOutcome:
    """Per-candidate outcome of the AI first-pass."""

    candidate_id: str
    status: str
    source: str
    text: str
    verdict: AIFirstPassVerdict
    action: AIFirstPassAction
    extraction: ExtractionResult
    codings: list[CodingOutcome] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def accepted_count(self) -> int:
        return sum(1 for c in self.codings if c.accepted)

    @property
    def rejected_count(self) -> int:
        return sum(1 for c in self.codings if not c.accepted)

    def to_event(self) -> dict[str, Any]:
        """Compact representation for an SSE 'candidate_done' event."""
        return {
            "type": "candidate_done",
            "candidate_id": self.candidate_id,
            "status": self.status,
            "source": self.source,
            "verdict": self.verdict,
            "action": self.action,
            "entity_count": self.extraction.entity_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "fallback_used": self.extraction.fallback_used,
            "rejection_reasons": list(self.rejection_reasons),
            "error": self.error,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "source": self.source,
            "text": self.text,
            "verdict": self.verdict,
            "action": self.action,
            "entity_count": self.extraction.entity_count,
            "fallback_used": self.extraction.fallback_used,
            "extractor_error": self.extraction.extractor_error,
            "codings": [c.to_dict() for c in self.codings],
            "rejection_reasons": list(self.rejection_reasons),
            "error": self.error,
        }
