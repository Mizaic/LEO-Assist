"""Retrieval-quality behaviour for the few-shot selector.

Covers the 2026 two-stage retrieval pattern: rank by similarity, then
apply a minimum-relevance floor and a diversity pass, and render the
strongest example closest to the query.

Defaults must preserve the pre-existing behaviour so enabling any of
this stays a deliberate configuration change.
"""

from __future__ import annotations

import numpy as np
import pytest

from libs.prompts.few_shot_config import FewShotSelectionConfig
from libs.prompts.few_shot_selector import FewShotSelector


class _CountingEmbedder:
    """Embeds each text as a fixed vector and counts encode calls."""

    model_name = "counting"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[list[str]] = []

    def encode(self, texts):  # noqa: ANN001 - test helper shim
        batch = list(texts)
        self.calls.append(batch)
        rows = [self._vectors[t] for t in batch]
        return np.asarray(rows, dtype=np.float32)

    @property
    def encoded_texts(self) -> list[str]:
        return [t for batch in self.calls for t in batch]


def _example_text(example: dict) -> str:
    return "\n".join(
        [
            f"category={example.get('category', '')}",
            f"description={example.get('description', '')}",
            f"input={example.get('input', '')}",
        ]
    )


def _lab_pool() -> list[dict]:
    return [
        {"id": "lab-1", "category": "labs:cbc", "description": "", "input": "Hb 116"},
        {"id": "lab-2", "category": "labs:cbc", "description": "", "input": "eGFR 58"},
        {"id": "lab-3", "category": "labs:cbc", "description": "", "input": "HbA1c 61"},
        {"id": "onc-1", "category": "oncology", "description": "", "input": "TNM"},
    ]


def _unit_vectors(pool: list[dict], query: str) -> dict[str, list[float]]:
    """Distinct near-orthogonal vectors so ranking is unambiguous."""
    vectors = {query: [1.0, 0.0, 0.0]}
    presets = [
        [1.0, 0.0, 0.0],
        [0.9, 0.44, 0.0],
        [0.6, 0.8, 0.0],
        [0.0, 0.0, 1.0],
    ]
    for example, vec in zip(pool, presets):
        vectors[_example_text(example)] = vec
    return vectors


# -- cache reuse on routed queries ------------------------------------------


def test_routed_query_reuses_warmed_pool_embeddings() -> None:
    """A lab query narrows the pool but must not re-embed pool text.

    Before the index-based refactor the routed path re-encoded every
    routed example on every call, so warming bought nothing on exactly
    the domain-routed queries where routing matters.
    """
    pool = _lab_pool()
    query = "HbA1c 61 mmol/mol and eGFR 58"
    embedder = _CountingEmbedder(_unit_vectors(pool, query))
    selector = FewShotSelector(dynamic_pool=pool, embedder=embedder)
    selector.warm()

    warm_calls = len(embedder.calls)
    selector.select(query, k=2)

    assert len(embedder.calls) == warm_calls + 1
    assert embedder.calls[-1] == [query]


def test_sparse_route_returns_every_pool_position_exactly_once() -> None:
    """Sparse routes fall back to routed positions then the remainder.

    Routing on indices rather than dict identity keeps this a set
    operation. The old ``ex not in mapped`` scan compared dict values
    pairwise, which is quadratic over a pool that can hold 1500 rows.
    """
    duplicate = {"category": "generic", "description": "", "input": "same text"}
    pool = [
        {"category": "medication:dose", "description": "", "input": "10mg OD"},
        dict(duplicate),
        dict(duplicate),
    ]
    selector = FewShotSelector(
        dynamic_pool=pool,
        embedder=_CountingEmbedder({}),
        config=FewShotSelectionConfig.disabled(),
    )

    indices = selector.route_indices("prescribed 10mg tablet")

    assert indices[0] == 0
    assert sorted(indices) == [0, 1, 2]


# -- minimum relevance floor ------------------------------------------------


def test_similarity_floor_drops_weak_examples() -> None:
    """An irrelevant exemplar misleads extraction; below the floor, drop it."""
    pool = _lab_pool()
    query = "HbA1c 61 mmol/mol"
    embedder = _CountingEmbedder(_unit_vectors(pool, query))
    selector = FewShotSelector(
        dynamic_pool=pool,
        embedder=embedder,
        config=FewShotSelectionConfig.disabled().replace(min_similarity=0.8),
    )
    selector.warm()

    selected, best = selector.select_with_scores(query, k=4)

    assert [e["id"] for e in selected] == ["lab-1", "lab-2"]
    assert best == pytest.approx(1.0)


