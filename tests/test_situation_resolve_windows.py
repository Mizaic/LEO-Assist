"""Per-situation resolve/expand window scoping.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
"""

from __future__ import annotations

from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
    _collect_concept_targets,
)


def test_collect_concept_targets_scopes_pathway_windows():
    tree = {
        "kind": "AND",
        "children": [
            {
                "kind": "demographic",
                "field": "age",
                "operator": ">=",
                "value": 55,
                "unit": "years",
                "node_id": "n_age",
            },
            {
                "kind": "OR",
                "children": [
                    {
                        "kind": "AND",
                        "pathway_key": "pw_aaaa",
                        "children": [
                            {
                                "kind": "concept",
                                "node_id": "n_a",
                                "term": {"text": "dyspepsia"},
                            }
                        ],
                    },
                    {
                        "kind": "AND",
                        "pathway_key": "pw_bbbb",
                        "children": [
                            {
                                "kind": "concept",
                                "node_id": "n_b",
                                "term": {"text": "haematemesis"},
                            }
                        ],
                    },
                ],
            },
        ],
    }
    targets: dict = {}
    context: dict = {}
    _collect_concept_targets(
        tree,
        targets,
        context_by_node=context,
        windows_by_key={
            "pw_aaaa": "situation A window only",
            "pw_bbbb": "situation B window only",
        },
        full_text="full recommendation text",
    )
    assert targets["n_a"]["text"] == "dyspepsia"
    assert targets["n_b"]["text"] == "haematemesis"
    assert context["n_a"] == "situation A window only"
    assert context["n_b"] == "situation B window only"
    # Age is a prerequisite (no pathway_key) so it uses the full text.
    assert "n_age" not in targets  # demographic is not concept-like
