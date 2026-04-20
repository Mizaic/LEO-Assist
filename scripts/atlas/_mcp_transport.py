"""HTTP transport for the Atlas Design Controls MCP server.

Lightweight, stdlib-only client that talks JSON-RPC over HTTP/SSE.
Initialise once per process via `initialize()`, then call tools via
`call_tool(name, arguments)`. Reads URL + headers from
~/.cursor/mcp.json (key: mcpServers.atlas-design-controls).

Adapted from design-controls/risks/fire_atlas_fmea.py.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

MCP_CFG_PATH = Path.home() / ".cursor" / "mcp.json"
MCP_SERVER_KEY = "atlas-design-controls"


class McpError(Exception):
    pass


def _load_mcp_config() -> tuple[str, dict]:
    cfg = json.loads(MCP_CFG_PATH.read_text())
    server = cfg["mcpServers"][MCP_SERVER_KEY]
    return server["url"], dict(server["headers"])


_MCP_URL, _MCP_HEADERS = _load_mcp_config()
_COOKIES: dict[str, str] = {}
_REQ_ID = 0
_SESSION_ID: str | None = None


def _build_request(payload: dict) -> urllib.request.Request:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(_MCP_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    req.add_header("User-Agent", "leo-ai-atlas-cutover/1.0")
    for k, v in _MCP_HEADERS.items():
        req.add_header(k, v)
    if _COOKIES:
        cookie_hdr = "; ".join(f"{k}={v}" for k, v in _COOKIES.items())
        req.add_header("Cookie", cookie_hdr)
    return req


def _capture_cookies(resp) -> None:
    for cookie in resp.headers.get_all("Set-Cookie") or []:
        kv = cookie.split(";", 1)[0].strip()
        if "=" in kv:
            k, v = kv.split("=", 1)
            _COOKIES[k] = v


def _parse_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    last_data = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            last_data = line[5:].strip()
    if last_data is None:
        raise McpError(f"Unparseable response: {raw[:300]}")
    return json.loads(last_data)


def _post(payload: dict, timeout: int = 90) -> dict:
    req = _build_request(payload)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _capture_cookies(resp)
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            _capture_cookies(e)
        except Exception:
            pass
        body = e.read().decode("utf-8", "ignore")[:500]
        raise McpError(f"HTTP {e.code}: {body}")
    return _parse_response(raw)


def initialize() -> str | None:
    """MCP initialise handshake. Captures mcp-session-id when present."""
    global _REQ_ID, _SESSION_ID, _MCP_HEADERS
    _REQ_ID += 1
    payload = {
        "jsonrpc": "2.0",
        "id": _REQ_ID,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "leo-ai-atlas-cutover", "version": "1.0"},
        },
    }
    req = _build_request(payload)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            _capture_cookies(resp)
            resp.read()
            sid = resp.headers.get("mcp-session-id") or resp.headers.get(
                "Mcp-Session-Id"
            )
    except urllib.error.HTTPError as e:
        try:
            _capture_cookies(e)
        except Exception:
            pass
        raise
    if sid:
        _SESSION_ID = sid
        _MCP_HEADERS = dict(_MCP_HEADERS)
        _MCP_HEADERS["mcp-session-id"] = sid
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    nreq = _build_request(notif)
    try:
        with urllib.request.urlopen(nreq, timeout=10) as r2:
            _capture_cookies(r2)
            r2.read()
    except Exception:
        pass
    return _SESSION_ID


def call_tool(name: str, arguments: dict, retries: int = 3) -> dict:
    """Call an Atlas MCP tool. Retries on network errors. Raises on tool errors."""
    global _REQ_ID
    last_err: Exception | None = None
    for attempt in range(retries):
        _REQ_ID += 1
        payload = {
            "jsonrpc": "2.0",
            "id": _REQ_ID,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        try:
            resp = _post(payload, timeout=120)
        except (McpError, urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
            continue
        if "error" in resp:
            err = resp["error"]
            raise McpError(f"{name}: {err.get('code')} {err.get('message')}")
        result = resp.get("result", {})
        if "structuredContent" in result:
            return result["structuredContent"]
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text":
                txt = item.get("text", "")
                if txt.startswith("Error executing tool"):
                    raise McpError(f"{name}: {txt[:2000]}")
                try:
                    return json.loads(txt)
                except json.JSONDecodeError:
                    return {"_text": txt}
        return result
    raise McpError(f"{name}: exhausted retries: {last_err}")
