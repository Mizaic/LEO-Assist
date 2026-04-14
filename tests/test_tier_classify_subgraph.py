from __future__ import annotations

import pytest

pytest.importorskip("langgraph.graph")

from libs.pipeline_graph.subgraphs.tier_classify import build_tier_classify_subgraph


def test_tier_classify_respects_tier_override():
    graph = build_tier_classify_subgraph()
    out = graph.invoke(
        {
            "coding_mode": "autonomous",
            "entities": [
                {
                    "text": "urgent referral",
                    "_tier_override": 2,
                    "_tier_override_reason": "llm_coding_check_force_review",
                }
            ],
        }
    )
    assert out["tier_decisions"][0]["tier"] == 2
    assert out["tier_decisions"][0]["decision"] == "route_to_review"
    assert out["tier_decisions"][0]["reason"] == "llm_coding_check_force_review"
