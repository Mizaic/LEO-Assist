"""Queue publish connector subgraph.

Publishes a message to the configured message bus queue.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class QueuePublishState(TypedDict, total=False):
    queue_name: str
    schedule_after_seconds: int
    message_body: dict[str, Any]
    errors: list[str]


def publish_to_queue(state: QueuePublishState) -> dict[str, Any]:
    queue_name = str(state.get("queue_name") or "pipeline-jobs")
    schedule_after_seconds = int(state.get("schedule_after_seconds") or 0)
    message_body = dict(state.get("message_body") or {})
    errors = list(state.get("errors") or [])

    # Actual publish is performed by WorkflowEngine (has async bus context).
    logger.info("Queue publish requested: queue=%s delay=%ss", queue_name, schedule_after_seconds)
    return {
        "queue_publish_request": {
            "queue_name": queue_name,
            "schedule_after_seconds": schedule_after_seconds,
            "message_body": message_body,
        },
        "queued": True,
        "errors": errors,
    }


def build_queue_publish_subgraph() -> CompiledStateGraph:
    g = StateGraph(QueuePublishState)
    g.add_node("publish_to_queue", publish_to_queue)
    g.add_edge(START, "publish_to_queue")
    g.add_edge("publish_to_queue", END)
    return g.compile()

