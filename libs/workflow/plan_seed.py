"""PlanDefinition seed immutability guards (M2.6).

Atlas trace:
  DO: DO-33776AFE
  DI: DI-090D4939, DI-29BF950F, DI-33376FBB, DI-8788B246, DI-9EE8D65E, DI-AB1C442D, DI-CB01B8A6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-33776AFE")

Seed creates missing draft templates only. Published PlanDefinitionVersion
snapshots are immutable; force-seed must not mutate versions referenced by
a PipelineRun.

Bump ``PLAN_SEED_REVISION`` (or a plan's ``_seedRevision``) in
``scripts/seed_plan_definitions.py`` when built-in pathway content changes.
Startup refresh applies repo revisions newer than the stored ``seedRevision``
on seed-sourced plans and publishes a new version snapshot when content
differs from the latest pinned version.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Bump when built-in PlanDefinition seed content changes (ISO-8601 UTC).
PLAN_SEED_REVISION = "2026-08-13T16:20:00Z"

GET_PLAN_SEED_STATE = """
MATCH (pd:PlanDefinition {id: $id})
OPTIONAL MATCH (pd)-[:HAS_VERSION]->(v:PlanDefinitionVersion)
OPTIONAL MATCH (run:PipelineRun)-[:USED_WORKFLOW]->(v)
RETURN pd.status AS status,
       count(v) AS version_count,
       count(run) AS referenced_version_count
"""

GET_PLAN_REFRESH_STATE = """
MATCH (pd:PlanDefinition {id: $id})
OPTIONAL MATCH (pd)-[:HAS_VERSION]->(v:PlanDefinitionVersion)
OPTIONAL MATCH (run:PipelineRun)-[:USED_WORKFLOW]->(v)
WITH pd, v, run
ORDER BY v.versionId DESC
WITH pd,
     collect(DISTINCT v)[0] AS latest_v,
     count(DISTINCT run) AS referenced_version_count,
     count(DISTINCT v) AS version_count
RETURN pd.status AS status,
       coalesce(pd.source, 'user') AS source,
       coalesce(pd.seedRevision, '') AS seed_revision,
       version_count,
       referenced_version_count,
       coalesce(latest_v.contentHash, '') AS latest_version_hash
"""

GET_VERSION_CONTENT_HASHES = """
MATCH (pd:PlanDefinition {id: $id})-[:HAS_VERSION]->(v:PlanDefinitionVersion)
RETURN v.id AS version_id,
       coalesce(v.contentHash, '') AS content_hash,
       v.versionId AS version_id_num
ORDER BY v.versionId ASC
"""

GET_MAX_VERSION_ID = """
MATCH (pd:PlanDefinition {id: $pid})-[:HAS_VERSION]->(v:PlanDefinitionVersion)
RETURN coalesce(max(v.versionId), 0) AS max_ver
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

PUBLISH_VERSION_SNAPSHOT = """
MATCH (pd:PlanDefinition {id: $pid})
CREATE (pd)-[:HAS_VERSION]->(v:PlanDefinitionVersion {
  id: $vid,
  planId: $pid,
  versionId: $ver,
  status: 'active',
  rawJson: $raw,
  contentHash: $content_hash,
  publishedAt: $now,
  versionNotes: $notes
})
RETURN v.id AS version_id
"""

UPDATE_SEED_REVISION = """
MATCH (pd:PlanDefinition {id: $id})
SET pd.seedRevision = $seed_revision
"""


def plan_content_hash(resource: dict[str, Any]) -> str:
    """Stable SHA-256 over canonical plan JSON."""
    canonical = json.dumps(resource, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_plan_seed_revision(plan_def: dict[str, Any]) -> str:
    """Return the repo revision stamp for a built-in plan definition."""
    override = str(plan_def.get("_seedRevision") or "").strip()
    if override:
        return override
    return PLAN_SEED_REVISION


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


def should_refresh_seeded_plan_on_startup(
    *,
    existing_count: int,
    plan_source: str,
    stored_revision: str,
    repo_revision: str,
) -> bool:
    """Return True when startup should refresh a seed-sourced plan from repo."""
    if existing_count <= 0:
        return False
    if str(plan_source or "").lower() != "seed":
        return False
    if not repo_revision:
        return False
    return repo_revision > str(stored_revision or "")


def should_publish_version_snapshot(
    *,
    plan_status: str,
    version_count: int,
    repo_content_hash: str,
    latest_version_hash: str,
) -> bool:
    """Return True when a new immutable version snapshot should be created."""
    if str(plan_status or "").lower() != "active":
        return False
    if version_count <= 0:
        return True
    if not latest_version_hash:
        return True
    return repo_content_hash != latest_version_hash


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


def publish_plan_version_snapshot(
    client: Any,
    *,
    plan_id: str,
    raw_json: str,
    content_hash: str,
    version_notes: str = "Startup seed revision refresh",
    validate: bool = True,
) -> str | None:
    """Append an immutable PlanDefinitionVersion for an active seeded plan."""
    if validate:
        from libs.pipeline_graph.capability_registry import validate_plan_snapshot

        resource = json.loads(raw_json)
        errors = validate_plan_snapshot(resource)
        if errors:
            logger.warning(
                "[Seed] Skipped version publish for %s: %s",
                plan_id,
                "; ".join(errors),
            )
            return None

    ver_rows = client.run(GET_MAX_VERSION_ID, pid=plan_id)
    max_ver = int(ver_rows[0].get("max_ver") or 0) if ver_rows else 0
    next_ver = max_ver + 1
    now = datetime.now(timezone.utc).isoformat()
    rows = client.run(
        PUBLISH_VERSION_SNAPSHOT,
        pid=plan_id,
        vid=str(uuid.uuid4()),
        ver=next_ver,
        raw=raw_json,
        content_hash=content_hash,
        now=now,
        notes=version_notes,
    )
    if not rows:
        return None
    version_id = str(rows[0].get("version_id") or "")
    logger.info(
        "[Seed] Published PlanDefinitionVersion v%s for %s (id=%s)",
        next_ver,
        plan_id,
        version_id,
    )
    return version_id


def touch_seed_revision(client: Any, *, plan_id: str, seed_revision: str) -> None:
    """Record the repo revision stamp without changing plan content."""
    client.run(UPDATE_SEED_REVISION, id=plan_id, seed_revision=seed_revision)
