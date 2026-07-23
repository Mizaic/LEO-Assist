"""Controlled workflow version admission for new pipeline runs (M2.7).

Atlas trace:
  DO: DO-55FE7CB1
  DI: DI-090D4939, DI-29BF950F, DI-33376FBB, DI-8788B246, DI-9EE8D65E, DI-AB1C442D, DI-CB01B8A6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-55FE7CB1")

Selects the pinned PlanDefinitionVersion for a new run using an approved org
allowlist or deterministic allocation. Rollback adjusts the default for new
runs only; in-flight runs retain their admission manifest.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from libs.workflow.plan_manifest import resolve_policy_version


@dataclass(frozen=True)
class VersionRollout:
    default_version: str = "latest"
    canary_version: str = ""
    canary_org_allowlist: tuple[str, ...] = ()
    canary_percent: int = 0
    rollback_target: str = ""


def parse_version_rollout(plan_resource: dict[str, Any]) -> VersionRollout:
    raw = plan_resource.get("_versionRollout")
    if not isinstance(raw, dict):
        return VersionRollout()
    allowlist = raw.get("canaryOrgAllowlist") or raw.get("canary_org_allowlist") or []
    if not isinstance(allowlist, list):
        allowlist = []
    default_version = str(
        raw.get("defaultVersion") or raw.get("default_version") or "latest"
    )
    rollback_target = str(raw.get("rollbackTarget") or raw.get("rollback_target") or "")
    if rollback_target:
        default_version = rollback_target
    return VersionRollout(
        default_version=default_version,
        canary_version=str(raw.get("canaryVersion") or raw.get("canary_version") or ""),
        canary_org_allowlist=tuple(str(item) for item in allowlist if item),
        canary_percent=max(0, min(100, int(raw.get("canaryPercent") or 0))),
        rollback_target=rollback_target,
    )


def _tenant_id(body: dict[str, Any]) -> str:
    ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
    for source in (body, ctx or {}):
        if not isinstance(source, dict):
            continue
        tenant = source.get("tenant_id")
        if tenant:
            return str(tenant)
    return ""


def _deterministic_bucket(*parts: str) -> int:
    payload = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def select_admission_version(
    body: dict[str, Any],
    rollout: VersionRollout,
    *,
    admission_key: str = "",
) -> tuple[str, str]:
    """Return policy_version and selection_reason for a new run."""
    explicit = resolve_policy_version(body)
    if explicit not in {"", "latest", "default"}:
        return explicit, "explicit_request"

    tenant_id = _tenant_id(body)
    canary_version = str(rollout.canary_version or "").strip()
    if canary_version and tenant_id and tenant_id in rollout.canary_org_allowlist:
        return canary_version, "org_allowlist"

    if canary_version and rollout.canary_percent > 0:
        bucket = _deterministic_bucket(
            admission_key or "",
            tenant_id,
            body.get("patient_id") or "",
            body.get("plan_definition_id") or "",
        )
        if bucket < rollout.canary_percent:
            return canary_version, "deterministic_allocation"

    if rollout.rollback_target:
        return str(rollout.rollback_target), "rollback_default"

    default_version = str(rollout.default_version or "latest").strip() or "latest"
    return default_version, "default"


_LOAD_PLAN_ROLLOUT = """
MATCH (pd:PlanDefinition {id: $plan_id})
RETURN pd.rawJson AS raw_json
LIMIT 1
"""


def load_rollout_for_plan(plan_id: str, *, client: Any | None = None) -> VersionRollout:
    """Load rollout config from the live PlanDefinition node."""
    import json

    from libs.neo4j_client.client import KnowledgeGraphClient

    owns_client = client is None
    kg = client or KnowledgeGraphClient()
    try:
        rows = kg.run(_LOAD_PLAN_ROLLOUT, plan_id=plan_id)
        if not rows or not rows[0].get("raw_json"):
            return VersionRollout()
        raw = rows[0]["raw_json"]
        resource = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(resource, dict):
            return VersionRollout()
        return parse_version_rollout(resource)
    finally:
        if owns_client:
            kg.close()
