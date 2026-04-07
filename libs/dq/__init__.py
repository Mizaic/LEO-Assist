"""Data Quality toolkit for LEO AI.

Three access paths over one shared service layer:
  - REST API  : /admin/dq/*  (FastAPI, require_admin)
  - MCP tools : dq_*         (services/dq_mcp/)
  - CLI       : scripts/dq/cli.py

All public service functions return Pydantic models.
All mutation functions default to dry_run=True.
"""
