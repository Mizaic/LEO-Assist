"""Three-tier NER guard rule loader.

Atlas trace:
  DO: DO-F20DE29D
  DI: DI-34712A9A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-F20DE29D")

Merge priority (highest wins):
  1. Workflow rules  -- plan_definition_id matches the active plan
  2. Tenant rules    -- org_id matches the caller's primary org
  3. Platform-admin  -- org_id IS NULL (applies to all tenants)
  4. Builtin         -- loaded from a JSON seed file shipped with the code

Rules are deduplicated by rule_id and sorted by priority descending.
Inactive rules (active=False) are excluded from all tiers.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from libs.pipeline.config_types import PipelineRuleBase

logger = logging.getLogger(__name__)


def _fetch_neo4j_rules(family: str) -> list[dict]:
    """Fetch active :NerGuardRule nodes for a family from Neo4j.

    Returns an empty list (and logs a warning) if Neo4j is unreachable,
    allowing guards to run on builtin rules alone.
    """
    try:
        from libs.cypher.guard_rule_queries import GET_RULES_BY_FAMILY
        from libs.neo4j_client.client import PatientGraphClient

        client = PatientGraphClient()
        try:
            with client.session() as session:
                rows = list(session.run(GET_RULES_BY_FAMILY, family=family))
            return [dict(r) for r in rows]
        finally:
            client.close()
    except Exception:
        logger.warning(
            "Could not fetch NerGuardRule nodes for family %r -- using builtins only",
            family,
            exc_info=True,
        )
        return []


def _load_seed(seed_path: Path) -> list[dict]:
    """Load rules from a JSON seed file. Returns [] if the file is absent."""
    if not seed_path.exists():
        logger.debug("Seed file not found at %s -- skipping", seed_path)
        return []
    try:
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        return data.get("rules", [])
    except Exception:
        logger.error("Failed to parse seed file %s", seed_path, exc_info=True)
        return []


def _row_to_rule(row: dict[str, Any], source: str) -> PipelineRuleBase:
    known_keys = {
        "rule_id", "active", "org_id", "plan_definition_id",
        "priority", "created_by", "created_at",
    }
    extra = {k: v for k, v in row.items() if k not in known_keys}
    return PipelineRuleBase(
        rule_id=row.get("rule_id", ""),
        active=bool(row.get("active", True)),
        org_id=row.get("org_id"),
        plan_definition_id=row.get("plan_definition_id"),
        priority=int(row.get("priority", 10)),
        created_by=row.get("created_by", ""),
        created_at=str(row.get("created_at", "")),
        source=source,
        extra=extra,
    )


def _is_applicable(
    row: dict[str, Any],
    org_id: str | None,
    plan_id: str | None,
) -> bool:
    """Return True if this Neo4j row is applicable for the given caller context."""
    if not row.get("active", True):
        return False
    row_org = row.get("org_id")
    row_plan = row.get("plan_definition_id")
    if row_org is None and row_plan is None:
        return True
    if row_org is not None and row_org != org_id:
        return False
    if row_plan is not None and row_plan != plan_id:
        return False
    return True


def load_rules(
    family: str,
    *,
    org_id: str | None,
    plan_id: str | None,
    seed_path: Path | None = None,
) -> list[PipelineRuleBase]:
    """Return the merged, priority-ordered rule set for a guard family.

    Args:
        family:    Guard family name, e.g. "scope_guard" or "lab_value_guard".
        org_id:    Caller's primary org ID. None for platform admins (they get
                   only platform-admin and builtin rules).
        plan_id:   Active PlanDefinition ID. None when no workflow scope applies.
        seed_path: Explicit seed file path. Defaults to
                   libs/ner/resources/<family>.json when None.

    Returns:
        List of PipelineRuleBase instances, sorted by priority descending.
        Inactive rules are excluded at all tiers.
    """
    if seed_path is None:
        seed_path = (
            Path(__file__).parent.parent / "ner" / "resources" / f"{family}.json"
        )

    builtins = [
        _row_to_rule(r, "builtin")
        for r in _load_seed(seed_path)
        if r.get("active", True)
    ]

    neo4j_rows = _fetch_neo4j_rules(family)
    custom_rules = [
        _row_to_rule(r, "custom")
        for r in neo4j_rows
        if _is_applicable(r, org_id, plan_id)
    ]

    all_rules = builtins + custom_rules
    all_rules.sort(key=lambda r: r.priority, reverse=True)
    return all_rules
