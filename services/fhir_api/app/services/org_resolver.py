"""Resolve user's allowed orgs and scope from analytics org-context.

Atlas trace:
  DO: DO-B3397C94
  DI: DI-FC9A8824
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B3397C94")
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

ANALYTICS_BASE = os.getenv("ANALYTICS_API_BASE_URL", "http://localhost:8003")


def fetch_org_context(email: str) -> Dict[str, Any]:
    """Fetch org context from analytics API. Returns { user, organizations }."""
    url = f"{ANALYTICS_BASE.rstrip('/')}/analytics/auth/org-context"
    with httpx.Client(timeout=10) as client:
        resp = client.get(url, params={"email": email})
        resp.raise_for_status()
        return resp.json()


def get_org_by_id(email: str, org_id: str) -> Optional[Dict[str, Any]]:
    """Get org by ID if user has access. Returns org dict with scopeType, odsCode or None."""
    ctx = fetch_org_context(email)
    orgs = ctx.get("organizations") or []
    for o in orgs:
        if o.get("id") == org_id:
            return o
    return None
