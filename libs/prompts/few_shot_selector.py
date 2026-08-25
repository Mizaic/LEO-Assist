"""Few-shot selector that ranks dynamic examples by semantic similarity.

Selection is two-stage: rank the routed pool by cosine similarity, then
apply a minimum-relevance floor and a diversity pass. Both stages are
no-ops by default (see ``FewShotSelectionConfig``).

The shared embedder lives in ``few_shot_embedder`` and is re-exported
here for the existing warm-up call sites.

Atlas trace:
  DO: DO-83EBEE2C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-83EBEE2C")
"""

from __future__ import annotations

import logging
import re

import numpy as np

from libs.prompts.few_shot_config import FewShotSelectionConfig
from libs.prompts.few_shot_embedder import (
    _get_shared_embedder,
    _LazySentenceEmbedder,
    warm_shared_embedder,
)
from libs.prompts.few_shot_ranking import (
    apply_similarity_floor,
    mmr_select,
    rank_by_score,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FewShotSelector",
    "warm_shared_embedder",
]

#: Minimum routed-bucket size before falling back to broad recall.
_MIN_ROUTED_POOL = 3

#: Query domain buckets, checked in order; first match wins.
_QUERY_BUCKET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "labs",
        re.compile(
            r"\b(hba1c|egfr|creatinine|haemoglobin|hemoglobin|platelet"
            r"|lymphocyte|neutrophil|monocyte|eosinophil|basophil"
            r"|mmol/l|10\^9/l|g/l|fbc|full blood count)\b"
        ),
    ),
    (
        "oncology",
        re.compile(
            r"\b(stage|staging|tnm|metastatic|oncology|carcinoma"
            r"|tumour|tumor|cancer)\b"
        ),
    ),
    (
        "referral_admin",
        re.compile(
            r"\b(referral|urgent|two week wait|2ww|booked"
            r"|appointment|admin|letter)\b"
        ),
    ),
    (
        "medication",
        re.compile(r"\b(medication|dose|tablet|capsule|mg|drug|prescribed)\b"),
    ),
)


