"""LEO Neo4j MCP Server - stdio JSON-RPC transport.

Atlas trace:
  DO: DO-5F438C17
  DI: DI-5700882E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F438C17")
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_keyvault_secrets()

from services.neo4j_mcp.tools.coded_links import TOOLS as CODED_LINK_TOOLS
from services.neo4j_mcp.tools.cypher import TOOLS as CYPHER_TOOLS
from services.neo4j_mcp.tools.encounter_candidates import TOOLS as ENCOUNTER_CANDIDATE_TOOLS
from services.neo4j_mcp.tools.episodes import TOOLS as EPISODE_TOOLS
from services.neo4j_mcp.tools.llm_usage import TOOLS as LLM_USAGE_TOOLS
from services.neo4j_mcp.tools.patients import TOOLS as PATIENT_TOOLS
from services.neo4j_mcp.tools.query_pack_escalation import TOOLS as QUERY_PACK_ESCALATION_TOOLS
from services.neo4j_mcp.tools.query_pack_pathway import TOOLS as QUERY_PACK_PATHWAY_TOOLS
from services.neo4j_mcp.tools.query_pack_safety import TOOLS as QUERY_PACK_SAFETY_TOOLS
from services.neo4j_mcp.tools.query_pack_training_quality import (
    TOOLS as QUERY_PACK_TRAINING_QUALITY_TOOLS,
)
from services.neo4j_mcp.tools.resets import TOOLS as RESET_TOOLS
from services.neo4j_mcp.tools.surface_forms import TOOLS as SURFACE_FORM_TOOLS
from services.neo4j_mcp.tools.training import TOOLS as TRAINING_TOOLS

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
logger = logging.getLogger(__name__)

TOOLS = (
    CYPHER_TOOLS
    + PATIENT_TOOLS
    + CODED_LINK_TOOLS
    + RESET_TOOLS
    + EPISODE_TOOLS
    + ENCOUNTER_CANDIDATE_TOOLS
    + TRAINING_TOOLS
    + LLM_USAGE_TOOLS
    + SURFACE_FORM_TOOLS
    + QUERY_PACK_SAFETY_TOOLS
    + QUERY_PACK_PATHWAY_TOOLS
    + QUERY_PACK_ESCALATION_TOOLS
    + QUERY_PACK_TRAINING_QUALITY_TOOLS
)
TOOL_MAP = {tool["name"]: tool for tool in TOOLS}


def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _recv() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


def _handle_initialize(req: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "leo-neo4j", "version": "1.0.0"},
            "capabilities": {"tools": {}},
        },
    }


def _handle_list_tools(req: dict) -> dict:
    tool_list = [
        {
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["inputSchema"],
        }
        for tool in TOOLS
    ]
    return {"jsonrpc": "2.0", "id": req.get("id"), "result": {"tools": tool_list}}


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
        text = json.dumps(result, default=str, ensure_ascii=True)
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


HANDLERS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_list_tools,
    "tools/call": _handle_call_tool,
}


def run() -> None:
    """Run MCP loop until stdin closes."""
    while True:
        req = _recv()
        if req is None:
            break
        method = req.get("method", "")
        handler = HANDLERS.get(method)
        if handler:
            _send(handler(req))
            continue
        if req.get("id") is not None:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


if __name__ == "__main__":
    run()

