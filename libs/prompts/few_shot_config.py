"""Configuration for dynamic few-shot example selection.

Every default here is a no-op that reproduces the pre-existing
behaviour. Extraction is a Class B path, so enabling a retrieval change
must be an explicit configuration decision that can go through change
control -- not something that shifts when this module is deployed.

Atlas trace:
  DO: DO-83EBEE2C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-83EBEE2C")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in _TRUE_VALUES


@dataclass(frozen=True)
class FewShotSelectionConfig:
    """How to turn a ranked candidate list into prompt examples.

    Attributes:
        min_similarity: Drop candidates scoring below this cosine value.
            An irrelevant exemplar misleads extraction, so returning
            fewer examples is safer than padding to k. 0.0 disables.
        diversity_lambda: Maximal-marginal-relevance weight. 1.0 is pure
            relevance (disabled); lower values trade relevance for
            spread so the budget is not spent on near-duplicates.
        candidate_multiplier: Retrieve ``k * multiplier`` candidates
            before the diversity pass. 1 disables the two-stage split.
        max_query_chars: Bound the query text to this many trailing
            characters before embedding. The query is the encounter text
            followed by the sentence block, and the sentences are what
            is actually being extracted, so the tail is the part worth
            keeping when the embedder has a token limit. 0 disables.
        ascending_prompt_order: Render examples weakest-first so the
            strongest sits immediately before the query.
    """

    min_similarity: float = 0.0
    diversity_lambda: float = 1.0
    candidate_multiplier: int = 1
    max_query_chars: int = 0
    ascending_prompt_order: bool = False

    @classmethod
    def disabled(cls) -> FewShotSelectionConfig:
        """Return the all-defaults config, ignoring the environment."""
        return cls()

    @classmethod
    def from_env(cls) -> FewShotSelectionConfig:
        """Read the config from the environment, defaulting to disabled."""
        return cls(
            min_similarity=max(0.0, _env_float("FEW_SHOT_MIN_SIMILARITY", 0.0)),
            diversity_lambda=min(
                1.0, max(0.0, _env_float("FEW_SHOT_DIVERSITY_LAMBDA", 1.0))
            ),
            candidate_multiplier=max(1, _env_int("FEW_SHOT_CANDIDATE_MULTIPLIER", 1)),
            max_query_chars=max(0, _env_int("FEW_SHOT_MAX_QUERY_CHARS", 0)),
            ascending_prompt_order=_env_bool("FEW_SHOT_ASCENDING_ORDER", False),
        )

    def replace(self, **changes: Any) -> FewShotSelectionConfig:
        """Return a copy with ``changes`` applied (test and tuning helper)."""
        return replace(self, **changes)

    def bounded_query(self, query_text: str) -> str:
        """Trim ``query_text`` to the configured trailing character budget."""
        if self.max_query_chars <= 0:
            return query_text
        return query_text[-self.max_query_chars :]
