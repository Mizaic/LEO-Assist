"""Top-level pipeline graph builder.

Atlas trace:
  DO: DO-C2F6CA16
  DI: DI-06CB6881
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C2F6CA16")

Composes multiple subgraphs into a single execution graph based on
the action sequence defined in a PlanDefinition.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from libs.pipeline_graph.registry import get_registry
from libs.pipeline_graph.state import PipelineState

logger = logging.getLogger(__name__)


def build_pipeline_graph(
    action_sequence: list[dict[str, Any]],
) -> CompiledStateGraph:
    """Build a composed pipeline graph from an ordered list of actions.

    Each action dict must have at least ``subgraph_id`` and ``action_id``.
    Actions are chained sequentially in the order provided.
    """
    registry = get_registry()
    g = StateGraph(PipelineState)

    if not action_sequence:
        g.add_node("noop", lambda state: state)
        g.add_edge(START, "noop")
        g.add_edge("noop", END)
        return g.compile()

    prev_node = None
    for action in action_sequence:
        subgraph_id = action["subgraph_id"]
        node_id = action.get("action_id", subgraph_id)

        try:
            subgraph = registry.build(subgraph_id)
            g.add_node(node_id, subgraph)
        except KeyError:
            logger.warning("Subgraph %s not found — skipping", subgraph_id)
            continue

        if prev_node is None:
            g.add_edge(START, node_id)
        else:
            g.add_edge(prev_node, node_id)
        prev_node = node_id

    if prev_node:
        g.add_edge(prev_node, END)
    else:
        g.add_node("noop", lambda state: state)
        g.add_edge(START, "noop")
        g.add_edge("noop", END)

    return g.compile()
