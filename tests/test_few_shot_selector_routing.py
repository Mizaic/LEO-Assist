from __future__ import annotations

import numpy as np


class _NoEmbedder:
    model_name = ""

    def encode(self, texts):
        _ = texts
        return None


class _Embedder:
    model_name = "dummy"

    def encode(self, texts):
        # deterministic tiny embeddings for stable rank tests
        vectors = []
        for t in texts:
            score = float(len(str(t)))
            vectors.append([score, 1.0])
        return np.asarray(vectors, dtype=np.float32)


def test_routes_lab_query_to_lab_examples():
    from libs.prompts.few_shot_selector import FewShotSelector

    pool = [
        {"id": "lab-1", "category": "labs:cbc", "input": "Hb 116 g/L"},
        {"id": "onc-1", "category": "oncology:stage", "input": "TNM T2N1M0"},
        {"id": "ref-1", "category": "referral:pathway", "input": "2ww referral"},
        {"id": "lab-2", "category": "observable:value-unit", "input": "eGFR 58"},
    ]
    selector = FewShotSelector(dynamic_pool=pool, embedder=_NoEmbedder())
    selected = selector.select("Full blood count Hb 116 g/L", k=2)
    ids = [x["id"] for x in selected]
    assert "lab-1" in ids
    assert "lab-2" in ids


def test_semantic_rank_works_after_routing():
    from libs.prompts.few_shot_selector import FewShotSelector

    pool = [
        {"id": "lab-short", "category": "labs", "input": "Hb"},
        {"id": "lab-long", "category": "labs", "input": "haemoglobin concentration"},
        {"id": "onc", "category": "oncology", "input": "staging"},
    ]
    selector = FewShotSelector(dynamic_pool=pool, embedder=_Embedder())
    selected = selector.select("haemoglobin concentration", k=1)
    assert selected[0]["id"] == "lab-long"
