"""REST connector subgraph.

Executes an HTTP request described by config fields in the runtime state and
returns mapped outputs into the shared pipeline state.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict
from urllib import error as url_error
from urllib import request as url_request

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class RestConnectorState(TypedDict, total=False):
    method: str
    url: str
    headers: dict[str, str]
    body_template: str | dict[str, Any]
    response_mapping: list[dict[str, Any]]
    connector_response: dict[str, Any]
    errors: list[str]


def _resolve_path(payload: Any, path: str) -> Any:
    cursor = payload
    for part in path.split("."):
        if isinstance(cursor, dict):
            cursor = cursor.get(part)
        elif isinstance(cursor, list):
            try:
                cursor = cursor[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cursor


def execute_rest_connector(state: RestConnectorState) -> dict[str, Any]:
    method = str(state.get("method") or "GET").upper()
    url = str(state.get("url") or "")
    headers = dict(state.get("headers") or {})
    body_template = state.get("body_template")
    response_mapping = list(state.get("response_mapping") or [])
    errors = list(state.get("errors") or [])

    if not url:
        errors.append("rest_connector: missing url")
        return {"connector_response": {}, "errors": errors}

    payload_bytes: bytes | None = None
    if body_template is not None:
        if isinstance(body_template, str):
            payload_bytes = body_template.encode("utf-8")
        else:
            payload_bytes = json.dumps(body_template).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    req = url_request.Request(
        url=url, data=payload_bytes, method=method, headers=headers
    )
    response_json: dict[str, Any] = {}
    try:
        with url_request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8") if response else ""
            if body:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    response_json = parsed
                else:
                    response_json = {"data": parsed}
    except (
        url_error.HTTPError,
        url_error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning("REST connector request failed: %s", exc)
        errors.append(f"rest_connector: {exc}")
        return {"connector_response": {}, "errors": errors}

    mapped: dict[str, Any] = {}
    for row in response_mapping:
        llm_field = str(row.get("llmField") or "").strip()
        state_path = str(row.get("statePath") or "").strip()
        if not llm_field or not state_path:
            continue
        mapped[state_path] = _resolve_path(response_json, llm_field)

    return {"connector_response": response_json, **mapped, "errors": errors}


def build_rest_connector_subgraph() -> CompiledStateGraph:
    g = StateGraph(RestConnectorState)
    g.add_node("execute_rest_connector", execute_rest_connector)
    g.add_edge(START, "execute_rest_connector")
    g.add_edge("execute_rest_connector", END)
    return g.compile()