def test_similarity_floor_can_return_no_examples_but_keeps_best_score() -> None:
    """Zero-shot beats a misleading exemplar, and the gate still sees the score."""
    pool = _lab_pool()
    query = "HbA1c 61 mmol/mol"
    embedder = _CountingEmbedder(_unit_vectors(pool, query))
    selector = FewShotSelector(
        dynamic_pool=pool,
        embedder=embedder,
        config=FewShotSelectionConfig.disabled().replace(min_similarity=1.01),
    )
    selector.warm()

    selected, best = selector.select_with_scores(query, k=4)

    assert selected == []
    assert best == pytest.approx(1.0)


# -- diversity --------------------------------------------------------------


def test_diversity_pass_avoids_near_duplicate_examples() -> None:
    """Pure top-k spends the budget on near-duplicates; MMR spreads it."""
    pool = [
        {"id": "a", "category": "labs", "description": "", "input": "one"},
        {"id": "near-a", "category": "labs", "description": "", "input": "two"},
        {"id": "different", "category": "labs", "description": "", "input": "three"},
    ]
    query = "q"
    # Unit vectors: near-a sits almost on top of a; different is further out.
    vectors = {
        query: [1.0, 0.0],
        _example_text(pool[0]): [0.99, 0.1411],
        _example_text(pool[1]): [0.98, 0.1990],
        _example_text(pool[2]): [0.80, 0.6000],
    }
    base = FewShotSelectionConfig.disabled()

    relevance_only = FewShotSelector(
        dynamic_pool=pool, embedder=_CountingEmbedder(vectors), config=base
    )
    relevance_only.warm()
    assert [e["id"] for e in relevance_only.select(query, k=2)] == ["a", "near-a"]

    diverse = FewShotSelector(
        dynamic_pool=pool,
        embedder=_CountingEmbedder(vectors),
        config=base.replace(diversity_lambda=0.3, candidate_multiplier=3),
    )
    diverse.warm()
    assert [e["id"] for e in diverse.select(query, k=2)] == ["a", "different"]


# -- defaults preserve current behaviour ------------------------------------


def test_defaults_are_pure_relevance_top_k() -> None:
    pool = _lab_pool()
    query = "HbA1c 61 mmol/mol"
    embedder = _CountingEmbedder(_unit_vectors(pool, query))
    selector = FewShotSelector(dynamic_pool=pool, embedder=embedder)
    selector.warm()

    selected, best = selector.select_with_scores(query, k=3)

    assert [e["id"] for e in selected] == ["lab-1", "lab-2", "lab-3"]
    assert best == pytest.approx(1.0)


def test_select_detailed_exposes_per_example_scores() -> None:
    """The admin preview needs per-example scores without reaching into privates.

    Going through the public API also means the preview applies domain
    routing, so what an author previews matches what runtime sends.
    """
    pool = _lab_pool()
    query = "HbA1c 61 mmol/mol"
    embedder = _CountingEmbedder(_unit_vectors(pool, query))
    selector = FewShotSelector(dynamic_pool=pool, embedder=embedder)
    selector.warm()

    detailed, best = selector.select_detailed(query, k=2)

    assert [ex["id"] for ex, _ in detailed] == ["lab-1", "lab-2"]
    assert [round(score, 3) for _, score in detailed] == [1.0, 0.9]
    assert best == pytest.approx(1.0)


def test_select_detailed_is_empty_without_embeddings_but_select_still_works() -> None:
    pool = _lab_pool()

    class _NoEmbedder:
        model_name = ""

        def encode(self, texts):  # noqa: ANN001 - test helper shim
            _ = texts
            return None

    selector = FewShotSelector(dynamic_pool=pool, embedder=_NoEmbedder())

    detailed, best = selector.select_detailed("HbA1c 61", k=2)

    assert detailed == []
    assert best == 0.0
    assert len(selector.select("HbA1c 61", k=2)) == 2


def test_disabled_config_matches_env_free_defaults() -> None:
    cfg = FewShotSelectionConfig.disabled()

    assert cfg.min_similarity == 0.0
    assert cfg.diversity_lambda == 1.0
    assert cfg.candidate_multiplier == 1
    assert cfg.max_query_chars == 0
    assert cfg.ascending_prompt_order is False


# -- long query bounding ----------------------------------------------------


def test_query_is_bounded_from_the_end_when_configured() -> None:
    """Front matter is boilerplate; the clinical content sits later.

    Silent truncation by the tokeniser keeps the letterhead and discards
    the clinical body, which is backwards for retrieval.
    """
    pool = _lab_pool()
    tail = "HbA1c 61 mmol/mol"
    query = ("Practice letterhead and address. " * 40) + tail
    vectors = _unit_vectors(pool, query)
    vectors[tail] = [1.0, 0.0, 0.0]
    embedder = _CountingEmbedder(vectors)
    selector = FewShotSelector(
        dynamic_pool=pool,
        embedder=embedder,
        config=FewShotSelectionConfig.disabled().replace(max_query_chars=len(tail)),
    )
    selector.warm()

    selector.select(query, k=1)

    assert embedder.calls[-1] == [tail]
