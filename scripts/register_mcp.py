"""Register or update the leo-neo4j MCP entry in Cursor config."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _build_env() -> dict[str, str]:
    env = {
        "NEO4J_URI": os.getenv("NEO4J_URI", ""),
        "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD", ""),
        "NEO4J_USER": os.getenv("NEO4J_USER", "neo4j"),
        "KNOWLEDGE_GRAPH_NEO4J_URI": os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", ""),
        "KNOWLEDGE_GRAPH_NEO4J_PASSWORD": os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", ""),
        "KNOWLEDGE_GRAPH_NEO4J_USERNAME": os.getenv(
            "KNOWLEDGE_GRAPH_NEO4J_USERNAME",
            "neo4j",
        ),
        "CORE_API_BASE_URL": os.getenv("CORE_API_BASE_URL", "http://localhost:8000"),
        "ANALYTICS_API_BASE_URL": os.getenv(
            "ANALYTICS_API_BASE_URL",
            "http://localhost:8003",
        ),
        "LEO_MCP_COOKIE": os.getenv("LEO_MCP_COOKIE", ""),
    }
    return env


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"mcpServers": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raw = {"mcpServers": {}}
    if not isinstance(raw, dict):
        return {"mcpServers": {}}
    if not isinstance(raw.get("mcpServers"), dict):
        raw["mcpServers"] = {}
    return raw


def _register_server(config: dict[str, Any], name: str, cwd: str) -> dict[str, Any]:
    servers = config.setdefault("mcpServers", {})
    servers[name] = {
        "command": ".venv/bin/python",
        "args": ["-m", "services.neo4j_mcp.server"],
        "cwd": cwd,
        "env": _build_env(),
    }
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-json", required=True, help="Path to Cursor mcp.json")
    parser.add_argument("--name", default="leo-neo4j", help="MCP server name")
    parser.add_argument("--cwd", required=True, help="Repo root for the MCP server")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.mcp_json).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    config = _load_json(path)
    updated = _register_server(config=config, name=args.name, cwd=args.cwd)
    path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

