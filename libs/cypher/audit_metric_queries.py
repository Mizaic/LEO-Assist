"""Pre-configured parameterised Cypher queries for the audit template system.

Atlas trace:
  DO: DO-3775670C
  DI: DI-64CA7740
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3775670C")

Public API
----------
  METRIC_REGISTRY  -- combined list of all 53 metrics
  get_metric(id)   -- single metric lookup (includes cypher)
  get_catalogue()  -- public catalogue (cypher excluded)

  _ORG_GUARD       -- shared tenant guard fragment (back-compat alias)
  _EPISODE_ACTIVE  -- shared episode filter fragment (back-compat alias)

Metrics are defined in two internal submodules:
  _audit_metrics_core.py     -- 14 original metrics
  _audit_metrics_extended.py -- 18 Phase-2 metrics (tiers A-E)
  _audit_metrics_referral.py -- 21 Phase-3 metrics (tier F, ReferralRequest)

Adding a new metric
-------------------
Append to the appropriate sub-module. The GET /audit-metrics endpoint
returns the catalogue automatically. Never expose the cypher field to
the client.

Security contract
-----------------
All queries receive $scope_org_ids injected server-side from the
authenticated CallerScope. The ORG_GUARD EXISTS sub-query is embedded
in every query so no cross-tenant data can be returned regardless of
caller-supplied params.
"""

from __future__ import annotations

from typing import Any

from libs.cypher._audit_metrics_core import CORE_METRICS, EPISODE_ACTIVE, ORG_GUARD
from libs.cypher._audit_metrics_extended import EXTENDED_METRICS
from libs.cypher._audit_metrics_referral import REFERRAL_METRICS

# ---------------------------------------------------------------------------
# Back-compat aliases used by tests and other modules
# ---------------------------------------------------------------------------

_ORG_GUARD = ORG_GUARD
_EPISODE_ACTIVE = EPISODE_ACTIVE

# ---------------------------------------------------------------------------
# Combined registry
# ---------------------------------------------------------------------------

METRIC_REGISTRY: list[dict[str, Any]] = CORE_METRICS + EXTENDED_METRICS + REFERRAL_METRICS

# ---------------------------------------------------------------------------
# Compatible tile-type mapping
# Derived from output_type -- no need to annotate each of the 32 metrics.
# "table" and "text" are universal fallbacks for every output shape.
# ---------------------------------------------------------------------------

_COMPATIBLE_TILE_TYPES: dict[str, list[str]] = {
    "kpi_strip":     ["kpi_strip", "table", "text"],
    "bar_chart":     ["bar_chart", "line_chart", "table", "text"],
    "line_chart":    ["line_chart", "bar_chart", "table", "text"],
    "interval_plot": ["interval_plot", "bar_chart", "table", "text"],
    "table":         ["table", "text"],
    "text":          ["text", "table"],
}

_ALL_TILE_TYPES = [
    "bar_chart", "line_chart", "kpi_strip", "table", "interval_plot", "text"
]

# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

_BY_ID: dict[str, dict[str, Any]] = {m["metric_id"]: m for m in METRIC_REGISTRY}


def get_metric(metric_id: str) -> dict[str, Any] | None:
    """Return the full metric record including cypher, or None if not found."""
    return _BY_ID.get(metric_id)


def get_catalogue() -> list[dict[str, Any]]:
    """Return the public catalogue (no cypher field) for the API response."""
    return [
        {
            "metric_id": m["metric_id"],
            "title": m["title"],
            "description": m["description"],
            "output_type": m["output_type"],
            "param_schema": m["param_schema"],
            "output_schema": m["output_schema"],
            "compatible_tile_types": _COMPATIBLE_TILE_TYPES.get(
                m["output_type"], _ALL_TILE_TYPES
            ),
        }
        for m in METRIC_REGISTRY
    ]
