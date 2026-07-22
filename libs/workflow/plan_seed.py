"""PlanDefinition seed immutability guards (M2.6).

Seed creates missing draft templates only. Published PlanDefinitionVersion
snapshots are immutable; force-seed must not mutate versions referenced by
a PipelineRun.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

GET_PLAN_SEED_STATE = """
MATCH (pd:PlanDefinition {id: $id})
OPTIONAL MATCH (pd)-[:HAS_VERSION]->(v:PlanDefinitionVersion)
OPTIONAL MATCH (run:PipelineRun)-[:USED_WORKFLOW]->(v)
RETURN pd.status AS status,
       count(v) AS version_count,
       count(run) AS referenced_version_count
"""

GET_VERSION_CONTENT_HASHES = """
MATCH (pd:PlanDefinition {id: $id})-[:HAS_VERSION]->(v:PlanDefinitionVersion)
RETURN v.id AS version_id,
       coalesce(v.contentHash, '') AS content_hash,
       v.versionId AS version_id_num
ORDER BY v.versionId ASC
"""

CREATE_INITIAL_VERSION = """
MATCH (pd:PlanDefinition {id: $pid})
WHERE NOT (pd)-[:HAS_VERSION]->(:PlanDefinitionVersion)
CREATE (pd)-[:HAS_VERSION]->(v:PlanDefinitionVersion {
  id: $vid,
  planId: $pid,
  versionId: 1,
  status: 'active',
  rawJson: $raw,
  contentHash: $content_hash,
  publishedAt: datetime(),
  versionNotes: 'Initial seed snapshot'
})
RETURN v.id AS version_id
"""


def plan_content_hash(resource: dict[str, Any]) -> str:
    """Stable SHA-256 over canonical plan JSON."""
    canonical = json.dumps(resource, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def seed_plan_status(_resource: dict[str, Any]) -> str:
    """New seeded templates are draft until an operator publishes."""
    return "draft"


def should_seed_plan(
    existing_count: int,
    *,
    force: bool,
    plan_status: str = "",
    referenced_version_count: int = 0,
) -> bool:
    """Return True when the seed pass may write this PlanDefinition."""
    if existing_count <= 0:
        return True
    if not force:
        return False
    if str(plan_status or "").lower() == "active":
        return False
    if referenced_version_count > 0:
        return False
    return True


def should_touch_activity(existing_count: int) -> bool:
    """ActivityDefinitions are create-only; never mutate existing rows."""
    return existing_count <= 0


def bootstrap_initial_version(
    client: Any,
    *,
    plan_id: str,
    raw_json: str,
    content_hash: str,
    version_node_id: str,
) -> str | None:
    """Create v1 snapshot when a newly seeded plan has no versions yet."""
    rows = client.run(
        CREATE_INITIAL_VERSION,
        pid=plan_id,
        vid=version_node_id,
        raw=raw_json,
        content_hash=content_hash,
    )
    if not rows:
        return None
    return str(rows[0].get("version_id") or "")
