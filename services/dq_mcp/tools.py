"""MCP tool definitions for the LEO DQ server.

Atlas trace:
  DO: DO-0998FAF5
  Also implements: DO-86800C9B
  DI: DI-FC80B65A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")

All tools are READ-ONLY. Mutation tools are intentionally excluded from MCP
to prevent AI agents from triggering graph writes (R-LEO-AI-063).

Each tool calls the core API at DQ_API_BASE_URL/admin/dq/* with an admin
session cookie or bearer token supplied via DQ_API_COOKIE env var.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_BASE = os.environ.get("DQ_API_BASE_URL", "http://localhost:8000")
_COOKIE = os.environ.get("DQ_API_COOKIE", "")
_TIMEOUT = 30.0


def _get(path: str, params: dict | None = None) -> dict:
    """Execute a GET request to the core API."""
    headers: dict[str, str] = {}
    cookies: dict[str, str] = {}
    if _COOKIE:
        for part in _COOKIE.split(";"):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                cookies[k.strip()] = v.strip()
    resp = httpx.get(
        f"{_API_BASE}/api{path}",
        params=params or {},
        headers=headers,
        cookies=cookies,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def dq_patient_inspect(patient_id: str, with_text: bool = False) -> dict:
    """Inspect a patient: encounters, episodes, coded concepts."""
    return _get(f"/admin/dq/patient/{patient_id}", {"with_text": with_text})


def dq_patient_encounters(
    patient_id: str,
    since: str | None = None,
    until: str | None = None,
    with_text: bool = False,
) -> dict:
    """List encounters for a patient with optional date filters."""
    params = {"with_text": with_text}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    return _get(f"/admin/dq/patient/{patient_id}/encounters", params)


def dq_episodes_health() -> dict:
    """Return episode status distribution and summary counts."""
    return _get("/admin/dq/episodes/health")


def dq_episodes_stale(site: str | None = None, threshold_days: int = 90) -> dict:
    """Return stale and long-running episodes."""
    params: dict = {"threshold_days": threshold_days}
    if site:
        params["site"] = site
    return _get("/admin/dq/episodes/stale", params)


def dq_episodes_completeness(site: str | None = None) -> dict:
    """Return per-episode milestone presence matrix."""
    params = {}
    if site:
        params["site"] = site
    return _get("/admin/dq/episodes/completeness", params)


def dq_episodes_audit(patient_id: str) -> dict:
    """Return deep single-patient episode and encounter audit."""
    return _get(f"/admin/dq/episodes/{patient_id}/audit")


def dq_episodes_infer_outcome(
    patient_id: str | None = None,
    site: str | None = None,
    threshold_days: int = 180,
) -> dict:
    """Run outcome inference on stale episodes; returns per-episode verdicts."""
    params: dict = {"threshold_days": threshold_days}
    if patient_id:
        params["patient_id"] = patient_id
    if site:
        params["site"] = site
    return _get("/admin/dq/episodes/infer-outcome", params)


def dq_sf_inspect(term: str) -> dict:
    """Inspect a surface form by normalized text."""
    return _get(f"/admin/dq/terminology/sf/{term}")


def dq_sf_audit() -> dict:
    """Return surface form health report: orphans, duplicates, inactive targets."""
    return _get("/admin/dq/terminology/sf/audit")


def dq_concept_check(concept_ids: list[str]) -> dict:
    """Check status (active/inactive) of one or more concept IDs."""
    return _get(
        f"/admin/dq/terminology/concept/{concept_ids[0]}"
        if len(concept_ids) == 1
        else "/admin/dq/terminology/sf/audit"
    )


def dq_domain_coverage(domain_id: str = "ncda-cancer-types") -> dict:
    """Return domain coverage: concepts not in ValueSets."""
    return _get("/admin/dq/domain/coverage", {"domain_id": domain_id})


def dq_domain_orphans() -> dict:
    """Return inactive/retired concept IDs appearing on patient data."""
    return _get("/admin/dq/domain/orphans")


def dq_domain_gaps(site: str | None = None) -> dict:
    """Return pathway gap analysis per site."""
    params = {}
    if site:
        params["site"] = site
    return _get("/admin/dq/domain/gaps", params)


def dq_sitrep() -> dict:
    """Return unified operational situation report."""
    return _get("/admin/dq/sitrep")


def dq_rules_run() -> dict:
    """Run all configured DQ rules and return a traffic-light scorecard."""
    return _get("/admin/dq/rules/run")


def dq_cohort(
    status: str | None = None,
    site: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """Return patient IDs matching episode filters."""
    params: dict = {}
    if status:
        params["status"] = status
    if site:
        params["site"] = site
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    return _get("/admin/dq/cohort", params)


# ---------------------------------------------------------------------------
# Tool registry -- maps name -> (fn, description, param schema)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "dq_patient_inspect",
        "description": "Inspect a patient in the graph: encounters, episodes, coded concepts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient node ID"},
                "with_text": {"type": "boolean", "default": False},
            },
            "required": ["patient_id"],
        },
        "fn": dq_patient_inspect,
    },
    {
        "name": "dq_patient_encounters",
        "description": "List a patient's encounters with optional date filtering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "since": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "until": {"type": "string"},
                "with_text": {"type": "boolean", "default": False},
            },
            "required": ["patient_id"],
        },
        "fn": dq_patient_encounters,
    },
    {
        "name": "dq_episodes_health",
        "description": "Episode status distribution, stale count, HITL count.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": dq_episodes_health,
    },
    {
        "name": "dq_episodes_stale",
        "description": "List stale and long-running in-progress episodes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "site": {"type": "string"},
                "threshold_days": {"type": "integer", "default": 90},
            },
        },
        "fn": dq_episodes_stale,
    },
    {
        "name": "dq_episodes_infer_outcome",
        "description": (
            "Run outcome inference on stale episodes. Returns per-episode verdict: "
            "INFERRED_CANCER, INFERRED_BENIGN, AMBIGUOUS, or UNRESOLVABLE."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "site": {"type": "string"},
                "threshold_days": {"type": "integer", "default": 180},
            },
        },
        "fn": dq_episodes_infer_outcome,
    },
    {
        "name": "dq_episodes_audit",
        "description": "Deep single-patient episode and encounter audit.",
        "inputSchema": {
            "type": "object",
            "properties": {"patient_id": {"type": "string"}},
            "required": ["patient_id"],
        },
        "fn": dq_episodes_audit,
    },
    {
        "name": "dq_sf_inspect",
        "description": "Inspect a surface form: MAPS_TO edges, scores, active status.",
        "inputSchema": {
            "type": "object",
            "properties": {"term": {"type": "string"}},
            "required": ["term"],
        },
        "fn": dq_sf_inspect,
    },
    {
        "name": "dq_sf_audit",
        "description": "Surface form health report: orphans, duplicates, inactive targets.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": dq_sf_audit,
    },
    {
        "name": "dq_domain_coverage",
        "description": "Concepts in patient encounters that are not in any domain ValueSet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain_id": {"type": "string", "default": "ncda-cancer-types"}
            },
        },
        "fn": dq_domain_coverage,
    },
    {
        "name": "dq_domain_orphans",
        "description": "Inactive or retired SNOMED codes appearing on patient data.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": dq_domain_orphans,
    },
    {
        "name": "dq_domain_gaps",
        "description": "Pathway gap analysis: referral-no-specialist, no-referral, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {"site": {"type": "string"}},
        },
        "fn": dq_domain_gaps,
    },
    {
        "name": "dq_sitrep",
        "description": "Unified operational situation report: episodes, HITL queue, SF backlog.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": dq_sitrep,
    },
    {
        "name": "dq_rules_run",
        "description": "Run all ISO-25012-aligned DQ rules. Returns traffic-light scorecard.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": dq_rules_run,
    },
    {
        "name": "dq_cohort",
        "description": "Return patient IDs matching episode filters (status, site, date range).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "site": {"type": "string"},
                "since": {"type": "string"},
                "until": {"type": "string"},
            },
        },
        "fn": dq_cohort,
    },
]

TOOL_MAP: dict[str, Any] = {t["name"]: t for t in TOOLS}
