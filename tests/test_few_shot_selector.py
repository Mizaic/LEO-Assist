from __future__ import annotations

import numpy as np

from libs.prompts.few_shot_selector import FewShotSelector


class _DummyEmbedder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def encode(self, texts):  # noqa: ANN001 - test helper shim
        rows = [self._vectors[t] for t in texts]
        return np.asarray(rows, dtype=np.float32)


def test_selector_picks_top_k_by_similarity() -> None:
    pool = [
        {"category": "observable", "description": "lab", "input": "egfr low"},
        {"category": "assertion:absent", "description": "negation", "input": "no fever"},
        {"category": "multi-entity", "description": "mixed", "input": "ecg and chest pain"},
    ]
    vectors = {
        "category=observable\ndescription=lab\ninput=egfr low": [1.0, 0.0],
        "category=assertion:absent\ndescription=negation\ninput=no fever": [0.0, 1.0],
        "category=multi-entity\ndescription=mixed\ninput=ecg and chest pain": [0.7, 0.7],
        "egfr 38 mmol": [1.0, 0.0],
    }
    selector = FewShotSelector(dynamic_pool=pool, embedder=_DummyEmbedder(vectors))
    selector.warm()

    selected = selector.select("egfr 38 mmol", k=2)
    assert len(selected) == 2
    assert selected[0]["category"] == "observable"
    assert selected[1]["category"] == "multi-entity"


def test_selector_fallback_when_embedder_unavailable() -> None:
    class _NoEmbedder:
        def encode(self, texts):  # noqa: ANN001 - test helper shim
            return None

    pool = [
        {"category": "multi-entity", "description": "mixed", "input": "a"},
        {"category": "abbreviation", "description": "abbr", "input": "b"},
        {"category": "assertion:absent", "description": "neg", "input": "c"},
    ]
    selector = FewShotSelector(dynamic_pool=pool, embedder=_NoEmbedder())
    selected = selector.select("anything", k=2)

    # Fallback order prioritizes critical categories; assertion:absent first.
    assert [e["category"] for e in selected] == ["assertion:absent", "multi-entity"]
