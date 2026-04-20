"""REST connector subgraph.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")

Executes an HTTP request described by config fields in the runtime state and
returns mapped outputs into the shared pipeline state.

SSRF guard
----------
Pipeline configs are authored by trusted users today, but the connector
treats every URL as attacker-controlled because future automated jobs
may pull URLs from external systems. The guard:

* Restricts schemes to http/https.
* Blocks RFC1918 / loopback / link-local / multicast / reserved IPs.
* Blocks IPv6 ULA, link-local, and loopback ranges.
* Optional REST_CONNECTOR_HOST_ALLOWLIST env var (comma-separated host
  list) shrinks the allowed surface further. When set, the URL host
  must match exactly (case-insensitive) one of the allow-listed hosts.

Hostnames are resolved before the request is issued; every resolved
address must pass the IP allowlist check, which prevents a DNS that
returns a private address from punching through the guard.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
from typing import Any, TypedDict
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = {"http", "https"}
_HOST_ALLOWLIST_ENV = "REST_CONNECTOR_HOST_ALLOWLIST"


class RestConnectorError(Exception):
    """Raised when the request URL fails the SSRF guard."""


class RestConnectorState(TypedDict, total=False):
    method: str
    url: str
    headers: dict[str, str]
    body_template: str | dict[str, Any]
    response_mapping: list[dict[str, Any]]
    connector_response: dict[str, Any]
    errors: list[str]


def _host_allowlist() -> set[str]:
    raw = os.environ.get(_HOST_ALLOWLIST_ENV, "").strip()
    if not raw:
        return set()
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _is_ip_safe(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return False
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return False
    return True


def _validate_url(url: str) -> None:
    parsed = url_parse.urlsplit(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise RestConnectorError(
            f"unsupported scheme {parsed.scheme!r}; only http/https are allowed"
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise RestConnectorError("url has no host")

    allowlist = _host_allowlist()
    if allowlist and host not in allowlist:
        raise RestConnectorError(f"host {host!r} is not in the allowlist")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise RestConnectorError(f"DNS lookup failed for {host!r}: {exc}") from exc
    if not infos:
        raise RestConnectorError(f"DNS lookup returned no addresses for {host!r}")
    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        if not _is_ip_safe(ip_str):
            raise RestConnectorError(
                f"host {host!r} resolves to disallowed address {ip_str!r}"
            )


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

    try:
        _validate_url(url)
    except RestConnectorError as exc:
        logger.warning("REST connector blocked URL %r: %s", url, exc)
        errors.append(f"rest_connector: blocked url ({exc})")
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