class FewShotSelector:
    """Select top-k dynamic examples using cosine similarity."""

    def __init__(
        self,
        dynamic_pool: list[dict],
        embedder: _LazySentenceEmbedder | None = None,
        config: FewShotSelectionConfig | None = None,
    ):
        self._pool = list(dynamic_pool or [])
        # Use the shared singleton unless a custom embedder is passed in.
        self._embedder = embedder if embedder is not None else _get_shared_embedder()
        self._config = (
            config if config is not None else FewShotSelectionConfig.from_env()
        )
        self._pool_embeddings: np.ndarray | None = None

    def warm(self) -> None:
        """Pre-compute and cache embeddings for the dynamic example pool."""
        if not self._pool:
            self._pool_embeddings = None
            return
        texts = [self._example_text(ex) for ex in self._pool]
        vectors = self._embedder.encode(texts)
        if vectors is None or len(vectors) != len(self._pool):
            self._pool_embeddings = None
            return
        self._pool_embeddings = vectors

    def select(self, query_text: str, k: int) -> list[dict]:
        """Return top-k examples by similarity, with deterministic fallback."""
        examples, _ = self.select_with_scores(query_text, k)
        return examples

    def select_with_scores(self, query_text: str, k: int) -> tuple[list[dict], float]:
        """Return selected examples and the best cosine similarity.

        The score is returned even when the floor rejects every
        candidate, because it doubles as the distribution-shift signal
        read by the document quality gate.
        """
        if k <= 0 or not self._pool:
            return [], 0.0
        query = self._config.bounded_query(query_text or "")
        indices = self.route_indices(query) or list(range(len(self._pool)))

        ranked, vectors = self._rank(query, indices)
        if ranked is None:
            return self._fallback(indices, k), 0.0

        chosen, best = self._choose(ranked, vectors, k)
        return [self._pool[i] for i, _ in chosen], best

    def select_detailed(
        self, query_text: str, k: int
    ) -> tuple[list[tuple[dict, float]], float]:
        """Return (example, similarity) pairs plus the best similarity.

        Only the semantic path produces per-example scores; the
        deterministic fallback returns an empty list so callers can tell
        "ranked by similarity" from "ordered by category".
        """
        if k <= 0 or not self._pool:
            return [], 0.0
        query = self._config.bounded_query(query_text or "")
        indices = self.route_indices(query) or list(range(len(self._pool)))

        ranked, vectors = self._rank(query, indices)
        if ranked is None:
            return [], 0.0

        chosen, best = self._choose(ranked, vectors, k)
        return [(self._pool[i], score) for i, score in chosen], best

    def _choose(
        self,
        ranked: list[tuple[int, float]],
        vectors: np.ndarray | None,
        k: int,
    ) -> tuple[list[tuple[int, float]], float]:
        """Apply the floor and diversity pass, keeping each item's score."""
        best = ranked[0][1] if ranked else 0.0
        candidates = apply_similarity_floor(ranked, self._config.min_similarity)
        window = candidates[: max(k, k * self._config.candidate_multiplier)]
        chosen = mmr_select(window, vectors, k, self._config.diversity_lambda)
        scores = dict(window)
        return [(i, scores.get(i, 0.0)) for i in chosen], best

    def _rank(
        self, query: str, indices: list[int]
    ) -> tuple[list[tuple[int, float]] | None, np.ndarray | None]:
        """Score ``indices`` against ``query``; None means no embeddings."""
        vectors = self._pool_embeddings
        if vectors is None:
            self.warm()
            vectors = self._pool_embeddings
        if vectors is None:
            vectors = self._encode_subset(indices)
            if vectors is None:
                return None, None
            qv = self._query_vector(query, vectors.shape[1])
            if qv is None:
                return None, None
            return rank_by_score(indices, vectors @ qv), None

        qv = self._query_vector(query, vectors.shape[1])
        if qv is None:
            return None, None
        return rank_by_score(indices, vectors[indices] @ qv), vectors

    def _encode_subset(self, indices: list[int]) -> np.ndarray | None:
        """Embed only the routed examples when no pool cache exists."""
        texts = [self._example_text(self._pool[i]) for i in indices]
        encoded = self._embedder.encode(texts)
        if encoded is None or len(encoded) != len(indices):
            return None
        return encoded

    def _query_vector(self, query: str, width: int) -> np.ndarray | None:
        qv = self._embedder.encode([query])
        if qv is None or qv.shape[0] != 1 or qv.shape[1] != width:
            return None
        return qv[0]

    def _fallback(self, indices: list[int], k: int) -> list[dict]:
        """Deterministic category ordering when embeddings are unavailable."""
        ordered = sorted(
            (self._pool[i] for i in indices),
            key=lambda ex: (
                self._fallback_priority(str(ex.get("category", ""))),
                str(ex.get("description", "")),
            ),
        )
        return ordered[: min(k, len(ordered))]

    def route_indices(self, query_text: str) -> list[int]:
        """Route retrieval by domain so lab-heavy notes prefer lab slices.

        Returns pool positions rather than example dicts so the warmed
        embedding matrix can be sliced directly, and so the sparse-route
        remainder is a set operation instead of a quadratic scan.
        """
        bucket = self._query_bucket(query_text)
        if bucket == "generic":
            return list(range(len(self._pool)))
        mapped = [
            i for i, ex in enumerate(self._pool) if self._example_bucket(ex) == bucket
        ]
        if len(mapped) >= _MIN_ROUTED_POOL:
            return mapped
        # Keep strict route preference while allowing broad recall when sparse.
        routed = set(mapped)
        return mapped + [i for i in range(len(self._pool)) if i not in routed]

    @staticmethod
    def _query_bucket(query_text: str) -> str:
        text = (query_text or "").lower()
        for bucket, pattern in _QUERY_BUCKET_PATTERNS:
            if pattern.search(text):
                return bucket
        return "generic"

    @staticmethod
    def _example_bucket(example: dict) -> str:
        category = str(example.get("category", "")).lower()
        if any(
            t in category for t in ("lab", "observable", "value-unit", "haematology")
        ):
            return "labs"
        if any(t in category for t in ("oncology", "staging", "cancer")):
            return "oncology"
        if any(t in category for t in ("referral", "admin", "pathway")):
            return "referral_admin"
        if any(t in category for t in ("medication", "drug", "substance")):
            return "medication"
        return "generic"

    @staticmethod
    def _example_text(example: dict) -> str:
        return "\n".join(
            [
                f"category={example.get('category', '')}",
                f"description={example.get('description', '')}",
                f"input={example.get('input', '')}",
            ]
        )

    @staticmethod
    def _fallback_priority(category: str) -> int:
        ordered_prefixes = [
            "assertion:absent",
            "negation:compound",
            "assertion:family",
            "assertion:historical",
            "observable",
            "multi-entity",
            "assertion:hypothetical",
            "abbreviation",
        ]
        for i, prefix in enumerate(ordered_prefixes):
            if category.startswith(prefix):
                return i
        return len(ordered_prefixes) + 1
