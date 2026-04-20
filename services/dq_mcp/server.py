"""LEO DQ MCP Server -- stdio transport.

Atlas trace:
  DO: DO-0998FAF5
  Also implements: DO-86800C9B
  DI: DI-FC80B65A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")

Usage:
  python -m services.dq_mcp.server

Or via mcp.json:
  {
    "mcpServers": {
      "leo-dq": {
        "command": "python",
        "args": ["-m", "services.dq_mcp.server"],
        "cwd": "/path/to/LEO-AI-CORE",
        "env": {
          "DQ_API_BASE_URL": "http://localhost:8000",
          "DQ_API_COOKIE": "session=<your-admin-session-cookie>"
        }
      }
    }
  }

All mutation tools are excluded (R-LEO-AI-063). Read-only tools only.
"""

from __future__ import annotations

import json
import logging
import sys

from services.dq_mcp.tools import TOOL_MAP, TOOLS

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCP protocol helpers (JSON-RPC 2.0 over stdio)
# ---------------------------------------------------------------------------


def _send(msg: dict) -> None:
    line = json.dumps(msg)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _recv() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Request handlers
# ---------------------------------------------------------------------------


def _handle_initialize(req: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "leo-dq", "version": "1.0.0"},
            "capabilities": {"tools": {}},
        },
    }


def _handle_list_tools(req: dict) -> dict:
    tool_list = [
        {
            "name": t["name"],
            "description": t["description"],
            "inputSchema": t["inputSchema"],
        }
        for t in TOOLS
    ]
    return {
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "result": {"tools": tool_list},
    }


def _handle_call_tool(req: dict) -> dict:
    params = req.get("params") or {}
    name = params.get("name") or ""
    arguments = params.get("arguments") or {}
    req_id = req.get("id")

    tool = TOOL_MAP.get(name)
    if not tool:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {name}"},
        }

    try:
        result = tool["fn"](**arguments)
        text = json.dumps(result, default=str, ensure_ascii=False)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            },
        }
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            },
        }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

_HANDLERS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_list_tools,
    "tools/call": _handle_call_tool,
}


def run() -> None:
    """Run the MCP server until stdin closes."""
    while True:
        req = _recv()
        if req is None:
            break
        method = req.get("method", "")
        handler = _HANDLERS.get(method)
        if handler:
            _send(handler(req))
        elif req.get("id") is not None:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


if __name__ == "__main__":
    run()
