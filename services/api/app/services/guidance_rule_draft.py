"""Persist in-progress rule-edit wizard state as a Neo4j :RuleEditDraft.

Atlas trace:
  DI: DI-D52E923B
  DO: DO-BED08F09
  VT: VT-35051473
  Risk: R-762335B1
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-D52E923B")

Drafts are sibling nodes linked by [:DRAFT_OF] to the live
:AppropriatenessRule. Upsert never changes rule status and never
writes [:SUPERSEDES]. Compilers and pickers match AppropriatenessRule
only and therefore ignore these nodes.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MAX_LOGIC_JSON_CHARS = 2_000_000
_MAX_WIZARD_JSON_CHARS = 500_000


class RuleEditDraftPayload(BaseModel):
    """Body for PUT /guidance/rules/review/{rule_id}/draft."""

    name: str = ""
    reason: str = ""
    logic_tree: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] | None = None
    priority: str | None = None
    due_days: int | None = None
    is_default: bool | None = None
    wizard_state: dict[str, Any] = Field(default_factory=dict)


_UPSERT_DRAFT = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
WHERE rule.status IN ['pending_review', 'active']
MERGE (draft:RuleEditDraft {ruleId: $rule_id, reviewer: $reviewer})
ON CREATE SET
    draft.id = $draft_id,
    draft.createdAt = datetime()
SET draft.name = $name,
    draft.reason = $reason,
    draft.logicJson = $logic_json,
    draft.actionJson = $action_json,
    draft.priority = $priority,
    draft.dueDays = $due_days,
    draft.isDefault = $is_default,
    draft.wizardStateJson = $wizard_state_json,
    draft.updatedAt = datetime()
MERGE (draft)-[:DRAFT_OF]->(rule)
RETURN draft.id AS draft_id,
       rule.id AS rule_id,
       rule.status AS rule_status,
       draft.updatedAt AS updated_at
"""

_GET_DRAFT = """
MATCH (draft:RuleEditDraft {ruleId: $rule_id, reviewer: $reviewer})
      -[:DRAFT_OF]->(rule:AppropriatenessRule {id: $rule_id})
RETURN draft.id AS draft_id,
       draft.name AS name,
       draft.reason AS reason,
       draft.logicJson AS logic_json,
       draft.actionJson AS action_json,
       draft.priority AS priority,
       draft.dueDays AS due_days,
       draft.isDefault AS is_default,
       draft.wizardStateJson AS wizard_state_json,
       draft.updatedAt AS updated_at,
       rule.status AS rule_status
"""

_DELETE_DRAFT = """
MATCH (draft:RuleEditDraft {ruleId: $rule_id, reviewer: $reviewer})
DETACH DELETE draft
RETURN count(*) AS deleted
"""

_DELETE_DRAFTS_FOR_RULE = """
MATCH (draft:RuleEditDraft {ruleId: $rule_id})
DETACH DELETE draft
RETURN count(*) AS deleted
"""


def _parse_json_field(raw: Any, fallback: Any) -> Any:
    if raw is None or raw == "":
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _serialise_payload(payload: RuleEditDraftPayload) -> dict[str, Any]:
    logic_json = json.dumps(payload.logic_tree)
    if len(logic_json) > _MAX_LOGIC_JSON_CHARS:
        raise ValueError("Draft logic tree is too large to save.")
    wizard_json = json.dumps(payload.wizard_state or {})
    if len(wizard_json) > _MAX_WIZARD_JSON_CHARS:
        raise ValueError("Draft wizard state is too large to save.")
    action_json = None
    if payload.actions is not None:
        action_json = json.dumps(payload.actions)
    return {
        "name": (payload.name or "")[:200],
        "reason": (payload.reason or "")[:2000],
        "logic_json": logic_json,
        "action_json": action_json,
        "priority": payload.priority,
        "due_days": payload.due_days,
        "is_default": payload.is_default,
        "wizard_state_json": wizard_json,
    }


def upsert_rule_edit_draft(
    client: Any,
    *,
    rule_id: str,
    reviewer: str,
    payload: RuleEditDraftPayload,
) -> dict[str, Any]:
    """Create or update a RuleEditDraft for rule_id + reviewer."""
    fields = _serialise_payload(payload)
    rows = client.run(
        _UPSERT_DRAFT,
        rule_id=rule_id,
        reviewer=reviewer,
        draft_id=str(uuid.uuid4()),
        **fields,
    )
    if not rows:
        raise LookupError(f"Rule {rule_id} not found or not editable for draft save.")
    row = rows[0]
    return {
        "draft_id": row["draft_id"],
        "rule_id": row["rule_id"],
        "rule_status": row["rule_status"],
        "updated_at": str(row.get("updated_at") or ""),
    }


def get_rule_edit_draft(
    client: Any,
    *,
    rule_id: str,
    reviewer: str,
) -> dict[str, Any] | None:
    """Return the reviewer's draft for a rule, or None."""
    rows = client.run(_GET_DRAFT, rule_id=rule_id, reviewer=reviewer)
    if not rows:
        return None
    row = rows[0]
    return {
        "draft_id": row["draft_id"],
        "rule_id": rule_id,
        "rule_status": row.get("rule_status"),
        "name": row.get("name") or "",
        "reason": row.get("reason") or "",
        "logic_tree": _parse_json_field(row.get("logic_json"), {}),
        "actions": _parse_json_field(row.get("action_json"), None),
        "priority": row.get("priority"),
        "due_days": row.get("due_days"),
        "is_default": row.get("is_default"),
        "wizard_state": _parse_json_field(row.get("wizard_state_json"), {}),
        "updated_at": str(row.get("updated_at") or ""),
    }


def delete_rule_edit_draft(
    client: Any,
    *,
    rule_id: str,
    reviewer: str,
) -> int:
    """Delete one reviewer's draft. Returns deleted count."""
    rows = client.run(_DELETE_DRAFT, rule_id=rule_id, reviewer=reviewer)
    if not rows:
        return 0
    return int(rows[0].get("deleted") or 0)


def clear_rule_edit_drafts(client: Any, *, rule_id: str) -> int:
    """Delete all drafts for a rule (after final Save)."""
    rows = client.run(_DELETE_DRAFTS_FOR_RULE, rule_id=rule_id)
    if not rows:
        return 0
    return int(rows[0].get("deleted") or 0)
